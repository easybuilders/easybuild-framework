##
# Copyright 2013-2018 Ghent University
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
EasyBuild support for foss compiler toolchain (includes GCC, OpenMPI, BLIS, LAPACK, ScaLAPACK and FFTW).

:author: Kenneth Hoste (Ghent University)
:author: Bart Oldeman (McGill University, Calcul Quebec, Compute Canada)
"""

from easybuild.toolchains.fft.fftw import Fftw
from easybuild.toolchains.gompi import Gompi
from easybuild.toolchains.linalg.blis import Blis
from easybuild.toolchains.linalg.lapack import Lapack
from easybuild.toolchains.linalg.scalapack import ScaLAPACK


class Goblf(Gompi, Blis, Lapack, ScaLAPACK, Fftw):
    """Compiler toolchain with GCC, OpenMPI, BLIS, LAPACK, ScaLAPACK and FFTW."""
    NAME = 'goblf'
    SUBTOOLCHAIN = Gompi.NAME
