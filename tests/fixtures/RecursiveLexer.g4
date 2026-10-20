lexer grammar RecursiveLexer;
BLOCK: '{' (BLOCK|~[{}])* '}';
WORD: [a-z]+;
WS: [ \t\r\n]+ -> skip;
