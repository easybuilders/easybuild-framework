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
from easybuild.tools.modules import Modules, get_software_root, get_software_version

from easybuild.tools.toolchain.toolkit import INTEL, GCC
from easybuild.tools.toolchain.mpi import INTELMPI, OPENMPI
from easybuild.tools.toolchain.variables import Variables
from easybuild.tools.toolchain.options import Options

from vsc.fancylogger import getLogger

class ScalableLinearAlgebraPackage(object):
    """General LinearAlgebra-like class
        To provide the BLAS/LAPACK/ScaLAPACK tools
    """
    BLAS_MODULE_NAME = None
    BLAS_LIB = None
    BLAS_LIB_MT = None
    BLAS_LIB_MAP = {}
    BLAS_LIB_GROUP = False
    BLAS_LIB_STATIC = False
    BLAS_LIB_DIR = ['lib']
    BLAS_INCLUDE_DIR = ['include']


    LAPACK_IS_BLAS = False
    LAPACK_REQUIRES = ['BLAS']
    LAPACK_MODULE_NAME = None
    LAPACK_LIB = None
    LAPACK_LIB_MT = None
    LAPACK_LIB_DIR = ['lib']
    LAPACK_INCLUDE_DIR = ['include']

    BLACS_MODULE_NAME = None
    BLACS_LIB_DIR = ['lib']
    BLACS_INCLUDE_DIR = ['include']

    SCALAPACK_MODULE_NAME = None
    SCALAPACK_REQUIRES = ['LIBBLACS','LIBLAPACK','LIBBLAS']
    SCALAPACK_LIB = None
    SCALAPACK_LIB_MT = None
    SCALAPACK_LIB_MAP = {}
    SCALAPACK_LIB_GROUP = False
    SCALAPACK_LIB_STATIC = False
    SCALAPACK_LIB_DIR = ['lib']
    SCALAPACK_INCLUDE_DIR = ['include']

    """
    {'packed-groups':False}
    # TODO: some tools (like pkg-utils) don't handle groups well, so pack them if required
    if opts['packed-groups']:
        for x in ['LIBBLAS', 'LIBLAPACK','LIBLAPACK_ONLY' 'LIBSCALAPACK']:
            for var in [x, "%s_MT" % x]:
                vars[var] = self.vars[var].replace(" ", ",")
                vars[var] = self.vars[var].replace(",-Wl,", ",")
    """
    def __init__(self):
        if not hasattr(self, 'log'):
            self.log = getLogger(self.__class__.__name__)

        self.opts = getattr(self, 'opts', Options())

        self.vars = getattr(self, 'vars', Variables())

        ## TODO is link order fully preserved with this order ?
        self._set_blas_vars()
        self._set_lapack_vars()
        self._set_blacs_vars()
        self._set_scalapack_vars()

        super(ScalableLinearAlgebraPackage, self).__init__()

    def _set_blas_vars(self):
        """Set BLAS related variables"""
        root = get_software_root(self.BLAS_MODULE_NAME[0])

        if self.BLAS_LIB is None:
            self.log.raiseException("_set_blas_vars: BLAS_LIB not set")

        self.BLAS_LIB=[x%self.BLAS_LIB_MAP for x in self.BLAS_LIB]

        self.vars.extend_lib_option('LIBBLAS', self.BLAS_LIB, group=self.BLAS_LIB_GROUP,static=self.BLAS_LIB_STATIC)
        if 'FLIBS' in self.vars:
            self.vars.extend_lib_option('LIBBLAS', self.vars['FLIBS'])

        ## multi-threaded
        if self.BLAS_LIB_MT is None:
            ## reuse BLAS variables
            self.vars.extend_lib_option('LIBBLAS_MT', self.vars['LIBBLAS'])
        else:
            self.BLAS_LIB_MT=[x%self.BLAS_LIB_MAP for x in self.BLAS_LIB_MT]
            self.vars.extend_lib_option('LIBBLAS_MT', self.BLAS_LIB_MT, group=self.BLAS_LIB_GROUP,static=self.BLAS_LIB_STATIC)
            if 'FLIBS' in self.vars:
                self.vars.extend_lib_option('LIBBLAS_MT', self.vars['FLIBS'])
            if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                self.vars.extend_lib_option('LIBBLAS_MT', self.LIB_MULTITHREAD)

        root = get_software_root(self.BLAS_MODULE_NAME[0])  ## TODO: deal with multiple modules properly

        self.vars.append_exist('BLAS_LIB_DIR',root, self.BLAS_LIB_DIR)
        self.vars.extend_comma_libs('BLAS_STATIC_LIBS', self.vars['LIBBLAS'],suffx='.a')
        self.vars.extend_comma_libs('BLAS_MT_STATIC_LIBS', self.vars['LIBBLAS_MT'],suffx='.a')


    def _set_lapack_vars(self):
        """Set LAPACK related variables
            and LAPACK only, for (working) use BLAS+LAPACK
        """
        if self.LAPACK_IS_BLAS:
            self.vars.extend_lib_option('LIBLAPACK_ONLY',self.vars['LIBBLAS'])
            self.vars.extend_lib_option('LIBLAPACK_MT_ONLY',self.vars['LIBBLAS_MT'])
            self.vars.extend_lib_option('LIBLAPACK',self.vars['LIBBLAS'])
            self.vars.extend_lib_option('LIBLAPACK_MT',self.vars['LIBBLAS_MT'])
            self.vars.extend_comma_libs('LAPACK_STATIC_LIBS', self.vars['BLAS_STATIC_LIBS'])
            self.vars.extend_comma_libs('LAPACK_MT_STATIC_LIBS', self.vars['BLAS_MT_STATIC_LIBS'])
            self.vars.append_exist('LAPACK_LIB_DIR',self.vars['BLAS_LIB_DIR'])
        else:
            if self.LAPACK_LIB is None:
                self.log.raiseException("_set_lapack_vars: LAPACK_LIB not set")
            self.vars.extend_lib_option('LIBLAPACK_ONLY',self.LAPACK_LIB)

            if self.LAPACK_LIB_MT is None:
                ## reuse LAPACK variables
                self.vars.extend_lib_option('LIBBLAS_MT_ONLY', self.vars['LIBLAPACK_ONLY'])
            else:
                self.vars.extend_lib_option('LIBLAPACK_MT_ONLY', self.LAPACK_LIB_MT)
                if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                    self.vars.extend_lib_option('LIBBLAS_MT_ONLY', self.LIB_MULTITHREAD)

            ## need BLAS for LAPACK ?
            if self.LAPACK_REQUIRES is not None:
                self.vars.join('LIBLAPACK','LIBLAPACK_ONLY',*self.LAPACK_REQUIRES)
                lapack_mt=["%s_MT"%x for x in self.LAPACK_REQUIRES]
                if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                    lapack_mt.extend(self.LIB_MULTITHREAD)
                self.vars.join('LIBLAPACK_MT','LIBLAPACK_MT_ONLY',*lapack_mt)
            else:
                self.vars.extend_lib_option('LIBLAPACK',self.vars['LIBLAPACK_ONLY'])
                self.vars.extend_lib_option('LIBLAPACK_MT',self.vars['LIBLAPACK_MT_ONLY'])

            self.vars.append_comma_libs('LAPACK_STATIC_LIBS',self.vars['LIBLAPACK'] ,suffx='.a')
            self.vars.append_comma_libs('LAPACK_MT_STATIC_LIBS', self.vars['LIBLAPACK_MT'],suffx='.a')

            root = get_software_root(self.BLAS_MODULE_NAME[0])  ## TODO: deal with multiple modules properly
            self.vars.extend_subdirs_option('LAPACK_LIB_DIR',root, self.LAPACK_LIB_DIR)

        self.vars.join('BLAS_LAPACK_LIB_DIR','LAPACK_LIB_DIR','BLAS_LIB_DIR')
        self.vars.join('BLAS_LAPACK_STATIC_LIBS', 'LAPACK_STATIC_LIBS','BLAS_STATIC_LIBS')
        self.vars.join('BLAS_LAPACK_MT_STATIC_LIBS','LAPACK_MT_STATIC_LIBS','BLAS_STATIC_LIBS')


    def _set_blacs_vars(self):
        """Set BLACS related variables"""

        self.BLACS_LIB=[x%self.BLACS_LIB_MAP for x in self.BLACS_LIB]

        ## BLACS
        self.vars.extend_lib_option('LIBBLACS',self.BLACS_LIBS)
        if self.BLACS_LIB_MT is None:
            self.vars.extend_lib_option('LIBBLACS_MT', self.vars['LIBBLACS'])
        else:
            self.log.raiseException("_set_blacs_vars: setting LIBBLACS_MT from self.BLACS_LIB_MT not implemented")

        root = get_software_root(self.BLACS_MODULE_NAME[0])  ## TODO: deal with multiple modules properly

        self.vars.append_exist('BLACS_LIB_DIR',root, self.BLACS_LIB_DIR)
        self.vars.append_exist('BLACS_INC_DIR',root, self.BLACS_INCLUDE_DIR)
        self.vars.extend_comma_libs('BLCAS_STATIC_LIBS', self.vars['LIBBLACS'],suffx='.a')
        self.vars.extend_comma_libs('BLACS_MT_STATIC_LIBS', self.vars['LIBBLACS_MT'],suffx='.a')

    def _set_scalapack_vars(self):
        """Set ScaLAPACK related variables"""

        if self.SCALAPACK_LIB is None:
            self.log.raiseException("_set_blas_vars: SCALAPACK_LIB not set")

        self.SCALAPACK_LIB=[x%self.SCALAPACK_LIB_MAP for x in self.SCALAPACK_LIB]

        self.vars.extend_lib_option('LIBSCALAPACK_ONLY', self.SCALAPACK_LIB, group=self.SCALAPACK_LIB_GROUP,static=self.SCALAPACK_LIB_STATIC)
        if 'FLIBS' in self.vars:
            self.vars.extend_lib_option('LIBSCALAPACK_ONLY', self.vars['FLIBS'])

        ## multi-threaded
        if self.SCALAPACK_LIB_MT is None:
            ## reuse BLAS variables
            self.vars.extend_lib_option('LIBSCALAPACK_MT_ONLY', self.vars['LIBSCALAPCK_ONLY'])
        else:
            self.SCALAPACK_LIB_MT=[x%self.SCALAPACK_LIB_MAP for x in self.SCALAPACK_LIB_MT]
            self.vars.extend_lib_option('LIBSCALAPACK_MT_ONLY', self.SCALAPACK_LIB_MT, group=self.SCALAPACK_LIB_GROUP,static=self.SCALAPACK_LIB_STATIC)
            if 'FLIBS' in self.vars:
                self.vars.extend_lib_option('LIBSCALAPACK_MT_ONLY', self.vars['FLIBS'])
            if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                self.vars.extend_lib_option('LIBSCALAPACK_MT_ONLY', self.LIB_MULTITHREAD)

        root = get_software_root(self.SCALAPACK_MODULE_NAME[0])  ## TODO: deal with multiple modules properly


        if self.SCALAPACK_REQUIRES is not None:
            self.vars.join('LIBSCALAPACK','LIBSCALAPACK_ONLY',*self.SCALAPACK_REQUIRES)
            scalapack_mt=["%s_MT"%x for x in self.SCALAPACK_REQUIRES]
            if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                lapack_mt.extend(self.LIB_MULTITHREAD)
            self.vars.join('LIBSCALAPACK_MT','LIBSCALAPACK_MT_ONLY',*scalapack_mt)
        else:
            self.log.raiseException("_set_scalapack_vars: LIBSCALAPACK without SCALAPACK_REQUIRES not implemented")


        self.vars.append_exist('SCALAPACK_LIB_DIR',root, self.SCALAPACK_LIB_DIR)
        self.vars.append_exist('SCALAPACK_INC_DIR',root, self.SCALAPACK_INCLUDE_DIR)
        self.vars.extend_comma_libs('SCALAPACK_STATIC_LIBS', self.vars['LIBSCALAPACK'],suffx='.a')
        self.vars.extend_comma_libs('SCALAPACK_MT_STATIC_LIBS', self.vars['LIBSCALAPACK_MT'],suffx='.a')


