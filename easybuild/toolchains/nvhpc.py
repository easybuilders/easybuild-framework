##
# Copyright 2012-2025 Ghent University
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
EasyBuild support for NVHPC compiler toolchain with support for MPI

Authors:

* Bart Oldeman (McGill University, Calcul Quebec, Compute Canada)
* Andreas Herten (Forschungszentrum Juelich)
* Alex Domingo (Vrije Universiteit Brussel)
"""
from easybuild.toolchains.gcccore import GCCcore
from easybuild.toolchains.linalg.nvblas import NVBLAS
from easybuild.toolchains.linalg.nvscalapack import NVScaLAPACK
from easybuild.toolchains.mpi.nvhpcx import NVHPCX
from easybuild.toolchains.nvidia_compilers import NvidiaCompilersToolchain
from easybuild.tools.toolchain.toolchain import SYSTEM_TOOLCHAIN_NAME


class NVHPC(NvidiaCompilersToolchain, NVHPCX, NVBLAS, NVScaLAPACK):
    """Toolchain with Nvidia compilers and NVHPCX."""
    NAME = 'NVHPC'
    # GCCcore and system need to be listed as subtoolchains here only for legacy reasons;
    # recent NVHPC toolchains (versions >= 25.0) only have nvidia-compilers are subtoolchain
    SUBTOOLCHAIN = [NvidiaCompilersToolchain.NAME, GCCcore.NAME, SYSTEM_TOOLCHAIN_NAME]
