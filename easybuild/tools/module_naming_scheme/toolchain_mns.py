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
Implementation of an example hierarchical module naming scheme.

@author: Alan O'Cais (Forschungszentrum Juelich GmbH)
@author: Eric "The Knife" Gregory (Forschungszentrum Juelich GmbH)
"""

from easybuild.tools.module_naming_scheme.hierarchical_mns import HierarchicalMNS
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME

TOOLCHAIN = 'Toolchain'
MODULECLASS_TC = 'toolchain'

class ToolchainMNS(HierarchicalMNS):
    """Class implementing a toolchain-based hierarchical module naming scheme."""

    def det_module_subdir(self, ec):
        """
        Determine module subdirectory, relative to the top of the module path.
        This determines the separation between module names exposed to users, and what's part of the $MODULEPATH.
        Examples: Core, Toolchain/gpsolf/2015.02
        """
        if ec.toolchain.name == DUMMY_TOOLCHAIN_NAME:
            # toolchain is dummy/dummy, put in Core
            subdir = CORE
        else:
            subdir = os.path.join(TOOLCHAIN,ec.toolchain.name,ec.toolchain.version)
        return subdir

    def det_modpath_extensions(self, ec):
        """
        Determine module path extensions, if any.
        Examples: Toolchain/intel/2014.12 (for intel/2014.12 module)
        """
        modclass = ec['moduleclass']
        paths = []
	# Take care of the corner cases, such as GCC, where it is both a compiler and a toolchain
        if modclass == MODULECLASS_TC or ec['name'] in ['GCC']:
            fullver = self.det_full_version(ec)
            paths.append(os.path.join(TOOLCHAIN,  ec['name'], fullver))
        return paths

    def expand_toolchain_load(self):
        """
        Determine whether load statements for a toolchain should be expanded to load statements for its dependencies.
        This is useful when toolchains are not exposed to users.
        """
	# In our case we still have to load the toolchains because they are explicitly exposed when extending the module path
        return True
