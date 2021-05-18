##
# Copyright 2021-2021 Ghent University
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

from easybuild.toolchains.compiler.inteliccifort import IntelIccIfort
from easybuild.tools.toolchain.compiler import Compiler


class IntelCompilers(IntelIccIfort):
    """
    Compiler class for Intel oneAPI compilers
    """

    COMPILER_MODULE_NAME = ['intel-compilers']

    def _set_compiler_vars(self):
        """Intel compilers-specific adjustments after setting compiler variables."""

        # skip IntelIccIfort._set_compiler_vars (no longer relevant for recent versions)
        Compiler._set_compiler_vars(self)

        root = self.get_software_root(self.COMPILER_MODULE_NAME)[0]

        libpaths = [
            'lib',
            os.path.join('lib', 'x64'),
            os.path.join('compiler', 'lib', 'intel64_lin'),
        ]

        self.variables.append_subdirs("LDFLAGS", root, subdirs=libpaths)

    def set_variables(self):
        """Set the variables."""

        # skip IntelIccIfort.set_variables (no longer relevant for recent versions)
        Compiler.set_variables(self)
