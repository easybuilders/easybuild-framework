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

from easybuild.tools.toolchain.linalg import LinAlg


class Acml(LinAlg):
    """
    Trivial class
        provides ACML BLAS and LAPACK
    """
    BLAS_MODULE_NAME = ['ACML']
    BLAS_LIB = ['acml_mv', 'acml']

    LAPACK_MODULE_NAME = ['ACML']
    LAPACK_IS_BLAS = True

    def _set_blas_variables(self):
        """Fix the map a bit"""
        if self.options.get('32bit', None):
            self.log.raiseException("_set_blas_variables: 32bit ACML not (yet) supported")

        interfacemap = {
                        "Intel": 'ifort',
                        "GCC": 'gfortran',
                       }
        root = self.get_software_root(self.BLAS_MODULE_NAME[0])  ## TODO: deal with multiple modules properly
        try:
            self.variables.append_exists('LDFLAGS', root, os.path.join(interfacemap[self.COMPILER_FAMILY], 'lib'))
        except:
            self.log.raiseException(("_set_blas_variables: ACML set LDFLAGS interfacemap unsupported combination"
                                     " with compiler family %s") % self.COMPILER_FAMILY)

        super(Acml, self)._set_blas_variables()

