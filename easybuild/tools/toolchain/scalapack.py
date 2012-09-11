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

from easybuild.tools.toolchain.toolkit import Variables, Options

from vsc.fancylogger import getLogger

class ScalableLinearAlgebraPackage(object):
    """General LinearAlgebra-like class
        To provide the BLAS/LAPACK/ScaLAPACK tools
    """

    BLAS_MODULE_NAME = None
    LAPACK_MODULE_NAME = None
    BLACS_MODULE_NAME = None
    SCALAPACK_MODULE_NAME = None

    {'packed-groups':False}
    def __init__(self):
        if not hasattr(self, 'log'):
            self.log = getLogger(self.__class__.__name__)

        self.opts = getattr(self, 'opts', Options())

        self.vars = getattr(self, 'vars', Variables())

        ## TODO is link order fully preserved with this order ?
        self._set_scalapack_vars()
        self._set_blacs_vars()
        self._set_lapack_vars()
        self._set_blas_vars()


    def _set_blas_vars(self):
        """Set BLAS releated variables"""

    def _set_lapack_vars(self):
        """Set LAPACK releated variables"""

    def _set_blacs_vars(self):
        """Set BLACS releated variables"""

    def _set_scalapack_vars(self):
        """Set BLACS releated variables"""


class GotoBLAS(object):
    """
    Trivial class
        provides GotoBLAS
    """
    BLAS_MODULE_NAME = ['GotoBLAS']

class LAPACK(object):
    """Trivial class
        provides LAPACK
    """
    LAPACK_MODULE_NAME = ['LAPACK']

class FLAME(LAPACK):
    """Less trivial module"""
    LAPACK_MODULE_NAME = ['FLAME'] + super(FLAME).LAPACK_MODULE_NAME

class ATLAS(object):
    """
    Trivial class
        provides ATLAS BLAS and LAPACK
            LAPACK is a build dependency only
    """
    BLAS_MODULE_NAME = ['ATLAS']
    LAPACK_MODULE_NAME = ['ATLAS']


class ACML(object):
    """
    Trivial class
        provides ACML BLAS and LAPACK
    """
    BLAS_MODULE_NAME = ['ACML']
    LAPACK_MODULE_NAME = ['ACML']

class BLACS(object):
    """
    Trivial class
        provides BLACS
    """
    BLACS_MODULE_NAME = ['BLACS']

class ScaLAPACK(object):
    """Trivial class
        provides ScaLAPACK
    """
    SCALAPACK_MODULE_NAME = ['ScaLAPACK']


