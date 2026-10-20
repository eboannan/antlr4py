grammar Attributes;
start: result=child[3] EOF;
child[n: int] returns [value: int = 0] locals [seen: list = []]
    : head=INT (rest+=INT)*;
INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
