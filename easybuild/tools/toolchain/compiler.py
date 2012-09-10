##
# Copyright 2009-2012 Stijn De Weirdt
# Copyright 2010 Dries Verdegem
# Copyright 2010-2012 Kenneth Hoste
# Copyright 2011 Pieter De Baets
# Copyright 2011-2012 Jens Timmerman
# Copyright 2012 Toon Willems
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
import copy
import os
from distutils.version import LooseVersion

import easybuild.tools.environment as env
from easybuild.tools import systemtools
from easybuild.tools.build_log import getLog
from easybuild.tools.modules import Modules, get_software_root, get_software_version

class Vars(dict):
    """Extend dict with

    ## example code
    v=Vars()
    v.extend('CFLAGS',['O3','lto'])
    v.flags_for_subdirs('LDFLAGS','/usr',subdirs=['lib','lib64','unknown'])


    for o in ['CFLAGS','LDFLAGS']:
        print o, v.options(o)

    ## output
    2012-09-10 08:11:52,189 WARNING    test.Vars       MainThread  _flags_for_subdirs: directory /usr/unknown was not found
    CFLAGS -O3 -lto
    LDFLAGS -L/usr/lib -L/usr/lib64

    """
    def __init__(self, *args, **kwargs):
        super(Vars, self).__init__(*args, **kwargs)
        self.log = getLog(self.__class__.__name__)

    def append(self, k, v):
        """append (k,v) : if k does not ,exists, initialise a list; append v to list"""

        tmp = self.setdefault(k, [])
        tmp.append(v)

    def extend(self, k, v):
        """extend (k,v) : if k does not ,exists, initialise a list; extend list with v"""
        tmp = self.setdefault(k, [])
        tmp.extend(v)

    def options(self, k):
        """options(k):
                print as option: if list, add '-' to each item, otherwise just return
        """
        res = self.__getitem__(k)
        if isinstance(res, (list,)):
            tmp = []
            for x in res:
                if isinstance(x, (list, tuple,)):
                    tmp.extend(x)
                else:
                    tmp.append(x)
            res = " ".join(["-%s" % x for x in tmp])
        return res

    def flags_for_subdirs(self, var, base  , subdirs=None, flag=None):
        """Generate flags to pass to the compiler """
        if flag is None:
            if var == 'LDFLAGS':
                flag = "L"
            elif var == 'CPPFLAGS':
                flag = 'I'
            else:
                self.log.raiseException("flags_for_subdirs: flag not set and can't derive value for var %s" % var)
        flags = []
        if subdirs is None:
            subdirs = ['']
        for subdir in subdirs:
            directory = os.path.join(base, subdir).rstrip(os.sep)
            if os.path.isdir(directory):
                flags.append("%s%s" % (flag , directory))
            else:
                self.log.warning("flags_for_subdirs: directory %s was not found" % directory)

        self.extend(var, flags)

    def flags_for_libs(self, var, libs):
        """Given libs, add them prefixed with 'l' """
        if isinstance(libs, str):
            libs = [libs]
        self.extend(var, ["l%s" % x for x in libs])


