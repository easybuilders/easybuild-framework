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
import os
from distutils.version import LooseVersion

from easybuild.tools.modules import get_software_root, get_software_version

from easybuild.tools.toolchain.compiler import INTEL, GCC
from easybuild.tools.toolchain.mpi import INTELMPI, OPENMPI
from easybuild.tools.toolchain.variables import ToolchainVariables
from easybuild.tools.toolchain.options import ToolchainOptions

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
    SCALAPACK_REQUIRES = ['LIBBLACS', 'LIBLAPACK', 'LIBBLAS']
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
    if options['packed-groups']:
        for x in ['LIBBLAS', 'LIBLAPACK','LIBLAPACK_ONLY' 'LIBSCALAPACK']:
            for var in [x, "%s_MT" % x]:
                variables[var] = self.variables[var].replace(" ", ",")
                variables[var] = self.variables[var].replace(",-Wl,", ",")
    """
    def __init__(self, *args, **kwargs):
        if not hasattr(self, 'log'):
            self.log = getLogger(self.__class__.__name__)

        self.options = getattr(self, 'options', ToolchainOptions())

        self.variables = getattr(self, 'variables', ToolchainVariables())

        super(ScalableLinearAlgebraPackage, self).__init__(*args, **kwargs)

    def set_variables(self):
        """Set the variables"""
        ## TODO is link order fully preserved with this order ?
        self._set_blas_vars()
        self._set_lapack_vars()
        self._set_blacs_vars()
        self._set_scalapack_vars()

        self.log.debug('set_variables: scalapack variables %s' % self.variables)
        super(ScalableLinearAlgebraPackage, self).set_variables()

    def _set_blas_variables(self):
        """Set BLAS related variables"""
        if self.BLAS_LIB is None:
            self.log.raiseException("_set_blas_variables: BLAS_LIB not set")

        self.BLAS_LIB = [x % self.BLAS_LIB_MAP for x in self.BLAS_LIB]

        self.variables.extend_lib_option('LIBBLAS', self.BLAS_LIB, group=self.BLAS_LIB_GROUP, static=self.BLAS_LIB_STATIC)
        if 'FLIBS' in self.variables:
            self.variables.extend_lib_option('LIBBLAS', self.variables['FLIBS'])

        ## multi-threaded
        if self.BLAS_LIB_MT is None:
            ## reuse BLAS variables
            self.variables.extend_lib_option('LIBBLAS_MT', self.variables['LIBBLAS'])
        else:
            self.BLAS_LIB_MT = [x % self.BLAS_LIB_MAP for x in self.BLAS_LIB_MT]
            self.variables.extend_lib_option('LIBBLAS_MT', self.BLAS_LIB_MT, group=self.BLAS_LIB_GROUP, static=self.BLAS_LIB_STATIC)
            if 'FLIBS' in self.variables:
                self.variables.extend_lib_option('LIBBLAS_MT', self.variables['FLIBS'])
            if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                self.variables.extend_lib_option('LIBBLAS_MT', self.LIB_MULTITHREAD)

        root = get_software_root(self.BLAS_MODULE_NAME[0])  ## TODO: deal with multiple modules properly

        self.variables.append_exist('BLAS_LIB_DIR', root, self.BLAS_LIB_DIR)
        self.variables.extend_comma_libs('BLAS_STATIC_LIBS', self.variables['LIBBLAS'], suffx='.a')
        self.variables.extend_comma_libs('BLAS_MT_STATIC_LIBS', self.variables['LIBBLAS_MT'], suffx='.a')

    def _set_lapack_variables(self):
        """Set LAPACK related variables
            and LAPACK only, for (working) use BLAS+LAPACK
        """
        if self.LAPACK_IS_BLAS:
            self.variables.extend_lib_option('LIBLAPACK_ONLY', self.variables['LIBBLAS'])
            self.variables.extend_lib_option('LIBLAPACK_MT_ONLY', self.variables['LIBBLAS_MT'])
            self.variables.extend_lib_option('LIBLAPACK', self.variables['LIBBLAS'])
            self.variables.extend_lib_option('LIBLAPACK_MT', self.variables['LIBBLAS_MT'])
            self.variables.extend_comma_libs('LAPACK_STATIC_LIBS', self.variables['BLAS_STATIC_LIBS'])
            self.variables.extend_comma_libs('LAPACK_MT_STATIC_LIBS', self.variables['BLAS_MT_STATIC_LIBS'])
            self.variables.append_exist('LAPACK_LIB_DIR', self.variables['BLAS_LIB_DIR'])
        else:
            if self.LAPACK_LIB is None:
                self.log.raiseException("_set_lapack_variables: LAPACK_LIB not set")
            self.variables.extend_lib_option('LIBLAPACK_ONLY', self.LAPACK_LIB)

            if self.LAPACK_LIB_MT is None:
                ## reuse LAPACK variables
                self.variables.extend_lib_option('LIBBLAS_MT_ONLY', self.variables['LIBLAPACK_ONLY'])
            else:
                self.variables.extend_lib_option('LIBLAPACK_MT_ONLY', self.LAPACK_LIB_MT)
                if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                    self.variables.extend_lib_option('LIBBLAS_MT_ONLY', self.LIB_MULTITHREAD)

            ## need BLAS for LAPACK ?
            if self.LAPACK_REQUIRES is not None:
                self.variables.join('LIBLAPACK', 'LIBLAPACK_ONLY', *self.LAPACK_REQUIRES)
                lapack_mt = ["%s_MT" % x for x in self.LAPACK_REQUIRES]
                if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                    lapack_mt.extend(self.LIB_MULTITHREAD)
                self.variables.join('LIBLAPACK_MT', 'LIBLAPACK_MT_ONLY', *lapack_mt)
            else:
                self.variables.extend_lib_option('LIBLAPACK', self.variables['LIBLAPACK_ONLY'])
                self.variables.extend_lib_option('LIBLAPACK_MT', self.variables['LIBLAPACK_MT_ONLY'])

            self.variables.append_comma_libs('LAPACK_STATIC_LIBS', self.variables['LIBLAPACK'] , suffx='.a')
            self.variables.append_comma_libs('LAPACK_MT_STATIC_LIBS', self.variables['LIBLAPACK_MT'], suffx='.a')

            root = get_software_root(self.BLAS_MODULE_NAME[0])  ## TODO: deal with multiple modules properly
            self.variables.extend_subdirs_option('LAPACK_LIB_DIR', root, self.LAPACK_LIB_DIR)

        self.variables.join('BLAS_LAPACK_LIB_DIR', 'LAPACK_LIB_DIR', 'BLAS_LIB_DIR')
        self.variables.join('BLAS_LAPACK_STATIC_LIBS', 'LAPACK_STATIC_LIBS', 'BLAS_STATIC_LIBS')
        self.variables.join('BLAS_LAPACK_MT_STATIC_LIBS', 'LAPACK_MT_STATIC_LIBS', 'BLAS_STATIC_LIBS')

    def _set_blacs_variables(self):
        """Set BLACS related variables"""

        self.BLACS_LIB = [x % self.BLACS_LIB_MAP for x in self.BLACS_LIB]

        ## BLACS
        self.variables.extend_lib_option('LIBBLACS', self.BLACS_LIBS)
        if self.BLACS_LIB_MT is None:
            self.variables.extend_lib_option('LIBBLACS_MT', self.variables['LIBBLACS'])
        else:
            self.log.raiseException("_set_blacs_variables: setting LIBBLACS_MT from self.BLACS_LIB_MT not implemented")

        root = get_software_root(self.BLACS_MODULE_NAME[0])  ## TODO: deal with multiple modules properly

        self.variables.append_exist('BLACS_LIB_DIR', root, self.BLACS_LIB_DIR)
        self.variables.append_exist('BLACS_INC_DIR', root, self.BLACS_INCLUDE_DIR)
        self.variables.extend_comma_libs('BLCAS_STATIC_LIBS', self.variables['LIBBLACS'], suffx='.a')
        self.variables.extend_comma_libs('BLACS_MT_STATIC_LIBS', self.variables['LIBBLACS_MT'], suffx='.a')

    def _set_scalapack_variables(self):
        """Set ScaLAPACK related variables"""

        if self.SCALAPACK_LIB is None:
            self.log.raiseException("_set_blas_variables: SCALAPACK_LIB not set")

        self.SCALAPACK_LIB = [x % self.SCALAPACK_LIB_MAP for x in self.SCALAPACK_LIB]

        self.variables.extend_lib_option('LIBSCALAPACK_ONLY', self.SCALAPACK_LIB, group=self.SCALAPACK_LIB_GROUP, static=self.SCALAPACK_LIB_STATIC)
        if 'FLIBS' in self.variables:
            self.variables.extend_lib_option('LIBSCALAPACK_ONLY', self.variables['FLIBS'])

        ## multi-threaded
        if self.SCALAPACK_LIB_MT is None:
            ## reuse BLAS variables
            self.variables.extend_lib_option('LIBSCALAPACK_MT_ONLY', self.variables['LIBSCALAPCK_ONLY'])
        else:
            self.SCALAPACK_LIB_MT = [x % self.SCALAPACK_LIB_MAP for x in self.SCALAPACK_LIB_MT]
            self.variables.extend_lib_option('LIBSCALAPACK_MT_ONLY', self.SCALAPACK_LIB_MT, group=self.SCALAPACK_LIB_GROUP, static=self.SCALAPACK_LIB_STATIC)
            if 'FLIBS' in self.variables:
                self.variables.extend_lib_option('LIBSCALAPACK_MT_ONLY', self.variables['FLIBS'])
            if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                self.variables.extend_lib_option('LIBSCALAPACK_MT_ONLY', self.LIB_MULTITHREAD)

        root = get_software_root(self.SCALAPACK_MODULE_NAME[0])  ## TODO: deal with multiple modules properly


        if self.SCALAPACK_REQUIRES is not None:
            self.variables.join('LIBSCALAPACK', 'LIBSCALAPACK_ONLY', *self.SCALAPACK_REQUIRES)
            scalapack_mt = ["%s_MT" % x for x in self.SCALAPACK_REQUIRES]
            if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                scalapack_mt.extend(self.LIB_MULTITHREAD)
            self.variables.join('LIBSCALAPACK_MT', 'LIBSCALAPACK_MT_ONLY', *scalapack_mt)
        else:
            self.log.raiseException("_set_scalapack_variables: LIBSCALAPACK without SCALAPACK_REQUIRES not implemented")


        self.variables.append_exist('SCALAPACK_LIB_DIR', root, self.SCALAPACK_LIB_DIR)
        self.variables.append_exist('SCALAPACK_INC_DIR', root, self.SCALAPACK_INCLUDE_DIR)
        self.variables.extend_comma_libs('SCALAPACK_STATIC_LIBS', self.variables['LIBSCALAPACK'], suffx='.a')
        self.variables.extend_comma_libs('SCALAPACK_MT_STATIC_LIBS', self.variables['LIBSCALAPACK_MT'], suffx='.a')

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
    BLACS_LIB = ["blacsCinit", "blacsF77init", "blacs"]


class ScaLAPACK(object):
    """Trivial class
        provides ScaLAPACK
    """
    SCALAPACK_MODULE_NAME = ['ScaLAPACK']


class IntelMKL(ScalableLinearAlgebraPackage):
    """Interface to Intel MKL"""
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
    BLACS_LIB_MPI = ["mkl_blacs_%(mpi)s%(lp64)s"]
    BLACS_LIB = ["mkl_blacs%(lp64)s"] + BLACS_LIB_MPI
    BLACS_LIB_MAP = {'mpi':None}

    SCALAPACK_MODULE_NAME = ['imkl']
    SCALAPACK_LIB = ["mkl_scalapack%(lp64_sc)s", "mkl_solver%(lp64)s_sequential"]
    SCALAPACK_LIB_MT = ["mkl_scalapack%(lp64_sc)s", "mkl_solver%(lp64)s"]
    SCALAPACK_LIB_MAP = {"lp64_sc":"_lp64"}
    SCALAPACK_REQUIRES = ['LIBBLACS', 'LIBBLAS']
    SCALAPACK_LIB_GROUP = True
    SCALAPACK_LIB_STATIC = True

    def _set_blas_variables(self):
        """Fix the map a bit"""
        interfacemap = {INTEL:'intel',
                        GCC:'gf',
                        }
        try:
            self.BLAS_LIB_MAP.update({"interface":interfacemap[self.COMPILER_FAMILY]})
        except:
            self.raiseException("_set_blas_variables: interface unsupported combination with MPI family %s" % self.COMPILER_FAMILY)

        interfacemap_mt = {INTEL:'intel',
                           GCC:'gnu',
                           }
        try:
            self.BLAS_LIB_MAP.update({"interface_mt":interfacemap_mt[self.COMPILER_FAMILY]})
        except:
            self.raiseException("_set_blas_variables: interface_mt unsupported combination with compiler family %s" % self.COMPILER_FAMILY)


        if self.options.get('32bit', None):
            ## 32bit
            self.BLAS_LIB_MAP.update({"lp64":''})
        if self.options.get('i8', None):
            ## ilp64/i8
            self.BLAS_LIB_MAP.update({"lp64":'_ilp64'})
            ## CPP / CFLAGS
            self.variables.append_el('CFLAGS', 'DMKL_ILP64')

        # exact paths/linking statements depend on imkl version
        found_version = get_software_version(self.BLAS_MODULE_NAME[0])
        if LooseVersion(found_version) < LooseVersion('10.3'):
            if self.options.get('32bit', None):
                self.BLAS_LIB_DIR = ['lib/32']
            else:
                self.BLAS_LIB_DIR = ['lib/em64t']
            self.BLAS_INCL_DIR = ['include']
        else:
            if self.options.get('32bit', None):
                self.log.raiseException("_set_blas_variables: 32-bit libraries not supported yet for IMKL v%s (> v10.3)" % found_version)
            else:
                self.BLAS_LIB_DIR = ['mkl/lib/intel64', 'compiler/lib/intel64' ]

            self.BLAS_INCL_DIR = ['mkl/include']


        super(IntelMKL, self)._set_blas_variables()

    def _set_blacs_variables(self):
        mpimap = {INTELMPI:'intelmpi',
                  OPENMPI:'openmpi',
                  }
        try:
            self.BLACS_LIB_MAP.update({'mpi':mpimap[self.MPI_FAMILY]})
        except:
            self.raiseException("_set_blacs_variables: mpi unsupported combination with MPI family %s" % self.MPI_FAMILY)

        self.BLACS_LIB_DIR = self.BLAS_LIB_DIR
        self.BLACS_INCLUDE_DIR = self.BLAS_INCLUDE_DIR

        super(IntelMKL, self)._set_blacs_variables()

    def _set_scalapack_variables(self):
        if self.options.get('32bit', None):
            ##32 bit
            self.SCALAPACK_LIB_MAP.update({"lp64_sc":'_core'})


        super(IntelMKL, self)._set_scalapack_variables()


###############################################################################################################################
###############################################################################################################################

    def prepareACML(self):
        """
        Prepare for AMD Math Core Library (ACML)
        """

        if self.options['32bit']:
            self.log.error("ERROR: 32-bit not supported (yet) for ACML.")

        self._addDependencyVariables(['ACML'])

        acml = get_software_root('ACML')

        if self.comp_family() == GCC:
            compiler = 'gfortran'
        elif self.comp_family() == INTEL:
            compiler = 'ifort'
        else:
            self.log.error("Don't know which compiler-specific subdir for ACML to use.")

        self.variables['LDFLAGS'] += " -L%s/%s64/lib/ " % (acml, compiler)


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
            if self.options['32bit']:
                mklld = ['lib/32']
            else:
                mklld = ['lib/em64t']
            mklcpp = ['include', 'include/fftw']
        else:
            if self.options['32bit']:
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
        self.variables['BLACS_INC_DIR'] = os.path.join(mklroot, "mkl", "include")
        self.variables['BLACS_LIB_DIR'] = libs_dir
        self.variables['BLACS_STATIC_LIBS'] = ','.join(["libmkl_%s.a" % x for x in blacs_libs])
        self.variables['BLACS_MT_STATIC_LIBS'] = self.variables['BLACS_STATIC_LIBS']


        # FFT library
        fftwsuff = ""
        if self.options['pic']:
            fftwsuff = "_pic"
        fftw_libs = ["fftw3xc_intel%s" % fftwsuff,
                     "fftw3x_cdft%s" % fftwsuff,
                     "mkl_cdft_core"]
        self.variables['LIBFFT'] = ' '.join(["-Wl,-Bstatic",
                                        ' '.join(["-%s" % x for x in fftw_libs]),
                                        "-Wl,-Bdynamic"])
        self.variables['FFTW_INC_DIR'] = os.path.join(mklroot, "mkl", "include", "fftw")
        self.variables['FFTW_LIB_DIR'] = libs_dir
        fftw_static_libs = ["lib%s.a" % x for x in fftw_libs]
        self.variables['FFTW_STATIC_LIBS'] = ','.join(fftw_static_libs + [self.variables['BLAS_STATIC_LIBS'],
                                                                     self.variables['BLACS_STATIC_LIBS']])


        # linker flags
        self._flagsForSubdirs(mklroot, mklld, flag="-L%s", variableskey="LDFLAGS")
        self._flagsForSubdirs(mklroot, mklcpp, flag="-I%s", variableskey="CPPFLAGS")
