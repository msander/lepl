
# Copyright 2009 Andrew Cooke

# This file is part of LEPL.
# 
#     LEPL is free software: you can redistribute it and/or modify
#     it under the terms of the GNU Lesser General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
# 
#     LEPL is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Lesser General Public License for more details.
# 
#     You should have received a copy of the GNU Lesser General Public License
#     along with LEPL.  If not, see <http://www.gnu.org/licenses/>.

'''
Create and evaluate parsers.

Once a consistent set of matchers is constructed (that describes a grammar)
they must be evaluated against some input.  The code here supports that 
evaluation (via `trampoline()`) and allows the graph of matchers to be 
rewritten beforehand.
'''


from logging import getLogger
from traceback import print_exc, format_exc
from types import MethodType, GeneratorType

from lepl.graph import order, FORWARD, preorder, clone, Clone, post_clone
from lepl.monitor import MultipleMonitors
from lepl.operators import Matcher
from lepl.stream import Stream
from lepl.support import BaseGeneratorWrapper
from lepl.trace import TraceResults, RecordDeepest
    
    
def tagged(call):
    '''
    Decorator for generators to add extra attributes.
    '''
    def tagged_call(matcher, stream):
        return GeneratorWrapper(call(matcher, stream), matcher, stream)
    return tagged_call


class GeneratorWrapper(BaseGeneratorWrapper):
    '''
    Associate basic info about call that created the generator with the 
    generator itself.  This lets us manage resources and provide logging.
    It is also used by `trampoline()` to recognise generators that must 
    be evaluated (rather than being treated as normal values).
    '''

    def __init__(self, generator, matcher, stream):
        super(GeneratorWrapper, self).__init__(generator)
        self.matcher = matcher
        self.stream = stream
        self.describe = '{0}({1})'.format(matcher.describe, stream)
        
    def __repr__(self):
        return self.describe
        

class Configuration(object):
    '''
    Encapsulate various parameters that describe how the matchers are
    rewritten and evaluated.
    '''
    
    def __init__(self, flatten=None, memoizers=None, monitors=None):
        '''
        `flatten` A map from type to attribute name.  If they type is nested 
        then the nested instance is replaced with the value(s) of the attribute 
        on the instance (see `make_flatten()`).
        
        `memoizers` A list of functions applied to cloned nodes.
        
        `monitors` Subclasses of `lepl.monitor.MonitorInterface` that will be
        invoked by `trampoline()`.
        '''
        self.flatten = [] if flatten is None else flatten 
        self.memoizers = [] if memoizers is None else memoizers
        if not monitors:
            self.monitor = None
        elif len(monitors) == 1:
            self.monitor = monitors[0]
        else:
            self.monitor = MultipleMonitors(monitors)
            
        
def make_flatten(table):
    '''
    Create a function that can be applied to a graph of matchers to implement
    flattening.
    '''
    def flatten(node, old_args, kargs):
        if type(node) in table:
            attribute_name = table[type(node)]
            new_args = []
            for arg in old_args:
                if type(arg) is type(node):
                    if attribute_name.startswith('*'):
                        new_args.extend(getattr(arg, attribute_name[1:]))
                    else:
                        new_args.append(getattr(arg, attribute_name))
                else:
                    new_args.append(arg)
        else:
            new_args = old_args
        return clone(node, new_args, kargs)
    return flatten


class CloneWithDescribe(Clone):
    '''
    Extend `lepl.graph.Clone` to copy the `describe` attribute.
    '''
    
    def constructor(self, *args, **kargs):
        node = super(CloneWithDescribe, self).constructor(*args, **kargs)
        node.describe = self._node.describe
        return node    
    

def flatten(matcher, conf):
    '''
    Flatten the matcher graph according to the configuration.
    '''
    if conf.flatten:
        matcher = matcher.postorder(CloneWithDescribe(make_flatten(conf.flatten)))
    return matcher


def memoize(matcher, conf):
    '''
    Add memoizers to the matcher graph according to the configuration.
    '''
    for memoizer in conf.memoizers:
        matcher = matcher.postorder(Clone(post_clone(memoizer)))
    return matcher


