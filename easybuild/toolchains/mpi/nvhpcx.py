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
Support for NVHPCX as toolchain MPI library.

Authors:

* Alex Domingo (Vrije Universiteit Brussel)
"""
from easybuild.toolchains.mpi.openmpi import OpenMPI
from easybuild.tools.toolchain.constants import MPI_COMPILER_VARIABLES

TC_CONSTANT_OPENMPI = "OpenMPI"
TC_CONSTANT_MPI_TYPE_OPENMPI = "MPI_TYPE_OPENMPI"


class NVHPCX(OpenMPI):
    """NVHPCX MPI class"""
    MPI_MODULE_NAME = ['NVHPC']
    MPI_FAMILY = TC_CONSTANT_OPENMPI
    MPI_TYPE = TC_CONSTANT_MPI_TYPE_OPENMPI

    MPI_LIBRARY_NAME = 'mpi'

    # version-dependent, so defined at runtime
    MPI_COMPILER_MPIF77 = None
    MPI_COMPILER_MPIF90 = None
    MPI_COMPILER_MPIFC = None

    # OpenMPI reads from CC etc env variables
    MPI_SHARED_OPTION_MAP = {'_opt_%s' % var: '' for var, _ in MPI_COMPILER_VARIABLES}

    MPI_LINK_INFO_OPTION = '-showme:link'
