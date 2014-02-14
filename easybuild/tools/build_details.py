#
# Copyright 2014-2014 Ghent University
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
#
"""
All required to provide details of build environment 
and allow for reproducable builds

@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""
import os
import platform
import time
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.systemtools import get_cpu_model, get_avail_core_count
from easybuild.tools.version import EASYBLOCKS_VERSION, FRAMEWORK_VERSION


def get_build_stats(app, start_time, command_line):
    """
    Return build statistics for this build
    """

    time_now = time.time()
    build_time = round(time_now - start_time, 2)

    buildstats = OrderedDict([
        ('easybuild-framework_version', str(FRAMEWORK_VERSION)),
        ('easybuild-easyblocks_version', str(EASYBLOCKS_VERSION)),
        ('host', os.uname()[1]),
        ('platform', platform.platform()),
        ('cpu_model', get_cpu_model()),
        ('core_count', get_avail_core_count()),
        ('timestamp', int(time_now)),
        ('build_time', build_time),
        ('install_size', app.det_installsize()),
        ('command_line', command_line),
        ('modules_tool', app.modules_tool.buildstats()),
    ])

    return buildstats
