##
# Copyright 2012 Stijn De Weirdt
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
Toolchain mpi module. Contains all MPI related classes
"""

from easybuild.tools.toolchain.variables import COMPILER_VARIABLES, MPI_COMPILER_TEMPLATE
from easybuild.tools.toolchain.toolchain import Toolchain


class Mpi(object):
    """General MPI-like class
        can't be used without creating new class M(MPI,Toolchain)
    """

    MPI_MODULE_NAME = None
    MPI_FAMILY = None

    MPI_LIBRARY_NAME = None

    MPI_UNIQUE_OPTS = None
    MPI_SHARED_OPTS = {
                       'usempi': (False, "Use MPI compiler as default compiler"), ## also FFTW
                       }

    MPI_UNIQUE_OPTION_MAP = None
    MPI_SHARED_OPTION_MAP = {
                             '_opt_MPICC': 'cc="%(CC_base)s"',
                             '_opt_MPICXX':'cxx="%(CXX_base)s"',
                             '_opt_MPIF77':'fc="%(F77_base)s"',
                             '_opt_MPIF90':'f90="%(F90_base)s"',
                             }

    MPI_COMPILER_MPICC = 'mpicc'
    MPI_COMPILER_MPICXX = 'mpicxx'

    MPI_COMPILER_MPIF77 = 'mpif77'
    MPI_COMPILER_MPIF90 = 'mpif90'

    def __init__(self, *args, **kwargs):
        Toolchain.base_init(self)

        self._set_mpi_options()

        super(Mpi, self).__init__(*args, **kwargs)


    def _set_mpi_options(self):
        self.options.add_options(self.MPI_SHARED_OPTS, self.MPI_SHARED_OPTION_MAP)

        self.options.add_options(self.MPI_UNIQUE_OPTS, self.MPI_UNIQUE_OPTION_MAP)

        self.log.debug('_set_mpi_options: all current options %s' % self.options)


    def set_variables(self):
        """Set the variables"""
        self._set_mpi_compiler_variables()
        self._set_mpi_variables()

        self.log.debug('set_variables: compiler variables %s' % self.variables)
        super(Mpi, self).set_variables()

    def _set_mpi_compiler_variables(self):
        """Set the compiler variables"""
        is32bit = self.options.get('32bit', None)
        if is32bit:
            self.log.debug("_set_compiler_variables: 32bit set: changing compiler definitions")

        for var_tuple in COMPILER_VARIABLES:
            c_var = var_tuple[0]  # [1] is the description
            var = MPI_COMPILER_TEMPLATE % {'c_var':c_var}

            value = getattr(self, 'MPI_COMPILER_%s' % var.upper(), None)
            if value is None:
                self.log.raiseException("_set_mpi_compiler_variables: mpi compiler variable %s undefined" % var)
            self.variables.nappend_el(var, value)

            templatedict = {c_var:str(self.variables[c_var]),
                            '%s_base' % c_var: str(self.variables[c_var].get_first()),
                            }

            self.variables.nappend_el(var, self.options.option('_opt_%s' % var, templatedict=templatedict))

            if is32bit:
                self.variables.nappend_el(var, self.options.option('32bit'))

            if self.options.get('usempi', None):
                self.log.debug("_set_mpi_compiler_variables: usempi set: switching %s value %s for %s value %s" %
                               (c_var, self.variables[c_var], var, self.variables[var]))
                self.variables[c_var] = self.variables[var]


        if self.options.get('cciscxx', None):
            self.log.debug("_set_mpi_compiler_variables: cciscxx set: switching MPICXX %s for MPICC value %s" %
                           (self.variables['MPICXX'], self.variables['MPICC']))
            self.variables['MPICXX'] = self.variables['MPICC']
            if self.options.get('usempi', None):
                ## possibly/likely changed
                self.variables['CXX'] = self.variables['CC']

    def _set_mpi_variables(self):
        """Set the other MPI variables"""

        lib_dir = ['lib']
        incl_dir = ['include']
        suffix = None
        if not self.options.get('32bit', None):
            suffix = '64'

        for root in self.get_software_root(self.MPI_MODULE_NAME):
            self.variables.append_exists('MPI_LIB_STATIC', root, lib_dir, filename="lib%s.a" % self.MPI_LIBRARY_NAME,
                                         suffix=suffix)
            self.variables.append_exists('MPI_LIB_SHARED', root, lib_dir, filename="lib%s.so" % self.MPI_LIBRARY_NAME,
                                         suffix=suffix)
            self.variables.append_exists('MPI_LIB_DIR', root, lib_dir, suffix=suffix)
            self.variables.append_exists('MPI_INC_DIR', root, incl_dir, suffix=suffix)

