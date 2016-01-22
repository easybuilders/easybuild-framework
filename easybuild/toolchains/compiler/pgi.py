##
# Copyright 2015 Bart Oldeman
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
Support for PGI compilers (pgcc, pgc++, pgfortran) as toolchain compilers.

@author: Bart Oldeman (McGill University, Calcul Quebec, Compute Canada)
"""

from distutils.version import LooseVersion

import easybuild.tools.systemtools as systemtools
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.toolchain.compiler import Compiler


TC_CONSTANT_PGI = "PGI"


class Pgi(Compiler):
    """PGI compiler class
    """

    COMPILER_MODULE_NAME = ['PGI']

    COMPILER_FAMILY = TC_CONSTANT_PGI

    # Reference: https://www.pgroup.com/doc/pgiref.pdf
    COMPILER_UNIQUE_OPTION_MAP = {
        'i8': 'i8',
        'r8': 'r8',
        'optarch': '', # PGI by default generates code for the arch it is running on!
        'openmp': 'mp',
        'strict': ['Mnoflushz','Kieee'],
        'precise': ['Mnoflushz'],
        'defaultprec': ['Mflushz'],
        'loose': ['Mfprelaxed'],
        'veryloose': ['Mfprelaxed=div,order,intrinsic,recip,sqrt,rsqrt', 'Mfpapprox'],
    }

    COMPILER_CC = 'pgcc'
    COMPILER_CXX = 'pgc++'

    COMPILER_F77 = 'pgfortran'
    COMPILER_F90 = 'pgfortran'

    LINKER_TOGGLE_STATIC_DYNAMIC = {
        'static': '-Bstatic',
        'dynamic':'-Bdynamic',
    }

