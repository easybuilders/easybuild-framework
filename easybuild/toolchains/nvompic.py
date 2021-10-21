##
# Copyright 2016-2021 Ghent University
# Copyright 2016-2021 Forschungszentrum Juelich
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
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
EasyBuild support for nvompic compiler toolchain (includes NVHPC and OpenMPI, and CUDA as dependency).

:author: Damian Alvarez (Forschungszentrum Juelich)
:author: Sebastian Achilles (Forschungszentrum Juelich)
"""

from easybuild.toolchains.nvhpc import NVHPCToolchain
# We pull in MPI and CUDA at once so this maps nicely to HMNS
from easybuild.toolchains.mpi.openmpi import OpenMPI
from easybuild.toolchains.compiler.cuda import Cuda


# Order matters!
class NVompic(NVHPCToolchain, Cuda, OpenMPI):
    """Compiler toolchain with NVHPC and OpenMPI, with CUDA as dependency."""
    NAME = 'nvompic'
    SUBTOOLCHAIN = NVHPCToolchain.NAME
