##
# Copyright 2012-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/easybuild
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
Support for Intel compilers (icc, ifort) as toolchain compilers.

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

from distutils.version import LooseVersion

import easybuild.tools.systemtools as systemtools
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.toolchain.compiler import Compiler


TC_CONSTANT_INTELCOMP = "Intel"


class IntelIccIfort(Compiler):
    """Intel compiler class
        - TODO: install as single package ?
            should be done anyway (all icc versions come with matching ifort version)
    """

    COMPILER_MODULE_NAME = ['icc', 'ifort']

    COMPILER_FAMILY = TC_CONSTANT_INTELCOMP
    COMPILER_UNIQUE_OPTS = {
        'intel-static': (False, "Link Intel provided libraries statically"),
        'no-icc': (False, "Don't set Intel specific macros"),
        'error-unknown-option': (False, "Error instead of warning for unknown options"),
    }

    COMPILER_UNIQUE_OPTION_MAP = {
        'i8': 'i8',
        'r8': 'r8',
        'optarch': 'xHost',
        'openmp': 'fopenmp',  # both -qopenmp/-fopenmp are valid for enabling OpenMP (-openmp is deprecated)
        'strict': ['fp-speculation=strict', 'fp-model strict'],
        'precise': ['fp-model precise'],
        'defaultprec': ['ftz', 'fp-speculation=safe', 'fp-model source'],
        'loose': ['fp-model fast=1'],
        'veryloose': ['fp-model fast=2'],
        'intel-static': 'static-intel',
        'no-icc': 'no-icc',
        'error-unknown-option': 'we10006',  # error at warning #10006: ignoring unknown option
    }

    # used when 'optarch' toolchain option is enabled (and --optarch is not specified)
    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = {
        systemtools.INTEL : 'xHost',
        systemtools.AMD : 'xHost',
    }
    # used with --optarch=GENERIC
    COMPILER_GENERIC_OPTION = {
        systemtools.INTEL : 'xSSE2',
        systemtools.AMD : 'xSSE2',
    }

    COMPILER_CC = 'icc'
    COMPILER_CXX = 'icpc'
    COMPILER_C_UNIQUE_FLAGS = ['intel-static', 'no-icc']

    COMPILER_F77 = 'ifort'
    COMPILER_F90 = 'ifort'
    COMPILER_FC = 'ifort'
    COMPILER_F_UNIQUE_FLAGS = ['intel-static']

    LINKER_TOGGLE_STATIC_DYNAMIC = {
        'static': '-Bstatic',
        'dynamic':'-Bdynamic',
    }

    LIB_MULTITHREAD = ['iomp5', 'pthread']  # iomp5 is OpenMP related

    def __init__(self, *args, **kwargs):
        """Toolchain constructor."""
        class_constants = kwargs.setdefault('class_constants', [])
        class_constants.append('LIB_MULTITHREAD')

        super(IntelIccIfort, self).__init__(*args, **kwargs)

    def _set_compiler_vars(self):
        """Intel compilers-specific adjustments after setting compiler variables."""
        super(IntelIccIfort, self)._set_compiler_vars()

        if not ('icc' in self.COMPILER_MODULE_NAME and 'ifort' in self.COMPILER_MODULE_NAME):
            raise EasyBuildError("_set_compiler_vars: missing icc and/or ifort from COMPILER_MODULE_NAME %s",
                                 self.COMPILER_MODULE_NAME)

        icc_root, _ = self.get_software_root(self.COMPILER_MODULE_NAME)
        icc_version, ifort_version = self.get_software_version(self.COMPILER_MODULE_NAME)

        if not ifort_version == icc_version:
            raise EasyBuildError("_set_compiler_vars: mismatch between icc version %s and ifort version %s",
                                 icc_version, ifort_version)

        if LooseVersion(icc_version) < LooseVersion('2011'):
            self.LIB_MULTITHREAD.insert(1, "guide")

        libpaths = ['intel64']
        if self.options.get('32bit', None):
            libpaths.append('ia32')
        libpaths = ['lib/%s' % x for x in libpaths]
        if LooseVersion(icc_version) > LooseVersion('2011.4') and LooseVersion(icc_version) < LooseVersion('2013_sp1'):
            libpaths = ['compiler/%s' % x for x in libpaths]

        self.variables.append_subdirs("LDFLAGS", icc_root, subdirs=libpaths)

    def set_variables(self):
        """Set the variables."""
        # -fopenmp is not supported in old versions (11.x)
        icc_version, _ = self.get_software_version(self.COMPILER_MODULE_NAME)
        if LooseVersion(icc_version) < LooseVersion('12'):
            self.options.options_map['openmp'] = 'openmp'

        super(IntelIccIfort, self).set_variables()
