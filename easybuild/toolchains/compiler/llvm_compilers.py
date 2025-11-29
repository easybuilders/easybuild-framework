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

* Dmitri Gribenko (National Technical University of Ukraine "KPI")
* Davide Grassano (CECAM EPFL)
"""

from easybuild.tools import LooseVersion
import easybuild.tools.systemtools as systemtools
from easybuild.tools.toolchain.compiler import Compiler, DEFAULT_OPT_LEVEL
from easybuild.tools.toolchain.toolchain import SYSTEM_TOOLCHAIN_NAME

TC_CONSTANT_LLVM = "LLVM"


class LLVMCompilers(Compiler):
    """Compiler toolchain with LLVM compilers (clang/flang)."""
    COMPILER_FAMILY = TC_CONSTANT_LLVM
    SUBTOOLCHAIN = SYSTEM_TOOLCHAIN_NAME

    # List of flags that are supported by Clang but not yet by Flang and should be filtered out
    # The element of the list are tuples with the following structure:
    # (min_version, max_version, [list of flags])
    # Where min_version and max_version are strings representing a left-inclusive and right-exclusive version range,
    # [min_version, max_version) respectively.
    # This is used to specify general `clang`-accepted flags and remove them from `flang` compiler flags if
    # not supported for a particular version of LLVM
    FLANG_UNSUPPORTED_VARS = [
        ('19', '21', [
            '-fmath-errno', '-fno-math-errno',
            '-fslp-vectorize',
            '-fvectorize', '-fno-vectorize',
            '-fno-unsafe-math-optimizations',
        ]),
        ('21', '22', [
            '-fmath-errno', '-fno-math-errno',
            '-fno-unsafe-math-optimizations',
        ]),
    ]

    FORTRAN_FLAGS = ['FCFLAGS', 'FFLAGS', 'F90FLAGS']

    COMPILER_UNIQUE_OPTS = {
        'loop-vectorize': (False, "Loop vectorization"),
        'basic-block-vectorize': (False, "Basic block vectorization"),

        # https://github.com/madler/zlib/issues/856
        'lld_undefined_version': (False, "-Wl,--undefined-version - Allow unused version in version script"),
        'no_unused_args': (
            True,
            "-Wno-unused-command-line-argument - Avoid some failures in CMake correctly recognizing "
            "feature due to linker warnings"
        ),
        'no_int_conversion_error': (
            True,
            "-Wno-error=int-conversion - Avoid some failures that are normally ignored by GCC"
        ),
    }

    COMPILER_UNIQUE_OPTION_MAP = {
        'unroll': '-funroll-loops',
        'loop-vectorize': ['-fvectorize'],
        'basic-block-vectorize': ['-fslp-vectorize'],
        # Clang's options do not map well onto these precision modes.  The flags enable and disable certain classes of
        # optimizations.
        #
        # -fassociative-math: allow re-association of operands in series of floating-point operations, violates the
        # ISO C and C++ language standard by possibly changing computation result.
        # -freciprocal-math: allow optimizations to use the reciprocal of an argument rather than perform division.
        # -fsigned-zeros: do not allow optimizations to treat the sign of a zero argument or result as insignificant.
        # -fhonor-infinities: disallow optimizations to assume that arguments and results are not +/- Infs.
        # -fhonor-nans: disallow optimizations to assume that arguments and results are not +/- NaNs.
        # -ffinite-math-only: allow optimizations for floating-point arithmetic that assume that arguments and results
        # are not NaNs or +-Infs (equivalent to -fno-honor-nans -fno-honor-infinities)
        # -funsafe-math-optimizations: allow unsafe math optimizations (implies -fassociative-math, -fno-signed-zeros,
        # -freciprocal-math).
        # -ffast-math: an umbrella flag that enables all optimizations listed above, provides preprocessor macro
        # __FAST_MATH__.
        #
        # Using -fno-fast-math is equivalent to disabling all individual optimizations, see
        # http://llvm.org/viewvc/llvm-project/cfe/trunk/lib/Driver/Tools.cpp?view=markup (lines 2100 and following)
        #
        # 'strict', 'precise' and 'defaultprec' are all ISO C++ and IEEE complaint, but we explicitly specify details
        # flags for strict and precise for robustness against future changes.
        'strict': ['-fno-fast-math'],
        'precise': ['-fno-unsafe-math-optimizations'],
        'defaultprec': [],
        'loose': ['-ffast-math', '-fno-unsafe-math-optimizations'],
        'veryloose': ['-ffast-math'],
        'vectorize': {False: '-fno-vectorize', True: '-fvectorize'},
        DEFAULT_OPT_LEVEL: ['-O2'],

        'lld_undefined_version': ['-Wl,--undefined-version'],
        'no_unused_args': ['-Wno-unused-command-line-argument'],
        'no_int_conversion_error': ['-Wno-error=int-conversion'],
    }

    # Ensure that compiler options only appear once, so that arguments do not appear multiple times when compiling.
    COMPILER_OPTIONS = list({
        *(Compiler.COMPILER_OPTIONS or []),
        'lld_undefined_version'
    })

    # Options only available for Clang compiler
    COMPILER_C_UNIQUE_OPTIONS = list({
        *(Compiler.COMPILER_C_UNIQUE_OPTIONS or []),
        'no_unused_args',
        'no_int_conversion_error'
    })

    # Options only available for Flang compiler
    COMPILER_F_UNIQUE_OPTIONS = Compiler.COMPILER_F_UNIQUE_OPTIONS

    # used when 'optarch' toolchain option is enabled (and --optarch is not specified)
    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = {
        **(Compiler.COMPILER_OPTIMAL_ARCHITECTURE_OPTION or {}),
        (systemtools.AARCH64, systemtools.ARM): '-march=native',
        (systemtools.POWER, systemtools.POWER): '-mcpu=native',  # no support for march=native on POWER
        (systemtools.POWER, systemtools.POWER_LE): '-mcpu=native',  # no support for march=native on POWER
        (systemtools.X86_64, systemtools.AMD): '-march=native',
        (systemtools.X86_64, systemtools.INTEL): '-march=native',
    }

    # used with --optarch=GENERIC
    COMPILER_GENERIC_OPTION = {
        **(Compiler.COMPILER_GENERIC_OPTION or {}),
        (systemtools.AARCH64, systemtools.ARM): '-mcpu=generic -mtune=generic',
        (systemtools.RISCV64, systemtools.RISCV): '-march=rv64gc -mabi=lp64d',  # default for -mabi is system-dependent
        (systemtools.X86_64, systemtools.AMD): '-march=x86-64 -mtune=generic',
        (systemtools.X86_64, systemtools.INTEL): '-march=x86-64 -mtune=generic',
    }

    COMPILER_CC = 'clang'
    COMPILER_CXX = 'clang++'

    COMPILER_F77 = 'flang'
    COMPILER_F90 = 'flang'
    COMPILER_FC = 'flang'

    LINKERS = ('lld', 'ld.lld', 'ld64.lld')

    LIB_MULTITHREAD = ['pthread']
    LIB_MATH = ['m']

    def _set_compiler_flags(self):
        super()._set_compiler_flags()

        unsupported_fortran_flags = None
        for v_min, v_max, flags in self.FLANG_UNSUPPORTED_VARS:
            if LooseVersion(self.version) >= LooseVersion(v_min) and LooseVersion(self.version) < LooseVersion(v_max):
                unsupported_fortran_flags = flags
                break
        else:
            self.log.debug("No unsupported flags found for LLVM version %s", self.version)

        if unsupported_fortran_flags is not None:
            self.log.debug(
                f"Ensuring unsupported Fortran flags `{unsupported_fortran_flags}` are removed from variables"
            )
            for key, lst in self.variables.items():
                if key not in self.FORTRAN_FLAGS:
                    continue
                for item in lst:
                    item.try_remove(unsupported_fortran_flags)
