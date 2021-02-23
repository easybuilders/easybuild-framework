#
# Copyright 2019-2021 Ghent University
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
from distutils.version import LooseVersion
from functools import cmp_to_key
from html.parser import HTMLParser  # noqa
from itertools import zip_longest
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


def safe_cmp_looseversions(v1, v2):
    """Safe comparison function for two (values containing) LooseVersion instances."""

    if not isinstance(v1, type(v2)):
        raise TypeError("Can't compare values of different types: %s (%s) vs %s (%s)" % (v1, type(v1), v2, type(v2)))

    # if we receive two iterative values, we need to recurse
    if isinstance(v1, (list, tuple)) and isinstance(v2, (list, tuple)):
        if len(v1) == len(v2):
            for x1, x2 in zip(v1, v2):
                res = safe_cmp_looseversions(x1, x2)
                # if a difference was found, we know the result;
                # if not, we need comparison on next item (if any), done in next iteration
                if res != 0:
                    return res
            return 0  # no difference
        else:
            raise ValueError("Can only compare iterative values of same length: %s vs %s" % (v1, v2))

    def simple_compare(x1, x2):
        """Helper function for simple comparison using standard operators ==, <, > """
        if x1 < x2:
            return -1
        elif x1 > x2:
            return 1
        else:
            return 0

    if isinstance(v1, LooseVersion) and isinstance(v2, LooseVersion):
        # implementation based on '14894.patch' patch file provided in https://bugs.python.org/issue14894
        for ver1_part, ver2_part in zip_longest(v1.version, v2.version, fillvalue=''):
            # use string comparison if version parts have different type
            if not isinstance(ver1_part, type(ver2_part)):
                ver1_part = str(ver1_part)
                ver2_part = str(ver2_part)

            res = simple_compare(ver1_part, ver2_part)
            if res == 0:
                continue
            else:
                return res

        # identical versions
        return 0
    else:
        # for non-LooseVersion values, use simple comparison
        return simple_compare(v1, v2)


def sort_looseversions(looseversions):
    """Sort list of (values including) LooseVersion instances."""
    # with Python 2, we can safely use 'sorted' on LooseVersion instances
    # (but we can't in Python 3, see https://bugs.python.org/issue14894)
    return sorted(looseversions, key=cmp_to_key(safe_cmp_looseversions))
