parser grammar ComposeParser;
options { tokenVocab=ComposeTokens; }
import ExpressionsBase;
start: expr EOF;
atom: INT | '(' expr ')';
