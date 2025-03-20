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
EasyBuild support for Fujitsu Compiler toolchain.

Authors:

* Miguel Dias Costa (National University of Singapore)
"""
from easybuild.toolchains.compiler.fujitsu import FujitsuCompiler
from easybuild.tools.toolchain.toolchain import SYSTEM_TOOLCHAIN_NAME


class FCC(FujitsuCompiler):
    """Compiler toolchain with Fujitsu Compiler."""
    NAME = 'FCC'
    SUBTOOLCHAIN = SYSTEM_TOOLCHAIN_NAME
    OPTIONAL = False

    # override in order to add an exception for the Fujitsu lang/tcsds module
    def _add_dependency_cpp_headers(self, dep_root, extra_dirs=None):
        """
        Append prepocessor paths for given dependency root directory
        """
        # skip Fujitsu's 'lang/tcsds' module, including the top level include breaks vectorization in clang mode
        if "tcsds" not in dep_root:
            super()._add_dependency_cpp_headers(dep_root, extra_dirs=extra_dirs)
