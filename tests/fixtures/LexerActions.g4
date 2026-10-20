lexer grammar LexerActions;

@members {
def record(self, name):
    self.events.append([name, self.text, self._input.index])
}

MARK: '#' {self.record('mark'); self.allow = True} -> skip;
PAIR: 'a' {self.record('middle')} 'b' {self.record('pair')};
WORD: {self.allow}? [a-z]+ {
self.record('word')
self.text = self.text.upper()
self.allow = False
};
FALLBACK: [a-z]+ {self.record('fallback')};
NUMBER: [0-9]+ {self.text = 'n:' + self.text};
WS: [ \t\r\n]+ -> skip;
