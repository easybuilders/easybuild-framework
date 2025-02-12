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
EasyBuild support for intel compiler toolchain (includes Intel compilers (icc, ifort), Intel MPI).

Authors:

* Stijn De Weirdt (Ghent University)
* Kenneth Hoste (Ghent University)
"""
from easybuild.tools import LooseVersion
import re

from easybuild.toolchains.iccifort import IccIfort
from easybuild.toolchains.intel_compilers import IntelCompilersToolchain
from easybuild.toolchains.mpi.intelmpi import IntelMPI


class Iimpi(IccIfort, IntelCompilersToolchain, IntelMPI):
    """
    Compiler toolchain with Intel compilers (icc/ifort), Intel MPI.
    """
    NAME = 'iimpi'
    # compiler-only subtoolchain can't be determined statically
    # since depends on toolchain version (see below),
    # so register both here as possible alternatives (which is taken into account elsewhere)
    SUBTOOLCHAIN = [(IntelCompilersToolchain.NAME, IccIfort.NAME)]

    def __init__(self, *args, **kwargs):
        """Constructor for Iimpi toolchain class."""

        super(Iimpi, self).__init__(*args, **kwargs)

        # make sure a non-symbolic version (e.g., 'system') is used before making comparisons using LooseVersion
        if re.match('^[0-9]', self.version):
            # need to transform a version like '2018b' with something that is safe to compare with '2019'
            # comparing subversions that include letters causes TypeErrors in Python 3
            # 'a' is assumed to be equivalent with '.01' (January), and 'b' with '.07' (June)
            # (good enough for this purpose)
            self.iimpi_ver = self.version.replace('a', '.01').replace('b', '.07')

            if LooseVersion(self.iimpi_ver) >= LooseVersion('2020.12'):
                self.oneapi_gen = True
                self.SUBTOOLCHAIN = IntelCompilersToolchain.NAME
                self.COMPILER_MODULE_NAME = IntelCompilersToolchain.COMPILER_MODULE_NAME
            else:
                self.oneapi_gen = False
                self.SUBTOOLCHAIN = IccIfort.NAME
                self.COMPILER_MODULE_NAME = IccIfort.COMPILER_MODULE_NAME
        else:
            self.iimpi_ver = self.version
            self.oneapi_gen = False

    def is_deprecated(self):
        """Return whether or not this toolchain is deprecated."""

        deprecated = False

        # make sure a non-symbolic version (e.g., 'system') is used before making comparisons using LooseVersion
        if re.match('^[0-9]', str(self.iimpi_ver)):
            # iimpi toolchains older than iimpi/2019a are deprecated since EasyBuild v4.5.0
            if LooseVersion(self.iimpi_ver) < LooseVersion('2019'):
                deprecated = True

        return deprecated

    def is_dep_in_toolchain_module(self, *args, **kwargs):
        """Check whether a specific software name is listed as a dependency in the module for this toolchain."""
        if self.oneapi_gen:
            res = IntelCompilersToolchain.is_dep_in_toolchain_module(self, *args, **kwargs)
        else:
            res = IccIfort.is_dep_in_toolchain_module(self, *args, **kwargs)

        return res

    def _set_compiler_vars(self):
        """Intel compilers-specific adjustments after setting compiler variables."""
        if self.oneapi_gen:
            IntelCompilersToolchain._set_compiler_vars(self)
        else:
            IccIfort._set_compiler_vars(self)

    def set_variables(self):
        """Intel compilers-specific adjustments after setting compiler variables."""
        if self.oneapi_gen:
            IntelCompilersToolchain.set_variables(self)
        else:
            IccIfort.set_variables(self)
