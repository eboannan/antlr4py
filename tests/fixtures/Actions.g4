grammar Actions;

@parser::header {
import math
}

@parser::members {
def number(self, text):
    return math.floor(float(text))
}

start returns [value: int]
@init {self.events = []}
@after {self.events.append(['after', $text, $stop.text])}
    : result=expr EOF {
$value = $result.value
self.events.append(['result', $value])
};

expr returns [value: int]
    : left=expr '*' right=expr {$value = $left.value * $right.value} {self.events.append(['multiply', $value])} # Multiply
    | left=expr '+' right=expr {$value = $left.value + $right.value} {self.events.append(['add', $value])} # Add
    | '(' inner=expr ')' {$value = $inner.value} # Parentheses
    | numberToken=INT {$value = self.number($numberToken.text)} {self.events.append(['integer', $value])} # Integer
    ;

PLUS: '+' {self.plusCount = getattr(self, 'plusCount', 0) + 1};
INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
