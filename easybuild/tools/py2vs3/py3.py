#
# Copyright 2019-2025 Ghent University
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

Authors:

* Kenneth Hoste (Ghent University)
"""
# these are not used here, but imported from here in other places
import configparser  # noqa
import urllib.request as std_urllib  # noqa
from collections.abc import Mapping  # noqa
from functools import cmp_to_key
from importlib.util import spec_from_file_location, module_from_spec
from html.parser import HTMLParser  # noqa
from itertools import zip_longest
from io import StringIO  # noqa
from os import makedirs  # noqa
from string import ascii_letters, ascii_lowercase  # noqa
from urllib.request import HTTPError, HTTPSHandler, Request, URLError, build_opener, urlopen  # noqa
from urllib.parse import urlencode  # noqa
from configparser import ConfigParser  # noqa

# reload function (no longer a built-in in Python 3)
# importlib only works with Python 3.4 & newer
from importlib import reload  # noqa

# distutils is deprecated, so prepare for it being removed
try:
    import distutils.version
    HAVE_DISTUTILS = True
except ImportError:
    HAVE_DISTUTILS = False

from easybuild._deprecated import json_loads # noqa
from easybuild.base.wrapper import mk_wrapper_baseclass  # noqa
from easybuild.tools.run import subprocess_popen_text, subprocess_terminate  # noqa

# string type that can be used in 'isinstance' calls
string_type = str


# note: also available in easybuild.tools.filetools, should be imported from there!
def load_source(filename, path):
    """Load file as Python module"""
    spec = spec_from_file_location(filename, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def raise_with_traceback(exception_class, message, traceback):
    """Raise exception of specified class with given message and traceback."""
    raise exception_class(message).with_traceback(traceback)


def extract_method_name(method_func):
    """Extract method name from lambda function."""
    return '_'.join(method_func.__code__.co_names)


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

    if isinstance(v1, distutils.version.LooseVersion) and isinstance(v2, distutils.version.LooseVersion):
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
    """Sort list of (values including) distutils.version.LooseVersion instances."""
    # with Python 2, we can safely use 'sorted' on LooseVersion instances
    # (but we can't in Python 3, see https://bugs.python.org/issue14894)
    if HAVE_DISTUTILS:
        return sorted(looseversions, key=cmp_to_key(safe_cmp_looseversions))
    else:
        return sorted(looseversions)
