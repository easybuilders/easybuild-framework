# Tomllib

Vendored `tomli` from https://github.com/hukkin/tomli version 2.3.0.
PEP 680 added a version of it as `tomllib` to Python 3.11.

Patched to remove features not available in Python 3.6, mostly type hints.

Will be used on Python < 3.11 where `tomllib` isn't available yet.
