##
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
##
"""
Support for OpenMPI as toolchain MPI library.

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

from easybuild.tools.toolchain.mpi import Mpi
from easybuild.tools.toolchain.variables import CommandFlagList


TC_CONSTANT_OPENMPI = "OpenMPI"
TC_CONSTANT_MPI_TYPE_OPENMPI = "MPI_TYPE_OPENMPI"


class OpenMPI(Mpi):
    """OpenMPI MPI class"""
    MPI_MODULE_NAME = ["OpenMPI"]
    MPI_FAMILY = TC_CONSTANT_OPENMPI
    MPI_TYPE = TC_CONSTANT_MPI_TYPE_OPENMPI

    MPI_LIBRARY_NAME = 'mpi'

    ## OpenMPI reads from CC etc env variables
    MPI_SHARED_OPTION_MAP = {
                             '_opt_MPICC': '',
                             '_opt_MPICXX':'',
                             '_opt_MPICF77':'',
                             '_opt_MPICF90':'',
                             }

    MPI_LINK_INFO_OPTION = '-showme:link'

    def _set_mpi_compiler_variables(self):
        """Add OMPI_XXX variables to set."""

        # this needs to be done first, otherwise e.g., CC is set to MPICC if the usempi toolchain option is enabled
        for var in ["CC", "CXX", "F77", ("F90", "FC")]:
            if isinstance(var, basestring):
                source_var = var
                target_var = var
            else:
                source_var = var[0]
                target_var = var[1]
            self.variables.nappend("OMPI_%s" % target_var, str(self.variables[source_var].get_first()), var_class=CommandFlagList)

        super(OpenMPI, self)._set_mpi_compiler_variables()
