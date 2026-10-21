# Releasing antlr4py

The current release candidate is **0.11.0a1**, an experimental alpha.
Publishing is a separate maintainer action; CI only builds and tests artifacts.

## Prepare

1. Confirm that you control the `antlr4py` project name on PyPI and TestPyPI.
   Name availability and account permissions are not established by a local build.
2. Keep the version in `pyproject.toml`, `src/antlr4_generator/__init__.py`,
   README.md, and COMPATIBILITY.md consistent. Never reuse an uploaded version.
3. Run the Package checks workflow on the exact commit to release. It covers
   Windows and Linux, Python 3.10, 3.13, and 3.14, the installed wheel, and tests
   extracted from the source distribution. Review all matrix results.
4. Review licenses, compatibility limits, and project URLs. The grammars and
   examples ship in the source distribution, not as installed Python packages.

## Build and validate locally

In a fresh virtual environment, from the repository root:

```sh
python -m pip install build twine
python -m build
python -m twine check --strict dist/*
python -m pip install dist/antlr4py-0.11.0a1-py3-none-any.whl
python scripts/check_installed.py
python -m unittest discover -s tests -v
python -m pip check
```

Start with an empty `dist/` directory so old releases cannot be uploaded by
accident. The default build creates the wheel from the source distribution.
Inspect both archives for the two Unicode JSON tables and both license files.
The source distribution must also contain tests, fixtures, examples, and grammars.

## TestPyPI and PyPI

Follow the [Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/).
Use an API token for the selected index when Twine prompts for credentials.

```sh
python -m twine upload --repository testpypi dist/*
```

In another clean environment, install the runtime from PyPI first, then install
only this package from TestPyPI (which may not contain its dependencies):

```sh
python -m pip install antlr4-python3-runtime==4.13.2
python -m pip install --index-url https://test.pypi.org/simple/ --no-deps antlr4py==0.11.0a1
python /path/to/checkout/scripts/check_installed.py
python -m pip check
```

After reviewing the TestPyPI page and installation, publish the same artifacts:

```sh
python -m twine upload dist/*
```

Verify installation from PyPI in a fresh environment, then tag the released commit
as `v0.11.0a1`. Update the README installation section to advertise
`python -m pip install antlr4py==0.11.0a1` once that source is verified.
Retain the release artifacts and their SHA-256 hashes with the release record.
