##
# Copyright 2012-2023 Ghent University
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
EasyBuild support for intel compiler toolchain (includes Intel compilers (icc, ifort), Intel MPI,
Intel Math Kernel Library (MKL), and Intel FFTW wrappers).

Authors:

* Stijn De Weirdt (Ghent University)
* Kenneth Hoste (Ghent University)
"""
import re

from easybuild.toolchains.iimpi import Iimpi
from easybuild.toolchains.iimkl import Iimkl
from easybuild.toolchains.fft.intelfftw import IntelFFTW
from easybuild.toolchains.linalg.intelmkl import IntelMKL
from easybuild.tools import LooseVersion


class Intel(Iimpi, IntelMKL, IntelFFTW):
    """
    Compiler toolchain with Intel compilers (icc/ifort), Intel MPI,
    Intel Math Kernel Library (MKL) and Intel FFTW wrappers.
    """
    NAME = 'intel'
    SUBTOOLCHAIN = [Iimpi.NAME, Iimkl.NAME]

    def is_deprecated(self):
        """Return whether or not this toolchain is deprecated."""
        # need to transform a version like '2018b' with something that is safe to compare with '2019'
        # comparing subversions that include letters causes TypeErrors in Python 3
        # 'a' is assumed to be equivalent with '.01' (January), and 'b' with '.07' (June) (good enough for this purpose)
        version = self.version.replace('a', '.01').replace('b', '.07')

        # intel toolchains older than intel/2019a are deprecated since EasyBuild v4.5.0
        # make sure a non-symbolic version (e.g., 'system') is used before making comparisons using LooseVersion
        if re.match('^[0-9]', version) and LooseVersion(version) < LooseVersion('2019'):
            deprecated = True
        else:
            deprecated = False

        return deprecated
