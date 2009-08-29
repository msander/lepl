# Copyright 2009 Andrew Cooke

# This file is part of LEPL.
# 
#     LEPL is free software: you can redistribute it and/or modify
#     it under the terms of the GNU Lesser General Public License as published 
#     by the Free Software Foundation, either version 3 of the License, or
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
Stream interfaces for the input, with an implementation using singly linked
lists.

This package defines both interfaces (via ABCs) and implementations.


Interfaces
----------

The simplest interface is `SimpleStream` .  This requires only a subset of 
the standard Python collection interface, and so is compatible with str, 
list, etc.  A `SimpleStream` implementation is all that is expected by the 
basic `parse` and `match` methods (and `null_parser` and `null_matcher`).

`LocationStream` then extends `SimpleStream` to add extra methods
that provide useful information for debugging and error messages (location 
in file etc).  Implementations of `LocationStream` are created by the
type-specific parse/match methods (`string_parser` etc).

Further interfaces exist (`StreamFactory` and `Source`), but they are of less
interest to end-users.

`StreamFactory` is the interface used to generate a stream during matching
(using the methods in `OperatorMatcher` like `parse_string`).  It is taken
from the `Configuration` object, so alternative configurations can supply
different streams.

`Source` is the interface used to wrap input in a standard way so that the
`Line` class (generated by `DefaultStreamFactory`) is as lightweight as 
possible.  See discussion below.


Implementations
---------------

Sometimes LEPL processes data from a single block of memory (a string, for
example).  Other times it may process a stream of data - eg characters
or tokens or lines from a file.

To minimise development and maintenance work it would be preferable to 
unify all these via a single source.  For example, we could always construct
an in-memory array of data and then use that.  This has the advantage of
being simple and using a minimal total amount of resources; the disadvantages
are that all input must be available immediately and that the instantaneous
amount of resources consumed is high.

An alternative approach would be to treat everything as a stream of values
and then add a linked list interface to give the minimal persistence
required for backtracking (see details below).  This is also conceptually
fairly simple, and the instantaneous resource use at any one time is
small; the disadvantages are that the total resource use over time is 
high and some operations - like calculating the total length, needed for
left recursive grammars, are very expensive.

To try get the best of both solutions described above I am going with an
intermediate approach which holds "lines" of data in memory in an array.
In most cases these will be natural text lines (eg terminated by a newline), 
but they could also be of arbitrary length.

The fundamental class is then Line, which holds a line of data in a 
linked list with other Line instances.  The client code interacts with this
via `StreamView`, which implements the `LocationStream` interface and stores 
state for a particular character location.  Because there are many `StreamView` 
instances (potentially one per character), and also, possibly, many Lines, 
we take care to make them compact.

