# #
# Copyright 2012-2021 Ghent University
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
Support for Intel MPI as toolchain MPI library.

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""

import os

import easybuild.tools.toolchain as toolchain

from distutils.version import LooseVersion
from easybuild.toolchains.mpi.mpich2 import Mpich2
from easybuild.tools.toolchain.constants import COMPILER_FLAGS, COMPILER_VARIABLES
from easybuild.tools.toolchain.variables import CommandFlagList


TC_CONSTANT_INTELMPI = "IntelMPI"


class IntelMPI(Mpich2):
    """Intel MPI class"""
    MPI_MODULE_NAME = ['impi']
    MPI_FAMILY = TC_CONSTANT_INTELMPI

    MPI_LIBRARY_NAME = 'mpi'

    # echo "   1. Command line option:  -cc=<compiler_name>"
    # echo "   2. Environment variable: I_MPI_CC (current value '$I_MPI_CC')"
    # echo "   3. Environment variable: MPICH_CC (current value '$MPICH_CC')"
    # cxx -> cxx only
    # intel mpicc only support few compiler names (and eg -cc='icc -m32' won't work.)

    def _set_mpi_compiler_variables(self):
        """Add I_MPI_XXX variables to set."""

        if self.comp_family() == toolchain.INTELCOMP:
            self.MPI_COMPILER_MPICC = 'mpiicc'
            self.MPI_COMPILER_MPICXX = 'mpiicpc'
            self.MPI_COMPILER_MPIF77 = 'mpiifort'
            self.MPI_COMPILER_MPIF90 = 'mpiifort'
            self.MPI_COMPILER_MPIFC = 'mpiifort'

        # this needs to be done first, otherwise e.g., CC is set to MPICC if the usempi toolchain option is enabled
        for var, _ in COMPILER_VARIABLES:
            self.variables.nappend('I_MPI_%s' % var, str(self.variables[var].get_first()), var_class=CommandFlagList)

        super(IntelMPI, self)._set_mpi_compiler_variables()

    def _set_mpi_variables(self):
        """Set the other MPI variables"""

        super(IntelMPI, self)._set_mpi_variables()

        if (LooseVersion(self.version) >= LooseVersion('2019')):
            lib_dir = [os.path.join('intel64', 'lib', 'release')]
            incl_dir = [os.path.join('intel64', 'include')]

            for root in self.get_software_root(self.MPI_MODULE_NAME):
                self.variables.append_exists('MPI_LIB_STATIC', root, lib_dir,
                                             filename="lib%s.a" % self.MPI_LIBRARY_NAME)
                self.variables.append_exists('MPI_LIB_SHARED', root, lib_dir,
                                             filename="lib%s.so" % self.MPI_LIBRARY_NAME)
                self.variables.append_exists('MPI_LIB_DIR', root, lib_dir)
                self.variables.append_exists('MPI_INC_DIR', root, incl_dir)

    MPI_LINK_INFO_OPTION = '-show'

    def set_variables(self):
        """Intel MPI-specific updates to variables."""
        super(IntelMPI, self).set_variables()
        # add -mt_mpi flag to ensure linking against thread-safe MPI library when OpenMP is enabled
        if self.options.get('openmp', None) and self.options.get('usempi', None):
            mt_mpi_option = ['mt_mpi']
            for flags_var, _ in COMPILER_FLAGS:
                self.variables.nappend(flags_var, mt_mpi_option)
