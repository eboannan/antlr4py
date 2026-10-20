grammar Predicates;

start returns [selected: str]
    : choice EOF {$selected = $choice.selected};

choice returns [selected: str]
    : {self.enabled}? INT {$selected = 'enabled'}
    | INT {$selected = 'fallback'}
    ;

guard[n: int] returns [value: int]
    : {$n > 0}? token=INT {$value = $token.int + $n};

checked returns [value: int]
    : token=INT {$token.int > 2}? {$value = $token.int};

INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
