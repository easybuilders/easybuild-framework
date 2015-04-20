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
Support for the Cray Programming Environment Wrappers (aka cc, CC, ftn).
The Cray compiler wrappers are actually way more than just a compiler drivers.

The basic concept is that the compiler driver knows how to invoke the true underlying
compiler with the compiler's specific options tuned to Cray systems.

That means that certain defaults are set that are specific to Cray's computers.

The compiler wrappers are quite similar to EB toolchains as they include
linker and compiler directives to use the Cray libraries for their MPI (and network drivers)
Cray's LibSci (BLAS/LAPACK et al), FFT library, etc.


@author: Petar Forai (IMP/IMBA, Austria)
@author: Kenneth Hoste (Ghent University)
"""
import os

from easybuild.toolchains.compiler.gcc import Gcc
from easybuild.toolchains.compiler.inteliccifort import IntelIccIfort
from easybuild.toolchains.fft.fftw import Fftw
from easybuild.toolchains.mpi.mpich import TC_CONSTANT_MPI_TYPE_MPICH
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option
from easybuild.tools.toolchain.compiler import Compiler
from easybuild.tools.toolchain.constants import COMPILER_VARIABLES, MPI_COMPILER_TEMPLATE, SEQ_COMPILER_TEMPLATE
from easybuild.tools.toolchain.linalg import LinAlg
from easybuild.tools.toolchain.mpi import Mpi


TC_CONSTANT_CRAYPEWRAPPER = "CRAYPEWRAPPER"


class CrayPEWrapper(Compiler, Mpi, LinAlg, Fftw):
    """Generic support for using Cray compiler wrappers"""

    # no toolchain components, so no modules to list here (empty toolchain definition w.r.t. components)
    # the PrgEnv and craype are loaded, but are not considered actual toolchain components
    COMPILER_MODULE_NAME = []
    COMPILER_FAMILY = TC_CONSTANT_CRAYPEWRAPPER

    COMPILER_UNIQUE_OPTS = {
        # FIXME: (kehoste) how is this different from the existing 'shared' toolchain option? just map 'shared' to '-dynamic'? (already done)
        'dynamic': (False, "Generate dynamically linked executable"),
        'mpich-mt': (False, "Directs the driver to link in an alternate version of the Cray-MPICH library which \
                             provides fine-grained multi-threading support to applications that perform \
                             MPI operations within threaded regions."),
        'usewrappedcompiler': (False, "Use the embedded compiler instead of the wrapper"),
        'verbose': (True, "Verbose output"),
        'optarch': (False, "Enable architecture optimizations"),
    }

    COMPILER_UNIQUE_OPTION_MAP = {
        #'pic': 'shared',  # FIXME (use compiler-specific setting?)
        'shared': 'shared',
        'dynamic': 'dynamic',
        'static': 'static',
        'verbose': 'craype-verbose',
        'mpich-mt': 'craympich-mt',
        # no optimization flags
        'noopt': [],
        'lowopt': [],
        'defaultopt': [],
        'opt': [],
        # no precision flags
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
    MPI_FAMILY = TC_CONSTANT_CRAYPEWRAPPER
    MPI_TYPE = TC_CONSTANT_MPI_TYPE_MPICH

    MPI_COMPILER_MPICC = COMPILER_CC
    MPI_COMPILER_MPICXX = COMPILER_CXX
    MPI_COMPILER_MPIF77 = COMPILER_F77
    MPI_COMPILER_MPIF90 = COMPILER_F90

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
    # specific library depends on PrgEnv flavor
    # FIXME: make this (always) empty list?
    BLAS_LIB = None
    BLAS_LIB_MT = None

    LAPACK_MODULE_NAME = ['cray-libsci']
    LAPACK_IS_BLAS = True

    BLACS_MODULE_NAME = []
    SCALAPACK_MODULE_NAME = []

    # FFT support, via Cray-provided fftw module
    FFT_MODULE_NAME = ['fftw']

    # template and name suffix for PrgEnv module that matches this toolchain
    # e.g. 'gnu' => 'PrgEnv-gnu/<version>'
    PRGENV_MODULE_NAME_TEMPLATE = 'PrgEnv-%(suffix)s/%(version)s'
    PRGENV_MODULE_NAME_SUFFIX = None

    # template for craype module (determines code generator backend of Cray compiler wrappers)
    CRAYPE_MODULE_NAME_TEMPLATE = 'craype-%(optarch)s'

    def _pre_prepare(self):
        """Load PrgEnv module."""
        prgenv_mod_name = self.PRGENV_MODULE_NAME_TEMPLATE % {
            'suffix': self.PRGENV_MODULE_NAME_SUFFIX,
            'version': self.version,
        }
        self.log.info("Loading PrgEnv module '%s' for Cray toolchain %s" % (prgenv_mod_name, self.mod_short_name))
        self.modules_tool.load([prgenv_mod_name])

    def _set_optimal_architecture(self):
        """Load craype module specified via 'optarch' build option."""
        optarch = build_option('optarch')
        if optarch is None:
            raise EasyBuildError("Don't know which 'craype' module to load, 'optarch' build option is unspecified.")
        else:
            self.modules_tool.load([self.CRAYPE_MODULE_NAME_TEMPLATE % {'optarch': optarch}])

        # no compiler flag when optarch toolchain option is enabled
        self.options.options_map['optarch'] = ''

    def _set_compiler_flags(self):
        """Set compiler flags."""
        self.COMPILER_FLAGS.extend(['dynamic'])
        super(CrayPEWrapper, self)._set_compiler_flags()

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
            root = super(CrayPEWrapper, self)._get_software_root(name)

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
            ver = super(CrayPEWrapper, self)._get_software_version(name)

        return ver

    def _set_blacs_variables(self):
        """Skip setting BLACS related variables"""
        pass

    def _set_scalapack_variables(self):
        """Skip setting ScaLAPACK related variables"""
        pass

    def definition(self):
        """Empty toolchain definition (no modules listed as toolchain dependencies)."""
        return {}


# Gcc's base is Compiler
class CrayPEWrapperGNU(CrayPEWrapper):
    """Support for using the Cray GNU compiler wrappers."""
    TC_CONSTANT_CRAYPEWRAPPER = TC_CONSTANT_CRAYPEWRAPPER + '_GNU'

    # FIXME: make this empty list?
    BLAS_LIB = ['sci_gnu_mpi']
    BLAS_LIB_MT = ['sci_gnu_mpi_mp']

    PRGENV_MODULE_NAME_SUFFIX = 'gnu'  # PrgEnv-gnu

    def _set_compiler_vars(self):
        """Set compiler variables, either for the compiler wrapper, or the underlying compiler."""
        if self.options.option('usewrappedcompiler'):
            self.log.info("Using underlying compiler, as specified by the %s class" % Gcc)

            comp_attrs = ['UNIQUE_OPTS', 'UNIQUE_OPTION_MAP', 'CC', 'CXX', 'C_UNIQUE_FLAGS',
                          'F77', 'F90', 'F_UNIQUE_FLAGS']
            for attr_name in ['COMPILER_%s' % a for a in comp_attrs]:
                setattr(self, attr_name, getattr(Gcc, attr_name))

        super(CrayPEWrapperGNU,self)._set_compiler_vars()


class CrayPEWrapperIntel(CrayPEWrapper):
    """Support for using the Cray Intel compiler wrappers."""
    TC_CONSTANT_CRAYPEWRAPPER = TC_CONSTANT_CRAYPEWRAPPER + '_INTEL'

    # FIXME: make this empty list?
    BLAS_LIB = ['sci_intel_mpi']
    BLAS_LIB_MT = ['sci_intel_mpi_mp']

    PRGENV_MODULE_NAME_SUFFIX = 'intel'  # PrgEnv-intel

    def _set_compiler_flags(self):
        """Set compiler variables, either for the compiler wrapper, or the underlying compiler."""
        if self.options.option("usewrappedcompiler"):
            self.log.info("Using underlying compiler, as specified by the %s class" % IntelIccIfort)

            comp_attrs = ['UNIQUE_OPTS', 'UNIQUE_OPTION_MAP', 'CC', 'CXX', 'C_UNIQUE_FLAGS',
                          'F77', 'F90', 'F_UNIQUE_FLAGS']
            for attr_name in ['COMPILER_%s' % a for a in comp_attrs] + ['LINKER_TOGGLE_STATIC_DYNAMIC']:
                setattr(self, attr_name, getattr(IntelIccIfort, attr_name))

        super(CrayPEWrapperIntel, self).set_compiler_flags()


class CrayPEWrapperCray(CrayPEWrapper):
    """Support for using the Cray CCE compiler wrappers."""
    TC_CONSTANT_CRAYPEWRAPPER = TC_CONSTANT_CRAYPEWRAPPER + '_CRAY'

    # FIXME: make this empty list?
    BLAS_LIB = ['sci_cray_mpi']
    BLAS_LIB_MT = ['sci_cray_mpi_mp']

    PRGENV_MODULE_NAME_SUFFIX = 'cray'  # PrgEnv-cray