class Compiler(object):
    """General compiler-like class"""
    COMPILER_UNIQUE_OPTS = None
    COMPILER_SHARED_OPTS = {'cciscxx': False, ## also MPI
                            'pic': False, ## also FFTW
                            'noopt': False,
                            'lowopt': False,
                            'defaultopt':False, ## not set, but default
                            'opt': False,
                            'optarch':True,
                            'strict': False,
                            'precise':False,
                            'defaultprec':False, ## not set, but default
                            'loose': False,
                            'veryloose': False,
                            'verbose': False,
                            'debug': False,
                            'i8': False, ## fortran only
                            'r8' : False, ## fortran only
                            'unroll': False,
                            'cstd': None,
                            'shared': False,
                            'static': False,
                            '32bit':False, ## LA, FFTW
                            'openmp':False,
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
                                  'cstd':'std=%(opt)s',
                                  }

    COMPILER_OPTIMAL_ARCHITECTURE_OPTION = None

    COMPILER_FLAGS = ['debug', 'verbose', 'static', 'shared', 'openmp', 'pic']  ## any compiler
    COMPILER_OPT_FLAGS = ['noopt', 'lowopt', 'defaultopt', 'opt'] ## optimisation args, ordered !
    COMPILER_PREC_FLAGS = ['strict', 'precise', 'defaultprec', 'loose', 'veryloose'] ## precision flags, ordered !

    COMPILER_CC = None
    COMPILER_CXX = None
    COMPILER_C_FLAGS = ['cstd']
    COMPILER_C_UNIQUE_FLAGS = []

    COMPILER_F70 = None
    COMPILER_F90 = None
    COMPILER_F_FLAGS = ['i8', 'r8']
    COMPILER_F_UNIQUE_FLAGS = []

    def __init__(self):
        if not hasattr(self, 'log'):
            self.log = getLog(self.__class__.__name__)

        self.arch = None

        self.opts = getattr(self, 'opts', {})
        self.option_map = getattr(self, 'option_map', {})

        self.vars = getattr(self, 'vars', Vars())

        self._set_compiler_opts()
        self._set_compiler_option_map()
        self._set_compiler_vars()
        self._set_compiler_flags()

        super(Compiler, self).__init__()

    def _set_compiler_opts(self):
        opts = self.COMPILER_SHARED_OPTS
        if self.COMPILER_UNIQUE_OPTS is not None:
            opts.update(self.COMPILER_UNIQUE_OPTS)

        self.log.debug('_set_compiler_opts: setting opts %s' % opts)

        self.opts.update(opts)

    def _set_compiler_option_map(self):
        option_map = self.COMPILER_SHARED_OPTION_MAP
        if self.COMPILER_UNIQUE_OPTION_MAP is not None:
            option_map.update(self.COMPILER_UNIQUE_OPTION_MAP)
        self.log.debug('_set_compiler_option_map: setting option_map %s' % option_map)

        ## sanity check: do all options from the optionmap have a corresponding entry in opts
        ## - reverse is not necessarily an issue
        for k in option_map.keys():
            if not k in self.opts:
                self.log.raiseException("_set_compiler_option_map: entry %s in option_map has not option with that name" % k)

        ## redefine optarch
        option_map['optarch'] = self._get_optimal_architecture(option_map['optarch'])

        self.option_map.update(option_map)

    def _get_compiler_option(self, name):
        """Return option value"""
        opt = self.option.get(name, None)
        if opt is None:
            self.log.warning("_get_compiler_option: opt with name %s returns None" % name)
            res = None
        elif isinstance(opt, bool):
            ## check if True?
            res = self.option_map[name]
        else:
            ## allow for template
            res = self.option_map[name] % {'opt':opt}

        return res

    def _set_compiler_vars(self):
        """Set the compiler variables"""
        varis = {}

        is32bit = self.opts.get('32bit', None)
        if is32bit:
            self.log.debug("_set_compiler_vars: 32bit set: changing compiler definitions")

        compiler_vars = ['CC', 'CXX', 'F70', 'F90']
        for var in compiler_vars:
            value = getattr(self, 'COMPILER_%s' % var.upper(), None)
            if value is None:
                self.log.raiseException("_set_compiler_vars: compiler variable %s undefined" % var)
            if is32bit:
                value += " -%s" % (self._get_compiler_option('32bit'))
            varis[var] = value  ## not a list. is not an option.

        if self.opts.get('cciscxx', None):
            self.log.debug("_set_compiler_vars: cciscxx set: switching CXX %s for CC value %s" % (varis['CXX'], varis['CC']))
            varis['CXX'] = varis['CC']

        self.vars.update(varis)


    def _set_compiler_flags(self):
        """Collect the flags set, and add them as variables too"""
        flags = [ self._get_compiler_option(x) for x in self.COMPILER_FLAGS if self.opts.get(x, False)]

        cflags = [ self._get_compiler_option(x) for x in self.COMPILER_C_FLAGS + self.COMPILER_C_UNIQUE_FLAGS if self.opts.get(x, False)]
        fflags = [ self._get_compiler_option(x) for x in self.COMPILER_F_FLAGS + self.COMPILER_F_UNIQUE_FLAGS if self.opts.get(x, False)]

        ## 1st one is the one to use. add default at the end so len is at least 1
        optflags = [self._get_compiler_option(x) for x in self.COMPILER_OPT_FLAGS if self.opts.get(x, False)] + [self._get_compiler_option('defaultopt')]
        precflags = [self._get_compiler_option(x) for x in self.COMPILER_PREC_FLAGS if self.opts.get(x, False)] + [self._get_compiler_option('defaultprec')]

        def_flags = flags + optflags[:1] + precflags[:1]

        self.vars.extend('CFLAGS', def_flags + cflags)
        self.vars.extend('CXXFLAGS', def_flags + cflags)
        self.vars.extend('FFLAGS', def_flags + fflags)
        self.vars.extend('F90FLAGS', def_flags + fflags)


    def _get_optimal_architecture(self, optarch):
        """ Get options for the current architecture """
        if self.arch is None:
            self.arch = systemtools.get_cpu_vendor()


        if self.COMPILER_OPTIMAL_ARCHITECTURE_OPTION is not None and self.arch in self.COMPILER_OPTIMAL_ARCHITECTURE_OPTION:
            optarch = self.COMPILER_OPTIMAL_ARCHITECTURE_OPTION[self.arch]
            self.log.info("_get_optimal_architecture: using %s as optarch for %s." % (optarch, self.arch))

        if optarch is None:
            self.log.raiseException("_get_optimal_architecture: don't know how to set optarch for %s." % self.arch)

        return optarch


