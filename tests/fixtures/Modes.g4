lexer grammar Modes;
tokens { STRING }
channels { COMMENTS }
OPEN: '"' -> more, pushMode(QUOTED);
TAG: '<' -> pushMode(TAGMODE);
SWITCH: '@' -> mode(TAGMODE);
ID: [a-z]+;
COMMENT: '//' ~[\r\n]* -> channel(COMMENTS);
WS: [ \t\r\n]+ -> channel(HIDDEN);
mode QUOTED;
CLOSE: '"' -> type(STRING), popMode;
ESC: '\\' . -> more;
TEXT: ~["\\]+ -> more;
mode TAGMODE;
END: '>' -> popMode;
BACK: '#' -> mode(DEFAULT_MODE);
ATTR: [a-z]+;
EQUAL: '=';
SPACE: [ \t]+ -> skip;
