##
# Copyright 2012-2018 Ghent University
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
Support for ACML (AMD Core Math Library) as toolchain linear algebra library.

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""

import os
from distutils.version import LooseVersion

from easybuild.toolchains.compiler.inteliccifort import TC_CONSTANT_INTELCOMP
from easybuild.toolchains.compiler.gcc import TC_CONSTANT_GCC
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.toolchain.linalg import LinAlg


TC_CONSTANT_ACML = 'ACML'


class Acml(LinAlg):
    """
    Provides ACML BLAS/LAPACK support.
    """
    BLAS_MODULE_NAME = ['ACML']
    # full list of libraries is highly dependent on ACML version and toolchain compiler (ifort, gfortran, ...)
    BLAS_LIB = ['acml']
    BLAS_LIB_MT = ['acml_mp']
    BLAS_FAMILY = TC_CONSTANT_ACML

    # is completed in _set_blas_variables, depends on compiler used
    BLAS_LIB_DIR = []

    LAPACK_MODULE_NAME = ['ACML']
    LAPACK_IS_BLAS = True
    LAPACK_FAMILY = TC_CONSTANT_ACML

    ACML_SUBDIRS_MAP = {
        TC_CONSTANT_INTELCOMP: ['ifort64', 'ifort64_mp'],
        TC_CONSTANT_GCC: ['gfortran64', 'gfortran64_mp'],
    }

    def __init__(self, *args, **kwargs):
        """Toolchain constructor."""
        class_constants = kwargs.setdefault('class_constants', [])
        class_constants.extend(['BLAS_LIB', 'BLAS_LIB_MT'])
        super(Acml, self).__init__(*args, **kwargs)

    def _set_blas_variables(self):
        """Fix the map a bit"""
        if self.options.get('32bit', None):
            raise EasyBuildError("_set_blas_variables: 32bit ACML not (yet) supported")
        try:
            for root in self.get_software_root(self.BLAS_MODULE_NAME):
                subdirs = self.ACML_SUBDIRS_MAP[self.COMPILER_FAMILY]
                self.BLAS_LIB_DIR = [os.path.join(x, 'lib') for x in subdirs]
                self.variables.append_exists('LDFLAGS', root, self.BLAS_LIB_DIR, append_all=True)
                incdirs = [os.path.join(x, 'include') for x in subdirs]
                self.variables.append_exists('CPPFLAGS', root, incdirs, append_all=True)
        except:
            raise EasyBuildError("_set_blas_variables: ACML set LDFLAGS/CPPFLAGS unknown entry in ACML_SUBDIRS_MAP "
                                 "with compiler family %s", self.COMPILER_FAMILY)

        # version before 5.x still featured the acml_mv library
        ver = self.get_software_version(self.BLAS_MODULE_NAME)[0]
        if LooseVersion(ver) < LooseVersion("5"):
            self.BLAS_LIB.insert(0, "acml_mv")
            self.BLAS_LIB_MT.insert(0, "acml_mv")

        super(Acml, self)._set_blas_variables()

