
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

'''
Stream support for lexers.
'''


from lepl.stream.iter import base_iterable_factory
from lepl.stream.core import OFFSET, s_delta, s_line, HashKey, s_key, s_next
from lepl.stream.facade import HelperFacade
from lepl.support.lib import fmt, LogMixin


class TokenHelper(base_iterable_factory(lambda cons: cons.head[1], '<token>')):
    '''
    This wraps a sequence of values generated by the lexer.  The sequence
    is a source of (tokens, stream) instances, where the stream was generated
    from the source.
    
    It follows that the `value` returned by s_next is also (tokens, stream).
    This is interpreted by `Token` which forwards `stream` to sub-matchers.
    
    Implementation is vaguely similar to `IterableHelper`, in that we use
    a `Cons` based linked list to allow memory handling.  However, instead
    of a "line" of data, each node contains, again, (tokens, stream) and
    there is no need to store the line_stream explicitly in the state.
    '''
    
    def __init__(self, id=None, factory=None, max=None, global_kargs=None, 
                 delta=None, len=None):
        super(TokenHelper, self).__init__(id=id, factory=factory, 
                                          max=max, global_kargs=global_kargs, 
                                          delta=delta)
        self._len = len

    def key(self, cons, other):
        try:
            (tokens, line_stream) = cons.head
            key = s_key(line_stream, other)
        except StopIteration:
            self._warn('Default hash')
            tokens = '<EOS>'
            key = HashKey(-1, other)
        self._debug(fmt('Hash at {0!r} {1}', tokens, hash(key)))
        return key

    def next(self, cons, count=1):
        assert count == 1
        s_next(cons.head[1], count=0) # ping max
        return (cons.head, (cons.tail, self))
    
    def line(self, cons, empty_ok):
        '''
        This doesn't have much meaning in terms of tokens, but might be
        used for some debug output, so return something vaguely useful.
        '''
        try:
            # implement in terms of next so that filtering works as expected
            ((_, line_stream), _) = self.next(cons)
            return s_line(line_stream, empty_ok)
        except StopIteration:
            if empty_ok:
                raise TypeError('Token stream cannot return an empty line')
            else:
                raise
    
    def len(self, cons):
        if self._len is None:
            raise TypeError
        else:
            try:
                (_, line_stream) = cons.head
                return self._len - s_delta(line_stream)[OFFSET]
            except StopIteration:
                return 0
    
    def stream(self, state, value, id_=None):
        raise TypeError
    


class FilteredTokenHelper(LogMixin, HelperFacade):
    '''
    Used by `RestrictTokensBy` to filter tokens from the delegate.
    
    This filters a list of token IDs in order.  If the entire list does
    not match then then next token is returned (even if it appears in the
    list).
    '''
    
    def __init__(self, delegate, *ids):
        super(FilteredTokenHelper, self).__init__(delegate)
        self._ids = ids
        self._debug(fmt('Filtering tokens {0}', ids))
        
    def next(self, state, count=1):
        
        def add_self(response):
            '''
            Replace the previous helper with this one, which will then 
            delegate to the previous when needed.
            '''
            ((tokens, token), (state, _)) = response
            self._debug(fmt('Return {0}', tokens))
            return ((tokens, token), (state, self))
        
        self._debug('Filtering')
        if count != 1:
            raise TypeError('Filtered tokens must be read singly')
        discard = list(reversed(self._ids))
        start = state
        while discard:
            ((tokens, _), (state, _)) = \
                        super(FilteredTokenHelper, self).next(state)
            if discard[-1] in tokens:
                self._debug(fmt('Discarding token {0}', discard[-1]))
                discard.pop()
            else:
                self._debug(fmt('Failed to discard token {0}: {1}', 
                                   discard[-1], tokens))
                return add_self(super(FilteredTokenHelper, self).next(start))
        return add_self(super(FilteredTokenHelper, self).next(state))
            
