
# The contents of this file are subject to the Mozilla Public License
# (MPL) Version 1.1 (the "License"); you may not use this file except
# in compliance with the License. You may obtain a copy of the License
# at http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS"
# basis, WITHOUT WARRANTY OF ANY KIND, either express or implied. See
# the License for the specific language governing rights and
# limitations under the License.
#
# The Original Code is LEPL (http://www.acooke.org/lepl)
# The Initial Developer of the Original Code is Andrew Cooke.
# Portions created by the Initial Developer are Copyright (C) 2009-2010
# Andrew Cooke (andrew@acooke.org). All Rights Reserved.
#
# Alternatively, the contents of this file may be used under the terms
# of the LGPL license (the GNU Lesser General Public License,
# http://www.gnu.org/licenses/lgpl.html), in which case the provisions
# of the LGPL License are applicable instead of those above.
#
# If you wish to allow use of your version of this file only under the
# terms of the LGPL License and not to allow others to use your version
# of this file under the MPL, indicate your decision by deleting the
# provisions above and replace them with the notice and other provisions
# required by the LGPL License.  If you do not delete the provisions
# above, a recipient may use your version of this file under either the
# MPL or the LGPL License.

from lepl.matchers.core import Literal
from lepl.regexp.matchers import DfaRegexp
from lepl.matchers.support import to, trampoline_matcher_factory,\
    OperatorMatcher, trampoline_matcher
from lepl.stream.factory import DEFAULT_STREAM_FACTORY
from lepl.core.parser import tagged, tagged_no_state
from lepl.stream.core import s_line, s_stream, s_next
from lepl.support.lib import fmt
from lepl.core.manager import NS_STREAM


@trampoline_matcher_factory(matcher=to(Literal), condition=to(DfaRegexp))
def PostMatch(matcher, condition, not_=False, equals=True, stream_factory=None):
    '''
    Apply the condition to each result from the matcher.  It should return
    either an exact match (equals=True) or simply not fail (equals=False).
    If `not_` is set, the test is inverted.
    
    `matcher` is coerced to `Literal()`, condition to `DfaRegexp()`
    
    `factory` is used to generate a stream from the result.  If not set the
    default factory is used.
    '''
    def match(support, stream_in, stream_factory=stream_factory):
        '''
        Do the match and test the result.
        '''
        stream_factory = stream_factory if stream_factory else DEFAULT_STREAM_FACTORY
        generator = matcher._match(stream_in)
        while True:
            (results, stream_out) = yield generator
            success = True
            for result in results:
                if not success: break
                generator2 = condition._match(stream_factory(result))
                try:
                    (results2, _ignored) = yield generator2
                    if not_:
                        # if equals is false, we need to fail just because
                        # we matched.  otherwise, we need to fail only if
                        # we match.
                        if not equals or (len(results2) == 1 or 
                                          results2[0] == result):
                            success = False
                    else:
                        # if equals is false, not generating an error is
                        # sufficient, otherwise we must fail if the result
                        # does not match
                        if equals and (len(results2) != 1 or 
                                       results2[0] != result):
                            success = False
                except:
                    # fail unless if we were expecting any kind of match
                    if not not_:
                        success = False
            if success:
                yield (results, stream_out)
    
    return match


# pylint: disable-msg=E1101
class _Columns(OperatorMatcher):
 
    def __init__(self, indices, *matchers):
        super(_Columns, self).__init__()
        self._arg(indices=indices)
        self._args(matchers=matchers)
        
    @tagged
    def _match(self, stream_in):
        '''
        Build the generator from standard components and then evaluate it.
        '''
        matcher = self.__build_matcher(stream_in)
        generator = matcher._match(stream_in)
        yield (yield generator)
        
    def __build_matcher(self, stream_in):
        '''
        Build a matcher that, when it is evaluated, will return the 
        matcher results for the columns.  We base this on `And`, but need
        to force the correct streams.
        '''
        def clean():
            right = 0
            for (col, matcher) in zip(self.indices, self.matchers):
                try:
                    (left, right) = col
                except TypeError:
                    left = right
                    right = right + col
                yield (left, right, matcher)
        cleaned = list(clean())
        
        @trampoline_matcher
        def LineMatcher(support, stream):
            # extract a line
            (line, next_stream) = s_line(stream, False)
            line_stream = s_stream(stream, line)
            results = []
            for (left, right, matcher) in cleaned:
                # extract the location in the line
                (_, left_aligned_line_stream) = s_next(line_stream, count=left)
                (word, _) = s_next(left_aligned_line_stream, count=right-left)
                support._debug(fmt('Columns {0}-{1} {2!r}', left, right, word))
                word_stream = s_stream(left_aligned_line_stream, word)
                # do the match
                (result, _) = yield matcher._match(word_stream)
                results.extend(result)
            support._debug(repr(results))
            yield (results, next_stream)
            
        return LineMatcher()


# Python 2.6 doesn't support named arg after *args
#def Columns(*columns, stream_factory=None):
def Columns(*columns, **kargs):
    '''
    Match data in a set of columns.
    
    This is a fairly complex matcher.  It allows matchers to be associated 
    with a range of indices (measured from the current point in the stream)
    and only succeeds if all matchers succeed.  The results are returned in
    a list, in the same order as the matchers are specified.
    
    A range if indices is given as a tuple (start, stop) which works like an
    array index.  So (0, 4) selects the first four characters (like [0:4]).
    Alternatively, a number of characters can be given, in which case they
    start where the previous column finished (or at zero for the first).
    
    The matcher for each column will see the (selected) input data as a 
    separate stream.  If a matcher should consume the entire column then
    it should check for `Eos`.
    
    Finally, the skip parameter controls how data to "the right" of the
    columns is handled.  If unset, the data are discarded (this functions
    as an additional, final, column that currently drops data).  Data to
    "the left" are simply discarded.
    
    Note: This does not support backtracking over the columns.
    '''
    # Note - this is the public-facing wrapper that pre-process the arguments  
    # so that matchers are handled correctly.  The work is done by `_Columns`.
    (indices, matchers) = zip(*columns)
    return _Columns(indices, *matchers)



class NO_STATE(OperatorMatcher):
    
    def __init__(self, matcher):
        super(NO_STATE, self).__init__()
        self._karg(matcher=matcher)
    
    @tagged_no_state    
    def _match(self, stream):
        generator = self.matcher._match(stream)
        stream = None
        generator.stream = NS_STREAM
        while True:
            yield (yield generator)
            
