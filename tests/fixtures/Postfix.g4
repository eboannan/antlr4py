grammar Postfix;
start: expr EOF;
expr: expr '!'
    | ID
    | expr '+' expr
    | '(' expr ')'
    ;
ID: [a-z]+;
WS: [ \t\r\n]+ -> skip;
