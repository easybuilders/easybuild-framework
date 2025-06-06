# #
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
# #
"""
Support for Parastation MPI as toolchain MPI library.

Authors:

* Kenneth Hoste (Ghent University)
"""

from easybuild.toolchains.mpi.mpich import Mpich


class Psmpi(Mpich):
    """Parastation MPI class"""
    MPI_MODULE_NAME = ['psmpi']

    def _set_mpi_compiler_variables(self):
        """Set the MPICH_{CC, CXX, F77, F90, FC} variables."""

        # hardwire MPI wrapper commands (otherwise Mpich parent class sets them based on MPICH version)
        self.MPI_COMPILER_MPIF77 = 'mpif77'
        self.MPI_COMPILER_MPIF90 = 'mpif90'
        self.MPI_COMPILER_MPIFC = 'mpif90'

        super()._set_mpi_compiler_variables()
