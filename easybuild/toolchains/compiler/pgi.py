##
# Copyright 2015 Bart Oldeman
#
# This file is triple-licensed under GPLv2 (see below), MIT, and
# BSD three-clause licenses.
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
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

    # References:
    # http://www.pgroup.com/doc/pgiref.pdf
    # http://www.pgroup.com/products/freepgi/freepgi_ref/ch02.html#Mflushz
    # http://www.pgroup.com/products/freepgi/freepgi_ref/ch02.html#Mfprelaxed
    # http://www.pgroup.com/products/freepgi/freepgi_ref/ch02.html#Mfpapprox
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

    # used when 'optarch' toolchain option is enabled (and --optarch is not specified)
    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = {
        systemtools.AMD : '',
        systemtools.INTEL : '',
    }
    # used with --optarch=GENERIC
    COMPILER_GENERIC_OPTION = {
        systemtools.AMD : 'tp=x64',
        systemtools.INTEL : 'tp=x64',
    }

    COMPILER_CC = 'pgcc'
    # C++ compiler command is version-dependent, see below
    COMPILER_CXX = None

    COMPILER_F77 = 'pgf77'
    COMPILER_F90 = 'pgfortran'
    COMPILER_FC = 'pgfortran'

    LINKER_TOGGLE_STATIC_DYNAMIC = {
        'static': '-Bstatic',
        'dynamic':'-Bdynamic',
    }

    def _set_compiler_flags(self):
        """Set -tp=x64 if optarch is set to False."""
        if not self.options.get('optarch', False):
            self.variables.nextend('OPTFLAGS', ['tp=x64'])
        super(Pgi, self)._set_compiler_flags()

    def _set_compiler_vars(self):
        """Set the compiler variables"""
        pgi_version = self.get_software_version(self.COMPILER_MODULE_NAME)[0]

        # based on feedback from PGI support: use pgc++ with PGI 14.10 and newer, pgCC for older versions
        if LooseVersion(pgi_version) >= LooseVersion('14.10'):
            self.COMPILER_CXX = 'pgc++'
        else:
            self.COMPILER_CXX = 'pgCC'

        super(Pgi, self)._set_compiler_vars()
