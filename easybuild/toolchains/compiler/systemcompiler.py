##
# Copyright 2019-2025 Ghent University
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
Support for system compiler.

Authors:

* Kenneth Hoste (Ghent University)
"""

from easybuild.tools.toolchain.compiler import Compiler


TC_CONSTANT_SYSTEM = 'SYSTEM'


class SystemCompiler(Compiler):
    """System compiler"""
    COMPILER_MODULE_NAME = []
    COMPILER_FAMILY = TC_CONSTANT_SYSTEM

    # The system compiler does not currently support even the shared options
    # (changing this would require updating set_minimal_build_env() of the toolchain class)
    COMPILER_UNIQUE_OPTS = None
    # only keep the rpath toolchainopt since we want to be able to disable it for
    # sanity checks in binary-only installations
    COMPILER_SHARED_OPTS = {k: Compiler.COMPILER_SHARED_OPTS[k] for k in ('rpath',)}
    COMPILER_UNIQUE_OPTION_MAP = None
    COMPILER_SHARED_OPTION_MAP = None
