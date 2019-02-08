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
import subprocess
import urllib.request as std_urllib  # noqa
from collections import OrderedDict  # noqa
from io import StringIO  # noqa
from string import ascii_letters, ascii_lowercase  # noqa
from urllib.request import HTTPError, HTTPSHandler, Request, URLError, build_opener, urlopen  # noqa

# reload function (no longer a built-in in Python 3)
# importlib only works with Python 3.4 & newer
from importlib import reload  # noqa

# string type that can be used in 'isinstance' calls
string_type = str


def subprocess_popen_text(cmd, **kwargs):
    """Call subprocess.Popen in text mode with specified named arguments."""
    # open stdout/stderr in text mode in Popen when using Python 3
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, **kwargs)


def raise_with_traceback(exception_class, message, traceback):
    """Raise exception of specified class with given message and traceback."""
    raise exception_class(message).with_traceback(traceback)