class GCC(Compiler):
    """GCC compiler class"""
    COMPILER_UNIQUE_OPTS = {'loop': False,
                            'f2c': False,
                            'lto':False
                            }
    COMPILER_UNIQUE_OPTION_MAP = {'i8': 'fdefault-integer-8',
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

    COMPILER_F70 = 'gfortran'
    COMPILER_F90 = 'gfortran'
    COMPILER_F_UNIQUE_FLAGS = []

    def _set_compiler_vars(self):
        super(GCC, self)._set_compiler_vars()

        if self.opts.get('32bit', None):
            self.log.raiseException("_set_compiler_vars: 32bit set, but no support yet for 32bit GCC in EasyBuild")

        ## to get rid of lots of problems with libgfortranbegin
        ## or remove the system gcc-gfortran
        self.vars.flags_for_libs('FLIBS', "gfortran")


class IccIfort(Compiler):
    """Intel compiler class
        - TODO: install as single package ?
            should be done anyway (all icc versions come with matching ifort version)
    """
    COMPILER_UNIQUE_OPTS = {'intel-static': False,
                            'no-icc': False,
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

    COMPILER_F70 = 'ifort'
    COMPILER_F90 = 'ifort'
    COMPILER_F_UNIQUE_FLAGS = ['intel-static']

    def _set_compiler_vars(self):
        super(IccIfort, self)._set_compiler_vars()

        icc_root = get_software_root('icc')
        icc_version = get_software_version('icc')

        ifort_root = get_software_root('ifort')
        ifort_version = get_software_version('ifort')

        if not ifort_version == icc_version:
            self.log.raiseException("_set_compiler_vars: mismatch between icc version %s and ifort version %s" % (icc_version, ifort_version))

        if "liomp5" not in self.vars['LIBS']:
            libs = ['iomp5', 'pthread']
            if LooseVersion(icc_version) < LooseVersion('2011'):
                libs.insert(1, "guide")
            self.vars.flags_for_libs('LIBS', libs)

        libpaths = ['intel64']
        if self.opts.get('32bit', None):
            libpaths.append('ia32')
        libpaths = ['lib/%s' % x for x in libpaths]
        if LooseVersion(icc_version) > LooseVersion('2011.4'):
            libpaths = ['compiler/%s' % x for x in libpaths]

        self.vars.flags_for_subdirs("LDFLAGS", icc_root, subdirs=libpaths)

