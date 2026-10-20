grammar Scopes;
start returns [value:int]: result=child EOF {$value = localctx.result};
child: INT {return int($INT.text) + 1};
closure returns [value:int]
@init {
count = 1
def read():
    return count
self.read = read
}
    : INT {count += $INT.int} {$value = read()} EOF;
captured returns [value:int]
@init {count = 2; read = lambda: count}
    : INT {count += $INT.int; raise ValueError('caught')};
catch [ValueError] {count += 10; localctx.value = read()}
finally {self.finalValue = read()}
handled: INT {raise ValueError('caught')};
catch [ValueError] {return 42}
finally {self.cleaned = True}
INT:[0-9]+;
WS:[ \t\r\n]+ -> skip;
