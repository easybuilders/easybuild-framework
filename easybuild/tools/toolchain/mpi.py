# #
# Copyright 2012-2023 Ghent University
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
# #
"""
Toolchain mpi module. Contains all MPI related classes

Authors:

* Stijn De Weirdt (Ghent University)
* Kenneth Hoste (Ghent University)
"""
import copy
import os
import tempfile

from easybuild.base import fancylogger
import easybuild.tools.environment as env
import easybuild.tools.toolchain as toolchain
from easybuild.tools import LooseVersion
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option
from easybuild.tools.filetools import write_file
from easybuild.tools.toolchain.constants import COMPILER_VARIABLES, MPI_COMPILER_TEMPLATE, SEQ_COMPILER_TEMPLATE
from easybuild.tools.toolchain.toolchain import Toolchain


_log = fancylogger.getLogger('tools.toolchain.mpi', fname=False)


def get_mpi_cmd_template(mpi_family, params, mpi_version=None):
    """
    Return template for MPI command, for specified MPI family.

    :param mpi_family: MPI family to use to determine MPI command template
    """

    params = copy.deepcopy(params)

    mpi_cmd_template = build_option('mpi_cmd_template')
    if mpi_cmd_template:
        _log.info("Using specified template for MPI commands: %s", mpi_cmd_template)
    else:
        # different known mpirun commands
        mpirun_n_cmd = "mpirun -n %(nr_ranks)s %(cmd)s"
        mpi_cmds = {
            toolchain.OPENMPI: mpirun_n_cmd,
            toolchain.QLOGICMPI: "mpirun -H localhost -np %(nr_ranks)s %(cmd)s",
            toolchain.INTELMPI: mpirun_n_cmd,
            toolchain.MVAPICH2: mpirun_n_cmd,
            toolchain.MPICH: mpirun_n_cmd,
            toolchain.MPICH2: mpirun_n_cmd,
            toolchain.MPITRAMPOLINE: "mpiexec -n %(nr_ranks)s %(cmd)s",
        }

    # Intel MPI mpirun needs more work
    if mpi_cmd_template is None:

        if mpi_family == toolchain.INTELMPI:

            if mpi_version is None:
                raise EasyBuildError("Intel MPI version unknown, can't determine MPI command template!")

            # for old versions of Intel MPI, we need to use MPD
            if LooseVersion(mpi_version) <= LooseVersion('4.1'):

                mpi_cmds[toolchain.INTELMPI] = "mpirun %(mpdbf)s %(nodesfile)s -np %(nr_ranks)s %(cmd)s"

                # set temporary dir for MPD
                # note: this needs to be kept *short*,
                # to avoid mpirun failing with "socket.error: AF_UNIX path too long"
                # exact limit is unknown, but ~20 characters seems to be OK
                env.setvar('I_MPI_MPD_TMPDIR', tempfile.gettempdir())
                mpd_tmpdir = os.environ['I_MPI_MPD_TMPDIR']
                if len(mpd_tmpdir) > 20:
                    _log.warning("$I_MPI_MPD_TMPDIR should be (very) short to avoid problems: %s", mpd_tmpdir)

                # temporary location for mpdboot and nodes files
                tmpdir = tempfile.mkdtemp(prefix='mpi_cmd_for-')

                # set PBS_ENVIRONMENT, so that --file option for mpdboot isn't stripped away
                env.setvar('PBS_ENVIRONMENT', "PBS_BATCH_MPI")

                # make sure we're always using mpd as process manager
                # only required for/picked up by Intel MPI v4.1 or higher, no harm done for others
                env.setvar('I_MPI_PROCESS_MANAGER', 'mpd')

                # create mpdboot file
                mpdboot = os.path.join(tmpdir, 'mpdboot')
                write_file(mpdboot, "localhost ifhn=localhost")

                params.update({'mpdbf': "--file=%s" % mpdboot})

                # create nodes file
                nodes = os.path.join(tmpdir, 'nodes')
                write_file(nodes, "localhost\n" * int(params['nr_ranks']))

                params.update({'nodesfile': "-machinefile %s" % nodes})

        if mpi_family in mpi_cmds:
            mpi_cmd_template = mpi_cmds[mpi_family]
            _log.info("Using template MPI command '%s' for MPI family '%s'", mpi_cmd_template, mpi_family)
        else:
            raise EasyBuildError("Don't know which template MPI command to use for MPI family '%s'", mpi_family)

    missing = []
    for key in sorted(params.keys()):
        tmpl = '%(' + key + ')s'
        if tmpl not in mpi_cmd_template:
            missing.append(tmpl)
    if missing:
        raise EasyBuildError("Missing templates in mpi-cmd-template value '%s': %s",
                             mpi_cmd_template, ', '.join(missing))

    return mpi_cmd_template, params


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
        '_opt_MPICXX': 'cxx=%(CXX_base)s',
        '_opt_MPIF77': 'fc=%(F77_base)s',
        '_opt_MPIF90': 'f90=%(F90_base)s',
        '_opt_MPIFC': 'fc=%(FC_base)s',
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

        self.log.devel('_set_mpi_options: all current options %s', self.options)

    def set_variables(self):
        """Set the variables"""
        self._set_mpi_compiler_variables()
        self._set_mpi_variables()

        self.log.devel('set_variables: compiler variables %s', self.variables)
        super(Mpi, self).set_variables()

    def _set_mpi_compiler_variables(self):
        """Set the MPI compiler variables"""
        is32bit = self.options.get('32bit', None)
        if is32bit:
            self.log.debug("_set_mpi_compiler_variables: 32bit set: changing compiler definitions")

        for var_tuple in COMPILER_VARIABLES:
            c_var = var_tuple[0]  # [1] is the description
            var = MPI_COMPILER_TEMPLATE % {'c_var': c_var}

            value = getattr(self, 'MPI_COMPILER_%s' % var.upper(), None)
            if value is None:
                raise EasyBuildError("_set_mpi_compiler_variables: mpi compiler variable %s undefined", var)
            self.variables.nappend_el(var, value)

            # complete compiler variable template to produce e.g. 'mpicc -cc=icc -X -Y' from 'mpicc -cc=%(CC_base)'
            templatedict = {
                c_var: str(self.variables[c_var]),
                '%s_base' % c_var: str(self.variables[c_var].get_first()),
            }

            self.variables.nappend_el(var, self.options.option('_opt_%s' % var, templatedict=templatedict))

            if is32bit:
                self.variables.nappend_el(var, self.options.option('32bit'))

            if self.options.get('usempi', None):
                var_seq = SEQ_COMPILER_TEMPLATE % {'c_var': c_var}
                self.log.debug("usempi set: defining %s as %s", var_seq, self.variables[c_var])
                self.variables[var_seq] = self.variables[c_var]
                self.log.debug("usempi set: switching %s value %s for %s value %s",
                               c_var, self.variables[c_var], var, self.variables[var])
                self.variables[c_var] = self.variables[var]

        if self.options.get('cciscxx', None):
            self.log.debug("_set_mpi_compiler_variables: cciscxx set: switching MPICXX %s for MPICC value %s",
                           self.variables['MPICXX'], self.variables['MPICC'])
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

        # take into account that MPI_MODULE_NAME could be None (see Cray toolchains)
        for root in self.get_software_root(self.MPI_MODULE_NAME or []):
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

    def mpi_cmd_prefix(self, nr_ranks=1):
        """Construct an MPI command prefix to precede an executable"""

        test_cmd = 'xxx_command_xxx'
        mpi_cmd = self.mpi_cmd_for(test_cmd, nr_ranks)

        # take into account that result from mpi_cmd_for may be None,
        # for example when it's called too early (before toolchain module is loaded)
        if mpi_cmd is None:
            result = None
        # verify that the command appears at the end of mpi_cmd_for
        elif mpi_cmd.rstrip().endswith(test_cmd):
            result = mpi_cmd.replace(test_cmd, '').rstrip()
        else:
            warning_msg = "mpi_cmd_for cannot be used by mpi_cmd_prefix, "
            warning_msg += "requires that %(cmd)s template appears at the end"
            self.log.warning(warning_msg)
            result = None

        return result

    def mpi_cmd_for(self, cmd, nr_ranks):
        """Construct an MPI command for the given command and number of ranks."""

        # parameter values for mpirun command
        params = {
            'nr_ranks': nr_ranks,
            'cmd': cmd,
        }

        mpi_family = self.mpi_family()

        mpi_version = None

        if mpi_family == toolchain.INTELMPI:
            # for Intel MPI, try to determine impi version
            # this fails when it's done too early (before modules for toolchain/dependencies are loaded),
            # but it's safe to ignore this
            mpi_version = self.get_software_version(self.MPI_MODULE_NAME, required=False)[0]
            if not mpi_version:
                self.log.debug("Ignoring error when trying to determine %s version", self.MPI_MODULE_NAME)
                # impi version is required to determine correct MPI command template,
                # so we have to return early if we couldn't determine the impi version...
                return None

        mpi_cmd_template, params = get_mpi_cmd_template(mpi_family, params, mpi_version=mpi_version)
        self.log.info("Using MPI command template '%s' (params: %s)", mpi_cmd_template, params)

        try:
            res = mpi_cmd_template % params
        except KeyError as err:
            raise EasyBuildError("Failed to complete MPI cmd template '%s' with %s: KeyError %s",
                                 mpi_cmd_template, params, err)

        return res
