##
# Copyright 2012 Stijn De Weirdt
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
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
from distutils.version import LooseVersion

from easybuild.tools import systemtools
from easybuild.tools.modules import get_software_root, get_software_version
from easybuild.tools.toolchain.variables import ToolchainVariables, COMPILER_VARIABLES

from easybuild.tools.toolchain.options import ToolchainOptions

from vsc.fancylogger import getLogger

# constants used for recognizing compilers, MPI libraries, ...
GCC = "GCC"
INTEL = "Intel"


class Compiler(object):
    """General compiler-like class"""

    OPTIONS_CLASS = ToolchainOptions
    VARIABLES_CLASS = ToolchainVariables  # set compiler specific usage

    COMPILER_MODULE_NAME = None

    COMPILER_FAMILY = None

    COMPILER_UNIQUE_OPTS = None
    COMPILER_SHARED_OPTS = {'cciscxx': (False, "Use CC as CXX"), ## also MPI
                            'pic': (False, "Use PIC"), ## also FFTW
                            'noopt': (False, "Disable compiler optiomisations"),
                            'lowopt': (False, "Low compiler optimisation"),
                            'defaultopt':(False, "Default compiler optimisation"), ## not set, but default
                            'opt': (False, "High compiler optimisation"),
                            'optarch':(True, "Enable architecture optimisations"),
                            'strict': (False, "Strict (highest) precision"),
                            'precise':(False, "High precision"),
                            'defaultprec':(False, "Default precision"), ## not set, but default
                            'loose': (False, "Loose precision"),
                            'veryloose': (False, "Very loose precision"),
                            'verbose': (False, "Verbose output"),
                            'debug': (False, "Enabel debug"),
                            'i8': (False, "Intergers are 8 byte integers"), ## fortran only -> no: MKL and icc give -DMKL_ILP64
                            'r8' : (False, "Real is 8 byte real"), ## fortran only
                            'unroll': (False, "Unroll loops"),
                            'cstd': (None, "Specify C standard"),
                            'shared': (False, "Build shared library"),
                            'static': (False, "Build static library"),
                            '32bit':(False, "Compile 32bit target"), ## LA, FFTW
                            'openmp':(False, "Enable OpenMP"),
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

    COMPILER_FLAGS = ['debug', 'verbose', 'static', 'shared', 'openmp', 'pic']  ## any compiler
    COMPILER_OPT_FLAGS = ['noopt', 'lowopt', 'defaultopt', 'opt'] ## optimisation args, ordered !
    COMPILER_PREC_FLAGS = ['strict', 'precise', 'defaultprec', 'loose', 'veryloose'] ## precision flags, ordered !

    COMPILER_CC = None
    COMPILER_CXX = None
    COMPILER_C_FLAGS = ['cstd']
    COMPILER_C_UNIQUE_FLAGS = []

    COMPILER_F77 = None
    COMPILER_F90 = None
    COMPILER_F_FLAGS = ['i8', 'r8']
    COMPILER_F_UNIQUE_FLAGS = []

    TOGGLE_STATIC_DYNAMIC = None

    LIB_MULTITHREAD = None

    def __init__(self):
        if not hasattr(self, 'log'):
            self.log = getLogger(self.__class__.__name__)

        self.arch = None

        self.options = getattr(self, 'options', self.OPTIONS_CLASS())

        self.variables = getattr(self, 'variables', self.VARIABLES_CLASS())

        self._set_compiler_toolchainoptions()

        self._set_compiler_vars()
        self._set_compiler_flags()

        super(Compiler, self).__init__()

    def _set_compiler_toolchainoptions(self):
        ## redefine optarch
        self.COMPILER_SHARED_OPTION_MAP['optarch'] = self._get_optimal_architecture(
                                                                self.COMPILER_SHARED_OPTION_MAP['optarch'])

        self.options.add_options(self.COMPILER_SHARED_OPTS, self.COMPILER_SHARED_OPTION_MAP)

        ## overwrite/add unique compiler specific toolchainoptions
        self.options.add_options(self.COMPILER_UNIQUE_OPTS, self.COMPILER_UNIQUE_OPTION_MAP)

        self.log.debug('_set_compiler_toolchainptions: all current toolchainoptions %s' % self.options)


    def _set_compiler_vars(self):
        """Set the compiler variables"""
        is32bit = self.options.get('32bit', None)
        if is32bit:
            self.log.debug("_set_compiler_vars: 32bit set: changing compiler definitions")

        for var in COMPILER_VARIABLES:
            value = getattr(self, 'COMPILER_%s' % var.upper(), None)
            if value is None:
                self.log.raiseException("_set_compiler_vars: compiler variable %s undefined" % var)
            self.variables[var] = value
            if is32bit:
                self.variables.append_el(var, self.options.option('32bit'))

        if self.options.get('cciscxx', None):
            self.log.debug("_set_compiler_vars: cciscxx set: switching CXX %s for CC value %s" %
                           (self.variables['CXX'], self.variables['CC']))
            self.variables['CXX'] = self.variables['CC']

        self.log.debug('_set_compiler_vars: current variables %s' % self.variables)


    def _set_compiler_flags(self):
        """Collect the flags set, and add them as variables too"""
        flags = [self.options.option(x) for x in self.COMPILER_FLAGS if self.options.get(x, False)]

        cflags = [self.options.option(x) for x in self.COMPILER_C_FLAGS + self.COMPILER_C_UNIQUE_FLAGS \
                  if self.options.get(x, False)]
        fflags = [self.options.option(x) for x in self.COMPILER_F_FLAGS + self.COMPILER_F_UNIQUE_FLAGS \
                  if self.options.get(x, False)]

        ## 1st one is the one to use. add default at the end so len is at least 1
        optflags = [self.options.option(x) for x in self.COMPILER_OPT_FLAGS if self.options.get(x, False)] + \
                   [self.options.option('defaultopt')]

        precflags = [self.options.option(x) for x in self.COMPILER_PREC_FLAGS if self.options.get(x, False)] + \
                    [self.options.option('defaultprec')]

        self.variables.append('OPTFLAGS', optflags)
        self.variables.append('PRECFLAGS', precflags)

        def_flags = flags + optflags[:1] + precflags[:1]

        self.variables.append('CFLAGS', def_flags + cflags)
        self.variables.append('CXXFLAGS', def_flags + cflags)
        self.variables.append('FFLAGS', def_flags + fflags)
        self.variables.append('F90FLAGS', def_flags + fflags)

        self.log.debug('_set_compiler_flags: current variables %s' % self.variables)

    def _get_optimal_architecture(self, optarch):
        """ Get options for the current architecture """
        if self.arch is None:
            self.arch = systemtools.get_cpu_vendor()


        if self.COMPILER_OPTIMAL_ARCHITECTURE_OPTION is not None and \
                self.arch in self.COMPILER_OPTIMAL_ARCHITECTURE_OPTION:
            optarch = self.COMPILER_OPTIMAL_ARCHITECTURE_OPTION[self.arch]
            self.log.info("_get_optimal_architecture: using %s as optarch for %s." % (optarch, self.arch))

        if optarch is None:
            self.log.raiseException("_get_optimal_architecture: don't know how to set optarch for %s." % self.arch)

        return optarch

class Dummy(Compiler):
    """Dummy compiler : try not to even use system gcc"""
    COMPILER_MODULE_NAME = []

    COMPILER_CC = 'DUMMYCC'
    COMPILER_CXX = 'DUMMYCXX'

    COMPILER_F77 = 'DUMMYF77'
    COMPILER_F90 = 'DUMMYF90'


class GNUCompilerCollection(Compiler):
    """GCC compiler class"""
    COMPILER_MODULE_NAME = ['GCC']

    COMPILER_FAMILY = GCC
    COMPILER_UNIQUE_OPTS = {
                            'loop': (False, "Automatic loop parallellisation"),
                            'f2c': (False, "Generate code comaptible with f2c and f77"),
                            'lto':(False, "Enable Link Time Optimisation"),
                            }
    COMPILER_UNIQUE_OPTION_MAP = {
                                  'i8': 'fdefault-integer-8',
                                  'r8': 'fdefault-real-8',
                                  'unroll': 'funroll-loops',
                                  'f2c': 'ff2c',
                                  'loop': ['ftree-switch-conversion', 'floop-interchange',
                                            'floop-strip-mine', 'floop-block'],
                                  'lto':'flto',
                                  'optarch':'march=native',
                                  'openmp':'fopenmp',
                                  'strict': ['mieee-fp', 'mno-recip'],
                                  'precise':['mno-recip'],
                                  'defaultprec':[],
                                  'loose': ['mrecip', 'mno-ieee-fp'],
                                  'veryloose': ['mrecip=all', 'mno-ieee-fp'],
                                  }

    COMPILER_CC = 'gcc'
    COMPILER_CXX = 'g++'
    COMPILER_C_UNIQUE_FLAGS = []

    COMPILER_F77 = 'gfortran'
    COMPILER_F90 = 'gfortran'
    COMPILER_F_UNIQUE_FLAGS = ['f2c']

    LIB_MULTITHREAD = ['pthread']


    def _set_compiler_vars(self):
        super(GNUCompilerCollection, self)._set_compiler_vars()

        if self.options.get('32bit', None):
            self.log.raiseException(("_set_compiler_vars: 32bit set, but no support yet for "
                                     "32bit GCC in EasyBuild"))

        ## to get rid of lots of problems with libgfortranbegin
        ## or remove the system gcc-gfortran
        ## also used in eg LIBBLAS variable
        self.variables.append('FLIBS', "gfortran")


class IntelIccIfort(Compiler):
    """Intel compiler class
        - TODO: install as single package ?
            should be done anyway (all icc versions come with matching ifort version)
    """
    VARIABLES_CLASS = ToolchainVariables


    COMPILER_MODULE_NAME = ['icc', 'ifort']

    COMPILER_FAMILY = INTEL
    COMPILER_UNIQUE_OPTS = {'intel-static': (False, "Link Intel provided libraries statically"),
                            'no-icc': (False, "Don't set Intel specific macros"),
                            }

    COMPILER_UNIQUE_OPTION_MAP = {'i8': 'i8',
                                  'r8':'r8',
                                  'optarch':'xHOST',
                                  'openmp':'openmp',
                                  'strict': ['fp-relaxed', 'fp-speculation=strict', 'fp-model strict'],
                                  'precise':['fp-model precise'],
                                  'defaultprec':['ftz', 'fp-relaxed', 'fp-speculation=safe', 'fp-model source'],
                                  'loose': ['fp-model fast=1'],
                                  'veryloose': ['fp-model fast=2'],
                                  'intel-static': 'static-intel',
                                  'no-icc': 'no-icc'
                                  }

    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = {systemtools.INTEL : 'xHOST',
                                            systemtools.AMD : 'msse3'
                                            }

    COMPILER_CC = 'icc'
    COMPILER_CXX = 'icpc'
    COMPILER_C_UNIQUE_FLAGS = ['intel-static', 'no-icc']

    COMPILER_F77 = 'ifort'
    COMPILER_F90 = 'ifort'
    COMPILER_F_UNIQUE_FLAGS = ['intel-static']

    TOGGLE_STATIC_DYNAMIC = {'static': '-Bstatic',
                             'dynamic':'-Bdynamic',
                             }


    LIB_MULTITHREAD = ['iomp5', 'pthread']  ## iomp5 is OpenMP related : TODO: harmful or not?

    def _set_compiler_vars(self):
        super(IntelIccIfort, self)._set_compiler_vars()

        icc_root = get_software_root('icc')
        icc_version = get_software_version('icc')

        ifort_root = get_software_root('ifort')
        ifort_version = get_software_version('ifort')

        if not ifort_version == icc_version:
            msg = "_set_compiler_vars: mismatch between icc version %s and ifort version %s"
            self.log.raiseException(msg % (icc_version, ifort_version))

        if LooseVersion(icc_version) < LooseVersion('2011'):
            self.LIB_MULTITHREAD.insert(1, "guide")

        if "liomp5" not in self.variables['LIBS']:
            self.variables.extend('LIBS', self.LIB_MULTITHREAD)

        libpaths = ['intel64']
        if self.options.get('32bit', None):
            libpaths.append('ia32')
        libpaths = ['lib/%s' % x for x in libpaths]
        if LooseVersion(icc_version) > LooseVersion('2011.4'):
            libpaths = ['compiler/%s' % x for x in libpaths]

        self.variables.append_subdirs("LDFLAGS", icc_root, subdirs=libpaths)
