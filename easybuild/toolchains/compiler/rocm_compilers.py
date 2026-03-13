##
# Copyright 2013-2025 Ghent University
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
EasyBuild support for Clang + Flang compiler toolchain.

Authors:

* Jan Reuter (jan@zyten.de)
"""

from easybuild.tools.toolchain.toolchain import SYSTEM_TOOLCHAIN_NAME
from easybuild.toolchains.compiler.llvm_compilers import LLVMCompilers

TC_CONSTANT_ROCM = "ROCm"


class ROCmCompilers(LLVMCompilers):
    """Compiler toolchain with ROCm compilers (clang/flang)."""
    COMPILER_FAMILY = TC_CONSTANT_ROCM
    SUBTOOLCHAIN = SYSTEM_TOOLCHAIN_NAME

    # We use clang, clang++ and flang for now (instead of amdclang/amdclang++/amdflang).
    # These are simply inherited from LLVMCompilers, so we don't need to respecify them
    # See https://github.com/easybuilders/easybuild-framework/pull/5099#issuecomment-4054952860
