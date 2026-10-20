lexer grammar PropertiesLexer;
GREEK: [\p{Script=Greek}]+;
EMOJI: [\p{Emoji}];
BLOCK: [\p{Block=Arrows}]+;
IDENTIFIER: [\p{XID_Start}] [\p{XID_Continue}]*;
SPACE: [\p{White_Space}]+ -> skip;
OTHER: [\P{Script=Greek}];
