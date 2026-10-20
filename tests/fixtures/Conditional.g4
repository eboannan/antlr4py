grammar Conditional;
start: expr EOF;
expr: <assoc=right> expr '?' expr ':' expr
    | expr '+' expr
    | '(' expr ')'
    | ID
    ;
ID: [a-z]+;
WS: [ \t\r\n]+ -> skip;
