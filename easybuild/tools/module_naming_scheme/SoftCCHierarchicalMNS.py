##
# Copyright 2013-2016 Ghent University
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
@author: Bart Oldeman  (Compute Canada)
"""

import os
import re
from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.module_naming_scheme.hierarchical_mns import HierarchicalMNS
from easybuild.tools.module_naming_scheme.toolchain import det_toolchain_compilers, det_toolchain_mpi, det_toolchain_cuda

CORE = 'Core'
COMPILER = 'Compiler'
MPI = 'MPI'
CUDA = 'CUDA'

MODULECLASS_COMPILER = 'compiler'
MODULECLASS_MPI = 'mpi'

GCCCORE = 'GCCcore'

# note: names in keys are ordered alphabetically
COMP_NAME_VERSION_TEMPLATES = {
    'icc,ifort': ('intel', '%(icc)s'),
    'Clang,GCC': ('Clang-GCC', '%(Clang)s-%(GCC)s'),
    'CUDA,GCC': ('GCC-CUDA', '%(GCC)s-%(CUDA)s'),
    'xlc,xlf': ('xlcxlf', '%(xlc)s'),
}

class SoftCCHierarchicalMNS(HierarchicalMNS):
    """Class implementing an example hierarchical module naming scheme."""
    def is_short_modname_for(self, short_modname, name):
        """
        Determine whether the specified (short) module name is a module for software with the specified name.
        Default implementation checks via a strict regex pattern, and assumes short module names are of the form:
            <name>/<version>[-<toolchain>]
        """
        # We rename our iccifort compiler to INTEL and this needs a hard fix because it is a toolchain
        modname_regex = re.compile('^%s/\S+$' % re.escape(name.lower()))
        res = bool(modname_regex.match(short_modname.lower()))
        if not res:
            if name == 'iccifort':
                modname_regex = re.compile('^%s/\S+$' % re.escape('intel'))
            elif name == 'impi':
                modname_regex = re.compile('^%s/\S+$' % re.escape('intelmpi'))
            res = bool(modname_regex.match(short_modname.lower()))

        self.log.debug("Checking whether '%s' is a module name for software with name '%s' via regex %s: %s",
                       short_modname, name, modname_regex.pattern, res)

        return res

    def det_short_module_name(self, ec):
        """
        Determine short module name, i.e. the name under which modules will be exposed to users.
        Examples: GCC/4.8.3, OpenMPI/1.6.5, OpenBLAS/0.2.9, HPL/2.1, Python/2.7.5
        """
        return os.path.join((ec['modaltsoftname'] or ec['name']).lower(), self.det_full_version(ec))

    def det_full_version(self, ec):
        """Determine full version, NOT using version prefix/suffix."""
        return ec['version']

    def det_module_subdir(self, ec):
        """
        Determine module subdirectory, relative to the top of the module path.
        This determines the separation between module names exposed to users, and what's part of the $MODULEPATH.
        Examples: Core, avx2/Compiler/gcc4.8, avx/MPI/gcc4.8/openmpi1.6
        """
        tc_comps = det_toolchain_compilers(ec)
        tc_comp_info = self.det_toolchain_compilers_name_version(tc_comps)
        # determine prefix based on type of toolchain used
        if tc_comp_info is None:
            # no compiler in toolchain, dummy toolchain => Core module
            subdir = CORE
        else:
            tc_comp_name, tc_comp_ver = tc_comp_info
            tc_comp_name = tc_comp_name.lower().split('-')[0]
            tc_comp_ver = self.det_twodigit_version({'version': tc_comp_ver})
            tc_mpi = det_toolchain_mpi(ec)
            tc_cuda = det_toolchain_cuda(ec)
            if tc_cuda is not None:
                # compiler-CUDA toolchain => CUDA/<comp_name>/<comp_version>/<CUDA_name>/<CUDA_version> namespace
                tc_cuda_name = tc_cuda['name'].lower()
                tc_cuda_fullver = self.det_twodigit_version(tc_cuda)
                subdir = os.path.join(tc_comp_name+tc_comp_ver, tc_cuda_name+tc_cuda_fullver)
                if tc_mpi is None:
                    subdir = os.path.join(CUDA, subdir)
                else:
                    tc_mpi_name = tc_mpi['name'].lower()
                    tc_mpi_fullver = self.det_twodigit_version(tc_mpi)
                    subdir = os.path.join(MPI, subdir, tc_mpi_name+tc_mpi_fullver)
            elif tc_mpi is None:
                # compiler-only toolchain => Compiler/<compiler_name><compiler_version> namespace
                if tc_comp_ver == 'system':
                    subdir = CORE
                else:
                    subdir = os.path.join(COMPILER, tc_comp_name+tc_comp_ver)
            else:
                # compiler-MPI toolchain => MPI/<comp_name><comp_version>/<MPI_name><MPI_version> namespace
                tc_mpi_name = tc_mpi['name'].lower()
                tc_mpi_fullver = self.det_twodigit_version(tc_mpi)
                subdir = os.path.join(MPI, tc_comp_name+tc_comp_ver, tc_mpi_name+tc_mpi_fullver)

        if os.getenv('RSNT_ARCH') is None:
            raise EasyBuildError("Need to set architecture to determine module path in $RSNT_ARCH")
        if subdir != CORE:
            subdir = os.path.join(os.getenv('RSNT_ARCH'), subdir)
        return subdir

    def det_twodigit_version(self, ec):
        """Determine two-digit version"""
        version = ec['version']
        if version.count('.') > 1:
            version = version[:version.find('.',version.find('.')+1)]
        return version

    def det_modpath_extensions(self, ec):
        """
        Determine module path extensions, if any.
        Examples: avx2/Compiler/gcc4.8 (for GCC/4.8.5 module), avx/MPI/intel2016.4/openmpi2.0 (for OpenMPI/2.0.2 module)
        """
        modclass = ec['moduleclass']
        tc_comps = det_toolchain_compilers(ec)
        tc_comp_info = self.det_toolchain_compilers_name_version(tc_comps)

        paths = []
        if modclass == MODULECLASS_COMPILER or ec['name'] in ['iccifort']:
            # obtain list of compilers based on that extend $MODULEPATH in some way other than <name>/<version>
            extend_comps = []
            # exclude GCC for which <name>/<version> is used as $MODULEPATH extension
            excluded_comps = ['GCC']
            for comps in COMP_NAME_VERSION_TEMPLATES.keys():
                extend_comps.extend([comp for comp in comps.split(',') if comp not in excluded_comps])

            comp_name_ver = None
            if ec['name'] in extend_comps:
                for key in COMP_NAME_VERSION_TEMPLATES:
                    if ec['name'] in key.split(','):
                        comp_name, comp_ver_tmpl = COMP_NAME_VERSION_TEMPLATES[key]
                        comp_versions = {ec['name']: self.det_twodigit_version(ec)}
                        if ec['name'] == 'ifort':
                            # 'icc' key should be provided since it's the only one used in the template
                            comp_versions.update({'icc': self.det_twodigit_version(ec)})
                        if tc_comp_info is not None:
                            # also provide toolchain version for non-dummy toolchains
                            comp_versions.update({tc_comp_info[0]: tc_comp_info[1]})

                        comp_name_ver = [comp_name.lower() + comp_ver_tmpl % comp_versions]
                        break
            else:
                comp_name_ver = [ec['name'].lower() + self.det_twodigit_version(ec)]
                # Handle the case where someone only wants iccifort to extend the path
                # This means icc/ifort are not of the moduleclass compiler but iccifort is
                if ec['name'] == 'iccifort':
                    comp_name_ver = ['intel' + self.det_twodigit_version(ec)]
            # Exclude extending the path for icc/ifort, the iccifort special case is handled above
            # XXX use custom code for MODULEPATH for compilers via modluafooter
            #if ec['name'] not in ['icc', 'ifort']:
            #    paths.append(os.path.join(COMPILER, *comp_name_ver))
        elif modclass == MODULECLASS_MPI or ec['name'] == CUDA:
            if modclass == MODULECLASS_MPI:
                prefix = MPI
            else:
                prefix = CUDA
            if tc_comp_info is None:
                raise EasyBuildError("No compiler available in toolchain %s used to install %s library %s v%s, "
                                     "which is required by the active module naming scheme.",
                                     ec['toolchain'], prefix, ec['name'].lower(), ec['version'])
            else:
                tc_comp_name, tc_comp_ver = tc_comp_info
                tc_comp_name = tc_comp_name.lower().split('-')[0]
                tc_comp_ver = self.det_twodigit_version({'version': tc_comp_ver})
                fullver = self.det_twodigit_version(ec)
                tc_cuda = det_toolchain_cuda(ec)
                subdir = tc_comp_name+tc_comp_ver
                if prefix == MPI and tc_cuda is not None:
                    tc_cuda_name = tc_cuda['name'].lower()
                    tc_cuda_fullver = self.det_twodigit_version(tc_cuda)
                    subdir = os.path.join(subdir, tc_cuda_name+tc_cuda_fullver)
                paths.append(os.path.join(prefix, subdir, ec['name'].lower()+fullver))

        if os.getenv('RSNT_ARCH') is None:
            raise EasyBuildError("Need to set architecture for MODULEPATH extension in $RSNT_ARCH")
        for i, path in enumerate(paths):
            paths[i] = os.path.join(os.getenv('RSNT_ARCH'), path)
        return paths

    def expand_toolchain_load(self, ec):
        """
        Determine whether load statements for a toolchain should be expanded to load statements for its dependencies.
        This is useful when toolchains are not exposed to users.
        """
        tc_elems = ec.toolchain.definition()
        # do not expand for compiler-only toolchains
        return not( len(tc_elems) == 1 and tc_elems.keys()[0] == 'COMPILER' )
