lexer grammar Alphabet;
WORD: LETTER+;
fragment LETTER: [a-z];
WS: [ \t\r\n]+ -> skip;