One result of keeping things compact is that there's no inheritance tree for
those classes; instead different sources are wrapped in `Source` instances 
which provide a general iterator over "lines".
'''

from abc import ABCMeta, abstractmethod, abstractproperty
from io import StringIO

from lepl.support import open_stop


class StreamException(Exception):
    '''
    Error raised by classes in this module.
    '''

#class _SimpleStream(metaclass=ABCMeta):
# Python 2.6
# pylint: disable-msg=W0105, C0103
_SimpleStream = ABCMeta('_SimpleStream', (object, ), {})
'''ABC used to identify streams.'''


# pylint: disable-msg=E1002,E1001
# (pylint bug?  this chains back to a new style abc)
# pylint: disable-msg=W0232
# defines only an interface
# pylint: disable-msg=R0903
# using __ methods
class SimpleStream(_SimpleStream):
    '''
    The minimal interface that matchers expect to be implemented.
    '''
    
    __slots__ = []

    @abstractmethod
    def __getitem__(self, spec):
        '''
        [n] returns a character (string of length 1)
        [n:] returns a new SimpleStream instance that starts at the offset n
        [n:m] returns a sequence (ie string, list, etc)
        '''
        pass
    
    @abstractmethod
    def __bool__(self):
        '''
        Non-empty?
        '''
        pass
    
    def __nonzero__(self):
        '''
        Called only by 2.6 (when __bool__ not called).
        '''
        return self.__bool__() 
    
    @abstractmethod
    def __len__(self):
        '''
        Amount of remaining data.
        
        This may be expensive if the data are in a file, but is needed for
        left recursion handling.
        '''
        pass
    
    @abstractmethod
    def __repr__(self):
        pass
    
    @abstractmethod
    def __str__(self):
        pass
    
    @abstractmethod
    def __hash__(self):
        pass
    
    @abstractmethod
    def __eq__(self, other):
        pass
    

# pylint: disable-msg=E1101
# pylint unaware of ABCs
SimpleStream.register(str)
SimpleStream.register(list)


class LocationStream(SimpleStream):
    '''
    Additional methods available on "real" streams.
    '''
    
    __slots__ = []
    
    @abstractproperty
    def location(self):
        '''
        A tuple containing line number, line offset, character offset,
        the line currently being processed, and a description of the source.
        
        The line number and offsets are -1 if this is past the end of the file.
        '''

    @abstractproperty
    def line_number(self):
        '''
        The line number (one indexed) from the source.
        '''
        return self.location()[0]
        
    @abstractproperty
    def line_offset(self):
        '''
        The position within the current line (zero indexed).
        '''
        return self.location()[1]
        
    @abstractproperty
    def character_offset(self):
        '''
        The character offset (zero indexed) for the entire data.
        '''
        return self.location()[2]
   
    @abstractproperty
    def text(self):
        '''
        The line of text in the underlying line indexed by this stream,
        starting at the offset.  Needed by ``Regexp`` for strings.
        '''
    
    @abstractproperty
    def source(self):
        '''
        This exposes the join and description attributes from the source,
        which are necessary to calculate derived sources (eg tokens).
        '''
    

def sample(prefix, rest, size=40):
    '''
    Provide a small sample of a string.
    '''
    text = prefix + rest
    if len(text) > size:
        text = prefix + rest[0:size-len(prefix)-3] + '...'
    return text


# this doesn't extend LocationStream, instead we register with it
# (i believe this saves memory space)
class StreamView(object):
    '''
    A view into a Line that implements LocationStream.
    
    This is intended to be as compact as possible.  Methods don't "count"
    because they are not per-instance, and putting the logic here, rather
    than in Line, makes it easy to iterate (rather than recurse) to the
    end of the data when necessary (for length). 
    '''
    
    __slots__ = ('_StreamView__line', '_StreamView__offset')

    def __init__(self, line, offset=0):
        self.__line = line
        self.__offset = offset
        
    # pylint: disable-msg=E1103
    # slice not inferred
    def __getitem__(self, index):
        '''
        [n] returns a character (string of length 1)
        [n:] returns a new StreamView instance that starts at the offset n
        [n:m] returns a sequence (ie string, list, etc)
        '''
        
        # [n]
        if isinstance(index, int):
            (line, index) = self.__at(index, True)
            return line.line[index]
        
        if index.step is not None:
            raise IndexError('Slice step not supported')
        
        if index.start is None:
            raise IndexError('Slice start must be specified')
        
        # [n:]
        if open_stop(index):
            if index.start == 0 and self.__offset == 0:
                return self
            return StreamView(*self.__at(index.start))
        
        # [n:m]
        length = index.stop - index.start
        if not length:
            return self.__line.source.join([])
        (line, start) = self.__at(index.start, True)
        line_length = len(line.line)
        remainder = length - (line_length - start)
        lines = [line.line[start:min(start+length, line_length)]]
        while line.line and remainder > 0:
            line = line.next
            if line.line:
                line_length = len(line.line)
                lines.append(line.line[0:min(remainder, line_length)])
                remainder -= line_length
        if remainder > 0:
            raise IndexError('Missing {0:d} items'.format(remainder))
        else:
            # in the code above we are careful to accumulate exactly what
            # we need; you might think it simpler to accumulate whole lines
            # and then take a slice below, but not all joins preserve length
            # (consider SOL/EOL).
            return line.source.join(lines)
            
    def __at(self, index, strict=False):
        '''
        Return a (line, index) pair, for which the index lies within the
        line.  Otherwise, raise an error.  
        
        If strict is False, (None, 0) is a possible return value.
        '''
        line = self.__line
        index += self.__offset
        while line.line and index >= len(line.line):
            index -= len(line.line)
            line = line.next
        # it's possible for index to be zero and line to be empty!
        if (not line.line) and (strict or index):
            raise IndexError()
        return (line, index)
    
    def __bool__(self):
        return bool(self.__line.line)
    
    def __nonzero__(self):
        return self.__bool__()
    
    def __len__(self):
        '''
        Calculate the total length (ie "from here on"), if necessary, and 
        store on the class.
        '''
        line = self.__line
        while line.source.total_length is None:
            line = line.next
        return line.source.total_length - (self.__line.previous_length + 
                                           self.__offset)
    
    def __repr__(self):
        return '{0!r}[{1:d}:]'.format(self.__line, self.__offset)
        
    def __str__(self):
        # pylint: disable-msg=W0702
        # we want this to be robust
        try:
            return str(self.text)
        except:
            return repr(self)
    
    def __hash__(self):
        return hash(type(self.__line)) ^ self.__offset
    
    def __eq__(self, other):
        # pylint: disable-msg=W0212
        # type is checked manually
        return type(self) is type(other) and \
            self.__line == other.__line and \
            self.__offset == other.__offset
    
    @property
    def location(self):
        '''
        A tuple containing line number, line offset, character offset,
        the line currently being processed, and a description of the source.
        
        The line number and offsets are -1 if this is past the end of the file.
        '''
        return self.__line.location(self.__offset)
    
    @property
    def line_number(self):
        '''
        The line number (one indexed) from the source.
        '''
        return self.location[0]
        
    @property
    def line_offset(self):
        '''
        The position within the current line (zero indexed).
        '''
        return self.location[1]
        
    @property
    def character_offset(self):
        '''
        The character offset (zero indexed) for the entire data.
        '''
        return self.location[2]
   
    @property
    def text(self):
        '''
        Provide the current line.
        '''
        return self.__line.text(self.__offset)
    
    @property
    def source(self):
        '''
        Expose the underlying source.
        '''
        return self.__line.source


LocationStream.register(StreamView)


#class StreamFactory(metaclass=ABCMeta):
# Python 2.6
# pylint: disable-msg=W0105, C0103
_StreamFactory = ABCMeta('_StreamFactory', (object, ), {})
'''ABC used to identify stream factories.'''


class StreamFactory(_StreamFactory):
    '''
    Support for Stream Factories.
    '''

    @abstractmethod
    def from_file(self, file_):
        '''
        Provide a stream for the contents of the file.
        '''
        
    @abstractmethod
    def from_path(self, path):
        '''
        Provide a stream for the contents of the file at the given path.
        '''
    
    @abstractmethod
    def from_string(self, text):
        '''
        Provide a stream for the contents of the string.
        '''

    @abstractmethod
    def from_lines(self, lines, source=None, join=''.join):
        '''
        Provide a stream for the contents of an iterator over lines.
        '''
    
    @abstractmethod
    def from_items(self, items, source=None, line_length=80):
        '''
        Provide a stream for the contents of an iterator over items
        (ie characters).
        '''
    
    @staticmethod
    def null(stream):
        '''
        Return the underlying data with no modification.
        '''
        assert isinstance(stream, SimpleStream), type(stream)
        return stream


class DefaultStreamFactory(StreamFactory):
    '''
    A source of Line instances, parameterised by the source.
    '''
    
    def __call__(self, source_):
        
        class Line(object):
            '''
            This class is specific to a single dataset.
            '''
            
            source = source_
            __slots__ = ['line', 'previous_length', '_Line__location_state', 
                         '_Line__next']
            
            def __init__(self, line=None, previous_length=0, 
                         location_state=None):
                self.line = line
                self.previous_length = previous_length
                self.__location_state = location_state
                self.__next = None
                
            def location(self, offset):
                '''
                Provide location from the source.
                '''
                return self.source.location(offset, self.line, 
                                            self.__location_state)
                    
            @property
            def next(self):
                '''
                Iterate over lines.
                '''
                if not self.__next:
                    (line, location_state) = next(self.source)
                    try:
                        previous_length = self.previous_length + len(self.line)
                    except TypeError:
                        previous_length = self.previous_length
                    self.__next = Line(line, previous_length, location_state)
                return self.__next
            
            def text(self, offset):
                '''
                The current line.
                '''
                return self.source.text(offset, self.line)
            
            def __repr__(self):
                return 'Line({0!r})'.format(self.line)
    
        return StreamView(Line().next)
    

    def from_path(self, path):
        '''
        Open the file with line buffering.
        '''
        return self(LineSource(open(path, 'rt', buffering=1), path))
    
    def from_string(self, text):
        '''
        Wrap a string.
        '''
        return self(LineSource(StringIO(text), sample('str: ', repr(text))))
    
    def from_lines(self, lines, source=None, join=''.join):
        '''
        Wrap an iterator over lines (strings, by default, but could be a 
        list of lists for example).
        '''
        if source is None:
            source = sample('lines: ', repr(lines))
        return self(LineSource(lines, source, join))
    
    def from_items(self, items, source=None, line_length=80):
        '''
        Wrap an iterator over items (or a list).
        '''
        if source is None:
            source = sample('list: ', repr(items))
        return self(CharacterSource(items, source, list_join, line_length))
    
    def from_file(self, file_):
        '''
        Wrap a file.
        '''
        return self(LineSource(file_, getattr(file_, 'name', '<file>')) )
        

DEFAULT_STREAM_FACTORY = DefaultStreamFactory()


#class Source(metaclass=ABCMeta):
# Python 2.6
# pylint: disable-msg=W0105, C0103
_Source = ABCMeta('_Source', (object, ), {})
'''ABC used to identify sources.'''


class Source(_Source):
    '''
    Support for sources.
    '''
    
    def __init__(self, description=None, join=''.join):
        self.__description = description
        self.join = join
        self.total_length = None
    
    def __iter__(self):
        return self
    
    @abstractmethod
    def __next__(self):
        '''
        Subclasses should return (line, location_state) where line is None
        when the nuderlying stream has expired.  This should NOT raise
        StopIteration - that is handled by StreamView.
        '''
    
    def next(self):
        '''
        Python 2.6
        '''
        return self.__next__()
    
    @abstractmethod
    def location(self, offset, line, location_state):
        '''
        A tuple containing line number, line offset, character offset,
        the line currently being processed, and a description of the source.
        '''
    
    # pylint: disable-msg=R0201
    # optional interface
    def text(self, _offset, _line):
        '''
        Subclasses should override this to return the current line, 
        if supported.
        '''
        raise StreamException('This source does not support lines.')
    
    def __str__(self):
        '''
        A description of the source.
        '''
        return self.__description
 
 
class LineSource(Source):
    '''
    Wrap a source of lines (like a file iterator), so that it provides
    both the line and associated state that can be used later, with an
    offset, to calculate location.
    '''
    
    def __init__(self, lines, description=None, join=''.join):
        '''
        lines is an iterator over the lines, description will be provided
        as part of location, and joinis used to combine lines together.
        '''
        super(LineSource, self).__init__(
                        repr(lines) if description is None else description,
                        join)
        self.__lines = iter(lines)
        self.__line_count = 1 # one-based indexing
        self.__character_count = 0
    
    def __next__(self):
        '''
        Note that this is infinite - it is the StreamView that detects when
        the Line is empty and terminates any processing by the user.
        '''
        try:
            line = next(self.__lines)
            character_count = self.__character_count
            self.__character_count += len(line)
            line_count = self.__line_count
            self.__line_count += 1
            return (line, (character_count, line_count))
        except StopIteration:
            self.total_length = self.__character_count
            return (None, (-1, -1))
    
    def location(self, offset, line, location_state):
        '''
        A tuple containing line number, line offset, character offset,
        the line currently being processed, and a description of the source.
        '''
        (character_count, line_count) = location_state
        return (line_count, offset, character_count + offset, 
                line, str(self))
        
    def text(self, offset, line):
        '''
        The current line.
        '''
        if line:
            return line[offset:]
        else:
            return self.join([])
        
    
class CharacterSource(Source):
    '''
    Wrap a sequence of characters (like a string or list) so that it provides
    "lines" in chunks of the given size.  Note that location has no concept
    of line number (lines are only an implementation detail).  This means,
    amongst other things, that Python regexps will not work with this source 
    (since they work on a "per line" basis).
    '''
    
    def __init__(self, characters, description=None, join=''.join, 
                 line_length=80):
        super(CharacterSource, self).__init__(
                    repr(characters) if description is None else description,
                    join)          
        self.__characters = iter(characters)
        self.__line_length = line_length
        self.__character_count = 0
    
    def __next__(self):
        line = []
        for _index in range(self.__line_length):
            try:
                line.append(next(self.__characters))
            except StopIteration:
                break
        if line:
            character_count = self.__character_count
            self.__character_count += len(line)
            return (line, character_count)
        else:
            self.total_length = self.__character_count
            return (None, -1)
    
    def location(self, offset, line, location_state):
        '''
        A tuple containing line number, line offset, character offset,
        the line currently being processed, and a description of the source.
        '''
        character_count = location_state
        return (None, offset, character_count + offset, 
                self.join(line), str(self))
        

def list_join(lists):
    '''
    Join function for lists (appends lists together).
    '''
    joined = []
    for list_ in lists:
        joined.extend(list_)
    return joined


#def single_line(line):
#    '''
#    Present a list as a single line in an iteration.
#    '''
#    yield line


