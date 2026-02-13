##
# Copyright 2013-2025 Ghent University
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
Support for BLAS and LAPACK libraries in NVHPC as toolchain linear algebra library.

Authors:

* Alex Domingo (Vrije Universiteit Brussel)
"""

from easybuild.tools.toolchain.linalg import LinAlg


class NVBLAS(LinAlg):
    """
    NVIDIA HPC SDK distributes its own BLAS and LAPACK libraries based on a custom OpenBLAS
    see https://docs.nvidia.com/hpc-sdk/compilers/hpc-compilers-user-guide/index.html#lapack-blas-and-ffts
    """
    BLAS_MODULE_NAME = ['NVHPC']
    BLAS_LIB = ['blas']
    BLAS_LIB_MT = ['blas']
    BLAS_FAMILY = 'OpenBLAS'

    LAPACK_IS_BLAS = False
    LAPACK_MODULE_NAME = ['NVHPC']
    LAPACK_LIB = ['lapack']
    LAPACK_FAMILY = 'LAPACK'
