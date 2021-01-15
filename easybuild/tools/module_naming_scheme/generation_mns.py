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

from easybuild.tools.module_naming_scheme.mns import ModuleNamingScheme
# from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version

DUMMY_TOOLCHAIN_NAME = 'dummy'
DUMMY_TOOLCHAIN_VERSION = 'dummy'

SYSTEM_TOOLCHAIN_NAME = 'system'


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

        if ec['toolchain']['name'] == 'foss':
            release_date = ec['toolchain']['version']
        elif ec['toolchain']['name'] == 'GCCcore': 
        # please add a new GCCcore version if you want to use a new toolchain version.
            if ec['toolchain']['version'] == '7.3.0':
                release_date = '2018b'
            elif ec['toolchain']['version'] == '6.3.0':
                release_date = '2017a'
            elif ec['toolchain']['version'] == '5.4.0':
                release_date = '2016b'
            elif ec['toolchain']['version'] == '4.9.3':
                release_date = '2016a'
            elif ec['toolchain']['version'] == '8.3.0':
                release_date = '2019b'
            elif ec['toolchain']['version'] == '10.2.0':
                release_date = '2020b'
        elif ec['toolchain']['name'] == 'GCC': 
        # please add a new GCC version if you want to use a new toolchain version.
            if ec['toolchain']['version'] == '7.3.0-2.30':
                release_date = '2018b'
            elif ec['toolchain']['version'] == '6.3.0-2.27':
                release_date = '2017a'
            elif ec['toolchain']['version'] == '5.4.0-2.26':
                release_date = '2016b'
            elif ec['toolchain']['version'] == '4.9.3-2.25':
                release_date = '2016a'
            elif ec['toolchain']['version'] == '8.3.0-2.32':
                release_date = '2019b'
            elif ec['toolchain']['version'] == '10.2.0':
                release_date = '2020b'
        elif ec['toolchain']['name'] == 'gompi':
            release_date = ec['toolchain']['version']
        elif ec['toolchain']['name'] == 'fosscuda':
            release_date = ec['toolchain']['version']
        elif ec['toolchain']['name'] in [DUMMY_TOOLCHAIN_NAME, SYSTEM_TOOLCHAIN_NAME]:
            release_date = ''
            release = 'General'
        else:
            release_date = "NOTFOUND"

        subdir = os.path.join(release, release_date)
        return subdir
