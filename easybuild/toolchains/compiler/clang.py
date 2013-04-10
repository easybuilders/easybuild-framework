##
# Copyright 2013 Ghent University
#
# This file is triple-licensed under GPLv2 (see below), MIT, and
# BSD three-clause licenses.
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
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
Support for Clang as toolchain compiler.

@author: Dmitri Gribenko (National Technical University of Ukraine "KPI")
"""

import easybuild.tools.systemtools as systemtools
from easybuild.tools.toolchain.compiler import Compiler


class Clang(Compiler):
    """Clang compiler class"""

    COMPILER_MODULE_NAME = ['Clang']

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

	# Clang's options do not map well onto these math modes.  The flags
	# control certain classes of optimization, and the actual speedup
	# depends on the application.  -fassociative-math -freciprocal-math
	# -fno-signed-zeros -fno-trapping-math and a superset of these,
	# -ffast-math, which means "do whatever you want".
        'strict': [],
        'precise':[],
        'defaultprec':[],
        'loose': [],
        'veryloose': ['ffast-math'],
    }

    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = {
        systemtools.INTEL : 'march=native',
        systemtools.AMD : 'march=native'
    }

    COMPILER_CC = 'clang'
    COMPILER_CXX = 'clang++'
    COMPILER_C_UNIQUE_FLAGS = []

    LIB_MULTITHREAD = ['pthread']
    LIB_MATH = ['m']

    def _set_compiler_vars(self):
        super(Clang, self)._set_compiler_vars()

        if self.options.get('32bit', None):
            self.log.raiseException("_set_compiler_vars: 32bit set, but no support yet for " \
                                    "32bit Clang in EasyBuild")

