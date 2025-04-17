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
import sys

from easybuild.base import fancylogger

from easybuild.base.wrapper import create_base_metaclass  # noqa

# all functionality provided by the py3 modules is made available via the easybuild.tools.py2vs3 namespace
from easybuild.tools.py2vs3.py3 import *  # noqa


_log = fancylogger.getLogger('py2vs3', fname=False)
_log.deprecated("Using py2vs3 is deprecated, since EasyBuild no longer runs on Python 2.", '6.0')


def python2_is_deprecated():
    """
    Exit with an error when using Python 2, since EasyBuild does not support it.
    We preserve the function name here in here EB5, to maintain the API, even though it now exits.
    """
    if sys.version_info[0] == 2:
        sys.stderr.write('\n\nEasyBuild v5.0+ is not compatible with Python v2. Use Python >= 3.6.\n\n\n')
        sys.exit(1)
