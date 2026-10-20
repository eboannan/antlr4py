from antlr4 import CommonTokenStream, InputStream
from generated.NumbersLexer import NumbersLexer
from generated.NumbersParser import NumbersParser

parser = NumbersParser(CommonTokenStream(NumbersLexer(InputStream("12, 34, 56"))))
print(parser.start().toStringTree(recog=parser))
