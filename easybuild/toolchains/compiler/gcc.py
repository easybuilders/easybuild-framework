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
Support for GCC (GNU Compiler Collection) as toolchain compiler.

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""

import re
from distutils.version import LooseVersion

import easybuild.tools.systemtools as systemtools
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.modules import get_software_root, get_software_version
from easybuild.tools.toolchain.compiler import Compiler, DEFAULT_OPT_LEVEL


TC_CONSTANT_GCC = "GCC"


class Gcc(Compiler):
    """GCC compiler class"""

    COMPILER_MODULE_NAME = ['GCC']

    COMPILER_FAMILY = TC_CONSTANT_GCC
    COMPILER_UNIQUE_OPTS = {
        'loop': (False, "Automatic loop parallellisation"),
        'f2c': (False, "Generate code compatible with f2c and f77"),
        'lto':(False, "Enable Link Time Optimization"),
    }
    COMPILER_UNIQUE_OPTION_MAP = {
        'i8': 'fdefault-integer-8',
        'r8': 'fdefault-real-8',
        'unroll': 'funroll-loops',
        'f2c': 'ff2c',
        'loop': ['ftree-switch-conversion', 'floop-interchange', 'floop-strip-mine', 'floop-block'],
        'lto': 'flto',
        'ieee': ['mieee-fp', 'fno-trapping-math'],
        'strict': ['mieee-fp', 'mno-recip'],
        'precise': ['mno-recip'],
        'defaultprec': ['fno-math-errno'],
        'loose': ['fno-math-errno', 'mrecip', 'mno-ieee-fp'],
        'veryloose': ['fno-math-errno', 'mrecip=all', 'mno-ieee-fp'],
        'vectorize': {False: 'fno-tree-vectorize', True: 'ftree-vectorize'},
        DEFAULT_OPT_LEVEL: ['O2', 'ftree-vectorize'],
    }

    # used when 'optarch' toolchain option is enabled (and --optarch is not specified)
    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = {
        (systemtools.AARCH32, systemtools.ARM): 'mcpu=native', # implies -march=native and -mtune=native
        (systemtools.AARCH64, systemtools.ARM): 'mcpu=native', # since GCC 6; implies -march=native and -mtune=native
        (systemtools.POWER, systemtools.POWER): 'mcpu=native',   # no support for -march on POWER; implies -mtune=native
        (systemtools.POWER, systemtools.POWER_LE): 'mcpu=native',   # no support for -march on POWER; implies -mtune=native
        (systemtools.X86_64, systemtools.AMD): 'march=native', # implies -mtune=native
        (systemtools.X86_64, systemtools.INTEL): 'march=native', # implies -mtune=native
    }
    # used with --optarch=GENERIC
    COMPILER_GENERIC_OPTION = {
        (systemtools.AARCH32, systemtools.ARM): 'mcpu=generic-armv7', # implies -march=armv7 and -mtune=generic-armv7
        (systemtools.AARCH64, systemtools.ARM): 'mcpu=generic',       # implies -march=armv8-a and -mtune=generic
        (systemtools.POWER, systemtools.POWER): 'mcpu=powerpc64',    # no support for -march on POWER
        (systemtools.POWER, systemtools.POWER_LE): 'mcpu=powerpc64le',    # no support for -march on POWER
        (systemtools.X86_64, systemtools.AMD): 'march=x86-64 -mtune=generic',
        (systemtools.X86_64, systemtools.INTEL): 'march=x86-64 -mtune=generic',
    }

    COMPILER_CC = 'gcc'
    COMPILER_CXX = 'g++'
    COMPILER_C_UNIQUE_FLAGS = []

    COMPILER_F77 = 'gfortran'
    COMPILER_F90 = 'gfortran'
    COMPILER_FC = 'gfortran'
    COMPILER_F_UNIQUE_FLAGS = ['f2c']

    LIB_MULTITHREAD = ['pthread']
    LIB_MATH = ['m']

    def _set_compiler_vars(self):
        super(Gcc, self)._set_compiler_vars()

        if self.options.get('32bit', None):
            raise EasyBuildError("_set_compiler_vars: 32bit set, but no support yet for 32bit GCC in EasyBuild")

        # to get rid of lots of problems with libgfortranbegin
        # or remove the system gcc-gfortran
        # also used in eg LIBBLAS variable
        self.variables.nappend('FLIBS', "gfortran", position=5)

        # append lib dir paths to LDFLAGS (only if the paths are actually there)
        # Note: hardcode 'GCC' here; we can not reuse COMPILER_MODULE_NAME because
        # it can be redefined by combining GCC with other compilers (e.g., Clang).
        gcc_root = get_software_root('GCCcore')
        if gcc_root is None:
            gcc_root = get_software_root('GCC')
            if gcc_root is None:
                raise EasyBuildError("Failed to determine software root for GCC")

        self.variables.append_subdirs("LDFLAGS", gcc_root, subdirs=["lib64", "lib"])

    def _set_optimal_architecture(self, default_optarch=None):
        """
        GCC-specific adjustments for optimal architecture flags.

        :param default_optarch: default value to use for optarch, rather than using default value based on architecture
                                (--optarch and --optarch=GENERIC still override this value)
        """
        if default_optarch is None and self.arch == systemtools.AARCH64:
            gcc_version = get_software_version('GCCcore')
            if gcc_version is None:
                gcc_version = get_software_version('GCC')
                if gcc_version is None:
                    raise EasyBuildError("Failed to determine software version for GCC")

            if LooseVersion(gcc_version) < LooseVersion('6'):
                # on AArch64, -mcpu=native is not supported prior to GCC 6,
                # so try to guess a proper default optarch if none was specified
                default_optarch = self._guess_aarch64_default_optarch()

        super(Gcc, self)._set_optimal_architecture(default_optarch=default_optarch)

    def _guess_aarch64_default_optarch(self):
        """
        Guess default optarch for AARCH64 (vanilla ARM cores only)
        This heuristic may fail if the CPU module is not supported by the GCC version being used.
        """
        default_optarch = None
        cpu_vendor = systemtools.get_cpu_vendor()
        cpu_model = systemtools.get_cpu_model()

        if cpu_vendor == systemtools.ARM and cpu_model.startswith('ARM '):
            self.log.debug("Determining architecture-specific optimization flag for ARM (model: %s)", cpu_model)
            core_types = []
            for core_type in [ct.strip().lower() for ct in cpu_model[4:].split('+')]:
                # Determine numeric ID for each core type, since we need to sort them later numerically
                res = re.search('\d+$', core_type)  # note: numeric ID is expected at the end
                if res:
                    core_id = int(res.group(0))
                    core_types.append((core_id, core_type))
                    self.log.debug("Extracted numeric ID for ARM core type '%s': %s", core_type, core_id)
                else:
                    # Bail out if we can't determine numeric ID
                    core_types = None
                    self.log.debug("Failed to extract numeric ID for ARM core type '%s', bailing out", core_type)
                    break
            if core_types:
                # On big.LITTLE setups, sort core types to have big core (higher model number) first.
                # Example: 'mcpu=cortex-a72.cortex-a53' for "ARM Cortex-A53 + Cortex-A72"
                default_optarch = 'mcpu=%s' % '.'.join([ct[1] for ct in sorted(core_types, reverse=True)])
                self.log.debug("Using architecture-specific compiler optimization flag '%s'", default_optarch)

        return default_optarch
