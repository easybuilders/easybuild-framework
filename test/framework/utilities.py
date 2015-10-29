##
# Copyright 2012-2015 Ghent University
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
Various test utility functions.

@author: Kenneth Hoste (Ghent University)
"""
import copy
import fileinput
import os
import re
import shutil
import sys
import tempfile
from vsc.utils import fancylogger
from vsc.utils.patterns import Singleton
from vsc.utils.testing import EnhancedTestCase as _EnhancedTestCase

import easybuild.tools.build_log as eb_build_log
import easybuild.tools.options as eboptions
import easybuild.tools.toolchain.utilities as tc_utils
import easybuild.tools.module_naming_scheme.toolchain as mns_toolchain
from easybuild.framework.easyconfig import easyconfig
from easybuild.framework.easyblock import EasyBlock
from easybuild.main import main
from easybuild.tools import config
from easybuild.tools.config import module_classes
from easybuild.tools.configobj import ConfigObj
from easybuild.tools.environment import modify_env
from easybuild.tools.filetools import mkdir, read_file
from easybuild.tools.module_naming_scheme import GENERAL_CLASS
from easybuild.tools.modules import modules_tool
from easybuild.tools.options import CONFIG_ENV_VAR_PREFIX, EasyBuildOptions, set_tmpdir


# make sure tests are robust against any non-default configuration settings;
# involves ignoring any existing configuration files that are picked up, and cleaning the environment
# this is tackled here rather than in suite.py, to make sure this is also done when test modules are ran separately

# clean up environment from unwanted $EASYBUILD_X env vars
for key in os.environ.keys():
    if key.startswith('%s_' % CONFIG_ENV_VAR_PREFIX):
        del os.environ[key]

# ignore any existing configuration files
go = EasyBuildOptions(go_useconfigfiles=False)
os.environ['EASYBUILD_IGNORECONFIGFILES'] = ','.join(go.options.configfiles)

# redefine $TEST_EASYBUILD_X env vars as $EASYBUILD_X
test_env_var_prefix = 'TEST_EASYBUILD_'
for key in os.environ.keys():
    if key.startswith(test_env_var_prefix):
        val = os.environ[key]
        del os.environ[key]
        newkey = '%s_%s' % (CONFIG_ENV_VAR_PREFIX, key[len(test_env_var_prefix):])
        os.environ[newkey] = val

class EnhancedTestCase(_EnhancedTestCase):
    """Enhanced test case, provides extra functionality (e.g. an assertErrorRegex method)."""

    def setUp(self):
        """Set up testcase."""
        super(EnhancedTestCase, self).setUp()

        # keep track of log handlers
        log = fancylogger.getLogger(fname=False)
        self.orig_log_handlers = log.handlers[:]

        log.info("setting up test %s" % self.id())

        self.orig_tmpdir = tempfile.gettempdir()
        # use a subdirectory for this test (which we can clean up easily after the test completes)
        self.test_prefix = set_tmpdir()

        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        fd, self.logfile = tempfile.mkstemp(suffix='.log', prefix='eb-test-')
        os.close(fd)
        self.cwd = os.getcwd()

        # keep track of original environment to restore
        self.orig_environ = copy.deepcopy(os.environ)

        # keep track of original environment/Python search path to restore
        self.orig_sys_path = sys.path[:]

        testdir = os.path.dirname(os.path.abspath(__file__))

        self.test_sourcepath = os.path.join(testdir, 'sandbox', 'sources')
        os.environ['EASYBUILD_SOURCEPATH'] = self.test_sourcepath
        os.environ['EASYBUILD_PREFIX'] = self.test_prefix
        self.test_buildpath = tempfile.mkdtemp()
        os.environ['EASYBUILD_BUILDPATH'] = self.test_buildpath
        self.test_installpath = tempfile.mkdtemp()
        os.environ['EASYBUILD_INSTALLPATH'] = self.test_installpath

        # make sure that the tests only pick up easyconfigs provided with the tests
        os.environ['EASYBUILD_ROBOT_PATHS'] = os.path.join(testdir, 'easyconfigs')

        # make sure no deprecated behaviour is being triggered (unless intended by the test)
        # trip *all* log.deprecated statements by setting deprecation version ridiculously high
        self.orig_current_version = eb_build_log.CURRENT_VERSION
        os.environ['EASYBUILD_DEPRECATED'] = '10000000'

        init_config()

        # remove any entries in Python search path that seem to provide easyblocks
        for path in sys.path[:]:
            if os.path.exists(os.path.join(path, 'easybuild', 'easyblocks', '__init__.py')):
                sys.path.remove(path)

        # add test easyblocks to Python search path and (re)import and reload easybuild modules
        import easybuild
        sys.path.append(os.path.join(testdir, 'sandbox'))
        reload(easybuild)
        import easybuild.easyblocks
        reload(easybuild.easyblocks)
        import easybuild.easyblocks.generic
        reload(easybuild.easyblocks.generic)
        reload(easybuild.tools.module_naming_scheme)  # required to run options unit tests stand-alone

        modtool = modules_tool()
        # purge out any loaded modules with original $MODULEPATH before running each test
        modtool.purge()
        self.reset_modulepath([os.path.join(testdir, 'modules')])

    def tearDown(self):
        """Clean up after running testcase."""
        super(EnhancedTestCase, self).tearDown()

        self.log.info("Cleaning up for test %s", self.id())

        # go back to where we were before
        os.chdir(self.cwd)

        # restore original environment
        modify_env(os.environ, self.orig_environ, verbose=False)

        # restore original Python search path
        sys.path = self.orig_sys_path

        # remove any log handlers that were added (so that log files can be effectively removed)
        log = fancylogger.getLogger(fname=False)
        new_log_handlers = [h for h in log.handlers if h not in self.orig_log_handlers]
        for log_handler in new_log_handlers:
            log_handler.close()
            log.removeHandler(log_handler)

        # cleanup test tmp dir
        try:
            shutil.rmtree(self.test_prefix)
        except (OSError, IOError):
            pass

        # restore original 'parent' tmpdir
        for var in ['TMPDIR', 'TEMP', 'TMP']:
            os.environ[var] = self.orig_tmpdir

        # reset to make sure tempfile picks up new temporary directory to use
        tempfile.tempdir = None

    def reset_modulepath(self, modpaths):
        """Reset $MODULEPATH with specified paths."""
        modtool = modules_tool()
        for modpath in os.environ.get('MODULEPATH', '').split(os.pathsep):
            modtool.remove_module_path(modpath)
        # make very sure $MODULEPATH is totally empty
        # some paths may be left behind, e.g. when they contain environment variables
        # example: "module unuse Modules/$MODULE_VERSION/modulefiles" may not yield the desired result
        os.environ['MODULEPATH'] = ''
        for modpath in modpaths:
            modtool.add_module_path(modpath)

    def eb_main(self, args, do_build=False, return_error=False, logfile=None, verbose=False, raise_error=False,
                reset_env=True, raise_systemexit=False, testing=True):
        """Helper method to call EasyBuild main function."""
        cleanup()

        myerr = False
        if logfile is None:
            logfile = self.logfile
        # clear log file
        if logfile:
            f = open(logfile, 'w')
            f.write('')
            f.close()

        env_before = copy.deepcopy(os.environ)

        try:
            main(args=args, logfile=logfile, do_build=do_build, testing=testing)
        except SystemExit:
            if raise_systemexit:
                raise err
        except Exception, err:
            myerr = err
            if verbose:
                print "err: %s" % err

        if logfile and os.path.exists(logfile):
            logtxt = read_file(logfile)
        else:
            logtxt = None

        os.chdir(self.cwd)

        # make sure config is reinitialized
        init_config()

        # restore environment to what it was before running main,
        # changes may have been made by eb_main (e.g. $TMPDIR & co)
        if reset_env:
            modify_env(os.environ, env_before)
            tempfile.tempdir = None

        if myerr and raise_error:
            raise myerr

        if return_error:
            return logtxt, myerr
        else:
            return logtxt

    def setup_hierarchical_modules(self):
        """Setup hierarchical modules to run tests on."""
        mod_prefix = os.path.join(self.test_installpath, 'modules', 'all')

        # simply copy module files under 'Core' and 'Compiler' to test install path
        # EasyBuild is responsible for making sure that the toolchain can be loaded using the short module name
        mkdir(mod_prefix, parents=True)
        for mod_subdir in ['Core', 'Compiler', 'MPI']:
            src_mod_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modules', mod_subdir)
            shutil.copytree(src_mod_path, os.path.join(mod_prefix, mod_subdir))

        # make sure only modules in a hierarchical scheme are available, mixing modules installed with
        # a flat scheme like EasyBuildMNS and a hierarhical one like HierarchicalMNS doesn't work
        self.reset_modulepath([mod_prefix, os.path.join(mod_prefix, 'Core')])

        # tweak use statements in modules to ensure correct paths
        mpi_pref = os.path.join(mod_prefix, 'MPI', 'GCC', '4.7.2', 'OpenMPI', '1.6.4')
        for modfile in [
            os.path.join(mod_prefix, 'Core', 'GCC', '4.7.2'),
            os.path.join(mod_prefix, 'Core', 'GCC', '4.8.3'),
            os.path.join(mod_prefix, 'Core', 'icc', '2013.5.192-GCC-4.8.3'),
            os.path.join(mod_prefix, 'Core', 'ifort', '2013.5.192-GCC-4.8.3'),
            os.path.join(mod_prefix, 'Compiler', 'GCC', '4.7.2', 'OpenMPI', '1.6.4'),
            os.path.join(mod_prefix, 'Compiler', 'intel', '2013.5.192-GCC-4.8.3', 'impi', '4.1.3.049'),
            os.path.join(mpi_pref, 'FFTW', '3.3.3'),
            os.path.join(mpi_pref, 'OpenBLAS', '0.2.6-LAPACK-3.4.2'),
            os.path.join(mpi_pref, 'ScaLAPACK', '2.0.2-OpenBLAS-0.2.6-LAPACK-3.4.2'),
        ]:
            for line in fileinput.input(modfile, inplace=1):
                line = re.sub(r"(module\s*use\s*)/tmp/modules/all",
                              r"\1%s/modules/all" % self.test_installpath,
                              line)
                sys.stdout.write(line)

    def setup_categorized_hmns_modules(self):
        """Setup categorized hierarchical modules to run tests on."""
        mod_prefix = os.path.join(self.test_installpath, 'modules', 'all')

        # simply copy module files under 'CategorizedHMNS/{Core,Compiler,MPI}' to test install path
        # EasyBuild is responsible for making sure that the toolchain can be loaded using the short module name
        mkdir(mod_prefix, parents=True)
        for mod_subdir in ['Core', 'Compiler', 'MPI']:
            src_mod_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        'modules', 'CategorizedHMNS', mod_subdir)
            shutil.copytree(src_mod_path, os.path.join(mod_prefix, mod_subdir))
        # create empty module file directory to make C/Tcl modules happy
        mpi_pref = os.path.join(mod_prefix, 'MPI', 'GCC', '4.7.2', 'OpenMPI', '1.6.4')
        mkdir(os.path.join(mpi_pref, 'base'))

        # make sure only modules in the CategorizedHMNS are available
        self.reset_modulepath([os.path.join(mod_prefix, 'Core', 'compiler'),
                               os.path.join(mod_prefix, 'Core', 'toolchain')])

        # tweak use statements in modules to ensure correct paths
        for modfile in [
            os.path.join(mod_prefix, 'Core', 'compiler', 'GCC', '4.7.2'),
            os.path.join(mod_prefix, 'Compiler', 'GCC', '4.7.2', 'mpi', 'OpenMPI', '1.6.4'),
        ]:
            for line in fileinput.input(modfile, inplace=1):
                line = re.sub(r"(module\s*use\s*)/tmp/modules/all",
                              r"\1%s/modules/all" % self.test_installpath,
                              line)
                sys.stdout.write(line)


def cleanup():
    """Perform cleanup of singletons and caches."""
    # clear Singelton instances, to start afresh
    Singleton._instances.clear()

    # empty caches
    tc_utils._initial_toolchain_instances.clear()
    easyconfig._easyconfigs_cache.clear()
    easyconfig._easyconfig_files_cache.clear()
    mns_toolchain._toolchain_details_cache.clear()

    # reset to make sure tempfile picks up new temporary directory to use
    tempfile.tempdir = None

def init_config(args=None, build_options=None):
    """(re)initialize configuration"""

    cleanup()

    # initialize configuration so config.get_modules_tool function works
    eb_go = eboptions.parse_options(args=args)
    config.init(eb_go.options, eb_go.get_options_by_section('config'))

    # initialize build options
    if build_options is None:
        build_options = {
            'extended_dry_run': False,
            'external_modules_metadata': ConfigObj(),
            'valid_module_classes': module_classes(),
            'valid_stops': [x[0] for x in EasyBlock.get_steps()],
        }
    if 'suffix_modules_path' not in build_options:
        build_options.update({'suffix_modules_path': GENERAL_CLASS})
    config.init_build_options(build_options=build_options)

    return eb_go.options


def find_full_path(base_path, trim=(lambda x: x)):
    """
    Determine full path for given base path by looking in sys.path and PYTHONPATH.
    trim: a function that takes a path and returns a trimmed version of that path
    """

    full_path = None

    pythonpath = os.getenv('PYTHONPATH')
    if pythonpath:
        pythonpath = pythonpath.split(':')
    else:
        pythonpath = []
    for path in sys.path + pythonpath:
        tmp_path = os.path.join(trim(path), base_path)
        if os.path.exists(tmp_path):
            full_path = tmp_path
            break

    return full_path
