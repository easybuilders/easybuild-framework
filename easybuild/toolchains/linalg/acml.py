##
# Copyright 2012 Ghent University
# Copyright 2012 Stijn De Weirdt
# Copyright 2012 Kenneth Hoste
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
Support for ACML (AMD Core Math Library) as toolchain linear algebra library.
"""

import os
from distutils.version import LooseVersion

from easybuild.toolchains.compiler.inteliccifort import TC_CONSTANT_INTELCOMP
from easybuild.toolchains.compiler.gcc import TC_CONSTANT_GCC
from easybuild.tools.toolchain.linalg import LinAlg


class Acml(LinAlg):
    """
    Trivial class
        provides ACML BLAS and LAPACK
    """
    BLAS_MODULE_NAME = ['ACML']
    # full list of libraries is highly dependent on ACML version and toolchain compiler (ifort, gfortran, ...)
    BLAS_LIB = ['acml']
    BLAS_LIB_MT = ['acml_mp']

    LAPACK_MODULE_NAME = ['ACML']
    LAPACK_IS_BLAS = True

    def _set_blas_variables(self):
        """Fix the map a bit"""
        if self.options.get('32bit', None):
            self.log.raiseException("_set_blas_variables: 32bit ACML not (yet) supported")

        interfacemap = {
                        TC_CONSTANT_INTELCOMP: 'ifort',
                        TC_CONSTANT_GCC: 'gfortran',
                       }
        try:
            for root in self.get_software_root(self.BLAS_MODULE_NAME):
                self.variables.append_exists('LDFLAGS', root, [os.path.join(interfacemap[self.COMPILER_FAMILY], 'lib')])
        except:
            self.log.raiseException(("_set_blas_variables: ACML set LDFLAGS interfacemap unsupported combination"
                                     " with compiler family %s") % self.COMPILER_FAMILY)

        # version before 5.x still featured the acml_mv library
        ver = self.get_software_version(self.BLAS_MODULE_NAME)[0]
        if LooseVersion(ver) < LooseVersion("5"):
            self.BLAS_LIB.insert(0, "acml_mv")
            self.BLAS_LIB_MT.insert(0, "acml_mv")

        super(Acml, self)._set_blas_variables()

