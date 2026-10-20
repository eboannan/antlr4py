grammar Exceptions;

start returns [value: int]
@init {count = 10}
@after {self.events.append(['afterStart', $value])}
    : child EOF {$value = $child.value};
catch [RuntimeError as problem] {self.events.append(['outerCatch', str(problem)])}
finally {self.events.append(['finallyStart', count, $value])}

child returns [value: int]
@init {saved = 5}
@after {self.events.append(['afterChild', $value])}
    : INT {
if self.mode == 'value':
    raise ValueError('bad value')
if self.mode == 'key':
    raise KeyError('missing key')
if self.mode == 'runtime':
    raise RuntimeError('bubble up')
$value = $INT.int
};
catch [ValueError as problem] {
self.events.append(['valueCatch', str(problem), saved])
localctx.value = saved
}
catch [(KeyError, IndexError) as problem] {
self.events.append(['keyCatch', type(problem).__name__])
localctx.value = -1
}
finally {self.events.append(['finallyChild', saved, $value])}

recognize @after {self.events.append(['afterRecognize'])}: INT ';' EOF;
catch [RecognitionException as problem] {
self.events.append(['recognitionCatch', type(problem).__name__])
self._errHandler.reportError(self, problem)
self._errHandler.recover(self, problem)
}
finally {self.events.append(['finallyRecognize'])}

reraised: child EOF;
catch [RuntimeError as problem] {self.events.append(['reraise', str(problem)]); raise}
finally {self.events.append(['finallyReraised'])}

INT: [0-9]+;
OTHER: '?';
WS: [ \t\r\n]+ -> skip;
