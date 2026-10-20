grammar Automata;
start: (pair | group)+ EOF;
pair: ID ':' (INT | ID) '!'?;
group: '(' pair* ')';
ID: [a-zA-Z]+;
INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
