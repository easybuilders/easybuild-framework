#
# Copyright 2019-2024 Ghent University
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
import sys

from easybuild.base import fancylogger

from easybuild.base.wrapper import create_base_metaclass  # noqa

# all functionality provided by the py3 modules is made available via the easybuild.tools.py2vs3 namespace
from easybuild.tools.py2vs3.py3 import *  # noqa


_log = fancylogger.getLogger('py2vs3', fname=False)
_log.deprecated("Using py2vs3 is deprecated, since EasyBuild no longer runs on Python 2.", '6.0')


def python2_is_deprecated():
    """
    Print warning when using Python 2, since the support for running EasyBuild with it is deprecated.
    """
    if sys.version_info[0] == 2:
        full_py_ver = '.'.join(str(x) for x in sys.version_info[:3])
        warning_lines = [
            "Running EasyBuild with Python v2.x is deprecated, found Python v%s." % full_py_ver,
            "Support for running EasyBuild with Python v2.x will be removed in EasyBuild v5.0.",
            '',
            "It is strongly recommended to start using Python v3.x for running EasyBuild,",
            "see https://docs.easybuild.io/en/latest/Python-2-3-compatibility.html for more information.",
        ]
        max_len = max(len(x) for x in warning_lines)
        for i in range(len(warning_lines)):
            line_len = len(warning_lines[i])
            warning_lines[i] = '!!! ' + warning_lines[i] + ' ' * (max_len - line_len) + ' !!!'
        max_len = max(len(x) for x in warning_lines)
        warning_lines.insert(0, '!' * max_len)
        warning_lines.append('!' * max_len)
        sys.stderr.write('\n\n' + '\n'.join(warning_lines) + '\n\n\n')
