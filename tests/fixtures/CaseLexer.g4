lexer grammar CaseLexer;
options {caseInsensitive=true; language=Python3;}
EXACT options {caseInsensitive=false;}: 'CaSe';
KEYWORD: 'hello';
WORD: LETTER+;
fragment LETTER: [a-z\u00C0-\u00DE];
NUMBER: [0-9]+;
WS: [ \t\r\n]+ -> skip;
