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
EasyBuild support for GCC compiler toolchain.

Authors:

* Kenneth Hoste (Ghent University)
"""
import re

from easybuild.toolchains.compiler.gcc import Gcc
from easybuild.tools import LooseVersion
from easybuild.tools.toolchain.toolchain import SYSTEM_TOOLCHAIN_NAME


class GCCcore(Gcc):
    """Compiler-only toolchain, including only GCC and binutils."""
    NAME = 'GCCcore'
    # Replace the default compiler module name with our own
    COMPILER_MODULE_NAME = [NAME]
    SUBTOOLCHAIN = SYSTEM_TOOLCHAIN_NAME
    # GCCcore is only guaranteed to be present in recent toolchains
    # for old versions of some toolchains (GCC, intel) it is not part of the hierarchy and hence optional
    OPTIONAL = True

    def is_deprecated(self):
        """Return whether or not this toolchain is deprecated."""
        # GCC toolchains older than GCC version 8.x are deprecated since EasyBuild v4.5.0
        # make sure a non-symbolic version (e.g., 'system') is used before making comparisons using LooseVersion
        if re.match('^[0-9]', self.version) and LooseVersion(self.version) < LooseVersion('8.0'):
            deprecated = True
        else:
            deprecated = False

        return deprecated
