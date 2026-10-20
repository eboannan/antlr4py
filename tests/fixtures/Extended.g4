grammar Extended;
options {language=Python3;}
start: payload EOF;
payload: 'open' part=.*? 'close';
wild: head=. tail=.*? EOF;
negative: first=~(STOP|EOF) rest+=~STOP* STOP EOF;
optionalRule: first=ID?? ID EOF;
plusRule: value=.+? STOP EOF;
endRule: ID EOF?;
STOP: '!';
ID: [a-z]+;
NUMBER: [0-9]+;
WS: [ \t\r\n]+ -> skip;
