##
# Copyright 2013-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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

    REQUIRED_KEYS = ['name', 'version', 'toolchain']

    def det_full_module_name(self, ec):
        """
        Determine full module name from given easyconfig, according to a simple testing module naming scheme.

        @param ec: dict-like object with easyconfig parameter values (e.g. 'name', 'version', etc.)

        @return: string with full module name, e.g.: 'gzip/1.5', 'intel/intelmpi/gzip'/1.5'
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

    def det_module_symlink_paths(self, ec):
        """
        Determine list of paths in which symlinks to module files must be created.
        """
        return [ec['moduleclass'].upper(), ec['name'].lower()[0]]

    def is_short_modname_for(self, modname, name):
        """
        Determine whether the specified (short) module name is a module for software with the specified name.
        """
        return modname.find('%s' % name)!= -1
