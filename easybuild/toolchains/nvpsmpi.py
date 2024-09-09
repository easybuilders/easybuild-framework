##
# Copyright 2016-2024 Ghent University
# Copyright 2016-2024 Forschungszentrum Juelich
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be),
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
EasyBuild support for nvsmpi compiler toolchain (includes NVHPC and ParaStationMPI).

Authors:

* Robert Mijakovic <robert.mijakovic@lxp.lu> (LuxProvide)
"""

from easybuild.toolchains.nvhpc import NVHPCToolchain
from easybuild.toolchains.mpi.psmpi import Psmpi


# Order matters!
class NVpsmpi(NVHPCToolchain, Psmpi):
    """Compiler toolchain with NVHPC and ParaStationMPI."""
    NAME = 'nvpsmpi'
    SUBTOOLCHAIN = NVHPCToolchain.NAME
