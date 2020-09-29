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
Support for NVIDIA HPC SDK ('NVHPC') compilers (nvc, nvc++, nvfortran) as toolchain compilers.
NVHPC is the successor of the PGI compilers, on which this file is based upon.

:author: Bart Oldeman (McGill University, Calcul Quebec, Compute Canada)
:author: Damian Alvarez (Forschungszentrum Juelich GmbH)
:author: Andreas Herten (Forschungszentrum Juelich GmbH)
"""

import easybuild.tools.systemtools as systemtools
from easybuild.tools.toolchain.compiler import Compiler


TC_CONSTANT_NVHPC = "NVHPC"


class NVHPC(Compiler):
    """NVHPC compiler class
    """

    COMPILER_MODULE_NAME = ['NVHPC']

    COMPILER_FAMILY = TC_CONSTANT_NVHPC

    # References:
    # https://docs.nvidia.com/hpc-sdk/compilers/hpc-compilers-user-guide/index.html
    # nvc --help
    # And previously, for PGI:
    # http://www.pgroup.com/doc/pgiref.pdf
    # http://www.pgroup.com/products/freepgi/freepgi_ref/ch02.html#Mflushz
    # http://www.pgroup.com/products/freepgi/freepgi_ref/ch02.html#Mfprelaxed
    # http://www.pgroup.com/products/freepgi/freepgi_ref/ch02.html#Mfpapprox
    COMPILER_UNIQUE_OPTION_MAP = {
        'i8': 'i8',
        'r8': 'r8',
        'optarch': '',  # PGI by default generates code for the arch it is running on!
        'openmp': 'mp',
        'ieee': 'Kieee',
        'strict': ['Mnoflushz', 'Kieee'],
        'precise': ['Mnoflushz'],
        'defaultprec': ['Mflushz'],
        'loose': ['Mfprelaxed'],
        'veryloose': ['Mfprelaxed=div,order,intrinsic,recip,sqrt,rsqrt', 'Mfpapprox'],
        'vectorize': {False: 'Mnovect', True: 'Mvect'},
    }

    # used when 'optarch' toolchain option is enabled (and --optarch is not specified)
    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = {
        (systemtools.X86_64, systemtools.AMD): 'tp=host',
        (systemtools.X86_64, systemtools.INTEL): 'tp=host',
    }
    # used with --optarch=GENERIC
    COMPILER_GENERIC_OPTION = {
        (systemtools.X86_64, systemtools.AMD): 'tp=px',
        (systemtools.X86_64, systemtools.INTEL): 'tp=px',
    }

    COMPILER_CC = 'nvc'
    COMPILER_CXX = 'nvc++'

    COMPILER_F77 = 'nvfortran'
    COMPILER_F90 = 'nvfortran'
    COMPILER_FC = 'nvfortran'

    LINKER_TOGGLE_STATIC_DYNAMIC = {
        'static': '-Bstatic',
        'dynamic': '-Bdynamic',
    }

    def _set_compiler_flags(self):
        """Set -tp=x64 if optarch is set to False."""
        if not self.options.get('optarch', False):
            self.variables.nextend('OPTFLAGS', ['tp=x64'])
        super(NVHPC, self)._set_compiler_flags()

    def _set_compiler_vars(self):
        """Set the compiler variables"""
        super(NVHPC, self)._set_compiler_vars()
