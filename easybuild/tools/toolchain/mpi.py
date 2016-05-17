# #
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
# #
"""
Toolchain mpi module. Contains all MPI related classes

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import os
import tempfile

import easybuild.tools.environment as env
import easybuild.tools.toolchain as toolchain
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import write_file
from easybuild.tools.toolchain.constants import COMPILER_VARIABLES, MPI_COMPILER_TEMPLATE, SEQ_COMPILER_TEMPLATE
from easybuild.tools.toolchain.toolchain import Toolchain


class Mpi(Toolchain):
    """General MPI-like class
        can't be used without creating new class M(Mpi)
    """

    MPI_MODULE_NAME = None
    MPI_FAMILY = None
    MPI_TYPE = None

    MPI_LIBRARY_NAME = None

    MPI_UNIQUE_OPTS = None
    MPI_SHARED_OPTS = {
                       'usempi': (False, "Use MPI compiler as default compiler"),  # also FFTW
                       }

    MPI_UNIQUE_OPTION_MAP = None
    MPI_SHARED_OPTION_MAP = {
        '_opt_MPICC': 'cc=%(CC_base)s',
        '_opt_MPICXX':'cxx=%(CXX_base)s',
        '_opt_MPIF77':'fc=%(F77_base)s',
        '_opt_MPIF90':'f90=%(F90_base)s',
        '_opt_MPIFC':'fc=%(FC_base)s',
    }

    MPI_COMPILER_MPICC = 'mpicc'
    MPI_COMPILER_MPICXX = 'mpicxx'

    MPI_COMPILER_MPIF77 = 'mpif77'
    MPI_COMPILER_MPIF90 = 'mpif90'
    MPI_COMPILER_MPIFC = 'mpifc'

    MPI_LINK_INFO_OPTION = None

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
        """Set the MPI compiler variables"""
        is32bit = self.options.get('32bit', None)
        if is32bit:
            self.log.debug("_set_compiler_variables: 32bit set: changing compiler definitions")

        for var_tuple in COMPILER_VARIABLES:
            c_var = var_tuple[0]  # [1] is the description
            var = MPI_COMPILER_TEMPLATE % {'c_var':c_var}

            value = getattr(self, 'MPI_COMPILER_%s' % var.upper(), None)
            if value is None:
                raise EasyBuildError("_set_mpi_compiler_variables: mpi compiler variable %s undefined", var)
            self.variables.nappend_el(var, value)

            # complete compiler variable template to produce e.g. 'mpicc -cc=icc -X -Y' from 'mpicc -cc=%(CC_base)'
            templatedict = {
                c_var:str(self.variables[c_var]),
                '%s_base' % c_var: str(self.variables[c_var].get_first()),
            }

            self.variables.nappend_el(var, self.options.option('_opt_%s' % var, templatedict=templatedict))

            if is32bit:
                self.variables.nappend_el(var, self.options.option('32bit'))

            if self.options.get('usempi', None):
                var_seq = SEQ_COMPILER_TEMPLATE % {'c_var': c_var}
                self.log.debug('_set_mpi_compiler_variables: usempi set: defining %s as %s' % (var_seq, self.variables[c_var]))
                self.variables[var_seq] = self.variables[c_var]
                self.log.debug("_set_mpi_compiler_variables: usempi set: switching %s value %s for %s value %s" %
                               (c_var, self.variables[c_var], var, self.variables[var]))
                self.variables[c_var] = self.variables[var]


        if self.options.get('cciscxx', None):
            self.log.debug("_set_mpi_compiler_variables: cciscxx set: switching MPICXX %s for MPICC value %s" %
                           (self.variables['MPICXX'], self.variables['MPICC']))
            self.variables['MPICXX'] = self.variables['MPICC']
            if self.options.get('usempi', None):
                # possibly/likely changed
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

    def mpi_family(self):
        """ Return type of MPI library used in this toolchain."""
        if self.MPI_FAMILY:
            return self.MPI_FAMILY
        else:
            raise EasyBuildError("mpi_family: MPI_FAMILY is undefined.")

    # FIXME: deprecate this function, use mympirun instead
    # this requires that either mympirun is packaged together with EasyBuild, or that vsc-tools is a dependency of EasyBuild
    def mpi_cmd_for(self, cmd, nr_ranks):
        """Construct an MPI command for the given command and number of ranks."""

        # parameter values for mpirun command
        params = {
            'nr_ranks': nr_ranks,
            'cmd': cmd,
        }

        # different known mpirun commands
        mpirun_n_cmd = "mpirun -n %(nr_ranks)d %(cmd)s"
        mpi_cmds = {
            toolchain.OPENMPI: mpirun_n_cmd,  # @UndefinedVariable
            toolchain.QLOGICMPI: "mpirun -H localhost -np %(nr_ranks)d %(cmd)s",  # @UndefinedVariable
            toolchain.INTELMPI: "mpirun %(mpdbf)s %(nodesfile)s -np %(nr_ranks)d %(cmd)s",  # @UndefinedVariable
            toolchain.MVAPICH2: mpirun_n_cmd,  # @UndefinedVariable
            toolchain.MPICH: mpirun_n_cmd,  # @UndefinedVariable
            toolchain.MPICH2: mpirun_n_cmd,  # @UndefinedVariable
        }

        mpi_family = self.mpi_family()

        # Intel MPI mpirun needs more work
        if mpi_family == toolchain.INTELMPI:  # @UndefinedVariable

            # set temporary dir for mdp
            # note: this needs to be kept *short*, to avoid mpirun failing with "socket.error: AF_UNIX path too long"
            # exact limit is unknown, but ~20 characters seems to be OK
            env.setvar('I_MPI_MPD_TMPDIR', tempfile.gettempdir())
            mpd_tmpdir = os.environ['I_MPI_MPD_TMPDIR']
            if len(mpd_tmpdir) > 20:
                self.log.warning("$I_MPI_MPD_TMPDIR should be (very) short to avoid problems: %s" % mpd_tmpdir)

            # temporary location for mpdboot and nodes files
            tmpdir = tempfile.mkdtemp(prefix='mpi_cmd_for-')

            # set PBS_ENVIRONMENT, so that --file option for mpdboot isn't stripped away
            env.setvar('PBS_ENVIRONMENT', "PBS_BATCH_MPI")

            # make sure we're always using mpd as process manager
            # only required for/picked up by Intel MPI v4.1 or higher, no harm done for others
            env.setvar('I_MPI_PROCESS_MANAGER', 'mpd')

            # create mpdboot file
            fn = os.path.join(tmpdir, 'mpdboot')
            try:
                if os.path.exists(fn):
                    os.remove(fn)
                write_file(fn, "localhost ifhn=localhost")
            except OSError, err:
                raise EasyBuildError("Failed to create file %s: %s", fn, err)

            params.update({'mpdbf': "--file=%s" % fn})

            # create nodes file
            fn = os.path.join(tmpdir, 'nodes')
            try:
                if os.path.exists(fn):
                    os.remove(fn)
                write_file(fn, "localhost\n" * nr_ranks)
            except OSError, err:
                raise EasyBuildError("Failed to create file %s: %s", fn, err)

            params.update({'nodesfile': "-machinefile %s" % fn})

        if mpi_family in mpi_cmds.keys():
            return mpi_cmds[mpi_family] % params
        else:
            raise EasyBuildError("Don't know how to create an MPI command for MPI library of type '%s'.", mpi_family)
