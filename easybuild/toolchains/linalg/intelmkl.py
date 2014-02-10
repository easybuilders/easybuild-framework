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
Support for Intel MKL as toolchain linear algebra library.

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

from distutils.version import LooseVersion

from easybuild.toolchains.compiler.inteliccifort import TC_CONSTANT_INTELCOMP
from easybuild.toolchains.compiler.gcc import TC_CONSTANT_GCC
from easybuild.tools.toolchain.linalg import LinAlg


class IntelMKL(LinAlg):
    """Support for Intel MKL."""

    # library settings are inspired by http://software.intel.com/en-us/articles/intel-mkl-link-line-advisor
    BLAS_MODULE_NAME = ['imkl']
    BLAS_LIB_MAP = {
        "lp64": '_lp64',
        "interface": None,
        "interface_mt": None,
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
    SCALAPACK_LIB = ["mkl_scalapack%(lp64_sc)s"]
    SCALAPACK_LIB_MT = ["mkl_scalapack%(lp64_sc)s"]
    SCALAPACK_LIB_MAP = {"lp64_sc":"_lp64"}
    SCALAPACK_REQUIRES = ['LIBBLACS', 'LIBBLAS']
    SCALAPACK_LIB_GROUP = True
    SCALAPACK_LIB_STATIC = True

    def _set_blas_variables(self):
        """Fix the map a bit"""
        interfacemap = {
            TC_CONSTANT_INTELCOMP: 'intel',
            TC_CONSTANT_GCC: 'gf',
        }
        try:
            self.BLAS_LIB_MAP.update({
                "interface": interfacemap[self.COMPILER_FAMILY],
            })
        except:
            self.log.raiseException(("_set_blas_variables: interface unsupported combination"
                                     " with MPI family %s") % self.COMPILER_FAMILY)

        interfacemap_mt = {
            TC_CONSTANT_INTELCOMP: 'intel',
            TC_CONSTANT_GCC: 'gnu',
        }
        try:
            self.BLAS_LIB_MAP.update({"interface_mt":interfacemap_mt[self.COMPILER_FAMILY]})
        except:
            self.log.raiseException(("_set_blas_variables: interface_mt unsupported combination "
                                     "with compiler family %s") % self.COMPILER_FAMILY)


        if self.options.get('32bit', None):
            # 32bit
            self.BLAS_LIB_MAP.update({"lp64":''})
        if self.options.get('i8', None):
            # ilp64/i8
            self.BLAS_LIB_MAP.update({"lp64":'_ilp64'})
            # CPP / CFLAGS
            self.variables.nappend_el('CFLAGS', 'DMKL_ILP64')

        # exact paths/linking statements depend on imkl version
        found_version = self.get_software_version(self.BLAS_MODULE_NAME)[0]
        if LooseVersion(found_version) < LooseVersion('10.3'):
            if self.options.get('32bit', None):
                self.BLAS_LIB_DIR = ['lib/32']
            else:
                self.BLAS_LIB_DIR = ['lib/em64t']
            self.BLAS_INCLUDE_DIR = ['include']
        else:
            if self.options.get('32bit', None):
                self.log.raiseException(("_set_blas_variables: 32-bit libraries not supported yet "
                                        "for IMKL v%s (> v10.3)") % found_version)
            else:
                self.BLAS_LIB_DIR = ['mkl/lib/intel64', 'compiler/lib/intel64' ]

            self.BLAS_INCLUDE_DIR = ['mkl/include']

        super(IntelMKL, self)._set_blas_variables()

    def _set_blacs_variables(self):
        mpimap = {
            "OpenMPI": '_openmpi',
            "IntelMPI": '_intelmpi',
            "MVAPICH2": '_intelmpi',
            "MPICH2":'',
        }
        try:
            self.BLACS_LIB_MAP.update({'mpi': mpimap[self.MPI_FAMILY]})
        except:
            self.log.raiseException(("_set_blacs_variables: mpi unsupported combination with"
                                     " MPI family %s") % self.MPI_FAMILY)

        self.BLACS_LIB_DIR = self.BLAS_LIB_DIR
        self.BLACS_INCLUDE_DIR = self.BLAS_INCLUDE_DIR

        super(IntelMKL, self)._set_blacs_variables()

    def _set_scalapack_variables(self):
        imkl_version = self.get_software_version(self.BLAS_MODULE_NAME)[0]
        if LooseVersion(imkl_version) < LooseVersion('10.3'):
            self.SCALAPACK_LIB.append("mkl_solver%(lp64)s_sequential")
            self.SCALAPACK_LIB_MT.append("mkl_solver%(lp64)s")

        if self.options.get('32bit', None):
            # 32 bit
            self.SCALAPACK_LIB_MAP.update({"lp64_sc":'_core'})

        elif self.options.get('i8', None):
            # ilp64/i8
            self.SCALAPACK_LIB_MAP.update({"lp64_sc":'_ilp64'})

        super(IntelMKL, self)._set_scalapack_variables()

