##
# Copyright 2013-2018 Ghent University
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
Support for OpenBLAS as toolchain linear algebra library.

:author: Kenneth Hoste (Ghent University)
"""

from easybuild.tools.toolchain.linalg import LinAlg


TC_CONSTANT_OPENBLAS = 'OpenBLAS'


class OpenBLAS(LinAlg):
    """
    Trivial class, provides OpenBLAS support.
    """
    BLAS_MODULE_NAME = ['OpenBLAS']
    BLAS_LIB = ['openblas']
    BLAS_FAMILY = TC_CONSTANT_OPENBLAS

    LAPACK_MODULE_NAME = ['OpenBLAS']
    LAPACK_IS_BLAS = True
    LAPACK_FAMILY = TC_CONSTANT_OPENBLAS
