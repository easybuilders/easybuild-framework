##
# Copyright 2014-2018 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# https://github.com/easybuilders/easybuild
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
MPI support for the Cray Programming Environment (craype).

:author: Petar Forai (IMP/IMBA, Austria)
:author: Kenneth Hoste (Ghent University)
"""
from easybuild.toolchains.compiler.craype import CrayPECompiler
from easybuild.toolchains.mpi.mpich import TC_CONSTANT_MPICH, TC_CONSTANT_MPI_TYPE_MPICH
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.toolchain.constants import COMPILER_VARIABLES, MPI_COMPILER_TEMPLATE, MPI_COMPILER_VARIABLES
from easybuild.tools.toolchain.constants import SEQ_COMPILER_TEMPLATE
from easybuild.tools.toolchain.mpi import Mpi


class CrayMPICH(Mpi):
    """Generic support for using Cray compiler wrappers"""
    # MPI support
    # no separate module, Cray compiler drivers always provide MPI support
    MPI_MODULE_NAME = []
    MPI_FAMILY = TC_CONSTANT_MPICH
    MPI_TYPE = TC_CONSTANT_MPI_TYPE_MPICH

    MPI_COMPILER_MPICC = CrayPECompiler.COMPILER_CC
    MPI_COMPILER_MPICXX = CrayPECompiler.COMPILER_CXX
    MPI_COMPILER_MPIF77 = CrayPECompiler.COMPILER_F77
    MPI_COMPILER_MPIF90 = CrayPECompiler.COMPILER_F90
    MPI_COMPILER_MPIFC = CrayPECompiler.COMPILER_FC

    # no MPI wrappers, so no need to specify serial compiler
    MPI_SHARED_OPTION_MAP = dict([('_opt_%s' % var, '') for var, _ in MPI_COMPILER_VARIABLES])

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
