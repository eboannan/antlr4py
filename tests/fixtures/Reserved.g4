grammar Reserved;
start returns [value:int]: result=class[3] EOF {$value=$result.value};
class[int: int] returns [value:int]: for=ID {$value=$int+len(localctx.for_.text)};
reset: TRUTH EOF;
TRUTH:'true';
ID:[a-z]+;
WS:' '+ -> skip;
