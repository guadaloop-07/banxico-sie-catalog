# Contributing

## Local setup

Create a Python 3.11+ virtual environment and install the development extras:

```bash
python -m pip install -e '.[dev]'
pre-commit install
```

Before opening a pull request, run:

```bash
pre-commit run --all-files
pytest
```

## Change discipline

- Keep crawler changes narrowly scoped and add a saved HTML fixture for every
  newly supported or changed SIE markup pattern.
- Do not commit generated catalog snapshots, API tokens, or downloaded source
  pages outside `tests/fixtures/`.
- Use imperative, conventional commit subjects, for example
  `feat: parse series metadata from SIE tables`.
- Open pull requests with a concise description, test evidence, and any impact
  on the catalog schema or crawler request volume.
