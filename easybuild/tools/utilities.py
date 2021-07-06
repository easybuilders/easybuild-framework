# #
# Copyright 2012-2021 Ghent University
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
# #
"""
Module with various utility functions

:author: Kenneth Hoste (Ghent University)
"""
import datetime
import glob
import os
import re
import sys
from string import digits

from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import build_option
from easybuild.tools.py2vs3 import ascii_letters, string_type


_log = fancylogger.getLogger('tools.utilities')

INDENT_2SPACES = ' ' * 2
INDENT_4SPACES = ' ' * 4


def flatten(lst):
    """Flatten a list of lists."""
    res = []
    for x in lst:
        res.extend(x)
    return res


def quote_str(val, escape_newline=False, prefer_single_quotes=False, escape_backslash=False, tcl=False):
    """
    Obtain a new value to be used in string replacement context.

    For non-string values, it just returns the exact same value.

    For string values, it tries to escape the string in quotes, e.g.,
    foo becomes 'foo', foo'bar becomes "foo'bar",
    foo'bar"baz becomes \"\"\"foo'bar"baz\"\"\", etc.

    :param escape_newline: wrap strings that include a newline in triple quotes
    :param prefer_single_quotes: if possible use single quotes
    :param escape_backslash: escape backslash characters in the string
    :param tcl: Boolean for whether we are quoting for Tcl syntax
    """

    if isinstance(val, string_type):
        # escape backslashes
        if escape_backslash:
            val = val.replace('\\', '\\\\')
        # forced triple double quotes
        if ("'" in val and '"' in val) or (escape_newline and '\n' in val):
            return '"""%s"""' % val
        # escape double quote(s) used in strings
        elif '"' in val:
            if tcl:
                return '"%s"' % val.replace('"', '\\"')
            else:
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
    return quote_str(val, escape_newline=True, prefer_single_quotes=True, escape_backslash=True)


def shell_quote(token):
    """
    Wrap provided token in single quotes (to escape space and characters with special meaning in a shell),
    so it can be used in a shell command. This results in token that is not expanded/interpolated by the shell.
    """
    # first, strip off double quotes that may wrap the entire value,
    # we don't want to wrap single quotes around a double-quoted value
    token = str(token).strip('"')
    # escape any non-escaped single quotes, and wrap entire token in single quotes
    return "'%s'" % re.sub(r"(?<!\\)'", r"\'", token)


def remove_unwanted_chars(inputstring):
    """Remove unwanted characters from the given string and return a copy

    All non-letter and non-numeral characters are considered unwanted except for underscore ('_').
    """
    return ''.join(c for c in inputstring if c in (ascii_letters + digits + '_'))


def import_available_modules(namespace):
    """
    Import all available module in the specified namespace.

    :param namespace: The namespace to import modules from.
    """
    modules = []
    for path in sys.path:

        cand_modpath_glob = os.path.sep.join([path] + namespace.split('.') + ['*.py'])

        # if sys.path entry being considered is the empty string
        # (which corresponds to Python packages/modules in current working directory being considered),
        # we need to strip off / from the start of the path
        if path == '' and cand_modpath_glob.startswith(os.path.sep):
            cand_modpath_glob = cand_modpath_glob.lstrip(os.path.sep)

        for module in sorted(glob.glob(cand_modpath_glob)):
            if not module.endswith('__init__.py'):
                mod_name = module.split(os.path.sep)[-1].split('.')[0]
                modpath = '.'.join([namespace, mod_name])
                _log.debug("importing module %s", modpath)
                try:
                    mod = __import__(modpath, globals(), locals(), [''])
                except ImportError as err:
                    raise EasyBuildError("import_available_modules: Failed to import %s: %s", modpath, err)

                if mod not in modules:
                    modules.append(mod)

    return modules


def only_if_module_is_available(modnames, pkgname=None, url=None):
    """Decorator to guard functions/methods against missing required module with specified name."""
    if pkgname and url is None:
        url = 'https://pypi.python.org/pypi/%s' % pkgname

    if isinstance(modnames, string_type):
        modnames = (modnames,)

    def wrap(orig):
        """Decorated function, raises ImportError if specified module is not available."""
        try:
            imported = None
            for modname in modnames:
                try:
                    __import__(modname)
                    imported = modname
                    break
                except ImportError:
                    pass

            if imported is None:
                raise ImportError
            else:
                return orig

        except ImportError:
            def error(*args, **kwargs):
                msg = "None of the specified modules (%s) is available" % ', '.join(modnames)
                if pkgname:
                    msg += " (provided by Python package %s, available from %s)" % (pkgname, url)
                elif url:
                    msg += " (available from %s)" % url
                msg += ", yet one of them is required!"
                raise EasyBuildError("ImportError: %s", msg)
            return error

    return wrap