class BaseDelegateSource(Source):
    '''
    Support for sources that delegate location to other sources.  The location
    state is a StreamView into the underlying source at the start of the
    current line.
    '''
    
    def location(self, offset, line, location_state):
        '''
        A tuple containing line number, line offset, character offset,
        the line currently being processed, and a description of the source.
        
        location_state is the original stream.
        '''
        if location_state:
            shifted = location_state[offset:]
            return shifted.location
        else:
            return (-1, -1, -1, None, None)
        
        
class BaseTransformedSource(BaseDelegateSource):
    '''
    Support for transformations of `LocationStream` instances.  The location is
    delegated to the underlying stream.
    
    Each item is transformed into a list of new tokens (all associated with 
    the same location).  To completely filter an item, return the empty list.
    '''

    def __init__(self, transform, stream):
        assert isinstance(stream, LocationStream)
        # join is unused(?) but passed on to ContentStream
        super(BaseTransformedSource, self).__init__(str(stream.source),
                                                    stream.source.join)
        self.__transform = transform
        self.__stream = stream
        self.__length = 0
        self.__state = (None, [])
    
    def __next__(self):
        stream_before, transformed = self.__state
        while not transformed and self.__stream:
            stream_before = self.__stream
            transformed = self.__transform(self.__stream[0])
            self.__stream = self.__stream[1:]
        if transformed:
            item = transformed[0]
            self.__state = (stream_before, transformed[1:])
            self.__length += 1
            return (item, stream_before)
        self.total_length = self.__length
        return (None, None)
        

