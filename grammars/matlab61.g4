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

tokens { MATRIXSEP }

@lexer::members {
def reset(self):
    super().reset()
    self._previous_type = None
    self._delimiters = []
    self._command_mode = False
    self._command_candidate = False
    self._statement_start = True

def expression_ends(self):
    return getattr(self, '_previous_type', None) in (
        self.IDENTIFIER, self.CONSTANT, self.STRING_LITERAL, self.END_INDEX,
        self.RPAREN, self.RBRACK, self.RBRACE, self.TRANSPOSE, self.NCTRANSPOSE)

def literal_context(self):
    stack = getattr(self, '_delimiters', [])
    return bool(stack and stack[-1][0] in ('[', '{') and not stack[-1][1])

def index_context(self):
    return any(indexing for delimiter, indexing in getattr(self, '_delimiters', []))

def emit(self):
    token = super().emit()
    stack = getattr(self, '_delimiters', [])
    if token.type in (self.LPAREN, self.LBRACK, self.LBRACE):
        delimiter = {self.LPAREN: '(', self.LBRACK: '[', self.LBRACE: '{'}[token.type]
        stack.append((delimiter, delimiter != '[' and self.expression_ends()))
    elif token.type in (self.RPAREN, self.RBRACK, self.RBRACE) and stack:
        expected = {self.RPAREN: '(', self.RBRACK: '[', self.RBRACE: '{'}[token.type]
        if stack[-1][0] == expected:
            stack.pop()
    self._delimiters = stack
    start = getattr(self, '_statement_start', True)
    self._command_candidate = start and token.type == self.IDENTIFIER
    if token.type in (self.CR, self.SEMI, self.COMMA) and not stack:
        self._statement_start = True
        self._command_mode = False
    else:
        self._statement_start = False
    self._previous_type = token.type
    return token

def string_can_start(self):
    return (not self.expression_ends()
            or self.literal_context() and self._input.LA(-1) in (32, 9))

def matrix_space(self):
    if not self.literal_context() or not self.expression_ends():
        return False
    offset = 1
    while self._input.LA(offset) in (32, 9):
        offset += 1
    char = self._input.LA(offset)
    if char in (43, 45):
        # [1 -2] has two columns; [1 - 2] is subtraction.
        return self._input.LA(offset + 1) not in (32, 9, 10, 13, -1)
    return char in (39, 40, 91, 123, 64, 126) or (
        char >= 0 and (chr(char).isalnum() or char == 46
                       and self._input.LA(offset + 1) in range(48, 58)))

def handle_continuation(self):
    if self.matrix_space():
        self.type = self.MATRIXSEP
    else:
        self.skip()

def handle_space(self):
    if getattr(self, '_command_candidate', False):
        char = self._input.LA(1)
        following = self._input.LA(2)
        # Parentheses and spaced operators retain expression syntax.
        bare = char >= 0 and (chr(char).isalnum() or char in (33, 34, 35, 39, 63, 64, 91, 95, 126))
        option = char in (43, 45, 47, 92) and following not in (32, 9, 10, 13, -1)
        path = char == 46 and following not in (42, 47, 92, 94, 39)
        path = path or char == 46 and following in (46, 47, 92)
        wildcard = char == 42 and following not in (32, 9)
        self._command_mode = bare or option or path or wildcard
    self.skip()
}

@parser::members {
def inside_loop(self):
    context = self._ctx
    while context is not None:
        if context.getRuleIndex() == self.RULE_function_definition:
            return False
        if (context.getRuleIndex() == self.RULE_statement
                and context.start is not None
                and context.start.type in (self.FOR, self.WHILE)):
            return True
        context = context.parentCtx
    return False
}

file_ : separator* (function_file | script_file)? EOF ;
function_file : function_definition (separator* function_definition)* separator* ;
script_file : statement (separator | statement)* ;

function_definition
    : FUNCTION function_declare eostmt block (END eostmt)?
    ;
function_declare
    : (func_return_list ASSIGN)? IDENTIFIER (LPAREN func_ident_list? RPAREN)?
    ;
func_ident_list : IDENTIFIER (COMMA IDENTIFIER)* ;
func_return_list : IDENTIFIER | LBRACK (IDENTIFIER ((COMMA | MATRIXSEP) IDENTIFIER)*)? RBRACK ;

block : (separator | statement)* ;
statement
    : (GLOBAL | PERSISTENT) IDENTIFIER+ eostmt
    | {self.inside_loop()}? (BREAK | CONTINUE) eostmt
    | RETURN eostmt
    | IF expression eostmt block
      (ELSEIF expression eostmt block)* (ELSE eostmt block)? END eostmt
    | SWITCH expression eostmt
      (CASE expression eostmt block)* (OTHERWISE eostmt block)? END eostmt
    | TRY eostmt block (CATCH eostmt block)? END eostmt
    | WHILE expression eostmt block END eostmt
    | FOR (IDENTIFIER ASSIGN expression
          | LPAREN IDENTIFIER ASSIGN expression RPAREN) eostmt block END eostmt
    | command_statement eostmt
    | SHELL_COMMAND eostmt
    | assignment_expression eostmt
    | expression eostmt
    ;

command_statement : IDENTIFIER COMMAND_ARGUMENT+ ;

// EOF may terminate the final statement without a newline.
separator : (COMMA | SEMI | CR)+ ;
eostmt : separator | {self._input.LA(1) == -1}? ;
assignment_expression : assignment_target ASSIGN expression ;
assignment_target
    : IDENTIFIER postfix_suffix*
    | LBRACK assignment_item ((COMMA | MATRIXSEP) assignment_item)* RBRACK
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
    : IDENTIFIER | CONSTANT | STRING_LITERAL | END_INDEX
    | AT IDENTIFIER
    | LPAREN expression RPAREN
    | LBRACK array_rows? RBRACK
    | LBRACE array_rows? RBRACE
    ;
// Only an actual comma or significant literal whitespace separates columns.
array_rows : CR* array_row ((SEMI | CR)+ array_row)* (SEMI | CR)* ;
array_row : expression ((COMMA | MATRIXSEP) expression)* ;

// Command text is kept as arguments, not interpreted as MATLAB expressions.
COMMAND_ARGUMENT
    : {getattr(self, '_command_mode', False)}?
      ('\'' ('\'\'' | ~['\r\n])* '\'' | ~[ \t\r\n,;%'])+
    ;
SHELL_COMMAND : {getattr(self, '_statement_start', True)}? '!' ~[\r\n]* ;
END_INDEX : {self.index_context()}? 'end' ;
FUNCTION : 'function' ;
GLOBAL : 'global' ;
PERSISTENT : 'persistent' ;
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
AT : '@' ;
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
CONTINUATION : '...' ~[\r\n]* ('\r\n' | '\r' | '\n') {self.handle_continuation()} ;
COMMENT : '%' ~[\r\n]* -> skip ;
CR : ('\r\n' | '\r' | '\n') ;
MATRIX_SPACE : {self.matrix_space()}? [ \t]+ -> type(MATRIXSEP) ;
WS : [ \t]+ {self.handle_space()} ;
