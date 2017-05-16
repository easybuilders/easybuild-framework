##
# Copyright 2012-2017 Ghent University
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
EasyBuild support for intel compiler toolchain (includes Intel compilers (icc, ifort), Intel MPI,
Intel Math Kernel Library (MKL), and Intel FFTW wrappers).

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""

from easybuild.toolchains.iimpi import Iimpi
from easybuild.toolchains.fft.intelfftw import IntelFFTW
from easybuild.toolchains.linalg.intelmkl import IntelMKL


class Intel(Iimpi, IntelMKL, IntelFFTW):
    """
    Compiler toolchain with Intel compilers (icc/ifort), Intel MPI,
    Intel Math Kernel Library (MKL) and Intel FFTW wrappers.
    """
    NAME = 'intel'
    SUBTOOLCHAIN = Iimpi.NAME

    def alt_definitions(self):
        """
        Return list of alternate definitions for the 'intel' toolchain.
        """
        # Intel compilers, MPI and MKL can also be installed as a whole as Intel Parallel Studio XE (PSXE)
        intel_psxe_modname = 'intel-psxe'
        intel_psxe = {
            'COMPILER': [intel_psxe_modname],
            'MPI': [intel_psxe_modname],
            'BLAS': [intel_psxe_modname],
            'LAPACK': [intel_psxe_modname],
            'SCALAPACK': [intel_psxe_modname],
            'FFT': [intel_psxe_modname],
        }

        return [intel_psxe]
