/*
BSD License
Copyright (c) 2013, Tom Everett
All rights reserved.
Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:
1. Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the distribution.
3. Neither the name of Tom Everett nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/
/*
* Grammar based on yacc-keable for matlab by Danny Luk 12/1995
*
* https://web.archive.org/web/20250822004304/http://www.angelfire.com/ar/CompiladoresUCSE/images/MATLAB.zip
*/

// Extended Python-target grammar derived from matlab.g4.
// Targets common MATLAB 6.1 syntax; not a certified complete language grammar.
grammar matlab61;

@lexer::members {
def emit(self):
    token = super().emit()
    self._previous_type = token.type
    depth = getattr(self, '_matrix_depth', 0)
    if token.type in (self.LBRACK, self.LBRACE):
        depth += 1
    elif token.type in (self.RBRACK, self.RBRACE):
        depth = max(0, depth - 1)
    self._matrix_depth = depth
    return token

def reset(self):
    super().reset()
    self._previous_type = None
    self._matrix_depth = 0

def string_can_start(self):
    previous = getattr(self, '_previous_type', None)
    endings = (self.IDENTIFIER, self.CONSTANT, self.STRING_LITERAL,
               self.RPAREN, self.RBRACK, self.RBRACE, self.END,
               self.TRANSPOSE, self.NCTRANSPOSE)
    if previous not in endings:
        return True
    # Horizontal space separates a character-array element inside a literal.
    return (getattr(self, '_matrix_depth', 0) > 0
            and self._input.LA(-1) in (32, 9))
}

file_ : (separator | function_definition | statement)* EOF ;

function_definition
    : FUNCTION function_declare eostmt block (END eostmt)?
    ;
function_declare
    : (func_return_list ASSIGN)? IDENTIFIER (LPAREN func_ident_list? RPAREN)?
    ;
func_ident_list : IDENTIFIER (COMMA IDENTIFIER)* ;
func_return_list : IDENTIFIER | LBRACK func_ident_list? RBRACK ;

block : (separator | statement)* ;
statement
    : (GLOBAL | PERSISTENT) IDENTIFIER+ eostmt
    | CLEAR IDENTIFIER* eostmt
    | (BREAK | CONTINUE | RETURN) eostmt
    | IF expression eostmt block
      (ELSEIF expression eostmt block)* (ELSE eostmt block)? END eostmt
    | SWITCH expression eostmt
      (CASE expression eostmt block)* (OTHERWISE eostmt block)? END eostmt
    | TRY eostmt block (CATCH eostmt block)? END eostmt
    | WHILE expression eostmt block END eostmt
    | FOR (IDENTIFIER ASSIGN expression
          | LPAREN IDENTIFIER ASSIGN expression RPAREN) eostmt block END eostmt
    | assignment_expression eostmt
    | expression eostmt
    ;

// EOF may terminate the final statement without a newline.
separator : (COMMA | SEMI | CR)+ ;
eostmt : separator | {self._input.LA(1) == -1}? ;
assignment_expression : assignment_target ASSIGN expression ;
assignment_target
    : IDENTIFIER postfix_suffix*
    | LBRACK assignment_item (COMMA? assignment_item)* RBRACK
    ;
assignment_item : IDENTIFIER postfix_suffix* ;

expression : or_expression ;
or_expression : and_expression (OR and_expression)* ;
and_expression : relational_expression (AND relational_expression)* ;
relational_expression
    : colon_expression ((LT | GT | LE_OP | GE_OP | EQ_OP | NE_OP) colon_expression)*
    ;
colon_expression : additive_expression (COLON additive_expression (COLON additive_expression)?)? ;
additive_expression : multiplicative_expression ((PLUS | MINUS) multiplicative_expression)* ;
multiplicative_expression
    : unary_expression ((STAR | SLASH | BACKSLASH | ARRAYMUL | ARRAYDIV | ARRAYRDIV) unary_expression)*
    ;
unary_expression : (PLUS | MINUS | NOT) unary_expression | power_expression ;
// MATLAB evaluates chained powers left-to-right; power binds above unary signs.
power_expression : postfix_expression ((POWER | ARRAYPOW) signed_postfix)* ;
signed_postfix : (PLUS | MINUS | NOT)* postfix_expression ;
postfix_expression : primary_expression (postfix_suffix | TRANSPOSE | NCTRANSPOSE)* ;
postfix_suffix
    : LPAREN index_expression_list? RPAREN
    | LBRACE index_expression_list RBRACE
    | DOT IDENTIFIER
    ;
index_expression_list : index_expression (COMMA index_expression)* ;
index_expression : COLON | expression ;
primary_expression
    : IDENTIFIER | CONSTANT | STRING_LITERAL | END
    | LPAREN expression RPAREN
    | LBRACK array_rows? RBRACK
    | LBRACE array_rows? RBRACE
    ;
// Skipped spaces permit adjacent expressions; see documented whitespace limits.
array_rows : array_row ((SEMI | CR)+ array_row)* (SEMI | CR)* ;
array_row : expression (COMMA? expression)* ;

FUNCTION : 'function' ;
GLOBAL : 'global' ;
PERSISTENT : 'persistent' ;
CLEAR : 'clear' ;
BREAK : 'break' ;
CONTINUE : 'continue' ;
RETURN : 'return' ;
IF : 'if' ;
ELSEIF : 'elseif' ;
ELSE : 'else' ;
SWITCH : 'switch' ;
CASE : 'case' ;
OTHERWISE : 'otherwise' ;
TRY : 'try' ;
CATCH : 'catch' ;
WHILE : 'while' ;
FOR : 'for' ;
END : 'end' ;
ARRAYMUL : '.*' ;
ARRAYDIV : '.\\' ;
ARRAYRDIV : './' ;
ARRAYPOW : '.^' ;
NCTRANSPOSE : '.\'' ;
LE_OP : '<=' ;
GE_OP : '>=' ;
EQ_OP : '==' ;
NE_OP : '~=' ;
LPAREN : '(' ;
RPAREN : ')' ;
LBRACK : '[' ;
RBRACK : ']' ;
LBRACE : '{' ;
RBRACE : '}' ;
COMMA : ',' ;
SEMI : ';' ;
COLON : ':' ;
ASSIGN : '=' ;
PLUS : '+' ;
MINUS : '-' ;
STAR : '*' ;
SLASH : '/' ;
BACKSLASH : '\\' ;
POWER : '^' ;
NOT : '~' ;
AND : '&' ;
OR : '|' ;
LT : '<' ;
GT : '>' ;
DOT : '.' ;
STRING_LITERAL
    : {self.string_can_start()}? '\'' ('\'\'' | ~['\r\n])* '\''
    ;
TRANSPOSE : '\'' ;
IDENTIFIER : [a-zA-Z] [a-zA-Z0-9_]* ;
CONSTANT : NUMBER ([eEdD] [+-]? [0-9]+)? [ij]? ;
fragment NUMBER
    : [0-9]+ ('.' {self._input.LA(1) not in (42, 47, 92, 94, 39, 46)}? [0-9]*)?
    | '.' [0-9]+
    ;
CONTINUATION : '...' ~[\r\n]* ('\r\n' | '\r' | '\n') -> skip ;
COMMENT : '%' ~[\r\n]* -> skip ;
CR : ('\r\n' | '\r' | '\n') ;
WS : [ \t]+ -> skip ;
