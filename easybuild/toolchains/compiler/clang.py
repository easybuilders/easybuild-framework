##
# Copyright 2013-2018 Ghent University
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
Support for Clang as toolchain compiler.

:author: Dmitri Gribenko (National Technical University of Ukraine "KPI")
"""

import easybuild.tools.systemtools as systemtools
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.toolchain.compiler import Compiler


TC_CONSTANT_CLANG = "Clang"


class Clang(Compiler):
    """Clang compiler class"""

    COMPILER_MODULE_NAME = ['Clang']
    
    COMPILER_FAMILY = TC_CONSTANT_CLANG

    # Don't set COMPILER_FAMILY in this class because Clang does not have
    # Fortran support, and thus it is not a complete compiler as far as
    # EasyBuild is concerned.

    COMPILER_UNIQUE_OPTS = {
        'loop-vectorize': (False, "Loop vectorization"),
        'basic-block-vectorize': (False, "Basic block vectorization"),
    }
    COMPILER_UNIQUE_OPTION_MAP = {
        'unroll': 'funroll-loops',
        'loop-vectorize': ['fvectorize'],
        'basic-block-vectorize': ['fslp-vectorize'],
        'optarch':'march=native',
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
        'strict': ['fno-fast-math'],
        'precise': ['fno-unsafe-math-optimizations'],
        'defaultprec': [],
        'loose': ['ffast-math', 'fno-unsafe-math-optimizations'],
        'veryloose': ['ffast-math'],
    }

    # used when 'optarch' toolchain option is enabled (and --optarch is not specified)
    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = {
        (systemtools.POWER, systemtools.POWER): 'mcpu=native',  # no support for march=native on POWER
        (systemtools.POWER, systemtools.POWER_LE): 'mcpu=native',  # no support for march=native on POWER
        (systemtools.X86_64, systemtools.AMD): 'march=native',
        (systemtools.X86_64, systemtools.INTEL): 'march=native',
    }
    # used with --optarch=GENERIC
    COMPILER_GENERIC_OPTION = {
        (systemtools.X86_64, systemtools.AMD): 'march=x86-64 -mtune=generic',
        (systemtools.X86_64, systemtools.INTEL): 'march=x86-64 -mtune=generic',
    }

    COMPILER_CC = 'clang'
    COMPILER_CXX = 'clang++'
    COMPILER_C_UNIQUE_FLAGS = []

    LIB_MULTITHREAD = ['pthread']
    LIB_MATH = ['m']

    def _set_compiler_vars(self):
        """Set compiler variables."""
        super(Clang, self)._set_compiler_vars()

        if self.options.get('32bit', None):
            raise EasyBuildError("_set_compiler_vars: 32bit set, but no support yet for 32bit Clang in EasyBuild")

