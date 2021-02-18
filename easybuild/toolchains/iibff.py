##
# Copyright 2013-2021 Ghent University
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
EasyBuild support for iibff compiler toolchain (includes Intel compilers + MPI, BLIS, libFLAME, ScaLAPACK and FFTW).

:author: Kenneth Hoste (HPC-UGent)
"""

from easybuild.toolchains.iimpi import Iimpi
from easybuild.toolchains.linalg.blis import Blis
from easybuild.toolchains.linalg.flame import Flame
from easybuild.toolchains.linalg.scalapack import ScaLAPACK
from easybuild.toolchains.fft.fftw import Fftw


class Iibff(Iimpi, Blis, Flame, ScaLAPACK, Fftw):
    """Compiler toolchain with GCC, OpenMPI, BLIS, libFLAME, ScaLAPACK and FFTW."""
    NAME = 'iibff'
    SUBTOOLCHAIN = Iimpi.NAME
