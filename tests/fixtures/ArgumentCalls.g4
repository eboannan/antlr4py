grammar ArgumentCalls;
@header {import math}
start returns [value: int]
@init {offset = 2}
    : token=INT child[int($token.text) + math.floor(1.8) + offset] EOF
      {$value = $child.value};
child[n: int] returns [value: int]: {$value = n * 2};
INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
