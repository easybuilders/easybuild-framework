##
# Copyright 2015 Bart Oldeman
#
# This file is triple-licensed under GPLv2 (see below), MIT, and
# BSD three-clause licenses.
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
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
EasyBuild support for NVHPC compiler toolchain.

:author: Bart Oldeman (McGill University, Calcul Quebec, Compute Canada)
:author: Andreas Herten (Forschungszentrum Juelich)
"""

from easybuild.toolchains.compiler.nvhpc import NVHPC
from easybuild.toolchains.gcccore import GCCcore
from easybuild.tools.toolchain.toolchain import SYSTEM_TOOLCHAIN_NAME


class NVHPCToolchain(NVHPC):
    """Simple toolchain with just the NVIDIA HPC SDK compilers."""
    NAME = 'NVHPC'
    # use GCCcore as subtoolchain rather than GCC, since two 'real' compiler-only toolchains don't mix well,
    # in particular in a hierarchical module naming scheme
    SUBTOOLCHAIN = [GCCcore.NAME, SYSTEM_TOOLCHAIN_NAME]
    OPTIONAL = False
