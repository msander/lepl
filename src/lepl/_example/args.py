
from lepl import *

comma  = Drop(',') 
none   = Literal('None')                        >> (lambda x: None)
bool   = (Literal('True') | Literal('False'))   >> (lambda x: x == 'True')
ident  = Word(Letter() | '_', 
              Letter() | '_' | Digit())
float_ = Float()                                >> float 
int_   = Integer()                              >> int
item   = int_ | float_ | none | bool | ident       
with Separator(~Regexp(r'\s*')):
    value  = Delayed()
    list_  = Drop('[') & value[:, comma] & Drop(']') > list
    tuple_ = Drop('(') & value[:, comma] & Drop(')') > tuple
    value += list_ | tuple_ | item  
    arg    = value                                   >> 'arg'
    karg   = (ident & Drop('=') & value              > tuple) >> 'karg'
    expr   = (karg | arg)[:, comma] & Drop(Eos())    > Node
    
parser = expr.string_parser()
ast = parser('True, type=rect, sizes=[3, 4], coords = ([1,2],[3,4])')[0]

print(ast)
print(ast.arg)
print(ast.karg)