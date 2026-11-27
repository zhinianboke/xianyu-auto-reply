# Order sync regression tests

Run from the repository root with Python 3.11 or newer:

```sh
python -m pip install ./scheduler aiosqlite
python -m unittest discover -s tests -v
```

The tests use the standard library's `unittest` runner. Unit tests cover detail
hydration decisions and Cookie propagation. Integration tests use a temporary
SQLite database and mocked HTTP responses, exercising the existing list parser,
upsert, detail API handling, SKU parser, database update and `CardMatcher` together.
SQLite schema adaptations are confined to copied test tables. All fixture IDs,
Cookie strings and API data are synthetic; no MySQL, Redis or live account is required.