class GotoBLAS(object):
    """
    Trivial class
        provides GotoBLAS
    """
    BLAS_MODULE_NAME = ['GotoBLAS']
    BLAS_LIB = ['goto']


class LAPACK(object):
    """Trivial class
        provides LAPACK
    """
    LAPACK_MODULE_NAME = ['LAPACK']
    LAPACK_LIB = ['lapack']

class FLAME(LAPACK):
    """Less trivial module"""
    LAPACK_MODULE_NAME = ['FLAME'] + super(FLAME).LAPACK_MODULE_NAME
    LAPACK_LIB = ['lapack2flame', 'flame'] + super(FLAME).LAPACK_LIB

class ATLAS(object):
    """
    Trivial class
        provides ATLAS BLAS and LAPACK
            LAPACK is a build dependency only
    """
    BLAS_MODULE_NAME = ['ATLAS']
    BLAS_LIB = ["cblas", "f77blas", "atlas"]
    BLAS_LIB_MT = ["ptcblas", "ptf77blas", "atlas"]

    LAPACK_MODULE_NAME = ['ATLAS']
    LAPACK_LIB = ['lapack']

class ACML(object):
    """
    Trivial class
        provides ACML BLAS and LAPACK
    """
    BLAS_MODULE_NAME = ['ACML']
    BLAS_LIB = ['acml_mv', 'acml']

    LAPACK_MODULE_NAME = ['ACML']
    LAPACK_IS_BLAS = True

