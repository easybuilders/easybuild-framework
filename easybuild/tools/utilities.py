# #
# Copyright 2012-2013 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
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
import os
from vsc import fancylogger
from vsc.utils.missing import any as _any
from vsc.utils.missing import all as _all

_log = fancylogger.getLogger('tools.utilities')


def any(ls):
    """Reimplementation of 'any' function, which is not available in Python 2.4 yet."""
    _log.deprecated("own definition of any", "2.0")
    return _any(ls)


def all(ls):
    """Reimplementation of 'all' function, which is not available in Python 2.4 yet."""
    _log.deprecated("own definition of all", "2.0")
    return _all(ls)


def read_environment(env_vars, strict=False):
    """
    Read variables from the environment
        @param: env_vars: a dict with key a name, value a environment variable name
        @param: strict, boolean, if True enforces that all specified environment variables are found
    """
    result = dict([(k, os.environ.get(v)) for k, v in env_vars.items() if v in os.environ])

    if not len(env_vars) == len(result):
        missing = ','.join(["%s / %s" % (k, v) for k, v in env_vars.items() if not k in result])
        msg = 'Following name/variable not found in environment: %s' % missing
        if strict:
            _log.error(msg)
        else:
            _log.debug(msg)

    return result


def flatten(lst):
    """Flatten a list of lists."""
    res = []
    for x in lst:
        res.extend(x)
    return res


def quote_str(x):
    """
    Obtain a new value to be used in string replacement context.

    For non-string values, it just returns the exact same value.

    For string values, it tries to escape the string in quotes, e.g.,
    foo becomes 'foo', foo'bar becomes "foo'bar",
    foo'bar"baz becomes \"\"\"foo'bar"baz\"\"\", etc.
    """

    if isinstance(x, basestring):
        if "'" in x and '"' in x:
            return '"""%s"""' % x
        elif '"' in x:
            return "'%s'" % x
        else:
            return '"%s"' % x
    else:
        return x

