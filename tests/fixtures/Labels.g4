grammar Labels;
start: values+=expr (',' values+=expr)* EOF;
expr: left=expr op='*' right=expr # Multiply
    | left=expr op='+' right=expr # Add
    | '(' inner=expr ')' # Parentheses
    | value=INT # Integer
    ;
INT: [0-9]+;
WS: [ \t\r\n]+ -> skip;
