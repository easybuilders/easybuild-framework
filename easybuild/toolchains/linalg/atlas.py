##
# Copyright 2012-2022 Ghent University
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
Support for ATLAS as toolchain linear algebra library.

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""

from easybuild.tools.toolchain.linalg import LinAlg


TC_CONSTANT_ATLAS = 'ATLAS'


class Atlas(LinAlg):
    """
    Provides ATLAS BLAS/LAPACK support.
    LAPACK is a build dependency only
    """
    BLAS_MODULE_NAME = ['ATLAS']
    BLAS_LIB = ["cblas", "f77blas", "atlas"]
    BLAS_LIB_MT = ["ptcblas", "ptf77blas", "atlas"]
    BLAS_FAMILY = TC_CONSTANT_ATLAS

    LAPACK_MODULE_NAME = ['ATLAS']
    LAPACK_LIB = ['lapack']
    LAPACK_FAMILY = TC_CONSTANT_ATLAS
