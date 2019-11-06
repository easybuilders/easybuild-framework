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
EasyBuild support for a iccifort+CUDA compiler toolchain.

:author: Ake Sandgren (HPC2N)
"""

from easybuild.toolchains.compiler.cuda import Cuda
from easybuild.toolchains.iccifort import IccIfort
from easybuild.tools.modules import get_software_root, get_software_version


class IccIfortCUDA(IccIfort, Cuda):
    """Compiler toolchain with iccifort and CUDA."""
    NAME = 'iccifortcuda'

    COMPILER_MODULE_NAME = IccIfort.COMPILER_MODULE_NAME + Cuda.COMPILER_CUDA_MODULE_NAME
    SUBTOOLCHAIN = IccIfort.NAME

    def is_dep_in_toolchain_module(self, name):
        """Check whether a specific software name is listed as a dependency in the module for this toolchain."""
        # icc & ifort do not need to be actual dependencies in iccifort module,
        # since they could also be installed together in a single directory.
        # Let IccIfort check that.
        res = IccIfort.is_dep_in_toolchain_module(self, name)

        # Also check for CUDA since this is IccIfortCUDA toolchain
        # as long as the corresponding $EBROOT* and $EBVERSION* environment variables are defined, it should be OK
        if not res:
            if name == 'CUDA':
                self.log.info("Checking whether %s is a toolchain component even though it is not a dependency", name)
                root = get_software_root(name)
                version = get_software_version(name)
                self.log.info("%s installation prefix: %s; version: %s", name, root, version)
                if root and version:
                    res = True
        return res
