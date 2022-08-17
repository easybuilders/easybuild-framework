##
# Copyright 2021-2022 Ghent University
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
Support for Intel compilers (icc, ifort) as toolchain compilers, version 2021.x and newer (oneAPI).

:author: Kenneth Hoste (Ghent University)
"""
import os

from distutils.version import LooseVersion

from easybuild.toolchains.compiler.inteliccifort import IntelIccIfort
from easybuild.tools.toolchain.compiler import Compiler


class IntelCompilers(IntelIccIfort):
    """
    Compiler class for Intel oneAPI compilers
    """

    COMPILER_MODULE_NAME = ['intel-compilers']
    COMPILER_UNIQUE_OPTS = dict(IntelIccIfort.COMPILER_UNIQUE_OPTS,
                                oneapi=(False, "Use oneAPI compilers icx/icpx/ifx instead of classic compilers"))

    def _set_compiler_vars(self):
        """Intel compilers-specific adjustments after setting compiler variables."""

        # skip IntelIccIfort._set_compiler_vars (no longer relevant for recent versions)
        Compiler._set_compiler_vars(self)

        root = self.get_software_root(self.COMPILER_MODULE_NAME)[0]
        version = self.get_software_version(self.COMPILER_MODULE_NAME)[0]

        libbase = os.path.join('compiler', version, 'linux')
        libpaths = [
            os.path.join(libbase, 'compiler', 'lib', 'intel64'),
        ]

        self.variables.append_subdirs("LDFLAGS", root, subdirs=libpaths)

    def set_variables(self):
        """Set the variables."""

        if self.options.get('oneapi', False):
            self.COMPILER_CXX = 'icpx'
            self.COMPILER_CC = 'icx'
            self.COMPILER_F77 = 'ifx'
            self.COMPILER_F90 = 'ifx'
            self.COMPILER_FC = 'ifx'
            self.COMPILER_MPICXX = 'mpiicpc -cxx=icpx'
            self.COMPILER_MPICC = 'mpiicc -cc=icx'
            self.COMPILER_MPIF77 = 'mpiifort -fc=ifx'
            self.COMPILER_MPIF90 = 'mpiifort -fc=ifx'
            self.COMPILER_MPIFC = 'mpiifort -fc=ifx'
            # fp-model source is not supported by icx but is equivalent to precise
            self.options.options_map['defaultprec'] = ['fp-speculation=safe', 'fp-model precise']
            if LooseVersion(self.get_software_version(self.COMPILER_MODULE_NAME)[0]) >= LooseVersion('2022'):
                self.options.options_map['defaultprec'].insert(0, 'ftz')
            # icx doesn't like -fp-model fast=1; fp-model fast is equivalent
            self.options.options_map['loose'] = ['fp-model fast']
            # fp-model fast=2 gives "warning: overriding '-ffp-model=fast=2' option with '-ffp-model=fast'"
            self.options.options_map['veryloose'] = ['fp-model fast']
            # recommended in porting guide
            self.options.options_map['openmp'] = ['fiopenmp']

        # skip IntelIccIfort.set_variables (no longer relevant for recent versions)
        Compiler.set_variables(self)
