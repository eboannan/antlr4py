grammar LeftFinally;

start @init {saved = 'wrapper'}: expr EOF;
finally {self.events.append(['finallyStart', saved])}
expr returns [value: int]
@init {seen = 0}
@after {self.events.append(['after', $value, seen])}
    : left=expr '+' right=expr {$value = $left.value + $right.value} {seen += 1}
    | number=INT {$value = $number.int} {seen += 1};

INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
