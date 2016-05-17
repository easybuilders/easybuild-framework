# #
# Copyright 2012-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/easybuild
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
# #
"""
Module with various utility functions

@author: Kenneth Hoste (Ghent University)
"""
import glob
import os
import string
import sys
from vsc.utils import fancylogger

import easybuild.tools.environment as env
from easybuild.tools.build_log import EasyBuildError


_log = fancylogger.getLogger('tools.utilities')


# a list of all ascii characters
ASCII_CHARS = string.maketrans('', '')
# a list of all unwanted ascii characters (we only want to keep digits, letters and _)
UNWANTED_CHARS = ASCII_CHARS.translate(ASCII_CHARS, string.digits + string.ascii_letters + "_")


def read_environment(env_vars, strict=False):
    """NO LONGER SUPPORTED: use read_environment from easybuild.tools.environment instead"""
    _log.nosupport("read_environment has been moved to easybuild.tools.environment", '2.0')


def flatten(lst):
    """Flatten a list of lists."""
    res = []
    for x in lst:
        res.extend(x)
    return res


def quote_str(val, escape_newline=False, prefer_single_quotes=False):
    """
    Obtain a new value to be used in string replacement context.

    For non-string values, it just returns the exact same value.

    For string values, it tries to escape the string in quotes, e.g.,
    foo becomes 'foo', foo'bar becomes "foo'bar",
    foo'bar"baz becomes \"\"\"foo'bar"baz\"\"\", etc.

    @param escape_newline: wrap strings that include a newline in triple quotes
    """

    if isinstance(val, basestring):
        # forced triple double quotes
        if ("'" in val and '"' in val) or (escape_newline and '\n' in val):
            return '"""%s"""' % val
        # single quotes to escape double quote used in strings
        elif '"' in val:
            return "'%s'" % val
        # if single quotes are preferred, use single quotes;
        # unless a space or a single quote are in the string
        elif prefer_single_quotes and "'" not in val and ' ' not in val:
            return "'%s'" % val
        # fallback on double quotes (required in tcl syntax)
        else:
            return '"%s"' % val
    else:
        return val


def quote_py_str(val):
    """Version of quote_str specific for generating use in Python context (e.g., easyconfig parameters)."""
    return quote_str(val, escape_newline=True, prefer_single_quotes=True)


def remove_unwanted_chars(inputstring):
    """Remove unwanted characters from the given string and return a copy

    All non-letter and non-numeral characters are considered unwanted except for underscore ('_'), see UNWANTED_CHARS.
    """
    return inputstring.translate(ASCII_CHARS, UNWANTED_CHARS)


def import_available_modules(namespace):
    """
    Import all available module in the specified namespace.

    @param namespace: The namespace to import modules from.
    """
    modules = []
    for path in sys.path:
        for module in sorted(glob.glob(os.path.sep.join([path] + namespace.split('.') + ['*.py']))):
            if not module.endswith('__init__.py'):
                mod_name = module.split(os.path.sep)[-1].split('.')[0]
                modpath = '.'.join([namespace, mod_name])
                _log.debug("importing module %s" % modpath)
                try:
                    mod = __import__(modpath, globals(), locals(), [''])
                except ImportError as err:
                    raise EasyBuildError("import_available_modules: Failed to import %s: %s", modpath, err)
                modules.append(mod)
    return modules


def only_if_module_is_available(modname, pkgname=None, url=None):
    """Decorator to guard functions/methods against missing required module with specified name."""
    if pkgname and url is None:
        url = 'https://pypi.python.org/pypi/%s' % pkgname

    def wrap(orig):
        """Decorated function, raises ImportError if specified module is not available."""
        try:
            __import__(modname)
            return orig

        except ImportError as err:
            def error(*args, **kwargs):
                msg = "%s; required module '%s' is not available" % (err, modname)
                if pkgname:
                    msg += " (provided by Python package %s, available from %s)" % (pkgname, url)
                elif url:
                    msg += " (available from %s)" % url
                raise EasyBuildError("ImportError: %s", msg)
            return error

    return wrap
