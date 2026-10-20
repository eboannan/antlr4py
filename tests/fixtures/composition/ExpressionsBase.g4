parser grammar ExpressionsBase;
expr: expr '*' expr | expr '+' expr | atom;
atom: ID | INT | '(' expr ')';
