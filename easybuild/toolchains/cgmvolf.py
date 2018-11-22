##
# Copyright 2013-2018 Ghent University
#
# This file is triple-licensed under GPLv2 (see below), MIT, and
# BSD three-clause licenses.
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
EasyBuild support for cgmvolf compiler toolchain (includes Clang, GFortran, MVAPICH2, OpenBLAS, LAPACK, ScaLAPACK and FFTW).

:author: Dmitri Gribenko (National Technical University of Ukraine "KPI")
"""

from easybuild.toolchains.cgmvapich2 import Cgmvapich2
from easybuild.toolchains.fft.fftw import Fftw
from easybuild.toolchains.linalg.openblas import OpenBLAS
from easybuild.toolchains.linalg.scalapack import ScaLAPACK


class Cgmvolf(Cgmvapich2, OpenBLAS, ScaLAPACK, Fftw):
    """Compiler toolchain with Clang, GFortran, MVAPICH2, OpenBLAS, ScaLAPACK and FFTW."""
    NAME = 'cgmvolf'
    SUBTOOLCHAIN = Cgmvapich2.NAME
