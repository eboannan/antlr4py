grammar Expressions;
start: expr EOF;
expr: '-' expr
    | expr '!'
    | <assoc=right> expr '^' expr
    | expr ('*' | '/') expr
    | expr ('+' | '-') expr
    | '(' expr ')'
    | INT
    ;
INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
