##
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
##
"""
Support for OpenMPI as toolchain MPI library.

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
from distutils.version import LooseVersion

from easybuild.tools.toolchain.constants import COMPILER_VARIABLES, MPI_COMPILER_VARIABLES
from easybuild.tools.toolchain.mpi import Mpi
from easybuild.tools.toolchain.variables import CommandFlagList


TC_CONSTANT_OPENMPI = "OpenMPI"
TC_CONSTANT_MPI_TYPE_OPENMPI = "MPI_TYPE_OPENMPI"


class OpenMPI(Mpi):
    """OpenMPI MPI class"""
    MPI_MODULE_NAME = ['OpenMPI']
    MPI_FAMILY = TC_CONSTANT_OPENMPI
    MPI_TYPE = TC_CONSTANT_MPI_TYPE_OPENMPI

    MPI_LIBRARY_NAME = 'mpi'

    # version-dependent, so defined at runtime
    MPI_COMPILER_MPIF77 = None
    MPI_COMPILER_MPIF90 = None
    MPI_COMPILER_MPIFC = None

    # OpenMPI reads from CC etc env variables
    MPI_SHARED_OPTION_MAP = dict([('_opt_%s' % var, '') for var, _ in MPI_COMPILER_VARIABLES])

    MPI_LINK_INFO_OPTION = '-showme:link'

    def _set_mpi_compiler_variables(self):
        """Define MPI wrapper commands (depends on OpenMPI version) and add OMPI_* variables to set."""
        ompi_ver = self.get_software_version(self.MPI_MODULE_NAME)[0]
        # version-dependent, see http://www.open-mpi.org/faq/?category=mpi-apps#override-wrappers-after-v1.0
        if LooseVersion(ompi_ver) >= LooseVersion('1.7'):
            self.MPI_COMPILER_MPIF77 = 'mpifort'
            self.MPI_COMPILER_MPIF90 = 'mpifort'
            self.MPI_COMPILER_MPIFC = 'mpifort'
        else:
            self.MPI_COMPILER_MPIF77 = 'mpif77'
            self.MPI_COMPILER_MPIF90 = 'mpif90'
            self.MPI_COMPILER_MPIFC = 'mpif90'

        # this needs to be done first, otherwise e.g., CC is set to MPICC if the usempi toolchain option is enabled
        for var, _ in COMPILER_VARIABLES:
            self.variables.nappend('OMPI_%s' % var, str(self.variables[var].get_first()), var_class=CommandFlagList)

        super(OpenMPI, self)._set_mpi_compiler_variables()
