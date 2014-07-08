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

@author: Kenneth Hoste (Ghent University)
@author: Markus Geimer (Forschungszentrum Juelich GmbH)
"""

import os
from vsc.utils import fancylogger

from easybuild.tools.module_naming_scheme import ModuleNamingScheme
from easybuild.tools.module_naming_scheme.toolchain import det_toolchain_compilers, det_toolchain_mpi


CORE = 'Core'
COMPILER = 'Compiler'
MPI = 'MPI'


_log = fancylogger.getLogger('HierarchicalMNS')


class HierarchicalMNS(ModuleNamingScheme):
    """Class implementing an example hierarchical module naming scheme."""

    REQUIRED_KEYS = ['name', 'version', 'versionsuffix', 'toolchain', 'moduleclass']

    def requires_toolchain_details(self):
        """
        Determine whether toolchain details are required by this module naming scheme,
        e.g. whether one of det_toolchain_* functions are relied upon.
        """
        return True

    def det_full_module_name(self, ec):
        """
        Determine full module name, relative to the top of the module path.
        Examples: Core/GCC/4.8.3, Compiler/GCC/4.8.3/OpenMPI/1.6.5, MPI/GCC/4.8.3/OpenMPI/1.6.5/HPL/2.1
        """
        return os.path.join(self.det_module_subdir(ec), self.det_short_module_name(ec))

    def det_short_module_name(self, ec):
        """
        Determine short module name, i.e. the name under which modules will be exposed to users.
        Examples: GCC/4.8.3, OpenMPI/1.6.5, OpenBLAS/0.2.9, HPL/2.1, Python/2.7.5
        """
        return os.path.join(ec['name'], ec['version'] + ec['versionsuffix'])

    def det_toolchain_compilers_name_version(self, tc_comps):
        """
        Determine toolchain compiler tag, for given list of compilers.
        """
        if len(tc_comps) == 1:
            tc_comp_name = tc_comps[0]['name']
            tc_comp_ver = tc_comps[0]['version']
        else:
            tc_comp_names = [comp['name'] for comp in tc_comps]
            if set(tc_comp_names) == set(['icc', 'ifort']):
                tc_comp_name = 'intel'
                if tc_comps[0]['version'] == tc_comps[1]['version']:
                    tc_comp_ver = tc_comps[0]['version']
                else:
                    _log.error("Bumped into different versions for toolchain compilers: %s" % tc_comps)
            else:
                mns = self.__class__.__name__
                _log.error("Unknown set of toolchain compilers, %s needs to be enhanced first." % mns)
        return tc_comp_name, tc_comp_ver

    def det_module_subdir(self, ec):
        """
        Determine module subdirectory, relative to the top of the module path.
        This determines the separation between module names exposed to users, and what's part of the $MODULEPATH.
        Examples: Core, Compiler/GCC/4.8.3, MPI/GCC/4.8.3/OpenMPI/1.6.5
        """
        # determine prefix based on type of toolchain used
        tc_comps = det_toolchain_compilers(ec)
        if tc_comps is None:
            # no compiler in toolchain, dummy toolchain => Core module
            subdir = CORE
        else:
            tc_comp_name, tc_comp_ver = self.det_toolchain_compilers_name_version(tc_comps)
            tc_mpi = det_toolchain_mpi(ec)
            if tc_mpi is None:
                # compiler-only toolchain => Compiler/<compiler_name>/<compiler_version> namespace
                subdir = os.path.join(COMPILER, tc_comp_name, tc_comp_ver)
            else:
                # compiler-MPI toolchain => MPI/<comp_name>/<comp_version>/<MPI_name>/<MPI_version> namespace
                tc_mpi_fullver = tc_mpi['version'] + tc_mpi['versionsuffix']
                subdir = os.path.join(MPI, tc_comp_name, tc_comp_ver, tc_mpi['name'], tc_mpi_fullver)

        return subdir

    def det_modpath_extensions(self, ec):
        """
        Determine module path extensions, if any.
        Examples: Compiler/GCC/4.8.3 (for GCC/4.8.3 module), MPI/GCC/4.8.3/OpenMPI/1.6.5 (for OpenMPI/1.6.5 module)
        """
        modclass = ec['moduleclass']

        paths = []
        if modclass == 'compiler':
            paths.append(os.path.join(COMPILER, ec['name'], ec['version']))
        elif modclass == 'mpi':
            tc_comps = det_toolchain_compilers(ec)
            tc_comp_name, tc_comp_ver = self.det_toolchain_compilers_name_version(tc_comps)
            fullver = ec['version'] + ec['versionsuffix']
            paths.append(os.path.join(MPI, tc_comp_name, tc_comp_ver, ec['name'], fullver))

        return paths

    def expand_toolchain_load(self):
        """
        Determine whether load statements for a toolchain should be expanded to load statements for its dependencies.
        This is useful when toolchains are not exposed to users.
        """
        return True

    def det_init_modulepaths(self, ec):
        """
        Determine list of initial module paths (i.e. top of the hierarchy).
        """
        return [CORE]
