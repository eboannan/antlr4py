grammar Prediction;
start: ('a' 'b' | 'a' 'c') tail EOF;
tail: 'x'* 'x';
WS: [ \t\r\n]+ -> skip;
