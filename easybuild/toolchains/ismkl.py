##
# Copyright 2012-2018 Ghent University
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
EasyBuild support for ismkl compiler toolchain (includes Intel compilers (icc, ifort), MPICH2 (ScaleMP MPI),
Intel Math Kernel Library (MKL), and Intel FFTW wrappers.

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""

from easybuild.toolchains.iccifort import IccIfort
from easybuild.toolchains.iimkl import Iimkl
from easybuild.toolchains.fft.intelfftw import IntelFFTW
from easybuild.toolchains.mpi.mpich2 import Mpich2
from easybuild.toolchains.linalg.intelmkl import IntelMKL


class Ismkl(IccIfort, Mpich2, IntelMKL, IntelFFTW):
    """
    Compiler toolchain with Intel compilers (icc/ifort), MPICH2 (ScaleMP MPI),
    Intel Math Kernel Library (MKL) and Intel FFTW wrappers.
    """
    NAME = 'ismkl'
    SUBTOOLCHAIN = [IccIfort.NAME, Iimkl.NAME]
