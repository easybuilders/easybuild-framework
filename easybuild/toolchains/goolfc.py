##
# Copyright 2013-2014 Ghent University
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
EasyBuild support for goolfc compiler toolchain (includes GCC+CUDA, OpenMPI, OpenBLAS, LAPACK, ScaLAPACK and FFTW).

@author: Kenneth Hoste (Ghent University)
"""

from easybuild.toolchains.gcccuda import GccCUDA
from easybuild.toolchains.fft.fftw import Fftw
from easybuild.toolchains.linalg.openblas import OpenBLAS
from easybuild.toolchains.linalg.scalapack import ScaLAPACK
from easybuild.toolchains.mpi.openmpi import OpenMPI

class Goolfc(GccCUDA, OpenMPI, OpenBLAS, ScaLAPACK, Fftw):
    """Compiler toolchain with GCC+CUDA, OpenMPI, OpenBLAS, ScaLAPACK and FFTW."""
    NAME = 'goolfc'
