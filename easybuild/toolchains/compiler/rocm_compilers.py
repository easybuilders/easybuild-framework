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
EasyBuild support for ROCm Clang + Flang compiler toolchain.

Authors:

* Jan Reuter (jan@zyten.de)
* Kenneth Hoste (HPC-UGent)
"""
import os
import re

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import copy_file, read_file, write_file, which
from easybuild.tools.toolchain.toolchain import SYSTEM_TOOLCHAIN_NAME
from easybuild.toolchains.compiler.llvm_compilers import LLVMCompilers

TC_CONSTANT_ROCM = "ROCm"


class ROCmCompilers(LLVMCompilers):
    """Compiler toolchain with ROCm compilers (amdclang/amdclang++/amdflang)."""
    COMPILER_FAMILY = TC_CONSTANT_ROCM
    SUBTOOLCHAIN = SYSTEM_TOOLCHAIN_NAME

    COMPILER_CC = 'amdclang'
    COMPILER_CXX = 'amdclang++'

    COMPILER_F77 = 'amdflang'
    COMPILER_F90 = 'amdflang'
    COMPILER_FC = 'amdflang'

    def prepare_rpath_wrappers(self, *args, **kwargs):
        """
        Put RPATH wrapper scripts in place for compiler and linker commands

        Also do this for clang/clang++/flang commands, next to ROCm compiler commands (amdclang/amdclang++/amdflang)
        """
        super().prepare_rpath_wrappers(*args, **kwargs)

        amd_prefix = 'amd'
        compiler_cmds = [self.COMPILER_CC, self.COMPILER_CXX, self.COMPILER_F77, self.COMPILER_F90, self.COMPILER_FC]
        for compiler_cmd in [c for c in compiler_cmds if c.startswith(amd_prefix)]:
            wrapper = which(compiler_cmd)

            if not wrapper:
                raise EasyBuildError(f"{compiler_cmd} command not found!")
            elif not self.is_rpath_wrapper(wrapper):
                raise EasyBuildError(f"{wrapper} is not an RPATH compiler wrapper for {compiler_cmd}")
            else:
                parent_dir = os.path.dirname(wrapper)
                new_compiler_cmd = compiler_cmd[len(amd_prefix):]
                new_wrapper = os.path.join(parent_dir, new_compiler_cmd)
                copy_file(wrapper, new_wrapper)

                new_wrapper_txt = read_file(new_wrapper)
                regex = re.compile(re.escape(compiler_cmd), re.M)
                new_wrapper_txt = regex.sub(new_compiler_cmd, new_wrapper_txt)
                write_file(new_wrapper, new_wrapper_txt)
                self.log.info(f"Extra RPATH compiler wrapper created for {new_compiler_cmd}")
