grammar Numbers;
start: INT (',' INT)* EOF;
INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
