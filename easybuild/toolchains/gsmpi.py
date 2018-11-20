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
EasyBuild support for gsmpi compiler toolchain (includes GCC and SpectrumMPI).

:author: Kenneth Hoste (Ghent University)
:author: Alan O'Cais (Juelich Supercomputing Centre)
"""

from easybuild.toolchains.gcc import GccToolchain
from easybuild.toolchains.mpi.spectrummpi import SpectrumMPI


class Gsmpi(GccToolchain, SpectrumMPI):
    """Compiler toolchain with GCC and SpectrumMPI."""
    NAME = 'gsmpi'
    SUBTOOLCHAIN = GccToolchain.NAME
