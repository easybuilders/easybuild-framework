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

from easybuild.tools.toolchain.compiler import COMPILER_VARIABLES
from easybuild.tools.toolchain.toolkit import Variables, Options, INTEL, GCC

from vsc.fancylogger import getLogger


class MPI(object):
    """General MPI-like class"""
    MPI_MODULE_NAME = None

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

    MPI_COMPILER_TEMPLATE = "MPI%(c_var)s"
    MPI_COMPILER_MPICC = 'mpicc'
    MPI_COMPILER_MPICXX = 'mpicxx'

    MPI_COMPILER_MPIF77 = 'mpif77'
    MPI_COMPILER_MPIF90 = 'mpif90'

    def __init__(self):
        if not hasattr(self, 'log'):
            self.log = getLogger(self.__class__.__name__)

        self.opts = getattr(self, 'opts', Options())

        self.vars = getattr(self, 'vars', Variables())

        self._set_mpi_opts()
        self._set_mpi_option_map()
        self._set_mpi_compiler_vars()
        self._set_mpi_vars()

        super(MPI, self).__init__()


    def _set_mpi_opts(self):
        self.opts.update(self.MPI_SHARED_OPTS)
        if self.MPI_UNIQUE_OPTS is not None:
            self.opts.update(self.MPI_UNIQUE_OPTS)

        self.log.debug('_set_mpi_opts: all current opts %s' % self.opts)


    def _set_mpi_option_map(self):
        option_map = self.MPI_SHARED_OPTION_MAP
        if self.MPI_UNIQUE_OPTION_MAP is not None:
            option_map.update(self.COMPILER_UNIQUE_OPTION_MAP)

        self.log.debug('_set_mpi_option_map: setting option_map %s' % option_map)

        self.opts.update_map(option_map)


    def _set_mpi_compiler_vars(self):
        """Set the compiler variables"""
        is32bit = self.opts.get('32bit', None)
        if is32bit:
            self.log.debug("_set_compiler_vars: 32bit set: changing compiler definitions")

        for c_var in COMPILER_VARIABLES:
            var = self.MPI_COMPILER_TEMPLATE % {'c_var':c_var}

            value = getattr(self, 'MPI_COMPILER_%s' % var.upper(), None)
            if value is None:
                self.log.raiseException("_set_mpi_compiler_vars: mpi compiler variable %s undefined" % var)
            self.vars.append(var, value)

            templatedict = {c_var:self.vars.as_cmd_option(c_var),
                            '%s_base' % c_var:self.vars[c_var][0],
                            }

            self.vars.append(var, self.opts.option('_opt_%s' % var, templatedict=templatedict))

            if is32bit:
                self.vars.append(var, self.opts.option('32bit'))

            if self.opts.get('usempi', None):
                self.log.debug("_set_mpi_compiler_vars: usempi set: switching %s value %s for %s value %s" % (c_var, self.vars[c_var], var, self.vars[var]))
                self.vars[c_var] = self.vars[var]


        if self.opts.get('cciscxx', None):
            self.log.debug("_set_mpi_compiler_vars: cciscxx set: switching MPICXX %s for MPICC value %s" % (self.vars['MPICXX'], self.vars['MPICC']))
            self.vars['MPICXX'] = self.vars['MPICC']
            if self.opts.get('usempi', None):
                ## possibly/likely changed
                self.vars['CXX'] = self.vars['CC']

    def _set_mpi_vars(self):
        """Set the other MPI variables"""
        root = get_software_root(self.MPI_MODULE_NAME)

        lib_dir = ['lib']
        incl_dir = ['include']
        if not self.opts.get('32bit', None):
            def _insert_suffix64_front(paths):
                res = []
                for path in paths:
                    res.extend(["%s64" % path, path])
                return res
            lib_dir = _insert_suffix64_front(lib_dir)
            incl_dir = _insert_suffix64_front(incl_dir)

        def _check_exists(prefix, paths, suffix=None):
            for path in paths:
                abs_path = os.path.join(prefix, path)
                if suffix is not None:
                    abs_path = os.path.join(abs_path, suffix)
                if os.path.exists(abs_path):
                    return abs_path

        variables = {}
        variables['MPI_LIB_STATIC'] = _check_exists(root, lib_dir, "lib%s.a" % self.MPI_LIBRARY_NAME)
        variables['MPI_LIB_SHARED'] = _check_exists(root, lib_dir, "lib%s.so" % self.MPI_LIBRARY_NAME)
        variables['MPI_LIB_DIR'] = _check_exists(root, lib_dir)
        variables['MPI_INC_DIR'] = _check_exists(root, incl_dir)

        ## sanity check
        for v in variables.values():
            if v is None:
                self.log.raiseException("_set_mpi_compiler_vars: one or more variables not set: %s" % variables)

        self.vars.update(variables)


class OpenMPI(MPI):
    """OpenMPI MPI class"""
    MPI_MODULE_NAME = ['OpenMPI']

    MPI_LIBRARY_NAME = 'mpi'

    ## OpenMPI reads from CC etc env vars
    COMPILER_UNIQUE_OPTION_MAP = {'_opt_MPICC': '',
                                  '_opt_MPICXX':'',
                                  '_opt_MPICF77':'',
                                  '_opt_MPICF90':'',
                                  }

class IntelMPI(MPI):
    """Intel MPI class"""
    MPI_MODULE_NAME = ['impi']

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
    MPI_MODULE_NAME = ['MVAPICH2']

    MPI_LIBRARY_NAME = 'mpich'


class MPICH2(MPI):
    """MPICH2 MPI class"""
    MPI_MODULE_NAME = ['MPICH2']

    MPI_LIBRARY_NAME = 'mpich'


class QLogicMPI(MPI):
    """QlogicMPI MPI class"""
    MPI_MODULE_NAME = ['QLogicMPI']

    MPI_LIBRARY_NAME = 'mpich'

    ## qlogic: cxx -> -CC only
    ## qlogic has seperate -m32 / -m64 option to mpicc/.. --> only one
    COMPILER_UNIQUE_OPTION_MAP = {'_opt_MPICXX':'-CC="%(CXX_base)s"',
                                  }


