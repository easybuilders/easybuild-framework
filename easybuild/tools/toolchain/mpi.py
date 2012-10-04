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
from easybuild.tools.modules import  get_software_root

from easybuild.tools.toolchain.variables import ToolchainVariables, COMPILER_VARIABLES, MPI_COMPILER_TEMPLATE
from easybuild.tools.toolchain.options import ToolchainOptions

from vsc.fancylogger import getLogger

INTELMPI = "IntelMPI"
OPENMPI = "OpenMPI"
QLOGICMPI = "QLogic"
MPICH2_F = "MPICH2"  ## _F family names, otherwise classes
MVAPICH2_F = "MVAPICH2"


class MPI(object):
    """General MPI-like class"""
    OPTIONS_CLASS = ToolchainOptions
    VARIABLES_CLASS = ToolchainVariables

    MPI_MODULE_NAME = None
    MPI_FAMILY = None

    MPI_LIBRARY_NAME = None

    MPI_UNIQUE_OPTS = None
    MPI_SHARED_OPTS = {'usempi': False, ## also FFTW
                       }

    MPI_UNIQUE_OPTION_MAP = None
    MPI_SHARED_OPTION_MAP = {'_opt_MPICC': 'cc="%(CC_base)s"',
                             '_opt_MPICXX':'cxx="%(CXX_base)s"',
                             '_opt_MPICF77':'fc="%(F77_base)s',
                             '_opt_MPICF90':'f90="%(F90_base)s',
                             }

    MPI_COMPILER_MPICC = 'mpicc'
    MPI_COMPILER_MPICXX = 'mpicxx'

    MPI_COMPILER_MPIF77 = 'mpif77'
    MPI_COMPILER_MPIF90 = 'mpif90'

    def __init__(self):
        if not hasattr(self, 'log'):
            self.log = getLogger(self.__class__.__name__)

        self.options = getattr(self, 'options', self.OPTIONS_CLASS())

        self.variables = getattr(self, 'variables', self.VARIABLES_CLASS())

        self._set_mpi_options()
        self._set_mpi_compiler_variables()
        self._set_mpi_variables()

        super(MPI, self).__init__()


    def _set_mpi_options(self):
        self.options.add_options(self.MPI_SHARED_OPTS, self.MPI_SHARED_OPTION_MAP)

        self.options.add_options(self.MPI_UNIQUE_OPTS, self.MPI_UNIQUE_OPTION_MAP)

        self.log.debug('_set_mpi_options: all current options %s' % self.options)


    def _set_mpi_compiler_variables(self):
        """Set the compiler variables"""
        is32bit = self.options.get('32bit', None)
        if is32bit:
            self.log.debug("_set_compiler_variables: 32bit set: changing compiler definitions")

        for c_var in COMPILER_VARIABLES:
            var = MPI_COMPILER_TEMPLATE % {'c_var':c_var}

            value = getattr(self, 'MPI_COMPILER_%s' % var.upper(), None)
            if value is None:
                self.log.raiseException("_set_mpi_compiler_variables: mpi compiler variable %s undefined" % var)
            self.variables.append_cmd_option(var, value)

            templatedict = {c_var:self.variables.as_cmd_option(c_var),
                            '%s_base' % c_var:self.variables[c_var][0],
                            }

            self.variables.extend_cmd_option(var, self.options.option('_opt_%s' % var, templatedict=templatedict))

            if is32bit:
                self.variables.append_cmd_option(var, self.options.option('32bit'))

            if self.options.get('usempi', None):
                self.log.debug("_set_mpi_compiler_variables: usempi set: switching %s value %s for %s value %s" %
                               (c_var, self.variables[c_var], var, self.variables[var]))
                self.variables.extend_cmd_option(c_var, self.variables[var])


        if self.options.get('cciscxx', None):
            self.log.debug("_set_mpi_compiler_variables: cciscxx set: switching MPICXX %s for MPICC value %s" %
                           (self.variables['MPICXX'], self.variables['MPICC']))
            self.variables['MPICXX'] = self.variables['MPICC']
            if self.options.get('usempi', None):
                ## possibly/likely changed
                self.variables['CXX'] = self.variables['CC']

    def _set_mpi_variables(self):
        """Set the other MPI variables"""
        root = get_software_root(self.MPI_MODULE_NAME[0])  ## TODO: deal with multiple modules properly

        lib_dir = ['lib']
        incl_dir = ['include']
        suffix = None
        if not self.options.get('32bit', None):
            suffix = '64'

        self.variables.append_exists('MPI_LIB_STATIC', root, lib_dir, filename="lib%s.a" % self.MPI_LIBRARY_NAME,
                                     suffix=suffix)
        self.variables.append_exists('MPI_LIB_SHARED', root, lib_dir, filename="lib%s.so" % self.MPI_LIBRARY_NAME,
                                     suffix=suffix)
        self.variables.append_exists('MPI_LIB_DIR', root, lib_dir, suffix=suffix)
        self.variables.append_exists('MPI_INC_DIR', root, incl_dir, suffix=suffix)


class OpenMPI(MPI):
    """OpenMPI MPI class"""
    MPI_MODULE_NAME = [OPENMPI]
    MPI_FAMILY = OPENMPI

    MPI_LIBRARY_NAME = 'mpi'

    ## OpenMPI reads from CC etc env variables
    COMPILER_UNIQUE_OPTION_MAP = {'_opt_MPICC': '',
                                  '_opt_MPICXX':'',
                                  '_opt_MPICF77':'',
                                  '_opt_MPICF90':'',
                                  }

class IntelMPI(MPI):
    """Intel MPI class"""
    MPI_MODULE_NAME = ['impi']
    MPI_FAMILY = INTELMPI

    MPI_LIBRARY_NAME = 'mpi'

    ## echo "   1. Command line option:  -cc=<compiler_name>"
    ## echo "   2. Environment variable: I_MPI_CC (current value '$I_MPI_CC')"
    ## echo "   3. Environment variable: MPICH_CC (current value '$MPICH_CC')"
    ## cxx -> cxx only
    ## intel mpicc only support few compiler names (and eg -cc='icc -m32' won't work.)
    COMPILER_UNIQUE_OPTION_MAP = {'_opt_MPICF90':'-fc="%(F90_base)s"',
                                  }


class MVAPICH2(MPI):
    """MVAPICH2 MPI class"""
    MPI_MODULE_NAME = [MVAPICH2_F]
    MPI_FAMILY = MVAPICH2_F

    MPI_LIBRARY_NAME = 'mpich'


class MPICH2(MPI):
    """MPICH2 MPI class"""
    MPI_MODULE_NAME = [MPICH2_F]
    MPI_FAMILY = MPICH2_F

    MPI_LIBRARY_NAME = 'mpich'


class QLogicMPI(MPI):
    """QlogicMPI MPI class"""
    MPI_MODULE_NAME = [QLOGICMPI]
    MPI_FAMILY = QLOGICMPI

    MPI_LIBRARY_NAME = 'mpich'

    ## qlogic: cxx -> -CC only
    ## qlogic has seperate -m32 / -m64 option to mpicc/.. --> only one
    COMPILER_UNIQUE_OPTION_MAP = {'_opt_MPICXX':'-CC="%(CXX_base)s"',
                                  }


