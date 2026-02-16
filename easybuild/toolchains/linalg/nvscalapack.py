##
# Copyright 2012-2025 Ghent University
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
Support for ScaLAPACK libraries in NVHPC as toolchain linear algebra library.

Authors:

* Alex Domingo (Vrije Universiteit Brussel)
"""

from easybuild.tools.toolchain.linalg import LinAlg


class NVScaLAPACK(LinAlg):
    """
    NVIDIA HPC SDK distributes its own ScaLAPACK libraries
    see https://docs.nvidia.com/hpc-sdk/compilers/hpc-compilers-user-guide/index.html#linking-with-scalapack
    """
    # the following emulates the `-Mscalapack` macro as defined in $NVHPC/compilers/bin/rcfiles/lin86rc
    SCALAPACK_MODULE_NAME = ['NVHPC']
    SCALAPACK_LIB_MAP = {'lp64_sc': '_lp64'}
    SCALAPACK_LIB = ["scalapack%(lp64_sc)s", "lapack%(lp64_sc)s", "blas%(lp64_sc)s"]
    SCALAPACK_LIB_MT = ["scalapack%(lp64_sc)s", "lapack%(lp64_sc)s", "blas%(lp64_sc)s"]
    SCALAPACK_REQUIRES = ['LIBLAPACK', 'LIBBLAS']

    def _set_scalapack_variables(self):
        if self.options.get('i8', None):
            # ilp64/i8
            self.SCALAPACK_LIB_MAP.update({"lp64_sc": '_ilp64'})

        super()._set_scalapack_variables()

    def _set_blacs_variables(self):
        """Skip setting BLACS related variables"""
        pass
