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
:author: Thomas Soenen (B-square IT services)
:author: Alan O'Cais (CECAM)
"""

import os
import json

from easybuild.tools.module_naming_scheme.mns import ModuleNamingScheme
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.robot import search_easyconfigs
from easybuild.tools.config import ConfigurationVariables
from easybuild.framework.easyconfig.easyconfig import get_toolchain_hierarchy
from easybuild.tools.toolchain.toolchain import is_system_toolchain

GMNS_ENV = "GENERATION_MODULE_NAMING_SCHEME_LOOKUP_TABLE"

class GenerationModuleNamingScheme(ModuleNamingScheme):
    """Class implementing the generational module naming scheme."""

    REQUIRED_KEYS = ['name', 'version', 'versionsuffix', 'toolchain']

    def __init__(self):
        """
        Generate lookup table that maps toolchains on foss generations. Generations (e.g. 2018a,
        2020b) are fetched from the foss easyconfigs and dynamically mapped on toolchains using
        get_toolchain_hierarchy. The lookup table can be extended by the user by providing a file.

        Lookup table is a dict with toolchain-generation key-value pairs:{(GCC, 4.8.2): 2016a},
        with toolchains resembled as a tuple.

        json format of file with custom mappings:
        {
          "2018b": [{"name": "GCC", "version": "5.2.0"}, {"name": "GCC", "version": "4.8.2"}],
          "2019b": [{"name": "GCC", "version": "5.2.4"}, {"name": "GCC", "version": "4.8.4"}],
        }
        """
        super().__init__()

        self.lookup_table = {}

        # Get all generations
        foss_filenames = search_easyconfigs("^foss-20[0-9]{2}[a-z]\.eb",
                                            filename_only=True,
                                            print_result=False)
        self.generations = [x.split('-')[1].split('.')[0] for x in foss_filenames]

        # get_toolchain_hierarchy() depends on ActiveMNS(), which can't point to 
        # GenerationModuleNamingScheme to prevent circular reference errors. For that purpose, the MNS
        # that ActiveMNS() points to is tweaked while get_toolchain_hierarchy() is used.
        ConfigurationVariables()._FrozenDict__dict['module_naming_scheme'] = 'EasyBuildMNS'

        # map generations on toolchains
        for generation in self.generations:
            for tc in get_toolchain_hierarchy({'name':'foss', 'version':generation}):
                self.lookup_table[(tc['name'], tc['version'])] = generation
            # include (foss, <generation>) as a toolchain aswell
            self.lookup_table[('foss', generation)] = generation

        # Force config to point to other MNS
        ConfigurationVariables()._FrozenDict__dict['module_naming_scheme'] = 'GenerationModuleNamingScheme'

        # users can provide custom generation-toolchain mapping through a file
        path = os.environ.get(GMNS_ENV)
        if path:
            if not os.path.isfile(path):
                msg = "value of ENV {} ({}) should be a valid filepath"
                raise EasyBuildError(msg.format(GMNS_ENV, path))
            with open(path, 'r') as hc_lookup:
                try:
                    hc_lookup_data = json.loads(hc_lookup.read())
                except json.decoder.JSONDecodeError:
                    raise EasyBuildError("{} can't be decoded as json".format(path))
                if not isinstance(hc_lookup_data, dict):
                    raise EasyBuildError("{} should contain a dict".format(path))
                if not set(hc_lookup_data.keys()) <= set(self.generations):
                    raise EasyBuildError("Keys of {} should be generations".format(path))
                for generation, toolchains in hc_lookup_data.items():
                    if not isinstance(toolchains, list):
                        raise EasyBuildError("Values of {} should be lists".format(path))
                    for tc in toolchains:
                        if not isinstance(tc, dict):
                            msg = "Toolchains in {} should be of type dict"
                            raise EasyBuildError(msg.format(path))
                        if set(tc.keys()) != {'name', 'version'}:
                            msg = "Toolchains in {} should have two keys ('name', 'version')"
                            raise EasyBuildError(msg.format(path))
                        self.lookup_table[(tc['name'], tc['version'])] = generation

    def det_full_module_name(self, ec):
        """
        Determine full module name, relative to the top of the module path.
        Examples: General/GCC/4.8.3, Releases/2018b/OpenMPI/1.6.5
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
        """
        Determine subdirectory for module file in $MODULEPATH. This determines the separation
        between module names exposed to users, and what's part of the $MODULEPATH. subdirectory
        is determined by mapping toolchain on a generation.
        """
        release = 'releases'
        release_version = ''

        if is_system_toolchain(ec['toolchain']['name']):
            release = 'General'
        else:
            if self.lookup_table.get((ec['toolchain']['name'], ec['toolchain']['version'])):
                release_version = self.lookup_table[(ec['toolchain']['name'], ec['toolchain']['version'])]
            else:
                tc_hierarchy = get_toolchain_hierarchy({'name': ec['toolchain']['name'],
                                                        'version': ec['toolchain']['version']})
                for tc in tc_hierarchy:
                    if self.lookup_table.get((tc['name'], tc['version'])):
                        release_version = self.lookup_table.get((tc['name'], tc['version']))
                        break

            if release_version == '':
                msg = "Couldn't map software version ({}, {}) to a generation. Provide a custom" \
                      "toolchain mapping through {}"
                raise EasyBuildError(msg.format(ec['name'], ec['version'], GMNS_ENV))

        return os.path.join(release, release_version).rstrip('/')
