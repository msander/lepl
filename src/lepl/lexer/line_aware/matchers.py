
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

from lepl.lexer.matchers import Token, RestrictTokensBy, EmptyToken
from lepl.lexer.line_aware.lexer import START, END


class LineStart(EmptyToken):
    
    def __init__(self, regexp=None, content=None, id_=None, alphabet=None,
                  complete=True, compiled=False):
        '''
        Arguments used only to support cloning.
        '''
        super(LineStart, self).__init__(regexp=None, content=None, id_=START, 
                                        alphabet=None, complete=True, 
                                        compiled=compiled)
        
        
LineAwareSol = lambda: ~LineStart()


class LineEnd(EmptyToken):
    
    def __init__(self, regexp=None, content=None, id_=None, alphabet=None,
                  complete=True, compiled=False):
        '''
        Arguments used only to support cloning.
        '''
        super(LineEnd, self).__init__(regexp=None, content=None, id_=END, 
                                      alphabet=None, complete=True, 
                                      compiled=compiled)
        
        
LineAwareEol = lambda: ~LineEnd()


def Line(matcher):
    '''
    Match the matcher within a line.
    '''
    return LineAwareSol() & matcher & LineAwareEol()


def ContinuedLineFactory(regexp):
    start = LineStart()
    end = LineEnd()
    restricted = RestrictTokensBy(Token(regexp), end, start)
    def factory(matcher):
        line = start & matcher & end
        return restricted(line)
    return factory

        