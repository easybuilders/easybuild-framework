# #
# Copyright 2012-2013 Ghent University
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
# #
"""
Toolchain compiler module, provides abstract class for compilers.

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

import os

from easybuild.tools import systemtools
from easybuild.tools.toolchain.constants import COMPILER_VARIABLES
from easybuild.tools.toolchain.toolchain import Toolchain


class Compiler(Toolchain):
    """General compiler-like class
        can't be used without creating new class C(Compiler,Toolchain)
    """

    COMPILER_MODULE_NAME = None

    COMPILER_FAMILY = None

    COMPILER_UNIQUE_OPTS = None
    COMPILER_SHARED_OPTS = {'cciscxx': (False, "Use CC as CXX"),  # also MPI
                            'pic': (False, "Use PIC"),  # also FFTW
                            'noopt': (False, "Disable compiler optimizations"),
                            'lowopt': (False, "Low compiler optimizations"),
                            'defaultopt':(False, "Default compiler optimizations"),  # not set, but default
                            'opt': (False, "High compiler optimizations"),
                            'optarch':(True, "Enable architecture optimizations"),
                            'strict': (False, "Strict (highest) precision"),
                            'precise':(False, "High precision"),
                            'defaultprec':(False, "Default precision"),  # not set, but default
                            'loose': (False, "Loose precision"),
                            'veryloose': (False, "Very loose precision"),
                            'verbose': (False, "Verbose output"),
                            'debug': (False, "Enable debug"),
                            'i8': (False, "Integers are 8 byte integers"),  # fortran only -> no: MKL and icc give -DMKL_ILP64
                            'r8' : (False, "Real is 8 byte real"),  # fortran only
                            'unroll': (False, "Unroll loops"),
                            'cstd': (None, "Specify C standard"),
                            'shared': (False, "Build shared library"),
                            'static': (False, "Build static library"),
                            '32bit':(False, "Compile 32bit target"),  # LA, FFTW
                            'openmp':(False, "Enable OpenMP"),
                            'packed-linker-options':(False, "Pack the linker options as comma separated list"),  # ScaLAPACK mainly
                            }

    COMPILER_UNIQUE_OPTION_MAP = None
    COMPILER_SHARED_OPTION_MAP = {'pic': 'fPIC',
                                  'verbose': 'v',
                                  'debug': 'g',
                                  'unroll': 'unroll',
                                  'static': 'static',
                                  'shared': 'shared',
                                  'noopt': 'O0',
                                  'lowopt': 'O1',
                                  'defaultopt':'O2',
                                  'opt': 'O3',
                                  '32bit' : 'm32',
                                  'cstd':'std=%(value)s',
                                  }

    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = None

    COMPILER_FLAGS = ['debug', 'verbose', 'static', 'shared', 'openmp', 'pic', 'unroll']  # any compiler
    COMPILER_OPT_FLAGS = ['noopt', 'lowopt', 'defaultopt', 'opt']  # optimisation args, ordered !
    COMPILER_PREC_FLAGS = ['strict', 'precise', 'defaultprec', 'loose', 'veryloose']  # precision flags, ordered !

    COMPILER_CC = None
    COMPILER_CXX = None
    COMPILER_C_FLAGS = ['cstd']
    COMPILER_C_UNIQUE_FLAGS = []

    COMPILER_F77 = None
    COMPILER_F90 = None
    COMPILER_F_FLAGS = ['i8', 'r8']
    COMPILER_F_UNIQUE_FLAGS = []

    LINKER_TOGGLE_STATIC_DYNAMIC = None
    LINKER_TOGGLE_START_STOP_GROUP = {
                                      'start':'--start-group',
                                      'stop':'--end-group',
                                      }

    LIB_MULTITHREAD = None
    LIB_MATH = None
    LIB_RUNTIME = None

    def __init__(self, *args, **kwargs):
        Toolchain.base_init(self)

        self.arch = None

        self._set_compiler_toolchainoptions()
        self.log.debug('_compiler_init: compiler toolchainoptions %s' % self.options)

        super(Compiler, self).__init__(*args, **kwargs)

    def set_variables(self):
        """Set the variables"""

        self._set_compiler_vars()
        self._set_compiler_flags()

        self.log.debug('set_variables: compiler variables %s' % self.variables)
        super(Compiler, self).set_variables()

    def _set_compiler_toolchainoptions(self, prefix=None):
        """Set the compiler related toolchain options"""
        self.options.add_options(self.COMPILER_SHARED_OPTS, self.COMPILER_SHARED_OPTION_MAP)

        # overwrite/add unique compiler specific toolchainoptions
        infix = ''
        if prefix is not None:
            infix = '%s_' % prefix
        self.options.add_options(
            getattr(self, 'COMPILER_%sUNIQUE_OPTS' % infix, None),
            getattr(self, 'COMPILER_%sUNIQUE_OPTION_MAP' % infix, None),
        )

        # redefine optarch
        self._get_optimal_architecture()

    def _set_compiler_vars(self, prefix=None):
        """Set the compiler variables"""
        is32bit = self.options.get('32bit', None)
        if is32bit:
            self.log.debug("_set_compiler_vars: 32bit set: changing compiler definitions")

        comp_var_tmpl_dict = {}

        for var_tuple in COMPILER_VARIABLES:
            var = var_tuple[0]  # [1] is the description

            # determine actual value for compiler variable
            compvar = 'COMPILER_%s' % var.upper()
            pref_var = var
            if prefix is not None:
                compvar = 'COMPILER_%s_%s' % (prefix, var.upper())
                pref_var = '_'.join([prefix, var])
            value = getattr(self, compvar, None)

            if value is None:
                if prefix is not None:
                    # only warn if prefix is set, since not all languages may be supported (e.g., no Fortran for CUDA)
                    self.log.warn("_set_compiler_vars: %s compiler variable %s undefined" % (prefix, var))
                else:
                    self.log.raiseException("_set_compiler_vars: compiler variable %s undefined" % var)

            self.variables[pref_var] = value
            if is32bit:
                self.variables.nappend_el(pref_var, self.options.option('32bit'))

            # update dictionary to complete compiler variable template
            # to produce e.g. 'nvcc -ccbin=icpc' from 'nvcc -ccbin=%(CXX_base)'
            comp_var_tmpl_dict.update({
                var: str(self.variables[var]),
                '%s_base' % var: str(self.variables[var].get_first()),
            })

        # complete compiler templates for (prefixed) compiler, e.g. CUDA_CC="nvcc -ccbin=%(CXX_base)s"
        for var_tuple in COMPILER_VARIABLES:
            var = var_tuple[0]  # [1] is the description

            # determine actual value for compiler variable
            pref_var = var
            if prefix is not None:
                pref_var = '_'.join([prefix, var])

            self.variables.nappend_el(pref_var, self.options.option('_opt_%s' % pref_var, templatedict=comp_var_tmpl_dict))

        if self.options.get('cciscxx', None):
            self.log.debug("_set_compiler_vars: cciscxx set: switching CXX %s for CC value %s" %
                           (self.variables['CXX'], self.variables['CC']))
            # FIXME (stdweird): shouldn't this be the other way around??
            self.variables['CXX'] = self.variables['CC']

        infix = ''
        if prefix is not None:
            infix = '%s_' % prefix

        for (lib_var, pos) in [
            ('LIB_%sMULTITHREAD' % infix, 10),
            ('LIB_%sMATH' % infix, None),
            ('LIB_%sRUNTIME' % infix, None),
        ]:
            lib = getattr(self, lib_var, None)
            if lib is not None:
                self.variables.nappend('LIBS', lib, position=pos)

    def _set_compiler_flags(self):
        """Collect the flags set, and add them as variables too"""

        flags = [self.options.option(x) for x in self.COMPILER_FLAGS if self.options.get(x, False)]
        cflags = [self.options.option(x) for x in self.COMPILER_C_FLAGS + self.COMPILER_C_UNIQUE_FLAGS \
                  if self.options.get(x, False)]
        fflags = [self.options.option(x) for x in self.COMPILER_F_FLAGS + self.COMPILER_F_UNIQUE_FLAGS \
                  if self.options.get(x, False)]

        # 1st one is the one to use. add default at the end so len is at least 1
        optflags = [self.options.option(x) for x in self.COMPILER_OPT_FLAGS if self.options.get(x, False)] + \
                   [self.options.option('defaultopt')]

        optarchflags = [self.options.option(x) for x in ['optarch'] if self.options.get(x, False)]

        precflags = [self.options.option(x) for x in self.COMPILER_PREC_FLAGS if self.options.get(x, False)] + \
                    [self.options.option('defaultprec')]

        self.variables.nextend('OPTFLAGS', optflags[:1] + optarchflags)
        self.variables.nextend('PRECFLAGS', precflags[:1])

        # precflags last
        self.variables.nappend('CFLAGS', flags)
        self.variables.nappend('CFLAGS', cflags)
        self.variables.join('CFLAGS', 'OPTFLAGS', 'PRECFLAGS')

        self.variables.nappend('CXXFLAGS', flags)
        self.variables.nappend('CXXFLAGS', cflags)
        self.variables.join('CXXFLAGS', 'OPTFLAGS', 'PRECFLAGS')

        self.variables.nappend('FFLAGS', flags)
        self.variables.nappend('FFLAGS', fflags)
        self.variables.join('FFLAGS', 'OPTFLAGS', 'PRECFLAGS')

        self.variables.nappend('F90FLAGS', flags)
        self.variables.nappend('F90FLAGS', fflags)
        self.variables.join('F90FLAGS', 'OPTFLAGS', 'PRECFLAGS')

    def update_variables(self):
        """Update the compiler variables."""
        self._update_variables()
        self.log.debug('update_variables: updated compiler variables %s' % self.variables)

    def _update_variables(self, prefix=None):
        """Update the compiler variables for the given compiler prefix."""

        # construct dict with sanitized variables
        sanitized_vars = {}
        for (key, value) in self.variables.items():
            sanitized_vars.update({str(key): str(value)})

        # complete compiler commands with compiler/linker/extra flags
        # e.g., CUDA_CC='nvcc -ccbin=g++ -Xcompiler="$CXXFLAGS" -Xlinker="$LDFLAGS $LIBS" -gencode ... '
        for var_tuple in COMPILER_VARIABLES:
            var = var_tuple[0]  # [1] is the description

            # determine actual value for compiler variable
            pref_var = var
            if prefix is not None:
                pref_var = '_'.join([prefix, var])

            flags = self.options.option('_opt_flags_%s' % pref_var, templatedict=sanitized_vars)
            if hasattr(flags, '__iter__'):
                self.variables.nextend_el(pref_var, flags)
            else:
                self.variables.nappend_el(pref_var, flags)

    def _get_optimal_architecture(self):
        """ Get options for the current architecture """
        if self.arch is None:
            self.arch = systemtools.get_cpu_vendor()

        if self.COMPILER_OPTIMAL_ARCHITECTURE_OPTION is not None and \
                self.arch in self.COMPILER_OPTIMAL_ARCHITECTURE_OPTION:
            optarch = self.COMPILER_OPTIMAL_ARCHITECTURE_OPTION[self.arch]
            self.log.info("_get_optimal_architecture: using %s as optarch for %s." % (optarch, self.arch))
            self.options.options_map['optarch'] = optarch

        if 'optarch' in self.options.options_map and self.options.options_map.get('optarch', None) is None:
            self.log.raiseException("_get_optimal_architecture: don't know how to set optarch for %s." % self.arch)

    def comp_family(self, prefix=None):
        """
        Return compiler family used in this toolchain.
        @prefix: Prefix for compiler (e.g. 'CUDA_').
        """
        infix = ''
        if prefix is not None:
            infix = '%s_' % prefix

        comp_family = getattr(self, 'COMPILER_%sFAMILY' % infix, None)
        if comp_family:
            return comp_family
        else:
            self.log.raiseException('comp_family: COMPILER_%sFAMILY is undefined.' % infix)
