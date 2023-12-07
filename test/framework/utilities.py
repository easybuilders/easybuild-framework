##
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
##
"""
Various test utility functions.

@author: Kenneth Hoste (Ghent University)
@author Caroline De Brouwer (Ghent University)
"""
import copy
import fileinput
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager

from easybuild.base import fancylogger
from easybuild.base.testing import TestCase
import easybuild.tools.build_log as eb_build_log
import easybuild.tools.options as eboptions
import easybuild.tools.toolchain.utilities as tc_utils
import easybuild.tools.module_naming_scheme.toolchain as mns_toolchain
from easybuild.framework.easyconfig import easyconfig
from easybuild.framework.easyblock import EasyBlock
from easybuild.main import main
from easybuild.tools import config
from easybuild.tools.config import GENERAL_CLASS, Singleton, module_classes, update_build_option
from easybuild.tools.configobj import ConfigObj
from easybuild.tools.environment import modify_env
from easybuild.tools.filetools import copy_dir, mkdir, read_file, which
from easybuild.tools.modules import curr_module_paths, modules_tool, reset_module_caches
from easybuild.tools.options import CONFIG_ENV_VAR_PREFIX, EasyBuildOptions, set_tmpdir
from easybuild.tools.py2vs3 import reload


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


class EnhancedTestCase(TestCase):
    """Enhanced test case, provides extra functionality (e.g. an assertErrorRegex method)."""

    def setUp(self):
        """Set up testcase."""
        super(EnhancedTestCase, self).setUp()

        # make sure option parser doesn't pick up any cmdline arguments/options
        while len(sys.argv) > 1:
            sys.argv.pop()

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
        os.environ['EASYBUILD_ROBOT_PATHS'] = os.path.join(testdir, 'easyconfigs', 'test_ecs')

        # make sure that the EasyBuild installation is still known even if we purge an EB module
        if os.getenv('EB_SCRIPT_PATH') is None:
            eb_path = which('eb')
            if eb_path is not None:
                os.environ['EB_SCRIPT_PATH'] = eb_path

        # make sure no deprecated behaviour is being triggered (unless intended by the test)
        self.orig_current_version = eb_build_log.CURRENT_VERSION
        self.disallow_deprecated_behaviour()

        init_config()

        # disable progress bars when running the tests,
        # since it messes with test suite progress output when test installations are performed
        os.environ['EASYBUILD_DISABLE_SHOW_PROGRESS_BAR'] = '1'
        update_build_option('show_progress_bar', False)

        import easybuild
        # try to import easybuild.easyblocks(.generic) packages
        # it's OK if it fails here, but important to import first before fiddling with sys.path
        try:
            import easybuild.easyblocks
            import easybuild.easyblocks.generic
        except ImportError:
            pass

        # add sandbox to Python search path, update namespace packages
        testdir_sandbox = os.path.join(testdir, 'sandbox')
        sys.path.append(testdir_sandbox)

        # required to make sure the 'easybuild' dir in the sandbox is picked up;
        # this relates to the other 'reload' statements below
        reload(easybuild)

        # required to 'reset' easybuild.tools.module_naming_scheme namespace
        reload(easybuild.tools)
        reload(easybuild.tools.module_naming_scheme)

        # remove any entries in Python search path that seem to provide easyblocks (except the sandbox)
        for path in sys.path[:]:
            if os.path.exists(os.path.join(path, 'easybuild', 'easyblocks', '__init__.py')):
                if not os.path.samefile(path, testdir_sandbox):
                    sys.path.remove(path)

        # hard inject location to (generic) test easyblocks into Python search path
        # only prepending to sys.path is not enough due to 'pkgutil.extend_path' in easybuild/easyblocks/__init__.py
        easybuild.__path__.insert(0, os.path.join(testdir_sandbox, 'easybuild'))
        import easybuild.easyblocks
        test_easyblocks_path = os.path.join(testdir_sandbox, 'easybuild', 'easyblocks')
        easybuild.easyblocks.__path__.insert(0, test_easyblocks_path)
        reload(easybuild.easyblocks)

        import easybuild.easyblocks.generic
        test_easyblocks_path = os.path.join(test_easyblocks_path, 'generic')
        easybuild.easyblocks.generic.__path__.insert(0, test_easyblocks_path)
        reload(easybuild.easyblocks.generic)

        # kick out any paths that shouldn't be there for easybuild.easyblocks and easybuild.easyblocks.generic
        # to avoid that easyblocks picked up from other places cause trouble
        for pkg in ('easybuild.easyblocks', 'easybuild.easyblocks.generic'):
            for path in sys.modules[pkg].__path__[:]:
                if testdir_sandbox not in path:
                    sys.modules[pkg].__path__.remove(path)

        # save values of $PATH & $PYTHONPATH, so they can be restored later
        # this is important in case EasyBuild was installed as a module, since that module may be unloaded,
        # for example due to changes to $MODULEPATH in case EasyBuild was installed in a module hierarchy
        # cfr. https://github.com/easybuilders/easybuild-framework/issues/1685
        self.env_path = os.environ.get('PATH')
        self.env_pythonpath = os.environ.get('PYTHONPATH')

        self.modtool = modules_tool()
        self.reset_modulepath([os.path.join(testdir, 'modules')])
        reset_module_caches()

    def disallow_deprecated_behaviour(self):
        """trip *all* log.deprecated statements by setting deprecation version ridiculously high"""
        os.environ['EASYBUILD_DEPRECATED'] = '10000000'
        eb_build_log.CURRENT_VERSION = os.environ['EASYBUILD_DEPRECATED']

    def allow_deprecated_behaviour(self):
        """Restore EasyBuild version to what it was originally, to allow triggering deprecated behaviour."""
        if 'EASYBUILD_DEPRECATED' in os.environ:
            del os.environ['EASYBUILD_DEPRECATED']
        eb_build_log.CURRENT_VERSION = self.orig_current_version

    @contextmanager
    def log_to_testlogfile(self):
        """Context manager class to capture log output in self.logfile for the scope used. Clears the file first"""
        open(self.logfile, 'w').close()  # Remove all contents
        fancylogger.logToFile(self.logfile)
        try:
            yield self.logfile
        finally:
            fancylogger.logToFile(self.logfile, enable=False)

    def tearDown(self):
        """Clean up after running testcase."""
        super(EnhancedTestCase, self).tearDown()

        self.log.info("Cleaning up for test %s", self.id())

        # go back to where we were before
        os.chdir(self.cwd)

        # restore original environment
        modify_env(os.environ, self.orig_environ, verbose=False)

        self.allow_deprecated_behaviour()

        # restore original Python search path
        sys.path[:] = self.orig_sys_path
        import easybuild.easyblocks
        reload(easybuild.easyblocks)
        import easybuild.easyblocks.generic
        reload(easybuild.easyblocks.generic)

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

    def restore_env_path_pythonpath(self):
        """
        Restore $PATH & $PYTHONPATH in environment using saved values.
        """
        if self.env_path is not None:
            os.environ['PATH'] = self.env_path
        if self.env_pythonpath is not None:
            os.environ['PYTHONPATH'] = self.env_pythonpath

    def reset_modulepath(self, modpaths):
        """Reset $MODULEPATH with specified paths."""
        for modpath in curr_module_paths():
            self.modtool.remove_module_path(modpath, set_mod_paths=False)
        # make very sure $MODULEPATH is totally empty
        # some paths may be left behind, e.g. when they contain environment variables
        # example: "module unuse Modules/$MODULE_VERSION/modulefiles" may not yield the desired result
        if 'MODULEPATH' in os.environ:
            del os.environ['MODULEPATH']
        for modpath in modpaths:
            self.modtool.add_module_path(modpath, set_mod_paths=False)
        self.modtool.set_mod_paths()

    def eb_main(self, args, do_build=False, return_error=False, logfile=None, verbose=False, raise_error=False,
                reset_env=True, raise_systemexit=False, testing=True, redo_init_config=True, clear_caches=True):
        """Helper method to call EasyBuild main function."""

        cleanup(clear_caches=clear_caches)

        # always run main in unit testing mode (which for example allows for using deprecated toolchains);
        # note: don't change 'args' value, which is passed by reference!
        main_args = args + ['--unit-testing-mode']

        myerr = False
        if logfile is None:
            logfile = self.logfile
        # clear log file
        if logfile:
            with open(logfile, 'w') as fh:
                fh.write('')

        env_before = copy.deepcopy(os.environ)

        try:
            if '--fetch' in args:
                # The config sets modules_tool to None if --fetch is specified,
                # so do the same here to keep the behavior consistent
                modtool = None
            else:
                modtool = self.modtool
            main(args=main_args, logfile=logfile, do_build=do_build, testing=testing, modtool=modtool)
        except SystemExit as err:
            if raise_systemexit:
                raise err
        except Exception as err:
            myerr = err
            if verbose:
                print("err: %s" % err)

        if logfile and os.path.exists(logfile):
            logtxt = read_file(logfile)
        else:
            logtxt = None

        os.chdir(self.cwd)

        if redo_init_config:
            # make sure config is reinitialized
            init_config(with_include=False, clear_caches=clear_caches)

        # restore environment to what it was before running main,
        # changes may have been made by eb_main (e.g. $TMPDIR & co)
        if reset_env:
            modify_env(os.environ, env_before, verbose=False)
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
            copy_dir(src_mod_path, os.path.join(mod_prefix, mod_subdir))

        # make sure only modules in a hierarchical scheme are available, mixing modules installed with
        # a flat scheme like EasyBuildMNS and a hierarhical one like HierarchicalMNS doesn't work
        self.reset_modulepath([mod_prefix, os.path.join(mod_prefix, 'Core')])

        # tweak use statements in modules to ensure correct paths
        mpi_pref = os.path.join(mod_prefix, 'MPI', 'GCC', '6.4.0-2.28', 'OpenMPI', '2.1.2')
        for modfile in [
            os.path.join(mod_prefix, 'Core', 'GCC', '6.4.0-2.28'),
            os.path.join(mod_prefix, 'Core', 'GCC', '4.9.3-2.25'),
            os.path.join(mod_prefix, 'Core', 'icc', '2016.1.150-GCC-4.9.3-2.25'),
            os.path.join(mod_prefix, 'Core', 'ifort', '2016.1.150-GCC-4.9.3-2.25'),
            os.path.join(mod_prefix, 'Compiler', 'GCC', '6.4.0-2.28', 'OpenMPI', '2.1.2'),
            os.path.join(mod_prefix, 'Compiler', 'intel', '2016.1.150-GCC-4.9.3-2.25', 'impi', '5.1.2.150'),
            os.path.join(mpi_pref, 'FFTW', '3.3.7'),
            os.path.join(mpi_pref, 'OpenBLAS', '0.2.20'),
            os.path.join(mpi_pref, 'ScaLAPACK', '2.0.2-OpenBLAS-0.2.20'),
        ]:
            for line in fileinput.input(modfile, inplace=1):
                line = re.sub(r"(module\s*use\s*)/tmp/modules/all",
                              r"\1%s/modules/all" % self.test_installpath,
                              line)
                sys.stdout.write(line)

        # make sure paths for 'module use' commands exist; required for modulecmd
        mod_subdirs = [
            os.path.join('Compiler', 'GCC', '6.4.0-2.28'),
            os.path.join('Compiler', 'GCC', '4.9.3-2.25'),
            os.path.join('Compiler', 'intel', '2016.1.150-GCC-4.9.3-2.25'),
            os.path.join('MPI', 'GCC', '6.4.0-2.28', 'OpenMPI', '2.1.2'),
            os.path.join('MPI', 'intel', '2016.1.150-GCC-4.9.3-2.25', 'impi', '5.1.2.150'),
        ]
        for mod_subdir in mod_subdirs:
            mkdir(os.path.join(mod_prefix, mod_subdir), parents=True)

    def setup_categorized_hmns_modules(self):
        """Setup categorized hierarchical modules to run tests on."""
        mod_prefix = os.path.join(self.test_installpath, 'modules', 'all')

        # simply copy module files under 'CategorizedHMNS/{Core,Compiler,MPI}' to test install path
        # EasyBuild is responsible for making sure that the toolchain can be loaded using the short module name
        mkdir(mod_prefix, parents=True)
        for mod_subdir in ['Core', 'Compiler', 'MPI']:
            src_mod_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        'modules', 'CategorizedHMNS', mod_subdir)
            copy_dir(src_mod_path, os.path.join(mod_prefix, mod_subdir))
        # create empty module file directory to make C/Tcl modules happy
        mpi_pref = os.path.join(mod_prefix, 'MPI', 'GCC', '6.4.0-2.28', 'OpenMPI', '2.1.2')
        mkdir(os.path.join(mpi_pref, 'base'))

        # make sure only modules in the CategorizedHMNS are available
        self.reset_modulepath([os.path.join(mod_prefix, 'Core', 'compiler'),
                               os.path.join(mod_prefix, 'Core', 'toolchain')])

        # tweak use statements in modules to ensure correct paths
        for modfile in [
            os.path.join(mod_prefix, 'Core', 'compiler', 'GCC', '6.4.0-2.28'),
            os.path.join(mod_prefix, 'Compiler', 'GCC', '6.4.0-2.28', 'mpi', 'OpenMPI', '2.1.2'),
        ]:
            for line in fileinput.input(modfile, inplace=1):
                line = re.sub(r"(module\s*use\s*)/tmp/modules/all",
                              r"\1%s/modules/all" % self.test_installpath,
                              line)
                sys.stdout.write(line)


