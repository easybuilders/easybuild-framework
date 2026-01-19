##
# Copyright 2026 Ghent University
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
"""Compatibility module such that compiler.nvhpc.NVHPC and compiler.compiler.nvidia_compilers.NvidiaCompilers
can be used interchangeably
"""

import abc
from easybuild.base import fancylogger
from easybuild.toolchains.compiler.nvidia_compilers import NvidiaCompilers

_log = fancylogger.getLogger('compiler.nvhpc', fname=False)
_log.deprecated("easybuild.toolchains.compiler.nvhpc was replaced by "
                "easybuild.toolchains.compiler.nvidia_compilers in EasyBuild 5.2.0", '6.0')


# Former name used in EasyBuild until 5.2.0, now a DEPRECATED alias
class NVHPC(metaclass=abc.ABCMeta):  # pylint: disable=too-few-public-methods
    """DEPRECATED alias for NvidiaCompilers."""
    def __new__(cls, *args, **kwargs):
        if cls is NVHPC:
            inst = NvidiaCompilers(*args, **kwargs)
            inst.log.deprecated(
                "easybuild.toolchains.compiler.nvhpc was replaced by "
                "easybuild.toolchains.compiler.nvidia_compilers in EasyBuild 5.2.0", '6.0')
            return inst
        return super().__new__(cls)


NVHPC.register(NvidiaCompilers)

# TODO EasyBuild 6.0: Remove NVHPC name from NvidiaCompilers.COMPILER_MODULE_NAME
