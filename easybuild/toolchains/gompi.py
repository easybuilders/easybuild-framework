##
# Copyright 2012-2021 Ghent University
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
EasyBuild support for gompi compiler toolchain (includes GCC and OpenMPI).

:author: Kenneth Hoste (Ghent University)
"""
from distutils.version import LooseVersion
import re

from easybuild.toolchains.gcc import GccToolchain
from easybuild.toolchains.mpi.openmpi import OpenMPI


class Gompi(GccToolchain, OpenMPI):
    """Compiler toolchain with GCC and OpenMPI."""
    NAME = 'gompi'
    SUBTOOLCHAIN = GccToolchain.NAME

    def is_deprecated(self):
        """Return whether or not this toolchain is deprecated."""
        # need to transform a version like '2016a' with something that is safe to compare with '2000'
        # comparing subversions that include letters causes TypeErrors in Python 3
        # 'a' is assumed to be equivalent with '.01' (January), and 'b' with '.07' (June) (good enough for this purpose)
        version = self.version.replace('a', '.01').replace('b', '.07')

        deprecated = False

        # make sure a non-symbolic version (e.g., 'system') is used before making comparisons using LooseVersion
        if re.match('^[0-9]', version):
            gompi_ver = LooseVersion(version)
            # deprecate oldest gompi toolchains (versions 1.x)
            if gompi_ver < LooseVersion('2000'):
                deprecated = True
            # gompi toolchains older than gompi/2016a are deprecated
            # take into account that gompi/2016.x is always < gompi/2016a according to LooseVersion;
            # gompi/2016.01 & co are not deprecated yet...
            elif gompi_ver < LooseVersion('2016.01'):
                deprecated = True

        return deprecated