class TestLoaderFiltered(unittest.TestLoader):
    """Test load that supports filtering of tests based on name."""

    def loadTestsFromTestCase(self, test_case_class, filters):
        """Return a suite of all tests cases contained in test_case_class."""

        test_case_names = self.getTestCaseNames(test_case_class)
        test_cnt = len(test_case_names)
        retained_test_names = []
        if len(filters) > 0:
            for test_case_name in test_case_names:
                if any(filt in test_case_name for filt in filters):
                    retained_test_names.append(test_case_name)

            retained_tests = ', '.join(retained_test_names)
            tup = (test_case_class.__name__, '|'.join(filters), len(retained_test_names), test_cnt, retained_tests)
            print("Filtered %s tests using '%s', retained %d/%d tests: %s" % tup)

            test_cases = [test_case_class(t) for t in retained_test_names]
        else:
            test_cases = [test_case_class(test_case_name) for test_case_name in test_case_names]

        return self.suiteClass(test_cases)


def cleanup(clear_caches=True):
    """Perform cleanup of singletons and caches."""

    # clear Singleton instances, to start afresh
    Singleton._instances.clear()

    # clear various caches, to start with a clean slate
    if clear_caches:
        tc_utils._initial_toolchain_instances.clear()
        easyconfig._easyconfigs_cache.clear()
        easyconfig._easyconfig_files_cache.clear()
        easyconfig.get_toolchain_hierarchy.clear()
        mns_toolchain._toolchain_details_cache.clear()

    # reset to make sure tempfile picks up new temporary directory to use
    tempfile.tempdir = None


def init_config(args=None, build_options=None, with_include=True, clear_caches=True):
    """(re)initialize configuration"""

    cleanup(clear_caches=clear_caches)

    # initialize configuration so config.get_modules_tool function works
    eb_go = eboptions.parse_options(args=args, with_include=with_include)
    config.init(eb_go.options, eb_go.get_options_by_section('config'))

    # initialize build options
    if build_options is None:
        build_options = {}

    default_build_options = {
        'extended_dry_run': False,
        'external_modules_metadata': ConfigObj(),
        'local_var_naming_check': 'error',
        'silence_deprecation_warnings': eb_go.options.silence_deprecation_warnings,
        'suffix_modules_path': GENERAL_CLASS,
        'unit_testing_mode': True,
        'valid_module_classes': module_classes(),
        'valid_stops': [x[0] for x in EasyBlock.get_steps()],
    }
    for key in default_build_options:
        if key not in build_options:
            build_options[key] = default_build_options[key]

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
