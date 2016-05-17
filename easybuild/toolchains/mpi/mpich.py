# #
# Copyright 2012-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
Support for MPICH as toolchain MPI library.

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Dmitri Gribenko (National Technical University of Ukraine "KPI")
"""
from distutils.version import LooseVersion

from easybuild.tools.toolchain.constants import COMPILER_VARIABLES, MPI_COMPILER_VARIABLES
from easybuild.tools.toolchain.mpi import Mpi
from easybuild.tools.toolchain.variables import CommandFlagList

TC_CONSTANT_MPICH = "MPICH"
TC_CONSTANT_MPI_TYPE_MPICH = "MPI_TYPE_MPICH"


class Mpich(Mpi):
    """MPICH MPI class"""
    MPI_MODULE_NAME = ['MPICH']
    MPI_FAMILY = TC_CONSTANT_MPICH
    MPI_TYPE = TC_CONSTANT_MPI_TYPE_MPICH

    MPI_LIBRARY_NAME = 'mpich'

    # version-dependent, so defined at runtime
    MPI_COMPILER_MPIF77 = None
    MPI_COMPILER_MPIF90 = None
    MPI_COMPILER_MPIFC = None

    # clear MPI wrapper command options
    MPI_SHARED_OPTION_MAP = dict([('_opt_%s' % var, '') for var, _ in MPI_COMPILER_VARIABLES])

    def _set_mpi_compiler_variables(self):
        """Set the MPICH_{CC, CXX, F77, F90, FC} variables."""
        # determine MPI wrapper commands to use based on MPICH version
        if self.MPI_COMPILER_MPIF77 is None and self.MPI_COMPILER_MPIF90 is None and self.MPI_COMPILER_MPIFC is None:
            # mpif77/mpif90 for MPICH v3.1.0 and earlier, mpifort for MPICH v3.1.2 and newer
            # see http://www.mpich.org/static/docs/v3.1/ vs http://www.mpich.org/static/docs/v3.1.2/
            if LooseVersion(self.get_software_version(self.MPI_MODULE_NAME)[0]) >= LooseVersion('3.1.2'):
                self.MPI_COMPILER_MPIF77 = 'mpif77'
                self.MPI_COMPILER_MPIF90 = 'mpifort'
                self.MPI_COMPILER_MPIFC = 'mpifort'
            else:
                self.MPI_COMPILER_MPIF77 = 'mpif77'
                self.MPI_COMPILER_MPIF90 = 'mpif90'
                self.MPI_COMPILER_MPIFC = 'mpif90'

        # this needs to be done first, otherwise e.g., CC is set to MPICC if the usempi toolchain option is enabled
        for var, _ in COMPILER_VARIABLES:
            self.variables.nappend('MPICH_%s' % var, str(self.variables[var].get_first()), var_class=CommandFlagList)

        super(Mpich, self)._set_mpi_compiler_variables()
