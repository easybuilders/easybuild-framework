"""Compatibility module referring to the Python 3.11+ tomllib or an internal copy"""
import sys

if sys.version_info < (3, 11):
    from .tomli import *  # noqa
else:
    from tomllib import *  # noqa, pylint: disable=import-error
