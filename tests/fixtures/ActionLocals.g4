grammar ActionLocals;

start returns [value: int]
@init {count = 0}
@after {
$value = count
self.summary = [$text, $stop.text]
}
    : (item {count += 1})+ EOF;

item returns [value: int]
    : INT {temporary = int($INT.text)} {
$value = temporary
self.last = temporary
};

INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
