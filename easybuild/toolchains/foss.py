##
# Copyright 2013-2019 Ghent University
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
EasyBuild support for foss compiler toolchain (includes GCC, OpenMPI, OpenBLAS, LAPACK, ScaLAPACK and FFTW).

:author: Kenneth Hoste (Ghent University)
"""
from distutils.version import LooseVersion

from easybuild.toolchains.gompi import Gompi
from easybuild.toolchains.golf import Golf
from easybuild.toolchains.fft.fftw import Fftw
from easybuild.toolchains.linalg.openblas import OpenBLAS
from easybuild.toolchains.linalg.scalapack import ScaLAPACK


class Foss(Gompi, OpenBLAS, ScaLAPACK, Fftw):
    """Compiler toolchain with GCC, OpenMPI, OpenBLAS, ScaLAPACK and FFTW."""
    NAME = 'foss'
    SUBTOOLCHAIN = [Gompi.NAME, Golf.NAME]

    def is_deprecated(self):
        """Return whether or not this toolchain is deprecated."""
        # need to transform a version like '2016a' with something that is safe to compare with '2000'
        # comparing subversions that include letters causes TypeErrors in Python 3
        # 'a' is assumed to be equivalent with '.01' (January), and 'b' with '.07' (June) (good enough for this purpose)
        version = self.version.replace('a', '.01').replace('b', '.07')

        # foss toolchains older than foss/2016a are deprecated
        # take into account that foss/2016.x is always < foss/2016a according to LooseVersion;
        # foss/2016.01 & co are not deprecated yet...
        foss_ver = LooseVersion(version)
        if foss_ver < LooseVersion('2016.01'):
            deprecated = True
        else:
            deprecated = False

        return deprecated
