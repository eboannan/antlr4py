grammar Accessors;
start: pair? item* tail EOF;
pair: ID ID;
item: INT | ID;
tail: ('!' | '?')?;
ID: [a-z]+;
INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
