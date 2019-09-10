#
# Copyright 2019-2019 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# https://github.com/easybuilders/easybuild
#
# EasyBuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
#
"""
Functionality to facilitate keeping code compatible with Python 2 & Python 3.

Implementations for Python 3.

:author: Kenneth Hoste (Ghent University)
"""
# these are not used here, but imported from here in other places
import configparser  # noqa
import json
import subprocess
import sys
import urllib.request as std_urllib  # noqa
from collections import OrderedDict  # noqa
from io import StringIO  # noqa
from string import ascii_letters, ascii_lowercase  # noqa
from urllib.request import HTTPError, HTTPSHandler, Request, URLError, build_opener, urlopen  # noqa
from urllib.parse import urlencode  # noqa

# reload function (no longer a built-in in Python 3)
# importlib only works with Python 3.4 & newer
from importlib import reload  # noqa

# string type that can be used in 'isinstance' calls
string_type = str


def json_loads(body):
    """Wrapper for json.loads that takes into account that Python versions older than 3.6 require a string value."""

    if isinstance(body, bytes) and sys.version_info[0] == 3 and sys.version_info[1] < 6:
        # decode bytes string as regular string with UTF-8 encoding for Python 3.5.x and older
        # only Python 3.6 and newer have support for passing bytes string to json.loads
        # cfr. https://docs.python.org/2/library/json.html#json.loads
        body = body.decode('utf-8', 'ignore')

    return json.loads(body)


def subprocess_popen_text(cmd, **kwargs):
    """Call subprocess.Popen in text mode with specified named arguments."""
    # open stdout/stderr in text mode in Popen when using Python 3
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, **kwargs)


def raise_with_traceback(exception_class, message, traceback):
    """Raise exception of specified class with given message and traceback."""
    raise exception_class(message).with_traceback(traceback)


def extract_method_name(method_func):
    """Extract method name from lambda function."""
    return '_'.join(method_func.__code__.co_names)


def mk_wrapper_baseclass(metaclass):

    class WrapperBase(object, metaclass=metaclass):
        """
        Wrapper class that provides proxy access to an instance of some internal instance.
        """
        __wraps__ = None

    return WrapperBase
