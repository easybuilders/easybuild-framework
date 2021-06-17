##
# Copyright 2013-2021 Ghent University
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
Implementation of an example hierarchical module naming scheme.

:author: Kenneth Hoste (Ghent University)
:author: Markus Geimer (Forschungszentrum Juelich GmbH)
"""

import os
import re

from easybuild.toolchains.gcccore import GCCcore
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.module_naming_scheme.mns import ModuleNamingScheme
from easybuild.tools.module_naming_scheme.toolchain import det_toolchain_compilers, det_toolchain_mpi


CORE = 'Core'
COMPILER = 'Compiler'
MPI = 'MPI'
TOOLCHAIN = 'Toolchain'

MODULECLASS_COMPILER = 'compiler'
MODULECLASS_MPI = 'mpi'
MODULECLASS_TOOLCHAIN = 'toolchain'

GCCCORE = GCCcore.NAME

# note: names in keys are ordered alphabetically
COMP_NAME_VERSION_TEMPLATES = {
    # required for use of iccifort toolchain
    'icc,ifort': ('intel', '%(icc)s'),
    'iccifort': ('intel', '%(iccifort)s'),
    # required for use of intel-compilers toolchain (OneAPI compilers)
    'intel-compilers': ('intel', '%(intel-compilers)s'),
    # required for use of ClangGCC toolchain
    'Clang,GCC': ('Clang-GCC', '%(Clang)s-%(GCC)s'),
    # required for use of gcccuda toolchain, and for CUDA installed with GCC toolchain
    'CUDA,GCC': ('GCC-CUDA', '%(GCC)s-%(CUDA)s'),
    # required for use of iccifortcuda toolchain
    'CUDA,icc,ifort': ('intel-CUDA', '%(icc)s-%(CUDA)s'),
    'CUDA,iccifort': ('intel-CUDA', '%(iccifort)s-%(CUDA)s'),
    # required for CUDA installed with iccifort toolchain
    # need to use 'intel' here because 'iccifort' toolchain maps to 'intel' (see above)
    'CUDA,intel': ('intel-CUDA', '%(intel)s-%(CUDA)s'),
    # required for use of xlcxlf toolchain
    'xlc,xlf': ('xlcxlf', '%(xlc)s'),
}

# possible prefixes for Cray toolchain names
# example: CrayGNU, CrayCCE, cpeGNU, cpeCCE, ...;
# important for determining $MODULEPATH extensions in det_modpath_extensions,
# cfr. https://github.com/easybuilders/easybuild-framework/issues/3575
CRAY_TOOLCHAIN_NAME_PREFIXES = ('Cray', 'cpe')


class HierarchicalMNS(ModuleNamingScheme):
    """Class implementing an example hierarchical module naming scheme."""

    REQUIRED_KEYS = ['name', 'versionprefix', 'version', 'versionsuffix', 'toolchain', 'moduleclass']

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
        return os.path.join(ec['name'], self.det_full_version(ec))

    def det_full_version(self, ec):
        """Determine full version, taking into account version prefix/suffix."""
        # versionprefix is not always available (e.g., for toolchains)
        versionprefix = ec.get('versionprefix', '')
        return versionprefix + ec['version'] + ec['versionsuffix']

    def det_toolchain_compilers_name_version(self, tc_comps):
        """
        Determine toolchain compiler tag, for given list of compilers.
        """
        if tc_comps is None:
            # no compiler in toolchain, system toolchain
            res = None
        else:
            if len(tc_comps) > 0 and tc_comps[0]:
                comp_versions = dict([(comp['name'], self.det_full_version(comp)) for comp in tc_comps])
                comp_names = comp_versions.keys()
                key = ','.join(sorted(comp_names))
                if key in COMP_NAME_VERSION_TEMPLATES:
                    tc_comp_name, tc_comp_ver_tmpl = COMP_NAME_VERSION_TEMPLATES[key]
                    tc_comp_ver = tc_comp_ver_tmpl % comp_versions
                    # make sure that icc/ifort versions match (unless not existing as separate modules)
                    if tc_comp_name == 'intel' and comp_versions.get('icc') != comp_versions.get('ifort'):
                        raise EasyBuildError("Bumped into different versions for Intel compilers: %s", comp_versions)
                    res = (tc_comp_name, tc_comp_ver)
                else:
                    if len(tc_comps) == 1:
                        tc_comp = tc_comps[0]
                        res = (tc_comp['name'], self.det_full_version(tc_comp))
                    else:
                        raise EasyBuildError("Unknown set of toolchain compilers, module naming scheme needs work: %s",
                                             comp_names)
            else:
                res = None

        return res

    def det_module_subdir(self, ec):
        """
        Determine module subdirectory, relative to the top of the module path.
        This determines the separation between module names exposed to users, and what's part of the $MODULEPATH.
        Examples: Core, Compiler/GCC/4.8.3, MPI/GCC/4.8.3/OpenMPI/1.6.5
        """
        tc_comps = det_toolchain_compilers(ec)
        # determine prefix based on type of toolchain used
        if tc_comps is None:
            # no compiler in toolchain, system toolchain => Core module
            subdir = CORE
        elif tc_comps == [None]:
            # no info on toolchain compiler (cfr. Cray toolchains),
            # then use toolchain name/version
            subdir = os.path.join(TOOLCHAIN, ec.toolchain.name, ec.toolchain.version)
        else:
            tc_comp_name, tc_comp_ver = self.det_toolchain_compilers_name_version(tc_comps)
            tc_mpi = det_toolchain_mpi(ec)
            if tc_mpi is None:
                # compiler-only toolchain => Compiler/<compiler_name>/<compiler_version> namespace
                subdir = os.path.join(COMPILER, tc_comp_name, tc_comp_ver)
            else:
                # compiler-MPI toolchain => MPI/<comp_name>/<comp_version>/<MPI_name>/<MPI_version> namespace
                tc_mpi_fullver = self.det_full_version(tc_mpi)
                subdir = os.path.join(MPI, tc_comp_name, tc_comp_ver, tc_mpi['name'], tc_mpi_fullver)

        return subdir

    def det_module_symlink_paths(self, ec):
        """
        Determine list of paths in which symlinks to module files must be created.
        """
        # symlinks are not very useful in the context of a hierarchical MNS
        return []

    def det_modpath_extensions(self, ec):
        """
        Determine module path extensions, if any.
        Examples: Compiler/GCC/4.8.3 (for GCC/4.8.3 module), MPI/GCC/4.8.3/OpenMPI/1.6.5 (for OpenMPI/1.6.5 module)
        """
        modclass = ec['moduleclass']
        tc_comps = det_toolchain_compilers(ec)
        tc_comp_info = self.det_toolchain_compilers_name_version(tc_comps)

        # we consider the following to be compilers:
        # * has 'compiler' specified as moduleclass
        is_compiler = modclass == MODULECLASS_COMPILER
        # * CUDA, but only when not installed with 'system' toolchain (i.e. one or more toolchain compilers found)
        non_system_tc = tc_comps is not None
        non_system_cuda = ec['name'] == 'CUDA' and non_system_tc

        paths = []
        if is_compiler or non_system_cuda:
            # obtain list of compilers based on that extend $MODULEPATH in some way other than <name>/<version>
            extend_comps = []
            # exclude GCC for which <name>/<version> is used as $MODULEPATH extension
            excluded_comps = ['GCC']
            for comps in COMP_NAME_VERSION_TEMPLATES.keys():
                extend_comps.extend([comp for comp in comps.split(',') if comp not in excluded_comps])

            comp_name_ver = None
            if ec['name'] in extend_comps:
                for key in COMP_NAME_VERSION_TEMPLATES:
                    comp_names = key.split(',')
                    if ec['name'] in comp_names:
                        comp_name, comp_ver_tmpl = COMP_NAME_VERSION_TEMPLATES[key]
                        comp_versions = {ec['name']: self.det_full_version(ec)}
                        if ec['name'] == 'ifort':
                            # 'icc' key should be provided since it's the only one used in the template
                            comp_versions.update({'icc': self.det_full_version(ec)})

                        if non_system_tc:
                            tc_comp_name, tc_comp_ver = tc_comp_info
                            # Stick to name GCC for GCCcore
                            if tc_comp_name == GCCCORE:
                                tc_comp_name = 'GCC'
                            if tc_comp_name in comp_names:
                                # also provide toolchain version for non-system toolchains
                                comp_versions.update({tc_comp_name: tc_comp_ver})

                        comp_ver_keys = re.findall(r'%\((\w+)\)s', comp_ver_tmpl)
                        if all(comp_ver_key in comp_versions for comp_ver_key in comp_ver_keys):
                            comp_name_ver = [comp_name, comp_ver_tmpl % comp_versions]
                            break
            else:
                comp_name_ver = [ec['name'], self.det_full_version(ec)]

            if comp_name_ver is None:
                raise EasyBuildError("Required compilers not available in toolchain %s for %s v%s",
                                     ec['toolchain'], ec['name'], ec['version'])

            paths.append(os.path.join(COMPILER, *comp_name_ver))

        elif modclass == MODULECLASS_MPI:
            if tc_comp_info is None:
                raise EasyBuildError("No compiler available in toolchain %s used to install MPI library %s v%s, "
                                     "which is required by the active module naming scheme.",
                                     ec['toolchain'], ec['name'], ec['version'])
            else:
                tc_comp_name, tc_comp_ver = tc_comp_info
                fullver = self.det_full_version(ec)
                paths.append(os.path.join(MPI, tc_comp_name, tc_comp_ver, ec['name'], fullver))

        # special case for Cray toolchains
        elif modclass == MODULECLASS_TOOLCHAIN and tc_comp_info is None:
            if any(ec.name.startswith(x) for x in CRAY_TOOLCHAIN_NAME_PREFIXES):
                paths.append(os.path.join(TOOLCHAIN, ec.name, ec.version))

        return paths

    def expand_toolchain_load(self, ec=None):
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
