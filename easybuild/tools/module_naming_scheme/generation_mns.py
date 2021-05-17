##
# Copyright 2016-2021 Ghent University
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
##
"""
Implementation of a different generation specific module naming scheme using release dates.
:author: Thomas Eylenbosch (Gluo N.V.)
"""

import os
import json
from pkgutil import get_data

from easybuild.tools.module_naming_scheme.mns import ModuleNamingScheme
# from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version

DUMMY_TOOLCHAIN_NAME = 'dummy'
DUMMY_TOOLCHAIN_VERSION = 'dummy'

SYSTEM_TOOLCHAIN_NAME = 'system'

# Lookup table for toolchain versions and generations
GENERATION_LOOKUP = json.loads(get_data(__package__, 'generation_lookup_table.json'))

class GenerationModuleNamingScheme(ModuleNamingScheme):
    """Class implementing the categorized module naming scheme."""

    REQUIRED_KEYS = ['name', 'version', 'versionsuffix', 'toolchain']

    def det_full_module_name(self, ec):
        """
        Determine short module name, i.e. the name under which modules will be exposed to users.
        Examples: GCC/4.8.3, OpenMPI/1.6.5, OpenBLAS/0.2.9, HPL/2.1, Python/2.7.5
        """

        return os.path.join(self.det_module_subdir(ec), self.det_short_module_name(ec))

    def det_short_module_name(self, ec):
        """
        Determine short module name, i.e. the name under which modules will be exposed to users.
        Examples: GCC/4.8.3, OpenMPI/1.6.5, OpenBLAS/0.2.9, HPL/2.1, Python/2.7.5
        """
        return os.path.join(ec['name'], self.det_full_version(ec))

    def det_full_version(self, ec):
        """Determine full version, taking into account version prefix/suffix."""
        # versionprefix is not always available (e.g., for toolchains)
        versionprefix = ec.get('versionprefix', '')
        return versionprefix + ec['version'] + ec['versionsuffix']

    def det_module_subdir(self, ec):

        release = 'releases'
        release_date = ''

        if ec['toolchain']['name'] in [DUMMY_TOOLCHAIN_NAME, SYSTEM_TOOLCHAIN_NAME]:
            release = 'General'

        elif ec['toolchain']['version'] in GENERATION_LOOKUP['releases']:
            release_date = ec['toolchain']['version']

        elif ec['toolchain']['name'] in GENERATION_LOOKUP:
            release_date = GENERATION_LOOKUP[ec['toolchain']['name']].get(ec['toolchain']['version'], 'NOTFOUND')

        else:
            release_date = 'NOTFOUND'

        subdir = os.path.join(release, release_date).rstrip('/')

        return subdir
