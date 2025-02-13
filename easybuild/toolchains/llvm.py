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

* Davide Grassano (CECAM EPFL)
"""
from easybuild.toolchains.compiler.clang import Clang
from easybuild.toolchains.compiler.flang import Flang
from easybuild.tools.toolchain.toolchain import SYSTEM_TOOLCHAIN_NAME


TC_CONSTANT_LLVMTC = "LLVMtc"


class LLVMtc(Clang, Flang):
    """Compiler toolchain with Clang and GFortran compilers."""
    NAME = 'LLVMtc'
    COMPILER_MODULE_NAME = ['LLVMtc']
    COMPILER_FAMILY = TC_CONSTANT_LLVMTC
    SUBTOOLCHAIN = SYSTEM_TOOLCHAIN_NAME

    COMPILER_UNIQUE_OPTS = {
        **Clang.COMPILER_UNIQUE_OPTS,
        **Flang.COMPILER_UNIQUE_OPTS,
        'lld_undefined_version': (True, "-Wl,--undefined-version Allow unused version in version script"), # https://github.com/madler/zlib/issues/856
        'no_unused_args': (True, "-Wno-unused-command-line-argument avoid some failures in CMake correctly recognizing feature due to linker warnings"),
    }

    COMPILER_UNIQUE_OPTION_MAP = {
        **Clang.COMPILER_UNIQUE_OPTION_MAP,
        **Flang.COMPILER_UNIQUE_OPTION_MAP,
        'lld_undefined_version': ['-Wl,--undefined-version',],
        'no_unused_args': ['-Wno-unused-command-line-argument'],
    }

    COMPILER_C_OPTIONS = [
        'lld_undefined_version',
        'no_unused_args',
    ]

    COMPILER_F_OPTIONS = [
        # 'lld_undefined_version',
        # 'no_unused_args',
    ]