class IntelMKL(ScalableLinearAlgebraPackage):
    """Interface to Intel MKL"""

    BLAS_MODULE_NAME = ['imkl']
    LAPACK_MODULE_NAME = ['imkl']
    BLACS_MODULE_NAME = ['imkl']
    SCALAPACK_MODULE_NAME = ['imkl']



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

        self.vars['LIBBLAS'] = " -lacml_mv -lacml " #-lpthread"
        self.vars['LIBBLAS_MT'] = self.vars['LIBBLAS']

        self.vars['LIBLAPACK'] = self.vars['LIBBLAS']
        self.vars['LIBLAPACK_MT'] = self.vars['LIBBLAS_MT']

    def prepareGotoBLAS(self):
        """
        Prepare for GotoBLAS BLAS library
        """

        self.vars['LIBBLAS'] = "-lgoto"
        self.vars['LIBBLAS_MT'] = self.vars['LIBBLAS']

        self._addDependencyVariables(['GotoBLAS'])


    def prepareLAPACK(self):
        """
        Prepare for LAPACK library
        """

        lapack = get_software_root("LAPACK")

        self.vars['LIBLAPACK'] = "-llapack %s" % self.vars['LIBBLAS']
        self.vars['LIBLAPACK_MT'] = "-llapack %s -lpthread" % self.vars['LIBBLAS_MT']

        self.vars['LAPACK_LIB_DIR'] = os.path.join(lapack, "lib")
        self.vars['LAPACK_STATIC_LIBS'] = "liblapack.a"
        self.vars['LAPACK_MT_STATIC_LIBS'] = self.vars['LAPACK_STATIC_LIBS']

        self._addDependencyVariables(['LAPACK'])

    def prepareATLAS(self):
        """
        Prepare for ATLAS BLAS/LAPACK library
        """
        blas_libs = ["cblas", "f77blas", "atlas"]
        blas_mt_libs = ["ptcblas", "ptf77blas", "atlas"]

        atlas = get_software_root("ATLAS")

        self.vars['LIBBLAS'] = ' '.join(["-l%s" % x for x in blas_libs] + ["-lgfortran"])
        self.vars['LIBBLAS_MT'] = ' '.join(["-l%s" % x for x in blas_mt_libs] + ["-lgfortran", "-lpthread"])
        self.vars['BLAS_LIB_DIR'] = os.path.join(atlas, "lib")
        self.vars['BLAS_STATIC_LIBS'] = ','.join(["lib%s.a" % x for x in blas_libs])
        self.vars['BLAS_MT_STATIC_LIBS'] = ','.join(["lib%s.a" % x for x in blas_mt_libs])

        if not self.vars.has_key('LIBLAPACK') and not self.vars.has_key('LIBLAPACK_MT'):
            self.vars['LIBLAPACK'] = ' '.join(["lapack", self.vars['LIBBLAS']])
            self.vars['LIBLAPACK_MT'] = ' '.join(["lapack", self.vars['LIBBLAS_MT']])
        self.vars['LAPACK_LIB_DIR'] = self.vars['BLAS_LIB_DIR']
        self.vars['LAPACK_STATIC_LIBS'] = "liblapack.a," + self.vars['BLAS_STATIC_LIBS']
        self.vars['LAPACK_MT_STATIC_LIBS'] = "liblapack.a," + self.vars['BLAS_MT_STATIC_LIBS']

        self.vars['BLAS_LAPACK_LIB_DIR'] = self.vars['LAPACK_LIB_DIR']
        self.vars['BLAS_LAPACK_STATIC_LIBS'] = self.vars['LAPACK_STATIC_LIBS']
        self.vars['BLAS_LAPACK_MT_STATIC_LIBS'] = self.vars['LAPACK_MT_STATIC_LIBS']

        self._addDependencyVariables(['ATLAS'])

    def prepareBLACS(self):
        """
        Prepare for BLACS library
        """

        blacs = get_software_root("BLACS")
        # order matters!
        blacs_libs = ["blacsCinit", "blacsF77init", "blacs"]

        self.vars['BLACS_INC_DIR'] = os.path.join(blacs, "include")
        self.vars['BLACS_LIB_DIR'] = os.path.join(blacs, "lib")
        self.vars['BLACS_STATIC_LIBS'] = ','.join(["lib%s.a" % x for x in blacs_libs])

        self.vars['LIBSCALAPACK'] = ' '.join(["-l%s" % x for x in blacs_libs])
        self.vars['LIBSCALAPACK_MT'] = self.vars['LIBSCALAPACK']

        self._addDependencyVariables(['BLACS'])

    def prepareFLAME(self):
        """
        Prepare for FLAME library
        """

        self.vars['LIBLAPACK'] += " -llapack2flame -lflame "
        self.vars['LIBLAPACK_MT'] += " -llapack2flame -lflame "

        self._addDependencyVariables(['FLAME'])


    def prepareScaLAPACK(self):
        """
        Prepare for ScaLAPACK library
        """

        scalapack = get_software_root("ScaLAPACK")

        # we need to be careful here, LIBSCALAPACK(_MT) may be set by prepareBLACS, or not
        self.vars['LIBSCALAPACK'] = "%s -lscalapack" % self.vars.get('LIBSCALAPACK', '')
        self.vars['LIBSCALAPACK_MT'] = "%s %s -lpthread" % (self.vars['LIBSCALAPACK'],
                                                            self.vars.get('LIBSCALAPACK_MT', ''))

        self.vars['SCALAPACK_INC_DIR'] = os.path.join(scalapack, "include")
        self.vars['SCALAPACK_LIB_DIR'] = os.path.join(scalapack, "lib")
        self.vars['SCALAPACK_STATIC_LIBS'] = "libscalapack.a"
        self.vars['SCALAPACK_MT_STATIC_LIBS'] = self.vars['SCALAPACK_STATIC_LIBS']

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

        # for more inspiration: see http://software.intel.com/en-us/articles/intel-mkl-link-line-advisor/

        libsfx = "_lp64"
        libsfxsl = "_lp64"
        if self.opts['32bit']:
            libsfx = ""
            libsfxsl = "_core"

        # MKL libraries for BLACS, BLAS, LAPACK, ScaLAPACK routines
        blacs_libs = ["blacs%s" % libsfx]
        blas_libs = ["intel%s" % libsfx, "sequential", "core"]
        blas_mt_libs = ["intel%s" % libsfx, "intel_thread", "core"]
        scalapack_libs = ["scalapack%s" % libsfxsl, "solver%s_sequential" % libsfx] + blas_libs + ["blacs_intelmpi%s" % libsfx]
        scalapack_mt_libs = ["scalapack%s" % libsfxsl, "solver%s" % libsfx] + blas_mt_libs + ["blacs_intelmpi%s" % libsfx]

        # adjust lib subdir if GCC is used
        if self.comp_family() == GCC:
            for libs in [blas_libs, blas_mt_libs, scalapack_libs]:
                libs.replace('mkl_intel_lp64', 'mkl_gf_lp64')

        # sequential BLAS and LAPACK
        prefix = "-Wl,-Bstatic -Wl,--start-group"
        suffix = "-Wl,--end-group -Wl,-Bdynamic"
        self.vars['LIBBLAS'] = ' '.join([prefix, ' '.join(["-lmkl_%s" % x for x in blas_libs]), suffix])
        self.vars['LIBLAPACK'] = self.vars['LIBBLAS']

        # multi-threaded BLAS and LAPACK
        suffix += " -liomp5 -lpthread"
        self.vars['LIBBLAS_MT'] = ' '.join([prefix, ' '.join(["-lmkl_%s" % x for x in blas_mt_libs]), suffix])
        self.vars['LIBLAPACK_MT'] = self.vars['LIBBLAS_MT']

        # determine BLACS/BLAS/LAPACK/FFTW library dir
        libs_dir = None
        for ld in mklld:
            fld = os.path.join(mklroot, ld)
            if os.path.isdir(fld):
                libs_dir = fld
        if not libs_dir:
            self.log.error("")
        else:
            self.vars['BLAS_LIB_DIR'] = libs_dir
            self.vars['LAPACK_LIB_DIR'] = libs_dir
            self.vars['BLAS_LAPACK_LIB_DIR'] = libs_dir

        # BLAS/LAPACK library
        self.vars['BLAS_STATIC_LIBS'] = ','.join(["libmkl_%s.a" % x for x in blas_libs])
        self.vars['BLAS_MT_STATIC_LIBS'] = ','.join(["libmkl_%s.a" % x for x in blas_mt_libs])

        self.vars['LAPACK_STATIC_LIBS'] = self.vars['BLAS_STATIC_LIBS']
        self.vars['LAPACK_MT_STATIC_LIBS'] = self.vars['BLAS_MT_STATIC_LIBS']

        self.vars['BLAS_LAPACK_STATIC_LIBS'] = self.vars['LAPACK_STATIC_LIBS']
        self.vars['BLAS_LAPACK_MT_STATIC_LIBS'] = self.vars['LAPACK_MT_STATIC_LIBS']

        # BLACS library
        self.vars['BLACS_INC_DIR'] = os.path.join(mklroot, "mkl", "include")
        self.vars['BLACS_LIB_DIR'] = libs_dir
        self.vars['BLACS_STATIC_LIBS'] = ','.join(["libmkl_%s.a" % x for x in blacs_libs])
        self.vars['BLACS_MT_STATIC_LIBS'] = self.vars['BLACS_STATIC_LIBS']

        # sequential ScaLAPACK
        self.vars['SCALAPACK_INC_DIR'] = os.path.join(mklroot, "mkl", "include")
        self.vars['SCALAPACK_LIB_DIR'] = libs_dir

        suffix = "-Wl,--end-group -Wl,-Bdynamic"
        self.vars['LIBSCALAPACK'] = ' '.join([prefix, ' '.join(["-lmkl_%s" % x for x in scalapack_libs]), suffix])
        self.vars['SCALAPACK_STATIC_LIBS'] = ','.join(["libmkl_%s.a" % x for x in scalapack_libs])

        # multi-threaded ScaLAPACK
        suffix += ' -liomp5 -lpthread'
        self.vars['LIBSCALAPACK_MT'] = ' '.join([prefix, ' '.join(["-lmkl_%s" % x for x in scalapack_mt_libs]), suffix])
        self.vars['SCALAPACK_MT_STATIC_LIBS'] = ','.join(["libmkl_%s.a" % x for x in scalapack_mt_libs])

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

        # some tools (like pkg-utils) don't handle groups well, so pack them if required
        if self.opts['packed-groups']:
            for x in ['LIBBLAS', 'LIBLAPACK', 'LIBSCALAPACK']:
                for var in [x, "%s_MT" % x]:
                    self.vars[var] = self.vars[var].replace(" ", ",")
                    self.vars[var] = self.vars[var].replace(",-Wl,", ",")

        # linker flags
        self._flagsForSubdirs(mklroot, mklld, flag="-L%s", varskey="LDFLAGS")
        self._flagsForSubdirs(mklroot, mklcpp, flag="-I%s", varskey="CPPFLAGS")
