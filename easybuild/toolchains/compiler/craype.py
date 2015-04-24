##
# Copyright 2014-2015 Ghent University
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
Support for the Cray Programming Environment (craype) compiler drivers (aka cc, CC, ftn).

The basic concept is that the compiler driver knows how to invoke the true underlying
compiler with the compiler's specific options tuned to Cray systems.

That means that certain defaults are set that are specific to Cray's computers.

The compiler drivers are quite similar to EB toolchains as they include
linker and compiler directives to use the Cray libraries for their MPI (and network drivers)
Cray's LibSci (BLAS/LAPACK et al), FFT library, etc.

@author: Petar Forai (IMP/IMBA, Austria)
@author: Kenneth Hoste (Ghent University)
"""
import os

from easybuild.toolchains.compiler.gcc import TC_CONSTANT_GCC
from easybuild.toolchains.compiler.inteliccifort import TC_CONSTANT_INTELCOMP
from easybuild.toolchains.fft.fftw import Fftw
from easybuild.toolchains.mpi.mpich import TC_CONSTANT_MPICH, TC_CONSTANT_MPI_TYPE_MPICH
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option
from easybuild.tools.toolchain.compiler import Compiler
from easybuild.tools.toolchain.constants import COMPILER_VARIABLES, MPI_COMPILER_TEMPLATE, SEQ_COMPILER_TEMPLATE
from easybuild.tools.toolchain.linalg import LinAlg
from easybuild.tools.toolchain.mpi import Mpi


TC_CONSTANT_CRAYPE = "CrayPE"
TC_CONSTANT_CRAYCE = "CrayCE"


class CrayPE(Compiler, Mpi, LinAlg, Fftw):
    """Generic support for using Cray compiler wrappers"""
    # toolchain family
    FAMILY = TC_CONSTANT_CRAYPE

    # compiler module name is PrgEnv, suffix name depends on CrayPE flavor (gnu, intel, cray)
    COMPILER_MODULE_NAME = None
    # compiler family depends on CrayPE flavor
    COMPILER_FAMILY = None

    COMPILER_UNIQUE_OPTS = {
        'dynamic': (False, "Generate dynamically linked executable"),
        'mpich-mt': (False, "Directs the driver to link in an alternate version of the Cray-MPICH library which \
                             provides fine-grained multi-threading support to applications that perform \
                             MPI operations within threaded regions."),
        'optarch': (False, "Enable architecture optimizations"),
        'verbose': (True, "Verbose output"),
    }

    COMPILER_UNIQUE_OPTION_MAP = {
        'shared': 'shared',
        'dynamic': 'dynamic',
        'static': 'static',
        'verbose': 'craype-verbose',
        'mpich-mt': 'craympich-mt',
        # no optimization flags
        # FIXME enable?
        'noopt': [],
        'lowopt': [],
        'defaultopt': [],
        'opt': [],
        # no precision flags
        # FIXME enable?
        'strict': [],
        'precise': [],
        'defaultprec': [],
        'loose': [],
        'veryloose': [],
    }

    COMPILER_CC = 'cc'
    COMPILER_CXX = 'CC'

    COMPILER_F77 = 'ftn'
    COMPILER_F90 = 'ftn'

    # MPI support
    # no separate module, Cray compiler drivers always provide MPI support
    MPI_MODULE_NAME = []
    MPI_FAMILY = TC_CONSTANT_MPICH
    MPI_TYPE = TC_CONSTANT_MPI_TYPE_MPICH

    MPI_COMPILER_MPICC = COMPILER_CC
    MPI_COMPILER_MPICXX = COMPILER_CXX
    MPI_COMPILER_MPIF77 = COMPILER_F77
    MPI_COMPILER_MPIF90 = COMPILER_F90

    # no MPI wrappers, so no need to specify serial compiler
    MPI_SHARED_OPTION_MAP = {
        '_opt_MPICC': '',
        '_opt_MPICXX': '',
        '_opt_MPIF77': '',
        '_opt_MPIF90': '',
    }

    # BLAS/LAPACK support
    # via cray-libsci module, which gets loaded via the PrgEnv module
    # see https://www.nersc.gov/users/software/programming-libraries/math-libraries/libsci/
    BLAS_MODULE_NAME = ['cray-libsci']

    # no need to specify libraries, compiler driver takes care of linking the right libraries
    # FIXME: need to revisit this, on numpy we ended up with a serial BLAS through the wrapper.
    BLAS_LIB = []
    BLAS_LIB_MT = []

    LAPACK_MODULE_NAME = ['cray-libsci']
    LAPACK_IS_BLAS = True

    BLACS_MODULE_NAME = []
    SCALAPACK_MODULE_NAME = []

    # FFT support, via Cray-provided fftw module
    FFT_MODULE_NAME = ['fftw']

    # suffix for PrgEnv module that matches this toolchain
    # e.g. 'gnu' => 'PrgEnv-gnu/<version>'
    PRGENV_MODULE_NAME_SUFFIX = None

    # template for craype module (determines code generator backend of Cray compiler wrappers)
    CRAYPE_MODULE_NAME_TEMPLATE = 'craype-%(optarch)s'

    # FIXME: add support for hugepages and accelerator modules that belong to CrayPE and allow to load modules
    # CRAYPE_HUGEMEM_MODULE_NAME_TEMPLATE = 'craype-hugepages%(hugemagesize)s'
    # CRAYPE_ACCEL_MODULE_NAME_TEMPLATE = 'craype-accel-%(acceltgt)s' 

    def __init__(self, *args, **kwargs):
        """Constructor."""
        super(CrayPE, self).__init__(*args, **kwargs)
        # 'register'  additional toolchain options that correspond to a compiler flag
        self.COMPILER_FLAGS.extend(['dynamic'])

        # use name of PrgEnv module as name of module that provides compiler
        self.COMPILER_MODULE_NAME = ['PrgEnv-%s' % self.PRGENV_MODULE_NAME_SUFFIX]

        # FIXME: force use of --experimental

    def _set_optimal_architecture(self):
        """Load craype module specified via 'optarch' build option."""
        optarch = build_option('optarch')
        if optarch is None:
            raise EasyBuildError("Don't know which 'craype' module to load, 'optarch' build option is unspecified.")
        else:
            self.modules_tool.load([self.CRAYPE_MODULE_NAME_TEMPLATE % {'optarch': optarch}])

        # no compiler flag when optarch toolchain option is enabled
        self.options.options_map['optarch'] = ''

    def _set_mpi_compiler_variables(self):
        """Set the MPI compiler variables"""
        for var_tuple in COMPILER_VARIABLES:
            c_var = var_tuple[0]  # [1] is the description
            var = MPI_COMPILER_TEMPLATE % {'c_var':c_var}

            value = getattr(self, 'MPI_COMPILER_%s' % var.upper(), None)
            if value is None:
                raise EasyBuildError("_set_mpi_compiler_variables: mpi compiler variable %s undefined", var)
            self.variables.nappend_el(var, value)

            if self.options.get('usempi', None):
                var_seq = SEQ_COMPILER_TEMPLATE % {'c_var': c_var}
                seq_comp = self.variables[c_var]
                self.log.debug('_set_mpi_compiler_variables: usempi set: defining %s as %s', var_seq, seq_comp)
                self.variables[var_seq] = seq_comp

        if self.options.get('cciscxx', None):
            self.log.debug("_set_mpi_compiler_variables: cciscxx set: switching MPICXX %s for MPICC value %s" %
                           (self.variables['MPICXX'], self.variables['MPICC']))
            self.variables['MPICXX'] = self.variables['MPICC']

    def _get_software_root(self, name):
        """Get install prefix for specified software name; special treatment for Cray modules."""
        if name == 'cray-libsci':
            # Cray-provided LibSci module
            env_var = 'CRAY_LIBSCI_PREFIX_DIR'
            root = os.getenv(env_var, None)
            if root is None:
                raise EasyBuildError("Failed to determine install prefix for %s via $%s", name, env_var)
            else:
                self.log.debug("Obtained install prefix for %s via $%s: %s", name, env_var, root)
        elif name == 'fftw':
            # Cray-provided fftw module
            env_var = 'FFTW_INC'
            incdir = os.getenv(env_var, None)
            if incdir is None:
                raise EasyBuildError("Failed to determine install prefix for %s via $%s", name, env_var)
            else:
                root = os.path.dirname(incdir)
                self.log.debug("Obtained install prefix for %s via $%s: %s", name, env_var, root)
        else:
            root = super(CrayPE, self)._get_software_root(name)

        return root

    def _get_software_version(self, name):
        """Get version for specified software name; special treatment for Cray modules."""
        if name == 'fftw':
            # Cray-provided fftw module
            env_var = 'FFTW_VERSION'
            ver = os.getenv(env_var, None)
            if ver is None:
                raise EasyBuildError("Failed to determine version for %s via $%s", name, env_var)
            else:
                self.log.debug("Obtained version for %s via $%s: %s", name, env_var, ver)
        else:
            ver = super(CrayPE, self)._get_software_version(name)

        return ver

    def _set_blacs_variables(self):
        """Skip setting BLACS related variables"""
        pass

    def _set_scalapack_variables(self):
        """Skip setting ScaLAPACK related variables"""
        pass


class CrayPEGNU(CrayPE):
    """Support for using the Cray GNU compiler wrappers."""
    PRGENV_MODULE_NAME_SUFFIX = 'gnu'  # PrgEnv-gnu
    COMPILER_FAMILY = TC_CONSTANT_GCC


class CrayPEIntel(CrayPE):
    """Support for using the Cray Intel compiler wrappers."""
    PRGENV_MODULE_NAME_SUFFIX = 'intel'  # PrgEnv-intel
    COMPILER_FAMILY = TC_CONSTANT_INTELCOMP


class CrayPECray(CrayPE):
    """Support for using the Cray CCE compiler wrappers."""
    PRGENV_MODULE_NAME_SUFFIX = 'cray'  # PrgEnv-cray
    COMPILER_FAMILY = TC_CONSTANT_CRAYCE