def trampoline(main, monitor=None):
    '''
    The main parser loop.  Evaluates matchers as coroutines. 
    '''
    stack = []
    value = main
    exception = False
    epoch = 0
    log = getLogger('lepl.parser.trampoline')
    last_exc = None
    while True:
        epoch += 1
        try:
            if monitor: monitor.next_iteration(epoch, value, exception, stack)
            if type(value) is GeneratorWrapper:
                if monitor: monitor.push(value)
                stack.append(value)
                if monitor: monitor.before_next(value)
                value = next(value)
                if monitor: monitor.after_next(value)
            else:
                pop = stack.pop()
                if monitor: monitor.pop(pop)
                if stack:
                    if exception:
                        exception = False
                        if monitor: monitor.before_throw(stack[-1], value)
                        value = stack[-1].throw(value)
                        if monitor: monitor.after_throw(value)
                    else:
                        if monitor: monitor.before_send(stack[-1], value)
                        value = stack[-1].send(value)
                        if monitor: monitor.after_send(value)
                else:
                    if exception:
                        if monitor: monitor.raise_(value)
                        raise value
                    else:
                        if monitor: monitor.yield_(value)
                        yield value
                    value = main
        except Exception as e:
            if exception: # raising to caller
                raise
            else:
                value = e
                exception = True
                if monitor: monitor.exception(value)
                if type(value) is not StopIteration and value != last_exc:
                    last_exc = value
                    log.warn(format_exc())
                    for generator in stack:
                        log.warn('Stack: ' + generator.matcher.describe)
                
    
def prepare(matcher, stream, conf):
    '''
    Rewrite the matcher and prepare the input for a parser.
    '''
    matcher = flatten(matcher, conf)
    matcher = memoize(matcher, conf)
    parser = lambda arg: trampoline(matcher(stream(arg, conf)), 
                                    monitor=conf.monitor)
    parser.matcher = matcher
    return parser


def make_parser(matcher, stream, conf):
    '''
    Make a parser.  This takes a matcher node, a stream constructor, and a 
    configuration, and return a function that takes an input and returns a
    *single* parse.
    '''
    matcher = prepare(matcher, stream, conf)
    def single(arg):
        try:
            return next(matcher(arg))[0]
        except StopIteration:
            return None
    single.matcher = matcher.matcher
    return single

    
def make_matcher(matcher, stream, conf):
    '''
    Similar to `make_parser`, but constructs a function that returns a 
    generator that provides a sequence of parses.
    '''
    return prepare(matcher, stream, conf)

    
def file_parser(matcher, conf):
    '''
    Construct a parser for file objects.
    '''
    return make_parser(matcher, Stream.from_file, conf)

def list_parser(matcher, conf):
    '''
    Construct a parser for lists.
    '''
    return make_parser(matcher, Stream.from_list, conf)

def path_parser(matcher, conf):
    '''
    Construct a parser for a file path.
    '''
    return make_parser(matcher, Stream.from_path, conf)

def string_parser(matcher, conf):
    '''
    Construct a parser for strings.
    '''
    return make_parser(matcher, Stream.from_string, conf)

def parser(matcher, conf):
    '''
    Construct a parser for strings and lists (this does not use streams).
    '''
    return make_parser(matcher, Stream.null, conf)


def file_matcher(matcher, conf):
    '''
    Construct a parser (that returns a sequence of parses) for file objects.
    '''
    return make_matcher(matcher, Stream.from_file, conf)

def list_matcher(matcher, conf):
    '''
    Construct a parser (that returns a sequence of parses) for lists.
    '''
    return make_matcher(matcher, Stream.from_list, conf)

def path_matcher(matcher, conf):
    '''
    Construct a parser (that returns a sequence of parses) for a file path.
    '''
    return make_matcher(matcher, Stream.from_path, conf)

def string_matcher(matcher, conf):
    '''
    Construct a parser (that returns a sequence of parses) for strings.
    '''
    return make_matcher(matcher, Stream.from_string, conf)

def matcher(matcher, conf):
    '''
    Construct a parser (that returns a sequence of parses) for strings
    and lists (this does not use streams).
    '''
    return make_matcher(matcher, Stream.null, conf)

