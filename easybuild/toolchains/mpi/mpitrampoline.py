##
# Copyright 2022-2025 Ghent University
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
Support for MPItrampoline as toolchain MPI library.

Authors:

* Alan O'Cais (CECAM)
"""

from easybuild.tools.toolchain.constants import COMPILER_VARIABLES, MPI_COMPILER_VARIABLES
from easybuild.tools.toolchain.mpi import Mpi
from easybuild.tools.toolchain.variables import CommandFlagList


TC_CONSTANT_MPITRAMPOLINE = "MPItrampoline"
TC_CONSTANT_MPI_TYPE_MPITRAMPOLINE = "MPI_TYPE_MPITRAMPOLINE"


class MPItrampoline(Mpi):
    """MPItrampoline MPI class"""
    MPI_MODULE_NAME = ['MPItrampoline']
    MPI_FAMILY = TC_CONSTANT_MPITRAMPOLINE
    MPI_TYPE = TC_CONSTANT_MPI_TYPE_MPITRAMPOLINE

    MPI_LIBRARY_NAME = 'mpi'

    # May be version-dependent, so defined at runtime
    MPI_COMPILER_MPIF77 = None
    MPI_COMPILER_MPIF90 = None
    MPI_COMPILER_MPIFC = None

    # MPItrampoline reads from CC etc env variables
    MPI_SHARED_OPTION_MAP = {'_opt_%s' % var: '' for var, _ in MPI_COMPILER_VARIABLES}

    MPI_LINK_INFO_OPTION = '-showme:link'

    def __init__(self, *args, **kwargs):
        """Toolchain constructor"""
        super(MPItrampoline, self).__init__(*args, **kwargs)

    def _set_mpi_compiler_variables(self):
        """Define MPI wrapper commands and add MPITRAMPOLINE_* variables to set."""

        self.MPI_COMPILER_MPIF77 = 'mpifort'
        self.MPI_COMPILER_MPIF90 = 'mpifort'
        self.MPI_COMPILER_MPIFC = 'mpifort'

        # this needs to be done first, otherwise e.g., CC is set to MPICC if the usempi toolchain option is enabled
        for var, _ in COMPILER_VARIABLES:
            self.variables.nappend(
                'MPITRAMPOLINE_%s' % var, str(self.variables[var].get_first()),
                var_class=CommandFlagList
            )

        super(MPItrampoline, self)._set_mpi_compiler_variables()