class TransformedSource(BaseTransformedSource):
    '''
    Transform a `LocationStream`.
    '''

    @staticmethod
    def transformed_stream(transform, stream, factory=DEFAULT_STREAM_FACTORY):
        '''
        Generated a transformed stream.
        '''
        return factory(TransformedSource(transform, stream))
        

class FilteredSource(BaseTransformedSource):
    '''
    Filter a `LocationStream`.
    '''

    def __init__(self, predicate, stream):
        assert isinstance(stream, LocationStream)
        # join is unused(?) but passed on to ContentStream
        super(FilteredSource, self).__init__(
                lambda item: [item] if predicate(item) else [], stream)

    @staticmethod
    def filtered_stream(predicate, stream, factory=DEFAULT_STREAM_FACTORY):
        '''
        Generated a filtered stream.
        '''
        return factory(FilteredSource(predicate, stream))
        

class CachingTransformedSource(BaseDelegateSource):
    '''
    An alternative to `TransformedSource` that allows efficient retrieval of
    the underlying stream at a location corresponding to a position in the
    transformed stream.  Typically used via `Filter`.
    
    This is necessary to avoid O(n^2) time when parsing chunks of data
    with a transformed stream (without the cache, retrieving an offset in 
    our linked-list style streams is O(n)).  However it is expensive in
    terms of memory consumed.
    '''

    def __init__(self, transform, stream):
        assert isinstance(stream, LocationStream)
        # join is unused(?) but passed on to ContentStream
        super(CachingTransformedSource, self).__init__(str(stream.source),
                                                       stream.source.join)
        self.__transform = transform
        self.__stream = stream
        self.__length = 0
        self.__state = (None, [])
        # map from character offset to underlying stream 
        self.__lookup = {}
        self.__earliest_possible_source = None
    
    def __next__(self):
        '''
        This is the same algorithm as `BaseTranformedSource`, unrolling a
        possibly expanded list of transformed items.  However, it is 
        complicated by the need to cache the result for `locate` - this
        is conservative, in that if an item is generated from the stream
        at a certain point, but earlier parts of the stream generated no
        items, then we use the earlier part of the stream.  This approach
        makes sense with filters because typically a filter is only valid
        in the region when it is used, and we are checking the stream after
        the region has finished, so any final discarded items were likely
        discarded incorrectly.  I think.
        '''
        stream_before, transformed = self.__state
        while not transformed and self.__stream:
            stream_before = self.__stream
            if self.__earliest_possible_source is None:
                self.__earliest_possible_source = stream_before
            transformed = self.__transform(self.__stream[0])
            self.__stream = self.__stream[1:]
        if transformed:
            item = transformed[0]
            transformed = transformed[1:]
            self.__state = (stream_before, transformed)
            self.__length += 1
            index = stream_before.character_offset
            if index not in self.__lookup:
                self.__lookup[index] = self.__earliest_possible_source
            if not transformed:
                self.__earliest_possible_source = None
            return (item, stream_before)
        self.total_length = self.__length
        return (None, None)

    def locate(self, stream):
        '''
        Find the first location in the original stream which, when filtered,
        would match the given stream.
        '''
        return self.__lookup[stream.character_offset]
        

