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

Implementations for Python 2.

:author: Kenneth Hoste (Ghent University)
"""
# these are not used here, but imported from here in other places
import ConfigParser as configparser  # noqa
import urllib2 as std_urllib  # noqa
from string import letters as ascii_letters  # noqa
from StringIO import StringIO  # noqa
from urllib2 import HTTPError, HTTPSHandler, Request, URLError, build_opener, urlopen  # noqa

try:
    # Python 2.7
    from collections import OrderedDict  # noqa
except ImportError:
    # only needed to keep supporting Python 2.6
    from easybuild.tools.ordereddict import OrderedDict  # noqa

# reload function (built-in in Python 2)
reload = reload

# string type that can be used in 'isinstance' calls
string_type = basestring


def raise_with_traceback(exception_class, message, traceback):
    """Raise exception of specified class with given message and traceback."""
    raise exception_class, message, traceback
