##
# Copyright 2012-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
Toolchain linalg module. Contains all (scalable) linear algebra related classes

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.toolchain.toolchain import Toolchain


class LinAlg(Toolchain):
    """General LinearAlgebra-like class
        can't be used without creating new class S(LinAlg)
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
    LAPACK_REQUIRES = ['LIBBLAS']
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

    LIB_EXTRA = None

    def __init__(self, *args, **kwargs):
        Toolchain.base_init(self)

        super(LinAlg, self).__init__(*args, **kwargs)

    def set_variables(self):
        """Set the variables"""
        ## TODO is link order fully preserved with this order ?
        self._set_blas_variables()
        self._set_lapack_variables()
        self._set_blacs_variables()
        self._set_scalapack_variables()

        self.log.debug('set_variables: LinAlg variables %s' % self.variables)

        super(LinAlg, self).set_variables()

    def _set_blas_variables(self):
        """Set BLAS related variables"""
        if self.BLAS_LIB is None:
            raise EasyBuildError("_set_blas_variables: BLAS_LIB not set")

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

        if getattr(self, 'LIB_EXTRA', None) is not None:
            self.variables.nappend('LIBBLAS', self.LIB_EXTRA, position=20)
            self.variables.nappend('LIBBLAS_MT', self.LIB_EXTRA, position=20)

        self.variables.join('BLAS_STATIC_LIBS', 'LIBBLAS')
        self.variables.join('BLAS_MT_STATIC_LIBS', 'LIBBLAS_MT')
        for root in self.get_software_root(self.BLAS_MODULE_NAME):
            self.variables.append_exists('BLAS_LIB_DIR', root, self.BLAS_LIB_DIR)
            self.variables.append_exists('BLAS_INC_DIR', root, self.BLAS_INCLUDE_DIR)

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
                raise EasyBuildError("_set_lapack_variables: LAPACK_LIB not set")
            self.LAPACK_LIB = self.variables.nappend('LIBLAPACK_ONLY', self.LAPACK_LIB)
            self.variables.add_begin_end_linkerflags(self.LAPACK_LIB,
                                                     toggle_startstopgroup=self.LAPACK_LIB_GROUP,
                                                     toggle_staticdynamic=self.LAPACK_LIB_STATIC)

            if self.LAPACK_LIB_MT is None:
                ## reuse LAPACK variables
                self.variables.join('LIBLAPACK_MT_ONLY', 'LIBLAPACK_ONLY')
            else:
                self.variables.nappend('LIBLAPACK_MT_ONLY', self.LAPACK_LIB_MT)
                if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                    self.variables.nappend('LIBLAPACK_MT_ONLY', self.LIB_MULTITHREAD)

            ## need BLAS for LAPACK ?
            if self.LAPACK_REQUIRES is not None:
                self.variables.join('LIBLAPACK', 'LIBLAPACK_ONLY', *self.LAPACK_REQUIRES)
                lapack_mt = ["%s_MT" % x for x in self.LAPACK_REQUIRES]
                self.variables.join('LIBLAPACK_MT', 'LIBLAPACK_MT_ONLY', *lapack_mt)
                if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                    self.variables.nappend('LIBLAPACK_MT', self.LIB_MULTITHREAD, position=10)

            else:
                self.variables.nappend('LIBLAPACK', 'LIBLAPACK_ONLY')
                self.variables.nappend('LIBLAPACK_MT', 'LIBLAPACK_MT_ONLY')

            if getattr(self, 'LIB_EXTRA', None) is not None:
                self.variables.nappend('LIBLAPACK', self.LIB_EXTRA, position=20)
                self.variables.nappend('LIBLAPACK_MT', self.LIB_EXTRA, position=20)

            self.variables.join('LAPACK_STATIC_LIBS', 'LIBLAPACK')
            self.variables.join('LAPACK_MT_STATIC_LIBS', 'LIBLAPACK_MT')

            for root in self.get_software_root(self.LAPACK_MODULE_NAME):
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
        if self.BLACS_LIB is not None:
            self.variables.add_begin_end_linkerflags(self.BLACS_LIB,
                                                     toggle_startstopgroup=self.BLACS_LIB_GROUP,
                                                     toggle_staticdynamic=self.BLACS_LIB_STATIC)

        if self.BLACS_LIB_MT is None:
            self.variables.join('LIBBLACS_MT', 'LIBBLACS')
        else:
            self.BLACS_LIB_MT = self.variables.nappend('LIBBLACS_MT', [x % self.BLACS_LIB_MAP for x in self.BLACS_LIB_MT])
            if self.BLACS_LIB_MT is not None:
                self.variables.add_begin_end_linkerflags(self.BLACS_LIB_MT,
                                                         toggle_startstopgroup=self.BLACS_LIB_GROUP,
                                                         toggle_staticdynamic=self.BLACS_LIB_STATIC)

        if getattr(self, 'LIB_EXTRA', None) is not None:
            self.variables.nappend('LIBBLACS', self.LIB_EXTRA, position=20)
            self.variables.nappend('LIBBLACS_MT', self.LIB_EXTRA, position=20)

        self.variables.join('BLACS_STATIC_LIBS', 'LIBBLACS')
        self.variables.join('BLACS_MT_STATIC_LIBS', 'LIBBLACS_MT')
        for root in self.get_software_root(self.BLACS_MODULE_NAME):
            self.variables.append_exists('BLACS_LIB_DIR', root, self.BLACS_LIB_DIR)
            self.variables.append_exists('BLACS_INC_DIR', root, self.BLACS_INCLUDE_DIR)

        ## add general dependency variables
        self._add_dependency_variables(self.BLACS_MODULE_NAME, ld=self.BLACS_LIB_DIR, cpp=self.BLACS_INCLUDE_DIR)

    def _set_scalapack_variables(self):
        """Set ScaLAPACK related variables"""

        if self.SCALAPACK_LIB is None:
            raise EasyBuildError("_set_blas_variables: SCALAPACK_LIB not set")

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

        if self.SCALAPACK_REQUIRES is not None:
            # remove variables that were not set, e.g. LIBBLACS (which is optional)
            scalapack_requires = self.SCALAPACK_REQUIRES[:]
            for req in scalapack_requires[:]:
                if self.variables.get(req, None) is None:
                    scalapack_requires.remove(req)
            self.variables.join('LIBSCALAPACK', 'LIBSCALAPACK_ONLY', *scalapack_requires)
            scalapack_mt = ["%s_MT" % x for x in scalapack_requires]
            self.variables.join('LIBSCALAPACK_MT', 'LIBSCALAPACK_MT_ONLY', *scalapack_mt)
            if getattr(self, 'LIB_MULTITHREAD', None) is not None:
                self.variables.nappend('LIBSCALAPACK_MT', self.LIB_MULTITHREAD)
        else:
            raise EasyBuildError("_set_scalapack_variables: LIBSCALAPACK without SCALAPACK_REQUIRES not implemented")

        if getattr(self, 'LIB_EXTRA', None) is not None:
            self.variables.nappend('LIBSCALAPACK', self.LIB_EXTRA, position=20)
            self.variables.nappend('LIBSCALAPACK_MT', self.LIB_EXTRA, position=20)

        self.variables.join('SCALAPACK_STATIC_LIBS', 'LIBSCALAPACK')
        self.variables.join('SCALAPACK_MT_STATIC_LIBS', 'LIBSCALAPACK_MT')
        for root in self.get_software_root(self.SCALAPACK_MODULE_NAME):
            self.variables.append_exists('SCALAPACK_LIB_DIR', root, self.SCALAPACK_LIB_DIR)
            self.variables.append_exists('SCALAPACK_INC_DIR', root, self.SCALAPACK_INCLUDE_DIR)

        self._add_dependency_variables(self.SCALAPACK_MODULE_NAME,
                                       ld=self.SCALAPACK_LIB_DIR, cpp=self.SCALAPACK_INCLUDE_DIR)
