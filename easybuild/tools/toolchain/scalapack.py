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

from easybuild.tools.toolchain.compiler import INTEL, GCC
from easybuild.tools.toolchain.mpi import INTELMPI, OPENMPI, MPICH2, MVAPICH2
from easybuild.tools.toolchain.toolchain import Toolchain

class ScalableLinearAlgebraPackage(Toolchain):
    """General LinearAlgebra-like class
        can't be used without creating new class S(ScalableLinearAlgebraPackage,Toolchain)
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
    LAPACK_LIB_STATIC = False
    LAPACK_LIB_GROUP = False
    LAPACK_LIB_DIR = ['lib']
    LAPACK_INCLUDE_DIR = ['include']

    BLACS_MODULE_NAME = None
    BLACS_LIB_DIR = ['lib']
    BLACS_INCLUDE_DIR = ['include']
    BLACS_LIB = None
    BLACS_LIB_MAP = None
    BLACS_LIB_MT = None
    BLACS_LIB_STATIC = False
    BLACS_LIB_GROUP = False

    SCALAPACK_MODULE_NAME = None
    SCALAPACK_REQUIRES = ['LIBBLACS', 'LIBLAPACK', 'LIBBLAS']
    SCALAPACK_LIB = None
    SCALAPACK_LIB_MT = None
    SCALAPACK_LIB_MAP = {}
    SCALAPACK_LIB_GROUP = False
    SCALAPACK_LIB_STATIC = False
    SCALAPACK_LIB_DIR = ['lib']
    SCALAPACK_INCLUDE_DIR = ['include']

    def __init__(self, *args, **kwargs):
        Toolchain.base_init(self)

        super(ScalableLinearAlgebraPackage, self).__init__(*args, **kwargs)

    def set_variables(self):
        """Set the variables"""
        ## TODO is link order fully preserved with this order ?
        self._set_blas_variables()
        self._set_lapack_variables()
        self._set_blacs_variables()
        self._set_scalapack_variables()

        self.log.debug('set_variables: ScalableLinearAlgebraPackage variables %s' % self.variables)

        super(ScalableLinearAlgebraPackage, self).set_variables()

    def _set_blas_variables(self):
        """Set BLAS related variables"""
        if self.BLAS_LIB is None:
            self.log.raiseException("_set_blas_variables: BLAS_LIB not set")

        self.BLAS_LIB = self.variables.nappend('LIBBLAS', [x % self.BLAS_LIB_MAP for x in self.BLAS_LIB])
        self.variables.add_begin_end_linkerflags(self.BLAS_LIB,
                                                 toggle_startstopgroup=self.BLAS_LIB_GROUP,
                                                 toggle_staticdynamic=self.BLAS_LIB_STATIC)
        if 'FLIBS' in self.variables:
            self.variables.join('LIBBLAS', 'FLIBS')

        ## multi-threaded
        if self.BLAS_LIB_MT is None:
            self.variables.join('LIBBLAS_MT', 'LIBBLAS')
        else:
            self.BLAS_LIB_MT = self.variables.nappend('LIBBLAS_MT', [x % self.BLAS_LIB_MAP for x in self.BLAS_LIB_MT])
            self.variables.add_begin_end_linkerflags(self.BLAS_LIB_MT,
                                                     toggle_startstopgroup=self.BLAS_LIB_GROUP,
                                                     toggle_staticdynamic=self.BLAS_LIB_STATIC)
            if 'FLIBS' in self.variables:
                self.variables.join('LIBBLAS_MT', 'FLIBS')
            if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                self.variables.nappend('LIBBLAS_MT', self.LIB_MULTITHREAD, position=10)

        root = self.get_software_root(self.BLAS_MODULE_NAME[0])  ## TODO: deal with multiple modules properly

        self.variables.append_exists('BLAS_LIB_DIR', root, self.BLAS_LIB_DIR)
        self.variables.append_exists('BLAS_INC_DIR', root, self.BLAS_INCLUDE_DIR)
        self.variables.join('BLAS_STATIC_LIBS', 'LIBBLAS')
        self.variables.join('BLAS_MT_STATIC_LIBS', 'LIBBLAS_MT')

        ## add general dependency variables
        self._add_dependency_variables(self.BLAS_MODULE_NAME, ld=self.BLAS_LIB_DIR, cpp=self.BLAS_INCLUDE_DIR)

    def _set_lapack_variables(self):
        """Set LAPACK related variables
            and LAPACK only, for (working) use BLAS+LAPACK
        """
        self.log.debug("_set_lapack_variables: LAPACK_IS_BLAS %s LAPACK_REQUIRES %s" %
                       (self.LAPACK_IS_BLAS, self.LAPACK_REQUIRES))
        if self.LAPACK_IS_BLAS:
            self.variables.join('LIBLAPACK_ONLY', 'LIBBLAS')
            self.variables.join('LIBLAPACK_MT_ONLY', 'LIBBLAS_MT')
            self.variables.join('LIBLAPACK', 'LIBBLAS')
            self.variables.join('LIBLAPACK_MT', 'LIBBLAS_MT')
            self.variables.join('LAPACK_STATIC_LIBS', 'BLAS_STATIC_LIBS')
            self.variables.join('LAPACK_MT_STATIC_LIBS', 'BLAS_MT_STATIC_LIBS')
            self.variables.join('LAPACK_LIB_DIR', 'BLAS_LIB_DIR')
            self.variables.join('LAPACK_INC_DIR', 'BLAS_INC_DIR')
        else:
            if self.LAPACK_LIB is None:
                self.log.raiseException("_set_lapack_variables: LAPACK_LIB not set")
            self.LAPACK_LIB = self.variables.nappend('LIBLAPACK_ONLY', self.LAPACK_LIB)
            self.variables.add_begin_end_linkerflags(self.LAPACK_LIB,
                                                     toggle_startstopgroup=self.LAPACK_LIB_GROUP,
                                                     toggle_staticdynamic=self.LAPACK_LIB_STATIC)

            if self.LAPACK_LIB_MT is None:
                ## reuse LAPACK variables
                self.LAPACK_LIB_MT = self.variables.join('LIBBLAS_MT_ONLY', 'LIBLAPACK_ONLY')
                self.variables.add_begin_end_linkerflags(self.LAPACK_LIB_MT,
                                                         toggle_startstopgroup=self.LAPACK_LIB_GROUP,
                                                         toggle_staticdynamic=self.LAPACK_LIB_STATIC)
            else:
                self.variables.nappend('LIBLAPACK_MT_ONLY', self.LAPACK_LIB_MT)
                if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                    self.variables.nappend('LIBBLAS_MT_ONLY', self.LIB_MULTITHREAD)

            ## need BLAS for LAPACK ?
            if self.LAPACK_REQUIRES is not None:
                self.variables.join('LIBLAPACK', 'LIBLAPACK_ONLY', *self.LAPACK_REQUIRES)
                lapack_mt = ["%s_MT" % x for x in self.LAPACK_REQUIRES]
                if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                    lapack_mt.extend(self.LIB_MULTITHREAD)
                self.variables.join('LIBLAPACK_MT', 'LIBLAPACK_MT_ONLY', *lapack_mt)
            else:
                self.variables.nappend('LIBLAPACK', 'LIBLAPACK_ONLY')
                self.variables.nappend('LIBLAPACK_MT', 'LIBLAPACK_MT_ONLY')

            self.variables.join('LAPACK_STATIC_LIBS', 'LIBLAPACK')
            self.variables.join('LAPACK_MT_STATIC_LIBS', 'LIBLAPACK_MT')

            root = self.get_software_root(self.LAPACK_MODULE_NAME[0])  ## TODO: deal with multiple modules properly
            self.variables.append_exists('LAPACK_LIB_DIR', root, self.LAPACK_LIB_DIR)
            self.variables.append_exists('LAPACK_INC_DIR', root, self.LAPACK_INCLUDE_DIR)

        self.variables.join('BLAS_LAPACK_LIB_DIR', 'LAPACK_LIB_DIR', 'BLAS_LIB_DIR')
        self.variables.join('BLAS_LAPACK_INC_DIR', 'LAPACK_INC_DIR', 'BLAS_INC_DIR')
        self.variables.join('BLAS_LAPACK_STATIC_LIBS', 'LAPACK_STATIC_LIBS', 'BLAS_STATIC_LIBS')
        self.variables.join('BLAS_LAPACK_MT_STATIC_LIBS', 'LAPACK_MT_STATIC_LIBS', 'BLAS_MT_STATIC_LIBS')

        ## add general dependency variables
        self._add_dependency_variables(self.LAPACK_MODULE_NAME, ld=self.LAPACK_LIB_DIR, cpp=self.LAPACK_INCLUDE_DIR)

    def _set_blacs_variables(self):
        """Set BLACS related variables"""

        lib_map = {}
        if hasattr(self, 'BLAS_LIB_MAP') and self.BLAS_LIB_MAP is not None:
            lib_map.update(self.BLAS_LIB_MAP)
        if hasattr(self, 'BLACS_LIB_MAP') and self.BLACS_LIB_MAP is not None:
            lib_map.update(self.BLACS_LIB_MAP)


        ## BLACS
        self.BLACS_LIB = self.variables.nappend('LIBBLACS', [x % lib_map for x in self.BLACS_LIB])
        self.variables.add_begin_end_linkerflags(self.BLACS_LIB,
                                                 toggle_startstopgroup=self.BLACS_LIB_GROUP,
                                                 toggle_staticdynamic=self.BLACS_LIB_STATIC)
        if self.BLACS_LIB_MT is None:
            self.variables.join('LIBBLACS_MT', 'LIBBLACS')
        else:
            self.log.raiseException("_set_blacs_variables: setting LIBBLACS_MT from self.BLACS_LIB_MT not implemented")

        root = self.get_software_root(self.BLACS_MODULE_NAME[0])  ## TODO: deal with multiple modules properly

        self.variables.append_exists('BLACS_LIB_DIR', root, self.BLACS_LIB_DIR)
        self.variables.append_exists('BLACS_INC_DIR', root, self.BLACS_INCLUDE_DIR)
        self.variables.join('BLACS_STATIC_LIBS', 'LIBBLACS')
        self.variables.join('BLACS_MT_STATIC_LIBS', 'LIBBLACS_MT')

        ## add general dependency variables
        self._add_dependency_variables(self.BLACS_MODULE_NAME, ld=self.BLACS_LIB_DIR, cpp=self.BLACS_INCLUDE_DIR)

    def _set_scalapack_variables(self):
        """Set ScaLAPACK related variables"""

        if self.SCALAPACK_LIB is None:
            self.log.raiseException("_set_blas_variables: SCALAPACK_LIB not set")

        lib_map = {}
        if hasattr(self, 'BLAS_LIB_MAP') and self.BLAS_LIB_MAP is not None:
            lib_map.update(self.BLAS_LIB_MAP)
        if hasattr(self, 'BLACS_LIB_MAP') and self.BLACS_LIB_MAP is not None:
            lib_map.update(self.BLACS_LIB_MAP)
        if hasattr(self, 'SCALAPACK_LIB_MAP') and self.SCALAPACK_LIB_MAP is not None:
            lib_map.update(self.SCALAPACK_LIB_MAP)

        self.SCALAPACK_LIB = self.variables.nappend('LIBSCALAPACK_ONLY', [x % lib_map for x in self.SCALAPACK_LIB])
        self.variables.add_begin_end_linkerflags(self.SCALAPACK_LIB,
                                                 toggle_startstopgroup=self.SCALAPACK_LIB_GROUP,
                                                 toggle_staticdynamic=self.SCALAPACK_LIB_STATIC)

        if 'FLIBS' in self.variables:
            self.variables.join('LIBSCALAPACK_ONLY', 'FLIBS')

        ## multi-threaded
        if self.SCALAPACK_LIB_MT is None:
            ## reuse BLAS variables
            self.variables.join('LIBSCALAPACK_MT_ONLY', 'LIBSCALAPACK_ONLY')
        else:
            self.SCALAPACK_LIB_MT = self.variables.nappend('LIBSCALAPACK_MT_ONLY',
                                                            [x % lib_map for x in self.SCALAPACK_LIB_MT])
            self.variables.add_begin_end_linkerflags(self.SCALAPACK_LIB_MT,
                                                     toggle_startstopgroup=self.SCALAPACK_LIB_GROUP,
                                                     toggle_staticdynamic=self.SCALAPACK_LIB_STATIC)

            if 'FLIBS' in self.variables:
                self.variables.join('LIBSCALAPACK_MT_ONLY', 'FLIBS')
            if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                self.variables.nappend('LIBSCALAPACK_MT_ONLY', self.LIB_MULTITHREAD)

        root = self.get_software_root(self.SCALAPACK_MODULE_NAME[0])  ## TODO: deal with multiple modules properly

        if self.SCALAPACK_REQUIRES is not None:
            self.variables.join('LIBSCALAPACK', 'LIBSCALAPACK_ONLY', *self.SCALAPACK_REQUIRES)
            scalapack_mt = ["%s_MT" % x for x in self.SCALAPACK_REQUIRES]
            if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                scalapack_mt.extend(self.LIB_MULTITHREAD)
            self.variables.join('LIBSCALAPACK_MT', 'LIBSCALAPACK_MT_ONLY', *scalapack_mt)
        else:
            self.log.raiseException("_set_scalapack_variables: LIBSCALAPACK without SCALAPACK_REQUIRES not implemented")


        self.variables.append_exists('SCALAPACK_LIB_DIR', root, self.SCALAPACK_LIB_DIR)
        self.variables.append_exists('SCALAPACK_INC_DIR', root, self.SCALAPACK_INCLUDE_DIR)
        self.variables.join('SCALAPACK_STATIC_LIBS', 'LIBSCALAPACK')
        self.variables.join('SCALAPACK_MT_STATIC_LIBS', 'LIBSCALAPACK_MT')

        self._add_dependency_variables(self.SCALAPACK_MODULE_NAME,
                                       ld=self.SCALAPACK_LIB_DIR, cpp=self.SCALAPACK_INCLUDE_DIR)

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
    LAPACK_MODULE_NAME = ['FLAME'] + LAPACK.LAPACK_MODULE_NAME # no super()
    LAPACK_LIB = ['lapack2flame', 'flame'] + LAPACK.LAPACK_LIB # no super()

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

    LAPACK_IS_BLAS = True

class ACML(object):
    """
    Trivial class
        provides ACML BLAS and LAPACK
    """
    BLAS_MODULE_NAME = ['ACML']
    BLAS_LIB = ['acml_mv', 'acml']

    LAPACK_MODULE_NAME = ['ACML']
    LAPACK_IS_BLAS = True

    def _set_blas_variables(self):
        """Fix the map a bit"""
        if self.options.get('32bit', None):
            self.log.raiseException("_set_blas_variables: 32bit ACML not (yet) supported")

        interfacemap = {INTEL:'ifort',
                        GCC:'gfortran',
                        }
        root = self.get_software_root(self.BLAS_MODULE_NAME[0])  ## TODO: deal with multiple modules properly
        try:
            self.variables.append_exists('LDFLAGS', root, os.path.join(interfacemap[self.COMPILER_FAMILY], 'lib'))
        except:
            self.log.raiseException(("_set_blas_variables: ACML set LDFLAGS interfacemap unsupported combination"
                                     " with compiler family %s") % self.COMPILER_FAMILY)

        super(ACML, self)._set_blas_variables()

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
    SCALAPACK_LIB = ['scalapack']

class ScaATLAS(ATLAS, BLACS, ScaLAPACK, ScalableLinearAlgebraPackage):
    """ScaLAPACK based on ATLAS/BLAS/SCALAPACK"""
    pass

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
    BLACS_LIB = ["mkl_blacs%(mpi)s%(lp64)s"]
    BLACS_LIB_MAP = {'mpi':None}
    BLACS_LIB_GROUP = True
    BLACS_LIB_STATIC = True

    SCALAPACK_MODULE_NAME = ['imkl']
    SCALAPACK_LIB = ["mkl_scalapack%(lp64_sc)s", "mkl_solver%(lp64)s_sequential"]
    SCALAPACK_LIB_MT = ["mkl_scalapack%(lp64_sc)s", "mkl_solver%(lp64)s"]
    SCALAPACK_LIB_MAP = {"lp64_sc":"_lp64"}
    SCALAPACK_REQUIRES = ['LIBBLACS', 'LIBBLAS']
    SCALAPACK_LIB_GROUP = True
    SCALAPACK_LIB_STATIC = True

    def _set_blas_variables(self):
        """Fix the map a bit"""
        interfacemap = {
                        INTEL:'intel',
                        GCC:'gf',
                        }
        try:
            self.BLAS_LIB_MAP.update({
                                      "interface":interfacemap[self.COMPILER_FAMILY]
                                      })
        except:
            self.log.raiseException(("_set_blas_variables: interface unsupported combination"
                                    " with MPI family %s") % self.COMPILER_FAMILY)

        interfacemap_mt = {
                           INTEL:'intel',
                           GCC:'gnu',
                           }
        try:
            self.BLAS_LIB_MAP.update({"interface_mt":interfacemap_mt[self.COMPILER_FAMILY]})
        except:
            self.log.raiseException(("_set_blas_variables: interface_mt unsupported combination "
                                     "with compiler family %s") % self.COMPILER_FAMILY)


        if self.options.get('32bit', None):
            ## 32bit
            self.BLAS_LIB_MAP.update({"lp64":''})
        if self.options.get('i8', None):
            ## ilp64/i8
            self.BLAS_LIB_MAP.update({"lp64":'_ilp64'})
            ## CPP / CFLAGS
            self.variables.append_el('CFLAGS', 'DMKL_ILP64')

        # exact paths/linking statements depend on imkl version
        found_version = self.get_software_version(self.BLAS_MODULE_NAME[0])
        if LooseVersion(found_version) < LooseVersion('10.3'):
            if self.options.get('32bit', None):
                self.BLAS_LIB_DIR = ['lib/32']
            else:
                self.BLAS_LIB_DIR = ['lib/em64t']
            self.BLAS_INCL_DIR = ['include']
        else:
            if self.options.get('32bit', None):
                self.log.raiseException(("_set_blas_variables: 32-bit libraries not supported yet "
                                        "for IMKL v%s (> v10.3)") % found_version)
            else:
                self.BLAS_LIB_DIR = ['mkl/lib/intel64', 'compiler/lib/intel64' ]

            self.BLAS_INCL_DIR = ['mkl/include']

        super(IntelMKL, self)._set_blas_variables()

    def _set_blacs_variables(self):
        mpimap = {
                  OPENMPI:'_openmpi',
                  INTELMPI:'_intelmpi',
                  MVAPICH2:'_intelmpi',
                  MPICH2:'',
                  }
        try:
            self.BLACS_LIB_MAP.update({'mpi':mpimap[self.MPI_FAMILY]})
        except:
            self.log.raiseException(("_set_blacs_variables: mpi unsupported combination with"
                                     " MPI family %s") % self.MPI_FAMILY)

        self.BLACS_LIB_DIR = self.BLAS_LIB_DIR
        self.BLACS_INCLUDE_DIR = self.BLAS_INCLUDE_DIR

        super(IntelMKL, self)._set_blacs_variables()

    def _set_scalapack_variables(self):
        if self.options.get('32bit', None):
            ##32 bit
            self.SCALAPACK_LIB_MAP.update({"lp64_sc":'_core'})

        super(IntelMKL, self)._set_scalapack_variables()