def trace_msg(message, silent=False):
    """Print trace message."""
    if build_option('trace'):
        print_msg('  >> ' + message, prefix=False)


def nub(list_):
    """Returns the unique items of a list of hashables, while preserving order of
    the original list, i.e. the first unique element encoutered is
    retained.

    Code is taken from
    http://stackoverflow.com/questions/480214/how-do-you-remove-duplicates-from-a-list-in-python-whilst-preserving-order

    Supposedly, this is one of the fastest ways to determine the
    unique elements of a list.

    @type list_: a list :-)

    :return: a new list with each element from `list` appearing only once (cfr. Michelle Dubois).
    """
    seen = set()
    seen_add = seen.add
    return [x for x in list_ if x not in seen and not seen_add(x)]


def get_class_for(modulepath, class_name):
    """
    Get class for a given Python class name and Python module path.

    :param modulepath: Python module path (e.g., 'easybuild.base.generaloption')
    :param class_name: Python class name (e.g., 'GeneralOption')
    """
    # try to import specified module path, reraise ImportError if it occurs
    try:
        module = __import__(modulepath, globals(), locals(), [''])
    except ImportError as err:
        raise ImportError(err)
    # try to import specified class name from specified module path, throw ImportError if this fails
    try:
        klass = getattr(module, class_name)
    except AttributeError as err:
        raise ImportError("Failed to import %s from %s: %s" % (class_name, modulepath, err))
    return klass


def get_subclasses_dict(klass, include_base_class=False):
    """Get dict with subclasses per classes, recursively from the specified base class."""
    res = {}
    subclasses = klass.__subclasses__()
    if include_base_class:
        res.update({klass: subclasses})
    for subclass in subclasses:
        # always include base class for recursive call
        res.update(get_subclasses_dict(subclass, include_base_class=True))
    return res


def get_subclasses(klass, include_base_class=False):
    """Get list of all subclasses, recursively from the specified base class."""
    return get_subclasses_dict(klass, include_base_class=include_base_class).keys()


def mk_rst_table(titles, columns):
    """
    Returns an rst table with given titles and columns (a nested list of string columns for each column)
    """
    # take into account that passed values may be iterators produced via 'map'
    titles = list(titles)
    columns = list(columns)

    title_cnt, col_cnt = len(titles), len(columns)
    if title_cnt != col_cnt:
        msg = "Number of titles/columns should be equal, found %d titles and %d columns" % (title_cnt, col_cnt)
        raise ValueError(msg)
    table = []
    tmpl = []
    line = []

    # figure out column widths
    for i, title in enumerate(titles):
        width = max(map(len, columns[i] + [title]))

        # make line template
        tmpl.append('{%s:{c}<%s}' % (i, width))

    line = [''] * col_cnt
    line_tmpl = INDENT_4SPACES.join(tmpl)
    table_line = line_tmpl.format(*line, c='=')

    table.append(table_line)
    table.append(line_tmpl.format(*titles, c=' '))
    table.append(table_line)

    for row in map(list, zip(*columns)):
        table.append(line_tmpl.format(*row, c=' '))

    table.extend([table_line, ''])

    return table


def time2str(delta):
    """Return string representing provided datetime.timedelta value in human-readable form."""
    res = None

    if not isinstance(delta, datetime.timedelta):
        raise EasyBuildError("Incorrect value type provided to time2str, should be datetime.timedelta: %s", type(delta))

    delta_secs = delta.total_seconds()

    hours, remainder = divmod(delta_secs, 3600)
    mins, secs = divmod(remainder, 60)

    res = []
    if hours:
        res.append('%d %s' % (hours, 'hour' if hours == 1 else 'hours'))
    if mins or hours:
        res.append('%d %s' % (mins, 'min' if mins == 1 else 'mins'))
    res.append('%d %s' % (secs, 'sec' if secs == 1 else 'secs'))

    return ' '.join(res)


def natural_keys(key):
    """Can be used as the sort key in list.sort(key=natural_keys) to sort in natural order (i.e. respecting numbers)"""
    def try_to_int(key_part):
        return int(key_part) if key_part.isdigit() else key_part
    return [try_to_int(key_part) for key_part in re.split(r'(\d+)', key)]
