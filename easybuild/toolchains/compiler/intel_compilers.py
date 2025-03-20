##
# Copyright 2021-2025 Ghent University
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

Authors:

* Kenneth Hoste (Ghent University)
"""
import os

import easybuild.tools.systemtools as systemtools
from easybuild.toolchains.compiler.inteliccifort import IntelIccIfort
from easybuild.tools import LooseVersion
from easybuild.tools.toolchain.compiler import Compiler


class IntelCompilers(IntelIccIfort):
    """
    Compiler class for Intel oneAPI compilers
    """

    COMPILER_MODULE_NAME = ['intel-compilers']
    COMPILER_UNIQUE_OPTS = dict(IntelIccIfort.COMPILER_UNIQUE_OPTS)
    COMPILER_UNIQUE_OPTS.update({
        'oneapi': (None, "Use oneAPI compilers icx/icpx/ifx instead of classic compilers"),
        'oneapi_c_cxx': (None, "Use oneAPI C/C++ compilers icx/icpx instead of classic Intel C/C++ compilers "
                               "(auto-enabled for Intel compilers version 2022.2.0, or newer)"),
        'oneapi_fortran': (None, "Use oneAPI Fortran compiler ifx instead of classic Intel Fortran compiler "
                                 "(auto-enabled for Intel compilers version 2024.0.0, or newer)"),
    })

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

        oneapi = False

        # auto-enable use of oneAPI C/C++ compilers for sufficiently recent versions of Intel compilers
        comp_ver = self.get_software_version(self.COMPILER_MODULE_NAME)[0]
        if LooseVersion(comp_ver) >= LooseVersion('2022.2.0'):
            if LooseVersion(comp_ver) >= LooseVersion('2024.0.0'):
                if self.options.get('oneapi_fortran', None) is None:
                    self.options['oneapi_fortran'] = True
            if self.options.get('oneapi_c_cxx', None) is None:
                self.options['oneapi_c_cxx'] = True

        oneapi_tcopt = self.options.get('oneapi')
        if oneapi_tcopt:
            oneapi = True
            self.COMPILER_CXX = 'icpx'
            self.COMPILER_CC = 'icx'
            self.COMPILER_F77 = 'ifx'
            self.COMPILER_F90 = 'ifx'
            self.COMPILER_FC = 'ifx'

        # if both 'oneapi' and 'oneapi_*' are set, the latter are ignored
        elif oneapi_tcopt is None:
            if self.options.get('oneapi_c_cxx', False):
                oneapi = True
                self.COMPILER_CC = 'icx'
                self.COMPILER_CXX = 'icpx'

            if self.options.get('oneapi_fortran', False):
                oneapi = True
                self.COMPILER_F77 = 'ifx'
                self.COMPILER_F90 = 'ifx'
                self.COMPILER_FC = 'ifx'

        if oneapi:
            # fp-model source is not supported by icx but is equivalent to precise
            self.options.options_map['defaultprec'] = ['-fp-speculation=safe', '-fp-model precise']
            if LooseVersion(comp_ver) >= LooseVersion('2022'):
                self.options.options_map['defaultprec'].insert(0, '-ftz')
            # icx doesn't like -fp-model fast=1; fp-model fast is equivalent
            self.options.options_map['loose'] = ['-fp-model fast']
            # fp-model fast=2 gives "warning: overriding '-ffp-model=fast=2' option with '-ffp-model=fast'"
            self.options.options_map['veryloose'] = ['-fp-model fast']
            # recommended in porting guide: qopenmp, unlike fiopenmp, works for both classic and oneapi compilers
            # https://www.intel.com/content/www/us/en/developer/articles/guide/porting-guide-for-ifort-to-ifx.html
            self.options.options_map['openmp'] = ['-qopenmp']

            # -xSSE2 is not supported by Intel oneAPI compilers,
            # so use -march=x86-64 -mtune=generic when using optarch=GENERIC
            self.COMPILER_GENERIC_OPTION = {
                (systemtools.X86_64, systemtools.AMD): '-march=x86-64 -mtune=generic',
                (systemtools.X86_64, systemtools.INTEL): '-march=x86-64 -mtune=generic',
            }

        # skip IntelIccIfort.set_variables (no longer relevant for recent versions)
        Compiler.set_variables(self)
