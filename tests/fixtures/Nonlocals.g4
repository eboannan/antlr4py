grammar Nonlocals;

start returns [value: int] locals [count: int = 0]
    : scope EOF {$value = $scope.value} {self.events.append(['count', $count])};
finally {self.events.append(['finallyStart', $count])}

scope returns [value: int] locals [total: int = 0]
    : '(' (child=scope {$total = $total + $child.value} | item)* ')'
      {$value = $total} {self.events.append(['scope', $value])};
finally {self.events.append(['finallyScope', $total])}

item: {$scope::total < self.limit}? INT
      {$scope::total = $scope::total + $INT.int}
      {$start::count = $start::count + 1}
      {self.events.append(['item', $scope::total, $start::count])}
      passed[$scope::total];

passed[n: int]: {self.events.append(['argument', $n])};

INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