class BLACS(object):
    """
    Trivial class
        provides BLACS
    """
    BLACS_MODULE_NAME = ['BLACS']
    BLACS_LIB=["blacsCinit", "blacsF77init", "blacs"]


class ScaLAPACK(object):
    """Trivial class
        provides ScaLAPACK
    """
    SCALAPACK_MODULE_NAME = ['ScaLAPACK']


class IntelMKL(ScalableLinearAlgebraPackage):
    """Interface to Intel MKL"""
        # MKL libraries for BLACS, BLAS, LAPACK, ScaLAPACK routines
        blacs_libs = ["blacs%s" % libsfx]
        blas_libs = ["intel%s" % libsfx, "sequential", "core"]
        blas_mt_libs = ["intel%s" % libsfx, "intel_thread", "core"]
        scalapack_libs = ["scalapack%s" % libsfxsl, "solver%s_sequential" % libsfx] + blas_libs + ["blacs_intelmpi%s" % libsfx]
        scalapack_mt_libs = ["scalapack%s" % libsfxsl, "solver%s" % libsfx] + blas_mt_libs + ["blacs_intelmpi%s" % libsfx]

    BLAS_MODULE_NAME = ['imkl']
    BLAS_LIB_MAP = {"lp64":'_lp64',
                    "interface":None,
                    "interface_mt":None,
                    }
    BLAS_LIB = ["mkl_%(interface)s%(lp64)s" , "mkl_sequential", "mkl_core"]
    BLAS_LIB_MT = ["mkl_%(interface)s%(lp64)s" , "mkl_%(interface_mt)s_thread", "mkl_core"]
    BLAS_LIB_GROUP = True
    BLAS_LIB_STATIC = True

    LAPACK_MODULE_NAME = ['imkl']
    LAPACK_IS_BLAS = True

    BLACS_MODULE_NAME = ['imkl']
    BLACS_LIB_MPI = ["mkl_blacs_%(mpi)s%(lp64)s]
    BLACS_LIB = ["mkl_blacs%(lp64)s"]+self.BLACS_LIB_MPI
    BLACS_LIB_MAP = {'mpi':None}

    SCALAPACK_MODULE_NAME = ['imkl']
    SCALAPACK_LIB = ["mkl_scalapack%(lp64_sc)s","mkl_solver%(lp64)s_sequential"]
    SCALAPACK_LIB_MT = ["mkl_scalapack%(lp64_sc)s","mkl_solver%(lp64)s"]
    SCALAPACK_LIB_MAP = {"lp64_sc":"_lp64"}
    SCALAPACK_REQUIRES = ['LIBBLACS','LIBBLAS']
    SCALAPACK_LIB_GROUP = True
    SCALAPACK_LIB_STATIC = True

    def _set_blas_vars(self):
        """Fix the map a bit"""
        interfacemap = {INTEL:'intel',
                        GCC:'gf',
                        }
        try:
            self.BLAS_LIB_MAP.update({"interface":interfacemap[self.COMPILER_FAMILY]})
        except:
            self.raiseException("_set_blas_vars: interface unsupported combination with MPI family %s"%self.COMPILER_FAMILY)

        interfacemap_mt = {INTEL:'intel',
                           GCC:'gnu',
                           }
        try:
            self.BLAS_LIB_MAP.update({"interface_mt":interfacemap_mt[self.COMPILER_FAMILY]})
        except:
            self.raiseException("_set_blas_vars: interface_mt unsupported combination with compiler family %s"%self.COMPILER_FAMILY)


        if self.opts.get('32bit', None):
            ## 32bit
            self.BLAS_LIB_MAP.update({"lp64":''})
        if self.opts.get('i8', None):
            ## ilp64/i8
            self.BLAS_LIB_MAP.update({"lp64":'_ilp64'})
            ## CPP / CFLAGS
            self.vars.append_option('CFLAGS', 'DMKL_ILP64')

        # exact paths/linking statements depend on imkl version
        found_version=get_software_version(self.BLAS_MODULE_NAME[0])
        if LooseVersion(found_version) < LooseVersion('10.3'):
            if self.opts.get('32bit', None):
                self.BLAS_LIB_DIR = ['lib/32']
            else:
                self.BLAS_LIB_DIR = ['lib/em64t']
            self.BLAS_INCL_DIR = ['include']
        else:
            if self.opts.get('32bit', None):
                self.log.raiseException("_set_blas_vars: 32-bit libraries not supported yet for IMKL v%s (> v10.3)" % found_version)
            else:
                self.BLAS_LIB_DIR = ['mkl/lib/intel64','compiler/lib/intel64' ]

            self.BLAS_INCL_DIR =  = ['mkl/include']


        super(IntelMKL, self)._set_blas_vars()

    def _set_blacs_vars(self):
        mpimap={INTELMPI:'intelmpi',
                OPENMPI:'openmpi',
                }
        try:
            self.BLACS_LIB_MAP.update({'mpi':mpimap[self.MPI_FAMILY})
        except:
            self.raiseException("_set_blacs_vars: mpi unsupported combination with MPI family %s"%self.MPI_FAMILY)

        self.BLACS_LIB_DIR = self.BLAS_LIB_DIR
        self.BLACS_INCLUDE_DIR=self.BLAS_INCLUDE_DIR

        super(IntelMKL, self)._set_blacs_vars()

    def _set_scalapack_vars(self):
        if self.opts.get('32bit', None):
            ##32 bit
            self.SCALAPACK_LIB_MAP.update({"lp64_sc":'_core'})


        super(IntelMKL, self)._set_scalapack_vars()


###############################################################################################################################
###############################################################################################################################

    def prepareACML(self):
        """
        Prepare for AMD Math Core Library (ACML)
        """

        if self.opts['32bit']:
            self.log.error("ERROR: 32-bit not supported (yet) for ACML.")

        self._addDependencyVariables(['ACML'])

        acml = get_software_root('ACML')

        if self.comp_family() == GCC:
            compiler = 'gfortran'
        elif self.comp_family() == INTEL:
            compiler = 'ifort'
        else:
            self.log.error("Don't know which compiler-specific subdir for ACML to use.")

        self.vars['LDFLAGS'] += " -L%s/%s64/lib/ " % (acml, compiler)


    def prepareGotoBLAS(self):
        """
        Prepare for GotoBLAS BLAS library
        """


        self._addDependencyVariables(['GotoBLAS'])


    def prepareLAPACK(self):
        """
        Prepare for LAPACK library
        """

        lapack = get_software_root("LAPACK")


        self._addDependencyVariables(['LAPACK'])

    def prepareATLAS(self):
        """
        Prepare for ATLAS BLAS/LAPACK library
        """
        atlas = get_software_root("ATLAS")


        self._addDependencyVariables(['ATLAS'])

    def prepareBLACS(self):
        """
        Prepare for BLACS library
        """

        blacs = get_software_root("BLACS")
        # order matters!

        self._addDependencyVariables(['BLACS'])

    def prepareFLAME(self):
        """
        Prepare for FLAME library
        """


        self._addDependencyVariables(['FLAME'])


    def prepareScaLAPACK(self):
        """
        Prepare for ScaLAPACK library
        """

        scalapack = get_software_root("ScaLAPACK")


        self._addDependencyVariables(['ScaLAPACK'])

    def prepareIMKL(self):
        """
        Prepare toolkit for IMKL: Intel Math Kernel Library
        """

        mklroot = os.getenv('MKLROOT')
        if not mklroot:
            self.log.error("MKLROOT not found in environment")

        # exact paths/linking statements depend on imkl version
        if LooseVersion(get_software_version('IMKL')) < LooseVersion('10.3'):
            if self.opts['32bit']:
                mklld = ['lib/32']
            else:
                mklld = ['lib/em64t']
            mklcpp = ['include', 'include/fftw']
        else:
            if self.opts['32bit']:
                root = get_software_root("IMKL")
                self.log.error("32-bit libraries not supported yet for IMKL v%s (> v10.3)" % root)

            mklld = ['lib/intel64', 'mkl/lib/intel64']
            mklcpp = ['mkl/include', 'mkl/include/fftw']


        # determine BLACS/BLAS/LAPACK/FFTW library dir
        libs_dir = None
        for ld in mklld:
            fld = os.path.join(mklroot, ld)
            if os.path.isdir(fld):
                libs_dir = fld
        if not libs_dir:
            self.log.error("")
        else:

        # BLACS library
        self.vars['BLACS_INC_DIR'] = os.path.join(mklroot, "mkl", "include")
        self.vars['BLACS_LIB_DIR'] = libs_dir
        self.vars['BLACS_STATIC_LIBS'] = ','.join(["libmkl_%s.a" % x for x in blacs_libs])
        self.vars['BLACS_MT_STATIC_LIBS'] = self.vars['BLACS_STATIC_LIBS']


        # FFT library
        fftwsuff = ""
        if self.opts['pic']:
            fftwsuff = "_pic"
        fftw_libs = ["fftw3xc_intel%s" % fftwsuff,
                     "fftw3x_cdft%s" % fftwsuff,
                     "mkl_cdft_core"]
        self.vars['LIBFFT'] = ' '.join(["-Wl,-Bstatic",
                                        ' '.join(["-%s" % x for x in fftw_libs]),
                                        "-Wl,-Bdynamic"])
        self.vars['FFTW_INC_DIR'] = os.path.join(mklroot, "mkl", "include", "fftw")
        self.vars['FFTW_LIB_DIR'] = libs_dir
        fftw_static_libs = ["lib%s.a" % x for x in fftw_libs]
        self.vars['FFTW_STATIC_LIBS'] = ','.join(fftw_static_libs + [self.vars['BLAS_STATIC_LIBS'],
                                                                     self.vars['BLACS_STATIC_LIBS']])


        # linker flags
        self._flagsForSubdirs(mklroot, mklld, flag="-L%s", varskey="LDFLAGS")
        self._flagsForSubdirs(mklroot, mklcpp, flag="-I%s", varskey="CPPFLAGS")
