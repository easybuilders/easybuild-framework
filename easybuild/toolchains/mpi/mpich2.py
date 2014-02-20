# #
# Copyright 2012-2014 Ghent University
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
# #
"""
Support for MPICH2 as toolchain MPI library.

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Jens Timmerman (Ghent University)
"""

from easybuild.tools.toolchain.mpi import Mpi
from easybuild.tools.toolchain.variables import CommandFlagList

TC_CONSTANT_MPICH2 = "MPICH2"
TC_CONSTANT_MPI_TYPE_MPICH = "MPI_TYPE_MPICH"


class Mpich2(Mpi):
    """MPICH2 MPI class"""
    MPI_MODULE_NAME = ["MPICH2"]
    MPI_FAMILY = TC_CONSTANT_MPICH2
    MPI_TYPE = TC_CONSTANT_MPI_TYPE_MPICH

    MPI_LIBRARY_NAME = 'mpich'

    # clear MPI wrapper command options
    MPI_SHARED_OPTION_MAP = {
                             '_opt_MPICC': '',
                             '_opt_MPICXX': '',
                             '_opt_MPIF77': '',
                             '_opt_MPIF90': '',
                             }

    def _set_mpi_compiler_variables(self):
        """Set the MPICH_{CC, CXX, F77, F90} variables."""

        # this needs to be done first, otherwise e.g., CC is set to MPICC if the usempi toolchain option is enabled
        for var in ["CC", "CXX", "F77", "F90"]:
            self.variables.nappend("MPICH_%s" % var, str(self.variables[var].get_first()), var_class=CommandFlagList)

        super(Mpich2, self)._set_mpi_compiler_variables()
