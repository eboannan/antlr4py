grammar Recovery;

start: statement* EOF;
statement: name=ID '=' result=expr ';';
expr: left=expr '+' right=expr # Add
    | '(' inner=expr ')' # Parentheses
    | number=INT # Integer;

single: name=ID '=' number=INT ';' EOF;
choice: ('let' ID | 'print' INT) EOF;
shared: ('open' ID 'end' | 'open' INT 'end') EOF;
optionalRule: 'begin' ID? 'end' EOF;
listRule: '[' values+=INT (',' values+=INT)* ']' EOF;
required: INT+ EOF;
setChoice: chosen=('a'|'b') EOF;
guard @after {self.finished = True}: INT {self.allowed}? ';' EOF;

ID: [a-z]+;
INT: [0-9]+;
OTHER: '?';
WS: [ \t\r\n]+ -> skip;