class CachingFilteredSource(CachingTransformedSource):
    '''
    An alternative to `FilteredSource` that allows efficient retrieval of
    the underlying stream at a location corresponding to a position in the
    filtered stream.  Typically used via `Filter`.
    
    This is necessary to avoid O(n^2) time when parsing chunks of data
    with a filtered stream (without the cache, retrieving an offset in 
    our linked-list style streams is O(n)).
    '''

    def __init__(self, predicate, stream):
        super(CachingFilteredSource, self).__init__(
                lambda item: [item] if predicate(item) else [], stream)
        

class Transform(object):
    '''
    Transform a `LocationStream` using a `CachingTransformedSource`.  This 
    consumes memory proportional to the amount of data read from the filtered 
    stream, but allows efficient retrieval of the underlying stream at a 
    location equivalent to the filtered stream.
    '''
    
    def __init__(self, transform, stream, factory=DEFAULT_STREAM_FACTORY):
        self.__source = CachingTransformedSource(transform, stream)
        self.stream = factory(self.__source)

    def locate(self, stream):
        '''
        Find the first location in the original stream which, when filtered,
        would match the given stream.
        '''
        return self.__source.locate(stream)
    
    
class Filter(object):
    '''
    Filter a `LocationStream` using a `CachingFilteredSource`.  This consumes
    memory proportional to the amount of data read from the filtered stream,
    but allows efficient retrieval of the underlying stream at a location
    equivalent to the filtered stream.
    '''
    
    def __init__(self, predicate, stream, factory=DEFAULT_STREAM_FACTORY):
        self.__source = CachingFilteredSource(predicate, stream)
        self.stream = factory(self.__source)

    def locate(self, stream):
        '''
        Find the first location in the original stream which, when filtered,
        would match the given stream.
        '''
        return self.__source.locate(stream)
