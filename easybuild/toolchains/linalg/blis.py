##
# Copyright 2013-2022 Ghent University
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
Support for BLIS as toolchain linear algebra library.

:author: Kenneth Hoste (Ghent University)
:author: Bart Oldeman (McGill University, Calcul Quebec, Compute Canada)
:author: Sebastian Achilles (Forschungszentrum Juelich GmbH)
"""
from distutils.version import LooseVersion

from easybuild.tools.toolchain.linalg import LinAlg


TC_CONSTANT_BLIS = 'BLIS'


class Blis(LinAlg):
    """
    Trivial class, provides BLIS support.
    """
    BLAS_MODULE_NAME = ['BLIS']
    BLAS_LIB = ['blis']
    BLAS_FAMILY = TC_CONSTANT_BLIS

    def _set_blas_variables(self):
        """AMD's fork with version number > 2.1 names the MT library blis-mt, while vanilla BLIS doesn't."""

        # This assumes that AMD's BLIS has ver > 2.1 and vanilla BLIS < 2.1

        found_version = self.get_software_version(self.BLAS_MODULE_NAME)[0]
        if LooseVersion(found_version) > LooseVersion('2.1'):
            self.BLAS_LIB_MT = ['blis-mt']

        super(Blis, self)._set_blas_variables()
