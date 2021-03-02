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
EasyBuild support for Intel compilers toolchain (icc, ifort)

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""
from distutils.version import LooseVersion
import re

from easybuild.toolchains.compiler.inteliccifort import IntelIccIfort
from easybuild.toolchains.gcccore import GCCcore
from easybuild.tools.modules import get_software_root, get_software_version
from easybuild.tools.toolchain.toolchain import SYSTEM_TOOLCHAIN_NAME

ICCIFORT_COMPONENTS = ('icc', 'ifort')


class IccIfort(IntelIccIfort):
    """Compiler toolchain with Intel compilers (icc/ifort)."""
    NAME = 'iccifort'
    # use GCCcore as subtoolchain rather than GCC, since two 'real' compiler-only toolchains don't mix well,
    # in particular in a hierarchical module naming scheme
    SUBTOOLCHAIN = [GCCcore.NAME, SYSTEM_TOOLCHAIN_NAME]
    OPTIONAL = False

    def is_deprecated(self):
        """Return whether or not this toolchain is deprecated."""

        # need to transform a version like '2016a' with something that is safe to compare with '2016.01'
        # comparing subversions that include letters causes TypeErrors in Python 3
        # 'a' is assumed to be equivalent with '.01' (January), and 'b' with '.07' (June) (good enough for this purpose)
        version = self.version.replace('a', '.01').replace('b', '.07')

        # iccifort toolchains older than iccifort/2016.1.150-* are deprecated
        # make sure a non-symbolic version (e.g., 'system') is used before making comparisons using LooseVersion
        if re.match('^[0-9]', version) and LooseVersion(version) < LooseVersion('2016.1'):
            deprecated = True
        else:
            deprecated = False

        return deprecated

    def is_dep_in_toolchain_module(self, name):
        """Check whether a specific software name is listed as a dependency in the module for this toolchain."""
        res = super(IccIfort, self).is_dep_in_toolchain_module(name)

        # icc & ifort do not need to be actual dependencies in iccifort module,
        # since they could also be installed together in a single directory;
        # as long as the corresponding $EBROOT* and $EBVERSION* environment variables are defined, it should be OK
        if not res:
            if name in ICCIFORT_COMPONENTS:
                self.log.info("Checking whether %s is a toolchain component even though it is not a dependency", name)
                root = get_software_root(name)
                version = get_software_version(name)
                self.log.info("%s installation prefix: %s; version: %s", name, root, version)
                if root and version:
                    res = True

        return res
