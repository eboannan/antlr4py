grammar RootComposition;
import First, Second;
start: item EOF;
item: atom '!'?;
WS: [ \t\r\n]+ -> skip;
