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
EasyBuild support for Intel compilers toolchain (icc, ifort)

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""
from distutils.version import LooseVersion

from easybuild.toolchains.compiler.inteliccifort import IntelIccIfort
from easybuild.toolchains.gcccore import GCCcore
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME


class IccIfort(IntelIccIfort):
    """Compiler toolchain with Intel compilers (icc/ifort)."""
    NAME = 'iccifort'
    # use GCCcore as subtoolchain rather than GCC, since two 'real' compiler-only toolchains don't mix well,
    # in particular in a hierarchical module naming scheme
    SUBTOOLCHAIN = [GCCcore.NAME, DUMMY_TOOLCHAIN_NAME]
    OPTIONAL = False

    def is_deprecated(self):
        """Return whether or not this toolchain is deprecated."""
        # iccifort toolchains older than iccifort/2016.1.150-* are deprecated
        if LooseVersion(self.version) < LooseVersion('2016.1'):
            deprecated = True
        else:
            deprecated = False

        return deprecated
