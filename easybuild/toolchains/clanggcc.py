##
# Copyright 2013-2018 Ghent University
#
# This file is triple-licensed under GPLv2 (see below), MIT, and
# BSD three-clause licenses.
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
EasyBuild support for Clang + GCC compiler toolchain.  Clang uses libstdc++.  GFortran is used for Fortran code.

:author: Dmitri Gribenko (National Technical University of Ukraine "KPI")
"""

import os
from easybuild.toolchains.compiler.clang import Clang
from easybuild.toolchains.compiler.gcc import Gcc
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME


TC_CONSTANT_CLANGGCC = "ClangGCC"


class ClangGcc(Clang, Gcc):
    """Compiler toolchain with Clang and GFortran compilers."""
    NAME = 'ClangGCC'
    COMPILER_MODULE_NAME = ['Clang', 'GCC']
    COMPILER_FAMILY = TC_CONSTANT_CLANGGCC
    SUBTOOLCHAIN = DUMMY_TOOLCHAIN_NAME
