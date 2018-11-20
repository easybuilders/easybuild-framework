#
# Copyright 2013-2018 Ghent University
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
Easyconfig constants module that provides all constants that can
be used within an Easyconfig file.

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""
import os
import platform
from vsc.utils import fancylogger

from easybuild.tools.systemtools import get_shared_lib_ext, get_os_name, get_os_type, get_os_version


_log = fancylogger.getLogger('easyconfig.constants', fname=False)


EXTERNAL_MODULE_MARKER = 'EXTERNAL_MODULE'

# constants that can be used in easyconfig
EASYCONFIG_CONSTANTS = {
    'EXTERNAL_MODULE': (EXTERNAL_MODULE_MARKER, "External module marker"),
    'HOME': (os.path.expanduser('~'), "Home directory ($HOME)"),
    'OS_TYPE': (get_os_type(), "System type (e.g. 'Linux' or 'Darwin')"),
    'OS_NAME': (get_os_name(), "System name (e.g. 'fedora' or 'RHEL')"),
    'OS_VERSION': (get_os_version(), "System version"),
    'SYS_PYTHON_VERSION': (platform.python_version(), "System Python version (platform.python_version())"),
}
