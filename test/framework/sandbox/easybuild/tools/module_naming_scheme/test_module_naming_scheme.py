##
# Copyright 2013-2014 Ghent University
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
##
"""
Implementation of a test module naming scheme.

@author: Kenneth Hoste (Ghent University)
"""

import os

from easybuild.tools.module_naming_scheme import ModuleNamingScheme


class TestModuleNamingScheme(ModuleNamingScheme):
    """Class implementing a simple module naming scheme for testing purposes."""

    def det_full_module_name(self, ec):
        """
        Determine full module name from given easyconfig, according to a simple testing module naming scheme.

        @param ec: dict-like object with easyconfig parameter values (e.g. 'name', 'version', etc.)

        @return: n-element tuple with full module name, e.g.: ('gzip', '1.5'), ('intel', 'intelmpi', 'gzip', '1.5')
        """
        if ec['toolchain']['name'] == 'goolf':
            mod_name = os.path.join('gnu', 'openmpi', ec['name'], ec['version'])
        elif ec['toolchain']['name'] == 'GCC':
            mod_name = os.path.join('gnu', ec['name'], ec['version'])
        elif ec['toolchain']['name'] == 'ictce':
            mod_name = os.path.join('intel', 'intelmpi', ec['name'], ec['version'])
        else:
            mod_name = os.path.join(ec['name'], ec['version'])
        return mod_name
