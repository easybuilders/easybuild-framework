##
# Copyright 2014-2021 Ghent University
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
MPI support for Fujitsu MPI.

:author: Miguel Dias Costa (National University of Singapore)
"""
from easybuild.toolchains.compiler.fujitsu import FujitsuCompiler
from easybuild.toolchains.mpi.openmpi import TC_CONSTANT_OPENMPI, TC_CONSTANT_MPI_TYPE_OPENMPI
from easybuild.tools.toolchain.constants import COMPILER_VARIABLES, MPI_COMPILER_VARIABLES
from easybuild.tools.toolchain.mpi import Mpi
from easybuild.tools.toolchain.variables import CommandFlagList


class FujitsuMPI(Mpi):
    """Generic support for using Fujitsu compiler wrappers"""
    # MPI support
    # no separate module, Fujitsu compiler drivers always provide MPI support
    MPI_MODULE_NAME = None
    MPI_FAMILY = TC_CONSTANT_OPENMPI
    MPI_TYPE = TC_CONSTANT_MPI_TYPE_OPENMPI

    # OpenMPI reads from CC etc env variables
    MPI_SHARED_OPTION_MAP = dict([('_opt_%s' % var, '') for var, _ in MPI_COMPILER_VARIABLES])

    MPI_LINK_INFO_OPTION = '-showme:link'

    def _set_mpi_compiler_variables(self):
        """Define MPI wrapper commands and add OMPI_* variables to set."""
        self.MPI_COMPILER_MPICC = 'mpi' + FujitsuCompiler.COMPILER_CC
        self.MPI_COMPILER_MPICXX = 'mpi' + FujitsuCompiler.COMPILER_CXX
        self.MPI_COMPILER_MPIF77 = 'mpi' + FujitsuCompiler.COMPILER_F77
        self.MPI_COMPILER_MPIF90 = 'mpi' + FujitsuCompiler.COMPILER_F90
        self.MPI_COMPILER_MPIFC = 'mpi' + FujitsuCompiler.COMPILER_FC

        # this needs to be done first, otherwise e.g., CC is set to MPICC if the usempi toolchain option is enabled
        for var, _ in COMPILER_VARIABLES:
            self.variables.nappend('OMPI_%s' % var, str(self.variables[var].get_first()), var_class=CommandFlagList)

        super(FujitsuMPI, self)._set_mpi_compiler_variables()
