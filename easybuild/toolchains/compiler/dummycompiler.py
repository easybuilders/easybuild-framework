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
Support for dummy compiler.

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""

import easybuild.tools.systemtools as systemtools
from easybuild.tools.toolchain.compiler import Compiler


TC_CONSTANT_DUMMY = "DUMMY"


class DummyCompiler(Compiler):
    """Dummy compiler : try not to even use system gcc"""
    COMPILER_MODULE_NAME = []
    COMPILER_FAMILY = TC_CONSTANT_DUMMY

    COMPILER_CC = '%sCC' % TC_CONSTANT_DUMMY
    COMPILER_CXX = '%sCXX' % TC_CONSTANT_DUMMY

    COMPILER_F77 = '%sF77' % TC_CONSTANT_DUMMY
    COMPILER_F90 = '%sF90' % TC_CONSTANT_DUMMY
    COMPILER_FC = '%sFC' % TC_CONSTANT_DUMMY
