##
# Copyright 2012-2024 Ghent University
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
EasyBuild support for iimkl compiler toolchain (includes Intel compilers (icc, ifort),
Intel Math Kernel Library (MKL), and Intel FFTW wrappers.

Authors:

* Stijn De Weirdt (Ghent University)
* Kenneth Hoste (Ghent University)
* Bart Oldeman (McGill University, Calcul Quebec, Compute Canada)
"""
import re

from easybuild.toolchains.iccifort import IccIfort
from easybuild.toolchains.intel_compilers import IntelCompilersToolchain
from easybuild.toolchains.fft.intelfftw import IntelFFTW
from easybuild.toolchains.linalg.intelmkl import IntelMKL
from easybuild.tools import LooseVersion


class Iimkl(IccIfort, IntelCompilersToolchain, IntelMKL, IntelFFTW):
    """
    Compiler toolchain with Intel compilers (icc/ifort),
    Intel Math Kernel Library (MKL) and Intel FFTW wrappers.
    """
    NAME = 'iimkl'
    # compiler-only subtoolchain can't be determined statically
    # since depends on toolchain version (see below),
    # so register both here as possible alternatives (which is taken into account elsewhere)
    SUBTOOLCHAIN = [(IntelCompilersToolchain.NAME, IccIfort.NAME)]
    OPTIONAL = True

    def __init__(self, *args, **kwargs):
        """Constructor for Iimkl toolchain class."""

        super(Iimkl, self).__init__(*args, **kwargs)

        # make sure a non-symbolic version (e.g., 'system') is used before making comparisons using LooseVersion
        if re.match('^[0-9]', self.version):
            # need to transform a version like '2018b' with something that is safe to compare with '2019'
            # comparing subversions that include letters causes TypeErrors in Python 3
            # 'a' is assumed to be equivalent with '.01' (January), and 'b' with '.07' (June)
            # (good enough for this purpose)
            self.iimkl_ver = self.version.replace('a', '.01').replace('b', '.07')

            if LooseVersion(self.iimkl_ver) >= LooseVersion('2020.12'):
                self.oneapi_gen = True
                self.SUBTOOLCHAIN = IntelCompilersToolchain.NAME
                self.COMPILER_MODULE_NAME = IntelCompilersToolchain.COMPILER_MODULE_NAME
            else:
                self.oneapi_gen = False
                self.SUBTOOLCHAIN = IccIfort.NAME
                self.COMPILER_MODULE_NAME = IccIfort.COMPILER_MODULE_NAME
        else:
            self.iimkl_ver = self.version
            self.oneapi_gen = False

    def is_deprecated(self):
        """Return whether or not this toolchain is deprecated."""

        deprecated = False

        # make sure a non-symbolic version (e.g., 'system') is used before making comparisons using LooseVersion
        if re.match('^[0-9]', str(self.iimkl_ver)):
            # iimkl toolchains older than iimkl/2019a are deprecated since EasyBuild v4.5.0
            if LooseVersion(self.iimkl_ver) < LooseVersion('2019'):
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
