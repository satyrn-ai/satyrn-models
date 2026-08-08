# SP5 collection fixtures

`collection_cases.json` is the committed, source-only fixture corpus reserved
by the SP5 readiness record. Task 3 consumes it through the AST extractor; Task
7 consumes the final two policy cases through provider qualification. It is not
an executable test module and must never be imported as a source sample.

`multi_origin`, `exact_repeat`, and `same_skeleton` are record-level fixtures:
Task 2/5 creates them from two occurrences or rendered rows rather than a
single Python source string.
