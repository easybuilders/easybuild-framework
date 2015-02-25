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

import easybuild.tools.systemtools as systemtools

TC_CONSTANT_CRAYPEWRAPPER = "CRAYPEWRAPPER"


class CrayPEWrapper(Compiler):
    """Base CrayPE compiler class"""

    COMPILER_MODULE_NAME = None
    COMPILER_FAMILY = TC_CONSTANT_CRAYPEWRAPPER

    COMPILER_UNIQUE_OPTS = {
        'mpich-mt': (False, """Directs the driver to link in an alternate version of the Cray-MPICH library which
                                 provides fine-grained multi-threading support to applications that perform
                                 MPI operations within threaded regions."""),
        'dynamic': (True, "Directs the compiler driver to link dynamic libraries at runtime."),
        'usewrappedcompiler': (False, "Use the embedded compiler instead of the wrapper"),
    }

    COMPILER_UNIQUE_OPTION_MAP = {
        'dynamic': 'dynamic',
        'shared': 'shared',
        'static': 'static',
        'verbose': 'craype-verbose',
        'mpich-mt': 'craympich-mt',
        'pic': 'dynamic',
    }

    COMPILER_SHARED_OPTION_MAP = {
        'pic': 'dynamic',
        'verbose': 'craype-verbose',
        'static': 'static',
    }

    # @todo this is BS.
    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = {
        systemtools.INTEL: 'march=native',
        systemtools.AMD: 'march=native'
    }

    #COMPILER_PREC_FLAGS = ['strict', 'precise', 'defaultprec', 'loose', 'veryloose']  # precision flags, ordered !

    COMPILER_CC = 'cc'
    COMPILER_CXX = 'CC'

    COMPILER_F77 = 'ftn'
    COMPILER_F90 = 'ftn'

    def _set_compiler_vars(self):
        super(CrayPEWrapper, self)._set_compiler_vars()

    def _get_optimal_architecture(self):
        """On a Cray system we assume that the optimal architecture is controlled
           by loading a craype module that instructs the compiler to generate backend code
           for that particular target"""
        pass

    def _set_compiler_flags(self):
        """Collect the flags set, and add them as variables too"""
        flags = [self.options.option(x) for x in self.COMPILER_FLAGS if self.options.get(x, False)]
        cflags = [self.options.option(x) for x in self.COMPILER_C_FLAGS + self.COMPILER_C_UNIQUE_FLAGS \
                  if self.options.get(x, False)]
        fflags = [self.options.option(x) for x in self.COMPILER_F_FLAGS + self.COMPILER_F_UNIQUE_FLAGS \
                  if self.options.get(x, False)]

        # 1st one is the one to use. add default at the end so len is at least 1
        # optflags = [self.options.option(x) for x in self.COMPILER_OPT_FLAGS if self.options.get(x, False)] + \
        #            [self.options.option('defaultopt')]
        #
        # optarchflags = [self.options.option(x) for x in ['optarch'] if self.options.get(x, False)]
        #
        # precflags = [self.options.option(x) for x in self.COMPILER_PREC_FLAGS if self.options.get(x, False)] + \
        #             [self.options.option('defaultprec')]
        #
        # self.variables.nextend('OPTFLAGS', optflags[:1] + optarchflags)
        # self.variables.nextend('PRECFLAGS', precflags[:1])

        # precflags last
        self.variables.nappend('CFLAGS', flags)
        self.variables.nappend('CFLAGS', cflags)
        self.variables.join('CFLAGS', )  # 'OPTFLAGS', 'PRECFLAGS')

        self.variables.nappend('CXXFLAGS', flags)
        self.variables.nappend('CXXFLAGS', cflags)
        self.variables.join('CXXFLAGS', )  # 'OPTFLAGS', 'PRECFLAGS')

        self.variables.nappend('FFLAGS', flags)
        self.variables.nappend('FFLAGS', fflags)
        self.variables.join('FFLAGS', )  # 'OPTFLAGS', 'PRECFLAGS')

        self.variables.nappend('F90FLAGS', flags)
        self.variables.nappend('F90FLAGS', fflags)
        self.variables.join('F90FLAGS', )  # 'OPTFLAGS', 'PRECFLAGS')


# Gcc's base is Compiler
class CrayPEWrapperGNU(CrayPEWrapper):
    """Base Cray Programming Environment GNU compiler class"""
    COMPILER_MODULE_NAME = ['PrgEnv-gnu']
    TC_CONSTANT_CRAYPEWRAPPER = TC_CONSTANT_CRAYPEWRAPPER + '_GNU'


    def _set_compiler_vars(self):
        if self.options.option('usewrappedcompiler'):

            COMPILER_UNIQUE_OPTS = Gcc.COMPILER_UNIQUE_OPTS
            COMPILER_UNIQUE_OPTION_MAP = Gcc.COMPILER_UNIQUE_OPTION_MAP

            COMPILER_CC = Gcc.COMPILER_CC
            COMPILER_CXX = Gcc.COMPILER_CXX
            COMPILER_C_UNIQUE_FLAGS = []

            COMPILER_F77 = Gcc.COMPILER_F77
            COMPILER_F90 = Gcc.COMPILER_F90
            COMPILER_F_UNIQUE_FLAGS = Gcc.COMPILER_F_UNIQUE_FLAGS

            super(CrayPEWrapperGNU, self)._set_compiler_vars()
        else:
            super(CrayPEWrapper, self)._set_compiler_vars()


class CrayPEWrapperIntel(CrayPEWrapper):
    TC_CONSTANT_CRAYPEWRAPPER = TC_CONSTANT_CRAYPEWRAPPER + '_INTEL'

    COMPILER_MODULE_NAME = ['PrgEnv-intel']

    def _set_compiler_vars(self):
        if self.options.option("usewrappedcompiler"):
            COMPILER_UNIQUE_OPTS = IntelIccIfort.COMPILER_UNIQUE_OPTS
            COMPILER_UNIQUE_OPTION_MAP = IntelIccIfort.COMPILER_UNIQUE_OPTION_MAP

            COMPILER_CC = IntelIccIfort.COMPILER_CC

            COMPILER_CXX = IntelIccIfort.COMPILER_CXX
            COMPILER_C_UNIQUE_FLAGS = IntelIccIfort.COMPILER_C_UNIQUE_FLAGS

            COMPILER_F77 = IntelIccIfort.COMPILER_F77
            COMPILER_F90 = IntelIccIfort.COMPILER_F90
            COMPILER_F_UNIQUE_FLAGS = IntelIccIfort.COMPILER_F_UNIQUE_FLAGS

            LINKER_TOGGLE_STATIC_DYNAMIC = IntelIccIfort.LINKER_TOGGLE_STATIC_DYNAMIC

            super(CrayPEWrapperIntel, self).set_compiler_vars()
        else:
            super(CrayPEWrapper, self)._set_compiler_vars()


class CrayPEWrapperCray(CrayPEWrapper):
    TC_CONSTANT_CRAYPEWRAPPER = TC_CONSTANT_CRAYPEWRAPPER + '_CRAY'
    COMPILER_MODULE_NAME = ['PrgEnv-cray']

    def _set_compiler_vars(self):
        super(CrayPEWrapperCray, self)._set_compiler_vars()