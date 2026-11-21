##
# Copyright 2022 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
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
Support for AOCC (AMD Optimizing C/C++ and Fortran Compilers) as compiler for toolchains
:author: Christoph Siegert (Leipzig University)
"""

import easybuild.tools.systemtools as systemtools
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.toolchain.compiler import Compiler, DEFAULT_OPT_LEVEL


TC_CONSTANT_AOCC = 'AOCC'


class Aocc(Compiler):
    """AOCC compiler class"""

    COMPILER_MODULE_NAME = ['AOCC']

    COMPILER_FAMILY = TC_CONSTANT_AOCC
    COMPILER_UNIQUE_OPTS = {
        'loop': (False, 'Automatic loop paralellization'),
        'math-vectorize': (False, 'Vectorize functions in math.h'),
        'f2c': (False, "Generate code compatible with f2c and f77"),
        'lto': (False, "Enable Link Time Optimization"),
        # TODO AOCC/LLVM vectorization options
        # https://developer.amd.com/wp-content/resources/57222_AOCC_UG_Rev_3.2.pdf page 24+
    }

    COMPILER_UNIQUE_OPTION_MAP = {
        'math-vectorize': ['fveclib=AMDLIBM'],
        'i8': 'fdefault-integer-8',
        'r8': 'fdefault-real-8',
        'unroll': 'funroll-loops',
        'f2c': 'ff2c',
        'loop': ['mllvm', 'loop-vectorize', 'mllvm', 'enable-loopinterchange', 'mllvm', 'compute-interchange-order',
                 'mllvm', 'loop-splitting', 'mllvm', 'enable-ipo-loop-split'],
        'lto': 'flto',
        'ieee': ['ffp-model=strict', 'ffp-exception-behavior=ignore'],
        'strict': ['ffp-model=strict', 'fno-reciprocal-math'],
        'precise': ['ffp-model=precise'],
        'defaultprec': ['fno-math-errno'],
        'loose': ['ffp-model=fast', 'fno-unsafe-math-optimizations'],
        'veryloose': ['ffp-model=fast'],
        'vectorize': {False: 'fno-vectorize', True: 'fvectorize'},
        DEFAULT_OPT_LEVEL: ['O2', 'fvectorize'],
    }

    # used when 'optarch' toolchain option is enabled (and --optarch is not specified)
    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = {
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

    COMPILER_F77 = 'flang'
    COMPILER_F90 = 'flang'
    COMPILER_FC = 'flang'
    COMPILER_C_UNIQUE_FLAGS = ['f2c']

    LIB_MULTITHREAD = ['pthread']
    # https://developer.amd.com/amd-aocl/amd-math-library-libm/
    LIB_MATH = 'alm'

    def _set_compiler_vars(self):
        """Set compiler variables to disable 32bit."""
        super(Aocc, self)._set_compiler_vars()

        if self.options.get('32bit', None):
            raise EasyBuildError('_set_compiler_vars: 32bit set, but AOCC does not support 32bit')
