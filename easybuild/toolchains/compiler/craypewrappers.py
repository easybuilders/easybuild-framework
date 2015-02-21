##
# Copyright 2012-2014 Ghent University
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
Support for the Cray Programming Environment Wrappers (aka cc, CC, ftn).
The Cray compiler wrappers are actually way more than just a compiler drivers.

The basic concept is that the compiler driver knows how to invoke the true underlying
compiler with the compiler's specific options tuned to cray systems.

That means that certain defaults are set that are specific to Cray's computers.

The compiler wrappers are quite similar to EB toolchains as they include
linker and compiler directives to use the Cray libraries for their MPI (and network drivers)
Cray's LibSci (BLAS/LAPACK et al), FFT library, etc.


@author: Petar Forai
"""

from easybuild.tools.toolchain.compiler import Compiler
from easybuild.toolchains.compiler.gcc import Gcc
from easybuild.toolchains.compiler.inteliccifort import IntelIccIfort

TC_CONSTANT_CRAYPEWRAPPER = "CRAYPEWRAPPER"


class CrayPEWrapper(Compiler):
    """Base CrayPE compiler class"""

    COMPILER_MODULE_NAME = ['PrgEnv']

    COMPILER_FAMILY = TC_CONSTANT_CRAYPEWRAPPER

    COMPILER_UNIQUE_OPTS = {
        'verbose' : (False, "Enable verbose calls to real compiler driver."),
        'dynamic' : (False, "Enables dynamic code generation."),
	}

    COMPILER_UNIQUE_OPTION_MAP = {
        'verbose': 'craype-verbose',
	    'dynamic': 'dynamic',
    }

    COMPILER_OPT_FLAGS = []
    COMPILER_PREC_FLAGS = []

    COMPILER_CC = 'cc'
    COMPILER_CXX = 'CC'
    COMPILER_C_UNIQUE_FLAGS = []


    COMPILER_F77 = 'ftn'
    COMPILER_F90 = 'ftn'
    COMPILER_F_UNIQUE_FLAGS = []


#    def _set_compiler_vars(self):
#        super(CrayPEWrapper, self)._set_compiler_vars()

#Gcc's base is Compiler
class CrayPEWrapperGNU(Gcc):
    """Base Cray Programming Environment GNU compiler class"""

    COMPILER_MODULE_NAME = ['PrgEnv-gnu']

    #COMPILER_FAMILY = TC_CONSTANT_GCC #@todo does this make sense?


class CrayPEWrapperIntel(CrayPEWrapper,IntelIccIfort):
    COMPILER_MODULE_NAME = ['PrgEnv-intel']


class CrayPEWrapperCray(CrayPEWrapper):
    pass