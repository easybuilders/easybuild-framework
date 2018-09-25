# #
# Copyright 2013-2018 Ghent University
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
Unit tests for eb command line options.

@author: Kenneth Hoste (Ghent University)
"""
import glob
import os
import re
import shutil
import sys
import tempfile
from unittest import TextTestRunner
from urllib2 import URLError

import easybuild.main
import easybuild.tools.build_log
import easybuild.tools.options
import easybuild.tools.toolchain
from easybuild.framework.easyblock import EasyBlock, FETCH_STEP
from easybuild.framework.easyconfig import BUILD, CUSTOM, DEPENDENCIES, EXTENSIONS, FILEMANAGEMENT, LICENSE
from easybuild.framework.easyconfig import MANDATORY, MODULES, OTHER, TOOLCHAIN
from easybuild.framework.easyconfig.easyconfig import EasyConfig, get_easyblock_class, robot_find_easyconfig
from easybuild.framework.easyconfig.parser import EasyConfigParser
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import DEFAULT_MODULECLASSES
from easybuild.tools.config import find_last_log, get_build_log_path, get_module_syntax, module_classes
from easybuild.tools.environment import modify_env
from easybuild.tools.filetools import copy_dir, copy_file, download_file, mkdir, read_file, remove_file, write_file
from easybuild.tools.github import GITHUB_RAW, GITHUB_EB_MAIN, GITHUB_EASYCONFIGS_REPO, URL_SEPARATOR
from easybuild.tools.github import fetch_github_token
from easybuild.tools.modules import Lmod
from easybuild.tools.options import EasyBuildOptions, parse_external_modules_metadata, set_tmpdir, use_color
from easybuild.tools.toolchain.utilities import TC_CONST_PREFIX
from easybuild.tools.run import run_cmd
from easybuild.tools.version import VERSION
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from vsc.utils import fancylogger


EXTERNAL_MODULES_METADATA = """[foobar/1.2.3]
name = foo, bar
version = 1.2.3, 3.2.1
prefix = FOOBAR_DIR

[foobar/2.0]
name = foobar
version = 2.0
prefix = FOOBAR_PREFIX

[foo]
name = Foo
prefix = /foo

[bar/1.2.3]
name = bar
version = 1.2.3
"""

# test account, for which a token may be available
GITHUB_TEST_ACCOUNT = 'easybuild_test'


class CommandLineOptionsTest(EnhancedTestCase):
    """Testcases for command line options."""

    logfile = None

    def setUp(self):
        """Set up test."""
        super(CommandLineOptionsTest, self).setUp()
        self.github_token = fetch_github_token(GITHUB_TEST_ACCOUNT)

        self.orig_terminal_supports_colors = easybuild.tools.options.terminal_supports_colors
        self.orig_os_getuid = easybuild.main.os.getuid

    def tearDown(self):
        """Clean up after test."""
        easybuild.main.os.getuid = self.orig_os_getuid
        easybuild.tools.options.terminal_supports_colors = self.orig_terminal_supports_colors
        super(CommandLineOptionsTest, self).tearDown()

    def purge_environment(self):
        """Remove any leftover easybuild variables"""
        for var in os.environ.keys():
            # retain $EASYBUILD_IGNORECONFIGFILES, to make sure the test is isolated from system-wide config files!
            if var.startswith('EASYBUILD_') and var != 'EASYBUILD_IGNORECONFIGFILES':
                del os.environ[var]

    def test_help_short(self, txt=None):
        """Test short help message."""

        if txt is None:
            topt = EasyBuildOptions(
                                    go_args=['-h'],
                                    go_nosystemexit=True,  # when printing help, optparse ends with sys.exit
                                    go_columns=100,  # fix col size for reproducible unittest output
                                    help_to_string=True,  # don't print to stdout, but to StingIO fh,
                                    prog='easybuildoptions_test',  # generate as if called from generaloption.py
                                   )

            outtxt = topt.parser.help_to_file.getvalue()
        else:
            outtxt = txt

        self.assertTrue(re.search(' -h ', outtxt), "Only short options included in short help")
        self.assertTrue(re.search("show short help message and exit", outtxt), "Documentation included in short help")
        self.assertEqual(re.search("--short-help ", outtxt), None, "Long options not included in short help")
        self.assertEqual(re.search("Software search and build options", outtxt), None, "Not all option groups included in short help (1)")
        self.assertEqual(re.search("Regression test options", outtxt), None, "Not all option groups included in short help (2)")

    def test_help_long(self):
        """Test long help message."""

        topt = EasyBuildOptions(
                                go_args=['-H'],
                                go_nosystemexit=True,  # when printing help, optparse ends with sys.exit
                                go_columns=100,  # fix col size for reproducible unittest output
                                help_to_string=True,  # don't print to stdout, but to StingIO fh,
                                prog='easybuildoptions_test',  # generate as if called from generaloption.py
                               )
        outtxt = topt.parser.help_to_file.getvalue()

        self.assertTrue(re.search("-H OUTPUT_FORMAT, --help=OUTPUT_FORMAT", outtxt), "Long documentation expanded in long help")
        self.assertTrue(re.search("show short help message and exit", outtxt), "Documentation included in long help")
        self.assertTrue(re.search("Software search and build options", outtxt), "Not all option groups included in short help (1)")
        self.assertTrue(re.search("Regression test options", outtxt), "Not all option groups included in short help (2)")

    def test_no_args(self):
        """Test using no arguments."""

        outtxt = self.eb_main([])

        error_msg = "ERROR.* Please provide one or multiple easyconfig files,"
        error_msg += " or use software build options to make EasyBuild search for easyconfigs"
        regex = re.compile(error_msg)
        self.assertTrue(regex.search(outtxt), "Pattern '%s' found in: %s" % (regex.pattern, outtxt))

    def test_debug(self):
        """Test enabling debug logging."""
        for debug_arg in ['-d', '--debug']:
            args = [
                'nosuchfile.eb',
                debug_arg,
            ]
            outtxt = self.eb_main(args)

            for log_msg_type in ['DEBUG', 'INFO', 'ERROR']:
                res = re.search(' %s ' % log_msg_type, outtxt)
                self.assertTrue(res, "%s log messages are included when using %s: %s" % (log_msg_type, debug_arg, outtxt))

    def test_info(self):
        """Test enabling info logging."""

        for info_arg in ['--info']:
            args = [
                    'nosuchfile.eb',
                    info_arg,
                   ]
            outtxt = self.eb_main(args)

            for log_msg_type in ['INFO', 'ERROR']:
                res = re.search(' %s ' % log_msg_type, outtxt)
                self.assertTrue(res, "%s log messages are included when using %s ( out: %s)" % (log_msg_type, info_arg, outtxt))

            for log_msg_type in ['DEBUG']:
                res = re.search(' %s ' % log_msg_type, outtxt)
                self.assertTrue(not res, "%s log messages are *not* included when using %s" % (log_msg_type, info_arg))

    def test_quiet(self):
        """Test enabling quiet logging (errors only)."""
        for quiet_arg in ['--quiet']:
            args = [
                    'nosuchfile.eb',
                    quiet_arg,
                   ]
            outtxt = self.eb_main(args)

            for log_msg_type in ['ERROR']:
                res = re.search(' %s ' % log_msg_type, outtxt)
                msg = "%s log messages are included when using %s (outtxt: %s)" % (log_msg_type, quiet_arg, outtxt)
                self.assertTrue(res, msg)

            for log_msg_type in ['DEBUG', 'INFO']:
                res = re.search(' %s ' % log_msg_type, outtxt)
                msg = "%s log messages are *not* included when using %s (outtxt: %s)" % (log_msg_type, quiet_arg, outtxt)
                self.assertTrue(not res, msg)

    def test_force(self):
        """Test forcing installation even if the module is already available."""

        # use GCC-4.6.3.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 'g', 'GCC', 'GCC-4.6.3.eb')

        # check log message without --force
        args = [
                eb_file,
                '--debug',
               ]
        outtxt, error_thrown = self.eb_main(args, return_error=True)

        self.assertTrue(not error_thrown, "No error is thrown if software is already installed (error_thrown: %s)" % error_thrown)

        already_msg = "GCC/4.6.3 is already installed"
        self.assertTrue(re.search(already_msg, outtxt), "Already installed message without --force, outtxt: %s" % outtxt)

        # clear log file
        write_file(self.logfile, '')

        # check that --force and --rebuild work
        for arg in ['--force', '--rebuild']:
            outtxt = self.eb_main([eb_file, '--debug', arg])
            self.assertTrue(not re.search(already_msg, outtxt), "Already installed message not there with %s" % arg)

    def test_skip(self):
        """Test skipping installation of module (--skip, -k)."""

        # use toy-0.0.eb easyconfig file that comes with the tests
        topdir = os.path.abspath(os.path.dirname(__file__))
        toy_ec = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        # check log message with --skip for existing module
        args = [
            toy_ec,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--force',
            '--debug',
        ]
        self.eb_main(args, do_build=True)

        args.append('--skip')
        outtxt = self.eb_main(args, do_build=True, verbose=True)

        found_msg = "Module toy/0.0 found.\n[^\n]+Going to skip actual main build"
        found = re.search(found_msg, outtxt, re.M)
        self.assertTrue(found, "Module found message present with --skip, outtxt: %s" % outtxt)

        # cleanup for next test
        write_file(self.logfile, '')
        os.chdir(self.cwd)

        # check log message with --skip for non-existing module
        args = [
            toy_ec,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--try-software-version=1.2.3.4.5.6.7.8.9',
            '--try-amend=sources=toy-0.0.tar.gz,toy-0.0.tar.gz',  # hackish, but fine
            '--force',
            '--debug',
            '--skip',
        ]
        outtxt = self.eb_main(args, do_build=True, verbose=True)

        found_msg = "Module toy/1.2.3.4.5.6.7.8.9 found."
        found = re.search(found_msg, outtxt)
        self.assertTrue(not found, "Module found message not there with --skip for non-existing modules: %s" % outtxt)

        not_found_msg = "No module toy/1.2.3.4.5.6.7.8.9 found. Not skipping anything."
        not_found = re.search(not_found_msg, outtxt)
        self.assertTrue(not_found, "Module not found message there with --skip for non-existing modules: %s" % outtxt)

        toy_mod_glob = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '*')
        for toy_mod in glob.glob(toy_mod_glob):
            remove_file(toy_mod)
        self.assertFalse(glob.glob(toy_mod_glob))

        # make sure that sanity check is *NOT* skipped under --skip
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ec_txt = read_file(toy_ec)
        regex = re.compile("sanity_check_paths = \{(.|\n)*\}", re.M)
        test_ec_txt = regex.sub("sanity_check_paths = {'files': ['bin/nosuchfile'], 'dirs': []}", test_ec_txt)
        write_file(test_ec, test_ec_txt)
        args = [
            test_ec,
            '--skip',
            '--force',
        ]
        error_pattern = "Sanity check failed: no file found at 'bin/nosuchfile'"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.eb_main, args, do_build=True, raise_error=True)

        # check use of skipsteps to skip sanity check
        test_ec_txt += "\nskipsteps = ['sanitycheck']\n"
        write_file(test_ec, test_ec_txt)
        self.eb_main(args, do_build=True, raise_error=True)

        self.assertEqual(len(glob.glob(toy_mod_glob)), 1)

    def test_job(self):
        """Test submitting build as a job."""

        # use gzip-1.4.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 'g', 'gzip', 'gzip-1.4.eb')

        def check_args(job_args, passed_args=None):
            """Check whether specified args yield expected result."""
            if passed_args is None:
                passed_args = job_args[:]

            # clear log file
            write_file(self.logfile, '')

            args = [
                    eb_file,
                    '--job',
                   ] + job_args
            outtxt = self.eb_main(args)

            job_msg = "INFO.* Command template for jobs: .* && eb %%\(spec\)s.* %s.*\n" % ' .*'.join(passed_args)
            assertmsg = "Info log msg with job command template for --job (job_msg: %s, outtxt: %s)" % (job_msg, outtxt)
            self.assertTrue(re.search(job_msg, outtxt), assertmsg)

        # options passed are reordered, so order here matters to make tests pass
        check_args(['--debug'])
        check_args(['--debug', '--stop=configure', '--try-software-name=foo'],
                   passed_args=['--debug', "--stop='configure'"])
        check_args(['--debug', '--robot-paths=/tmp/foo:/tmp/bar'],
                   passed_args=['--debug', "--robot-paths='/tmp/foo:/tmp/bar'"])
        # --robot has preference over --robot-paths, --robot is not passed down
        check_args(['--debug', '--robot-paths=/tmp/foo', '--robot=/tmp/bar'],
                   passed_args=['--debug', "--robot-paths='/tmp/bar:/tmp/foo'"])

    # 'zzz' prefix in the test name is intentional to make this test run last,
    # since it fiddles with the logging infrastructure which may break things
    def test_zzz_logtostdout(self):
        """Testing redirecting log to stdout."""

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        for stdout_arg in ['--logtostdout', '-l']:

            args = [
                '--software-name=somethingrandom',
                '--robot', '.',
                '--debug',
                stdout_arg,
            ]
            self.mock_stdout(True)
            self.eb_main(args, logfile=dummylogfn)
            stdout = self.get_stdout()
            self.mock_stdout(False)

            # make sure we restore
            fancylogger.logToScreen(enable=False, stdout=True)

            error_msg = "Log messages are printed to stdout when %s is used (stdout: %s)" % (stdout_arg, stdout)
            self.assertTrue(len(stdout) > 100, error_msg)


        topdir = os.path.dirname(os.path.abspath(__file__))
        toy_ecfile = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        self.logfile = None

        self.mock_stdout(True)
        self.eb_main([toy_ecfile, '--debug', '-l', '--force'], do_build=True, raise_error=True)
        stdout = self.get_stdout()
        self.mock_stdout(False)

        self.assertTrue("Auto-enabling streaming output" in stdout)
        self.assertTrue("== (streaming) output for command 'gcc toy.c -o toy':" in stdout)

        if os.path.exists(dummylogfn):
            os.remove(dummylogfn)

    def test_avail_easyconfig_params(self):
        """Test listing available easyconfig parameters."""

        def run_test(custom=None, extra_params=[], fmt=None):
            """Inner function to run actual test in current setting."""

            fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
            os.close(fd)

            avail_args = [
                '-a',
                '--avail-easyconfig-params',
            ]
            for avail_arg in avail_args:

                # clear log
                write_file(self.logfile, '')

                args = [
                    '--unittest-file=%s' % self.logfile,
                    avail_arg,
                ]
                if fmt is not None:
                    args.append(fmt)
                if custom is not None:
                    args.extend(['-e', custom])

                outtxt = self.eb_main(args, logfile=dummylogfn, verbose=True)
                logtxt = read_file(self.logfile)

                # check whether all parameter types are listed
                par_types = [BUILD, DEPENDENCIES, EXTENSIONS, FILEMANAGEMENT,
                             LICENSE, MANDATORY, MODULES, OTHER, TOOLCHAIN]
                if custom is not None:
                    par_types.append(CUSTOM)

                for param_type in [x[1] for x in par_types]:
                    # regex for parameter group title, matches both txt and rst formats
                    regex = re.compile("%s.*\n%s" % (param_type, '-' * len(param_type)), re.I)
                    tup = (param_type, avail_arg, args, logtxt)
                    msg = "Parameter type %s is featured in output of eb %s (args: %s): %s" % tup
                    self.assertTrue(regex.search(logtxt), msg)

                # check a couple of easyconfig parameters
                for param in ["name", "version", "toolchain", "versionsuffix", "buildopts", "sources", "start_dir",
                              "dependencies", "group", "exts_list", "moduleclass", "buildstats"] + extra_params:
                    # regex for parameter name (with optional '*') & description, matches both txt and rst formats
                    regex = re.compile("^[`]*%s(?:\*)?[`]*\s+\w+" % param, re.M)
                    tup = (param, avail_arg, args, regex.pattern, logtxt)
                    msg = "Parameter %s is listed with help in output of eb %s (args: %s, regex: %s): %s" % tup
                    self.assertTrue(regex.search(logtxt), msg)

            if os.path.exists(dummylogfn):
                os.remove(dummylogfn)

        for fmt in [None, 'txt', 'rst']:
            run_test(fmt=fmt)
            run_test(custom='EB_foo', extra_params=['foo_extra1', 'foo_extra2'], fmt=fmt)
            run_test(custom='bar', extra_params=['bar_extra1', 'bar_extra2'], fmt=fmt)
            run_test(custom='EB_foofoo', extra_params=['foofoo_extra1', 'foofoo_extra2'], fmt=fmt)

    # double underscore to make sure it runs first, which is required to detect certain types of bugs,
    # e.g. running with non-initialized EasyBuild config (truly mimicing 'eb --list-toolchains')
    def test__list_toolchains(self):
        """Test listing known compiler toolchains."""

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        args = [
                '--list-toolchains',
                '--unittest-file=%s' % self.logfile,
               ]
        outtxt = self.eb_main(args, logfile=dummylogfn)

        info_msg = r"INFO List of known toolchains \(toolchainname: module\[,module\.\.\.\]\):"
        logtxt = read_file(self.logfile)
        self.assertTrue(re.search(info_msg, logtxt), "Info message with list of known toolchains found in: %s" % logtxt)
        # toolchain elements should be in alphabetical order
        tcs = {
            'dummy': [],
            'goalf': ['ATLAS', 'BLACS', 'FFTW', 'GCC', 'OpenMPI', 'ScaLAPACK'],
            'ictce': ['icc', 'ifort', 'imkl', 'impi'],
        }
        for tc, tcelems in tcs.items():
            res = re.findall("^\s*%s: .*" % tc, logtxt, re.M)
            self.assertTrue(res, "Toolchain %s is included in list of known compiler toolchains" % tc)
            # every toolchain should only be mentioned once
            n = len(res)
            self.assertEqual(n, 1, "Toolchain %s is only mentioned once (count: %d)" % (tc, n))
            # make sure definition is correct (each element only named once, in alphabetical order)
            self.assertEqual("\t%s: %s" % (tc, ', '.join(tcelems)), res[0])

        if os.path.exists(dummylogfn):
            os.remove(dummylogfn)

    def test_avail_lists(self):
        """Test listing available values of certain types."""

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        name_items = {
            'modules-tools': ['EnvironmentModulesC', 'Lmod'],
            'module-naming-schemes': ['EasyBuildMNS', 'HierarchicalMNS', 'CategorizedHMNS'],
        }
        for (name, items) in name_items.items():
            args = [
                    '--avail-%s' % name,
                    '--unittest-file=%s' % self.logfile,
                   ]
            outtxt = self.eb_main(args, logfile=dummylogfn)
            logtxt = read_file(self.logfile)

            words = name.replace('-', ' ')
            info_msg = r"INFO List of supported %s:" % words
            self.assertTrue(re.search(info_msg, logtxt), "Info message with list of available %s" % words)
            for item in items:
                res = re.findall("^\s*%s" % item, logtxt, re.M)
                self.assertTrue(res, "%s is included in list of available %s" % (item, words))
                # every item should only be mentioned once
                n = len(res)
                self.assertEqual(n, 1, "%s is only mentioned once (count: %d)" % (item, n))

        if os.path.exists(dummylogfn):
            os.remove(dummylogfn)

    def test_avail_cfgfile_constants(self):
        """Test --avail-cfgfile-constants."""
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # copy test easyconfigs to easybuild/easyconfigs subdirectory of temp directory
        # to check whether easyconfigs install path is auto-included in robot path
        tmpdir = tempfile.mkdtemp(prefix='easybuild-easyconfigs-pkg-install-path')
        mkdir(os.path.join(tmpdir, 'easybuild'), parents=True)

        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        copy_dir(test_ecs_dir, os.path.join(tmpdir, 'easybuild', 'easyconfigs'))

        orig_sys_path = sys.path[:]
        sys.path.insert(0, tmpdir)  # prepend to give it preference over possible other installed easyconfigs pkgs

        args = [
            '--avail-cfgfile-constants',
            '--unittest-file=%s' % self.logfile,
        ]
        outtxt = self.eb_main(args, logfile=dummylogfn)
        logtxt = read_file(self.logfile)
        cfgfile_constants = {
            'DEFAULT_ROBOT_PATHS': os.path.join(tmpdir, 'easybuild', 'easyconfigs'),
        }
        for cst_name, cst_value in cfgfile_constants.items():
            cst_regex = re.compile(r"^\*\s%s:\s.*\s\[value: .*%s.*\]" % (cst_name, cst_value), re.M)
            tup = (cst_regex.pattern, logtxt)
            self.assertTrue(cst_regex.search(logtxt), "Pattern '%s' in --avail-cfgfile_constants output: %s" % tup)

        if os.path.exists(dummylogfn):
            os.remove(dummylogfn)
        sys.path[:] = orig_sys_path

    def test_list_easyblocks(self):
        """Test listing easyblock hierarchy."""

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # simple view
        for list_arg in ['--list-easyblocks', '--list-easyblocks=simple']:

            # clear log
            write_file(self.logfile, '')

            args = [
                    list_arg,
                    '--unittest-file=%s' % self.logfile,
                   ]
            self.eb_main(args, logfile=dummylogfn)
            logtxt = read_file(self.logfile)

            expected = '\n'.join([
                r'EasyBlock',
                r'\|-- bar',
                r'\|-- ConfigureMake',
                r'\|-- EB_foo',
                r'\|   \|-- EB_foofoo',
                r'\|-- EB_GCC',
                r'\|-- EB_HPL',
                r'\|-- EB_ScaLAPACK',
                r'\|-- EB_toy_buggy',
                r'\|-- ExtensionEasyBlock',
                r'\|   \|-- DummyExtension',
                r'\|   \|-- EB_toy',
                r'\|   \|-- Toy_Extension',
                r'\|-- ModuleRC',
                r'\|-- Toolchain',
                r'Extension',
                r'\|-- ExtensionEasyBlock',
                r'\|   \|-- DummyExtension',
                r'\|   \|-- EB_toy',
                r'\|   \|-- Toy_Extension',
            ])
            regex = re.compile(expected, re.M)
            self.assertTrue(regex.search(logtxt), "Pattern '%s' found in: %s" % (regex.pattern, logtxt))

        # clear log
        write_file(self.logfile, '')

        # detailed view
        args = [
                '--list-easyblocks=detailed',
                '--unittest-file=%s' % self.logfile,
               ]
        self.eb_main(args, logfile=dummylogfn)
        logtxt = read_file(self.logfile)

        for pat in [
                    r"EasyBlock\s+\(easybuild.framework.easyblock\)\n",
                    r"|--\s+EB_foo\s+\(easybuild.easyblocks.foo\)\n|\s+|--\s+EB_foofoo\s+\(easybuild.easyblocks.foofoo\)\n",
                    r"|--\s+bar\s+\(easybuild.easyblocks.generic.bar\)\n",
                   ]:

            msg = "Pattern '%s' is found in output of --list-easyblocks: %s" % (pat, logtxt)
            self.assertTrue(re.search(pat, logtxt), msg)

        if os.path.exists(dummylogfn):
            os.remove(dummylogfn)

    def test_search(self):
        """Test searching for easyconfigs."""

        test_easyconfigs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')

        # simple search
        args = [
            '--search=gzip',
            '--robot=%s' % test_easyconfigs_dir,
        ]
        self.mock_stdout(True)
        self.eb_main(args, testing=False)
        txt = self.get_stdout()
        self.mock_stdout(False)

        for ec in ["gzip-1.4.eb", "gzip-1.4-GCC-4.6.3.eb"]:
            regex = re.compile(r" \* \S*%s$" % ec, re.M)
            self.assertTrue(regex.search(txt), "Found pattern '%s' in: %s" % (regex.pattern, txt))

        # search w/ regex
        args = [
            '--search=^gcc.*2.eb',
            '--robot=%s' % test_easyconfigs_dir,
        ]
        self.mock_stdout(True)
        self.eb_main(args, testing=False)
        txt = self.get_stdout()
        self.mock_stdout(False)

        for ec in ['GCC-4.7.2.eb', 'GCC-4.8.2.eb', 'GCC-4.9.2.eb']:
            regex = re.compile(r" \* \S*%s$" % ec, re.M)
            self.assertTrue(regex.search(txt), "Found pattern '%s' in: %s" % (regex.pattern, txt))

        gcc_ecs = [
            'GCC-4.6.3.eb',
            'GCC-4.6.4.eb',
            'GCC-4.7.2.eb',
            'GCC-4.8.2.eb',
            'GCC-4.8.3.eb',
            'GCC-4.9.2.eb',
        ]

        # test --search-filename
        args = [
            '--search-filename=^gcc',
            '--robot=%s' % test_easyconfigs_dir,
        ]
        self.mock_stdout(True)
        self.eb_main(args, testing=False)
        txt = self.get_stdout()
        self.mock_stdout(False)

        for ec in gcc_ecs:
            regex = re.compile(r"^ \* %s$" % ec, re.M)
            self.assertTrue(regex.search(txt), "Found pattern '%s' in: %s" % (regex.pattern, txt))

        # test --search-filename --terse
        args = [
            '--search-filename=^gcc',
            '--terse',
            '--robot=%s' % test_easyconfigs_dir,
        ]
        self.mock_stdout(True)
        self.eb_main(args, testing=False)
        txt = self.get_stdout()
        self.mock_stdout(False)

        for ec in gcc_ecs:
            regex = re.compile(r"^%s$" % ec, re.M)
            self.assertTrue(regex.search(txt), "Found pattern '%s' in: %s" % (regex.pattern, txt))

        # also test --search-short/-S
        for search_arg in ['-S', '--search-short']:
            args = [
                search_arg,
                'toy-0.0',
                '-r',
                test_easyconfigs_dir,
            ]
            self.mock_stdout(True)
            self.eb_main(args, raise_error=True, verbose=True, testing=False)
            txt = self.get_stdout()
            self.mock_stdout(False)

            self.assertTrue(re.search('^CFGS\d+=', txt, re.M), "CFGS line message found in '%s'" % txt)
            for ec in ["toy-0.0.eb", "toy-0.0-multiple.eb"]:
                regex = re.compile(r" \* \$CFGS\d+/*%s" % ec, re.M)
                self.assertTrue(regex.search(txt), "Found pattern '%s' in: %s" % (regex.pattern, txt))

        # combining --search with --try-* should not cause trouble; --try-* should just be ignored
        args = [
            '--search=^gcc',
            '--robot-paths=%s' % test_easyconfigs_dir,
            '--try-toolchain-version=1.2.3',
        ]
        self.mock_stdout(True)
        self.eb_main(args, testing=False, raise_error=True)
        txt = self.get_stdout()
        self.mock_stdout(False)
        self.assertTrue(re.search('GCC-4.9.2', txt))

    def test_search_archived(self):
        "Test searching for archived easyconfigs"
        args = ['--search-filename=^ictce']
        self.mock_stdout(True)
        self.eb_main(args, testing=False)
        txt = self.get_stdout().rstrip()
        self.mock_stdout(False)
        expected = '\n'.join([
            ' * ictce-4.1.13.eb',
            '',
            "Note: 1 matching archived easyconfig(s) found, use --consider-archived-easyconfigs to see them",
        ])
        self.assertEqual(txt, expected)

        args.append('--consider-archived-easyconfigs')
        self.mock_stdout(True)
        self.eb_main(args, testing=False)
        txt = self.get_stdout().rstrip()
        self.mock_stdout(False)
        expected = '\n'.join([
            ' * ictce-4.1.13.eb',
            '',
            "Matching archived easyconfigs:",
            '',
            ' * ictce-3.2.2.u3.eb',
        ])
        self.assertEqual(txt, expected)

    def test_dry_run(self):
        """Test dry run (long format)."""
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        args = [
            'gzip-1.4-GCC-4.6.3.eb',
            '--dry-run',  # implies enabling dependency resolution
            '--unittest-file=%s' % self.logfile,
        ]
        self.eb_main(args, logfile=dummylogfn)
        logtxt = read_file(self.logfile)

        info_msg = r"Dry run: printing build status of easyconfigs and dependencies"
        self.assertTrue(re.search(info_msg, logtxt, re.M), "Info message dry running in '%s'" % logtxt)
        ecs_mods = [
            ("gzip-1.4-GCC-4.6.3.eb", "gzip/1.4-GCC-4.6.3", ' '),
            ("GCC-4.6.3.eb", "GCC/4.6.3", 'x'),
        ]
        for ec, mod, mark in ecs_mods:
            regex = re.compile(r" \* \[%s\] \S+%s \(module: %s\)" % (mark, ec, mod), re.M)
            self.assertTrue(regex.search(logtxt), "Found match for pattern %s in '%s'" % (regex.pattern, logtxt))

    def test_dry_run_short(self):
        """Test dry run (short format)."""
        # unset $EASYBUILD_ROBOT_PATHS that was defined in setUp
        del os.environ['EASYBUILD_ROBOT_PATHS']

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # copy test easyconfigs to easybuild/easyconfigs subdirectory of temp directory
        # to check whether easyconfigs install path is auto-included in robot path
        tmpdir = tempfile.mkdtemp(prefix='easybuild-easyconfigs-pkg-install-path')
        mkdir(os.path.join(tmpdir, 'easybuild'), parents=True)

        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        copy_dir(test_ecs_dir, os.path.join(tmpdir, 'easybuild', 'easyconfigs'))

        orig_sys_path = sys.path[:]
        sys.path.insert(0, tmpdir)  # prepend to give it preference over possible other installed easyconfigs pkgs

        for dry_run_arg in ['-D', '--dry-run-short']:
            open(self.logfile, 'w').write('')
            args = [
                os.path.join(tmpdir, 'easybuild', 'easyconfigs', 'g', 'gzip', 'gzip-1.4-GCC-4.6.3.eb'),
                dry_run_arg,
                # purposely specifying senseless dir, to test auto-inclusion of easyconfigs pkg path in robot path
                '--robot=%s' % os.path.join(tmpdir, 'robot_decoy'),
                '--unittest-file=%s' % self.logfile,
            ]
            outtxt = self.eb_main(args, logfile=dummylogfn)

            info_msg = r"Dry run: printing build status of easyconfigs and dependencies"
            self.assertTrue(re.search(info_msg, outtxt, re.M), "Info message dry running in '%s'" % outtxt)
            self.assertTrue(re.search('CFGS=', outtxt), "CFGS line message found in '%s'" % outtxt)
            ecs_mods = [
                ("gzip-1.4-GCC-4.6.3.eb", "gzip/1.4-GCC-4.6.3", ' '),
                ("GCC-4.6.3.eb", "GCC/4.6.3", 'x'),
            ]
            for ec, mod, mark in ecs_mods:
                regex = re.compile(r" \* \[%s\] \$CFGS\S+%s \(module: %s\)" % (mark, ec, mod), re.M)
                self.assertTrue(regex.search(outtxt), "Found match for pattern %s in '%s'" % (regex.pattern, outtxt))

        if os.path.exists(dummylogfn):
            os.remove(dummylogfn)

        # cleanup
        shutil.rmtree(tmpdir)
        sys.path[:] = orig_sys_path

    def test_try_robot_force(self):
        """
        Test correct behavior for combination of --try-toolchain --robot --force.
        Only the listed easyconfigs should be forced, resolved dependencies should not (even if tweaked).
        """
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # use toy-0.0.eb easyconfig file that comes with the tests
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        eb1 = os.path.join(test_ecs, 'f', 'FFTW', 'FFTW-3.3.3-gompi-1.4.10.eb')
        eb2 = os.path.join(test_ecs, 's', 'ScaLAPACK', 'ScaLAPACK-2.0.2-gompi-1.4.10-OpenBLAS-0.2.6-LAPACK-3.4.2.eb')

        # check log message with --skip for existing module
        args = [
            eb1,
            eb2,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--debug',
            '--force',
            '--robot=%s' % test_ecs,
            '--try-toolchain=gompi,1.3.12',
            '--dry-run',
            '--unittest-file=%s' % self.logfile,
        ]
        outtxt = self.eb_main(args, logfile=dummylogfn)

        scalapack_ver = '2.0.2-gompi-1.3.12-OpenBLAS-0.2.6-LAPACK-3.4.2'
        ecs_mods = [
            # GCC/OpenMPI dependencies are there, but part of toolchain => 'x'
            ("GCC-4.6.4.eb", "GCC/4.6.4", 'x'),
            ("OpenMPI-1.6.4-GCC-4.6.4.eb", "OpenMPI/1.6.4-GCC-4.6.4", 'x'),
            # OpenBLAS dependency is listed, but not there => ' '
            # toolchain used for OpenBLAS is mapped to GCC/4.6.4 subtoolchain in gompi/1.3.12
            # (rather than the original GCC/4.7.2 as subtoolchain of gompi/1.4.10)
            ("OpenBLAS-0.2.6-GCC-4.6.4-LAPACK-3.4.2.eb", "OpenBLAS/0.2.6-GCC-4.6.4-LAPACK-3.4.2", ' '),
            # both FFTW and ScaLAPACK are listed => 'F'
            ("ScaLAPACK-%s.eb" % scalapack_ver, "ScaLAPACK/%s" % scalapack_ver, 'F'),
            ("FFTW-3.3.3-gompi-1.3.12.eb", "FFTW/3.3.3-gompi-1.3.12", 'F'),
        ]
        for ec, mod, mark in ecs_mods:
            regex = re.compile("^ \* \[%s\] \S+%s \(module: %s\)$" % (mark, ec, mod), re.M)
            self.assertTrue(regex.search(outtxt), "Found match for pattern %s in '%s'" % (regex.pattern, outtxt))

    def test_dry_run_hierarchical(self):
        """Test dry run using a hierarchical module naming scheme."""
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        args = [
            'gzip-1.5-goolf-1.4.10.eb',
            'OpenMPI-1.6.4-GCC-4.7.2.eb',
            '--dry-run',
            '--unittest-file=%s' % self.logfile,
            '--module-naming-scheme=HierarchicalMNS',
            '--ignore-osdeps',
            '--force',
            '--debug',
        ]
        outtxt = self.eb_main(args, logfile=dummylogfn, verbose=True, raise_error=True)

        ecs_mods = [
            # easyconfig, module subdir, (short) module name
            ("GCC-4.7.2.eb", "Core", "GCC/4.7.2", 'x'),  # already present but not listed, so 'x'
            ("hwloc-1.6.2-GCC-4.7.2.eb", "Compiler/GCC/4.7.2", "hwloc/1.6.2", 'x'),
            ("OpenMPI-1.6.4-GCC-4.7.2.eb", "Compiler/GCC/4.7.2", "OpenMPI/1.6.4", 'F'),  # already present and listed, so 'F'
            ("gompi-1.4.10.eb", "Core", "gompi/1.4.10", 'x'),
            ("OpenBLAS-0.2.6-GCC-4.7.2-LAPACK-3.4.2.eb", "Compiler/GCC/4.7.2",
             "OpenBLAS/0.2.6-LAPACK-3.4.2", ' '),
            ("FFTW-3.3.3-gompi-1.4.10.eb", "MPI/GCC/4.7.2/OpenMPI/1.6.4", "FFTW/3.3.3", 'x'),
            ("ScaLAPACK-2.0.2-gompi-1.4.10-OpenBLAS-0.2.6-LAPACK-3.4.2.eb", "MPI/GCC/4.7.2/OpenMPI/1.6.4",
             "ScaLAPACK/2.0.2-OpenBLAS-0.2.6-LAPACK-3.4.2", 'x'),
            ("goolf-1.4.10.eb", "Core", "goolf/1.4.10", 'x'),
            ("gzip-1.5-goolf-1.4.10.eb", "MPI/GCC/4.7.2/OpenMPI/1.6.4", "gzip/1.5", ' '),  # listed but not there: ' '
        ]
        for ec, mod_subdir, mod_name, mark in ecs_mods:
            regex = re.compile("^ \* \[%s\] \S+%s \(module: %s \| %s\)$" % (mark, ec, mod_subdir, mod_name), re.M)
            self.assertTrue(regex.search(outtxt), "Found match for pattern %s in '%s'" % (regex.pattern, outtxt))

        if os.path.exists(dummylogfn):
            os.remove(dummylogfn)

    def test_dry_run_categorized(self):
        """Test dry run using a categorized hierarchical module naming scheme."""
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        self.setup_categorized_hmns_modules()
        args = [
            'gzip-1.5-goolf-1.4.10.eb',
            'OpenMPI-1.6.4-GCC-4.7.2.eb',
            '--dry-run',
            '--unittest-file=%s' % self.logfile,
            '--module-naming-scheme=CategorizedHMNS',
            '--ignore-osdeps',
            '--force',
            '--debug',
        ]
        outtxt = self.eb_main(args, logfile=dummylogfn, verbose=True, raise_error=True)

        ecs_mods = [
            # easyconfig, module subdir, (short) module name, mark
            ("GCC-4.7.2.eb", "Core/compiler", "GCC/4.7.2", 'x'),  # already present but not listed, so 'x'
            ("hwloc-1.6.2-GCC-4.7.2.eb", "Compiler/GCC/4.7.2/system", "hwloc/1.6.2", 'x'),
            ("OpenMPI-1.6.4-GCC-4.7.2.eb", "Compiler/GCC/4.7.2/mpi", "OpenMPI/1.6.4", 'F'),  # already present and listed, so 'F'
            ("gompi-1.4.10.eb", "Core/toolchain", "gompi/1.4.10", 'x'),
            ("OpenBLAS-0.2.6-GCC-4.7.2-LAPACK-3.4.2.eb", "Compiler/GCC/4.7.2/numlib",
             "OpenBLAS/0.2.6-LAPACK-3.4.2", ' '),
            ("FFTW-3.3.3-gompi-1.4.10.eb", "MPI/GCC/4.7.2/OpenMPI/1.6.4/numlib", "FFTW/3.3.3", 'x'),
            ("ScaLAPACK-2.0.2-gompi-1.4.10-OpenBLAS-0.2.6-LAPACK-3.4.2.eb", "MPI/GCC/4.7.2/OpenMPI/1.6.4/numlib",
             "ScaLAPACK/2.0.2-OpenBLAS-0.2.6-LAPACK-3.4.2", 'x'),
            ("goolf-1.4.10.eb", "Core/toolchain", "goolf/1.4.10", 'x'),
            ("gzip-1.5-goolf-1.4.10.eb", "MPI/GCC/4.7.2/OpenMPI/1.6.4/tools", "gzip/1.5", ' '),  # listed but not there: ' '
        ]
        for ec, mod_subdir, mod_name, mark in ecs_mods:
            regex = re.compile("^ \* \[%s\] \S+%s \(module: %s \| %s\)$" % (mark, ec, mod_subdir, mod_name), re.M)
            self.assertTrue(regex.search(outtxt), "Found match for pattern %s in '%s'" % (regex.pattern, outtxt))

        if os.path.exists(dummylogfn):
            os.remove(dummylogfn)

    def test_from_pr(self):
        """Test fetching easyconfigs from a PR."""
        if self.github_token is None:
            print "Skipping test_from_pr, no GitHub token available?"
            return

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        tmpdir = tempfile.mkdtemp()
        args = [
            # PR for foss/2015a, see https://github.com/easybuilders/easybuild-easyconfigs/pull/1239/files
            '--from-pr=1239',
            '--dry-run',
            # an argument must be specified to --robot, since easybuild-easyconfigs may not be installed
            '--robot=%s' % os.path.join(os.path.dirname(__file__), 'easyconfigs'),
            '--unittest-file=%s' % self.logfile,
            '--github-user=%s' % GITHUB_TEST_ACCOUNT,  # a GitHub token should be available for this user
            '--tmpdir=%s' % tmpdir,
        ]
        try:
            outtxt = self.eb_main(args, logfile=dummylogfn, raise_error=True)
            modules = [
                (tmpdir, 'FFTW/3.3.4-gompi-2015a'),
                (tmpdir, 'foss/2015a'),
                ('.*', 'GCC/4.9.2'),  # not included in PR
                (tmpdir, 'gompi/2015a'),
                (tmpdir, 'HPL/2.1-foss-2015a'),
                (tmpdir, 'hwloc/1.10.0-GCC-4.9.2'),
                (tmpdir, 'numactl/2.0.10-GCC-4.9.2'),
                (tmpdir, 'OpenBLAS/0.2.13-GCC-4.9.2-LAPACK-3.5.0'),
                (tmpdir, 'OpenMPI/1.8.3-GCC-4.9.2'),
                (tmpdir, 'OpenMPI/1.8.4-GCC-4.9.2'),
                (tmpdir, 'ScaLAPACK/2.0.2-gompi-2015a-OpenBLAS-0.2.13-LAPACK-3.5.0'),
            ]
            for path_prefix, module in modules:
                ec_fn = "%s.eb" % '-'.join(module.split('/'))
                path = '.*%s' % os.path.dirname(path_prefix)
                regex = re.compile(r"^ \* \[.\] %s.*%s \(module: %s\)$" % (path, ec_fn, module), re.M)
                self.assertTrue(regex.search(outtxt), "Found pattern %s in %s" % (regex.pattern, outtxt))

            # make sure that *only* these modules are listed, no others
            regex = re.compile(r"^ \* \[.\] .*/(?P<filepath>.*) \(module: (?P<module>.*)\)$", re.M)
            self.assertTrue(sorted(regex.findall(outtxt)), sorted(modules))

            pr_tmpdir = os.path.join(tmpdir, 'eb-\S{6}', 'files_pr1239')
            regex = re.compile("Appended list of robot search paths with %s:" % pr_tmpdir, re.M)
            self.assertTrue(regex.search(outtxt), "Found pattern %s in %s" % (regex.pattern, outtxt))
        except URLError, err:
            print "Ignoring URLError '%s' in test_from_pr" % err
            shutil.rmtree(tmpdir)

    def test_from_pr_listed_ecs(self):
        """Test --from-pr in combination with specifying easyconfigs on the command line."""
        if self.github_token is None:
            print "Skipping test_from_pr, no GitHub token available?"
            return

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # copy test easyconfigs to easybuild/easyconfigs subdirectory of temp directory
        test_ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        ecstmpdir = tempfile.mkdtemp(prefix='easybuild-easyconfigs-pkg-install-path')
        mkdir(os.path.join(ecstmpdir, 'easybuild'), parents=True)
        copy_dir(test_ecs_path, os.path.join(ecstmpdir, 'easybuild', 'easyconfigs'))

        # inject path to test easyconfigs into head of Python search path
        sys.path.insert(0, ecstmpdir)

        tmpdir = tempfile.mkdtemp()
        args = [
            'toy-0.0.eb',
            'gompi-2015a.eb',  # also pulls in GCC, OpenMPI (which pulls in hwloc and numactl)
            'GCC-4.6.3.eb',
            # PR for foss/2015a, see https://github.com/easybuilders/easybuild-easyconfigs/pull/1239/files
            '--from-pr=1239',
            '--dry-run',
            # an argument must be specified to --robot, since easybuild-easyconfigs may not be installed
            '--robot=%s' % test_ecs_path,
            '--unittest-file=%s' % self.logfile,
            '--github-user=%s' % GITHUB_TEST_ACCOUNT,  # a GitHub token should be available for this user
            '--tmpdir=%s' % tmpdir,
        ]
        try:
            outtxt = self.eb_main(args, logfile=dummylogfn, raise_error=True)
            modules = [
                (test_ecs_path, 'toy/0.0'),  # not included in PR
                (test_ecs_path, 'GCC/4.9.2'),  # not included in PR, available locally
                ('.*%s' % os.path.dirname(tmpdir), 'hwloc/1.10.0-GCC-4.9.2'),
                ('.*%s' % os.path.dirname(tmpdir), 'numactl/2.0.10-GCC-4.9.2'),
                ('.*%s' % os.path.dirname(tmpdir), 'OpenMPI/1.8.4-GCC-4.9.2'),
                ('.*%s' % os.path.dirname(tmpdir), 'gompi/2015a'),
                (test_ecs_path, 'GCC/4.6.3'),  # not included in PR, available locally
            ]
            for path_prefix, module in modules:
                ec_fn = "%s.eb" % '-'.join(module.split('/'))
                regex = re.compile(r"^ \* \[.\] %s.*%s \(module: %s\)$" % (path_prefix, ec_fn, module), re.M)
                self.assertTrue(regex.search(outtxt), "Found pattern %s in %s" % (regex.pattern, outtxt))

            # make sure that *only* these modules are listed, no others
            regex = re.compile(r"^ \* \[.\] .*/(?P<filepath>.*) \(module: (?P<module>.*)\)$", re.M)
            self.assertTrue(sorted(regex.findall(outtxt)), sorted(modules))

        except URLError, err:
            print "Ignoring URLError '%s' in test_from_pr" % err
            shutil.rmtree(tmpdir)

    def test_from_pr_x(self):
        """Test combination of --from-pr with --extended-dry-run."""
        if self.github_token is None:
            print "Skipping test_from_pr_x, no GitHub token available?"
            return

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        args = [
            # PR for foss/2015a, see https://github.com/easybuilders/easybuild-easyconfigs/pull/1239/files
            '--from-pr=1239',
            'FFTW-3.3.4-gompi-2015a.eb',  # required ConfigureMake easyblock, which is available in test easyblocks
            # an argument must be specified to --robot, since easybuild-easyconfigs may not be installed
            '--github-user=%s' % GITHUB_TEST_ACCOUNT,  # a GitHub token should be available for this user
            '--tmpdir=%s' % self.test_prefix,
            '--extended-dry-run',
        ]
        try:
            self.mock_stdout(True)
            self.eb_main(args, do_build=True, raise_error=True, testing=False)
            stdout = self.get_stdout()
            self.mock_stdout(False)

            msg_regexs = [
                re.compile(r"^== Build succeeded for 1 out of 1", re.M),
                re.compile(r"^\*\*\* DRY RUN using 'ConfigureMake' easyblock", re.M),
                re.compile(r"^== building and installing FFTW/3.3.4-gompi-2015a\.\.\.", re.M),
                re.compile(r"^building... \[DRY RUN\]", re.M),
                re.compile(r"^== COMPLETED: Installation ended successfully", re.M),
            ]

            for msg_regex in msg_regexs:
                self.assertTrue(msg_regex.search(stdout), "Pattern '%s' found in: %s" % (msg_regex.pattern, stdout))

        except URLError, err:
            print "Ignoring URLError '%s' in test_from_pr_x" % err

    def test_no_such_software(self):
        """Test using no arguments."""

        args = [
                '--software-name=nosuchsoftware',
                '--robot=.',
                '--debug',
               ]
        outtxt = self.eb_main(args)

        # error message when template is not found
        error_msg1 = "ERROR.* No easyconfig files found for software nosuchsoftware, and no templates available. "
        error_msg1 += "I'm all out of ideas."
        # error message when template is found
        error_msg2 = "ERROR Unable to find an easyconfig for the given specifications"
        regex = re.compile("(%s|%s)" % (error_msg1, error_msg2))
        self.assertTrue(regex.search(outtxt), "Pattern '%s' found in: %s" % (regex.pattern, outtxt))

    def test_header_footer(self):
        """Test specifying a module header/footer."""

        # create file containing modules footer
        if get_module_syntax() == 'Tcl':
            modules_header_txt = '\n'.join([
                "# test header",
                "setenv SITE_SPECIFIC_HEADER_ENV_VAR foo",
            ])
            modules_footer_txt = '\n'.join([
                "# test footer",
                "setenv SITE_SPECIFIC_FOOTER_ENV_VAR bar",
            ])
        elif get_module_syntax() == 'Lua':
            modules_header_txt = '\n'.join([
                "-- test header",
                'setenv("SITE_SPECIFIC_HEADER_ENV_VAR", "foo")',
            ])
            modules_footer_txt = '\n'.join([
                "-- test footer",
                'setenv("SITE_SPECIFIC_FOOTER_ENV_VAR", "bar")',
            ])
        else:
            self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())

        # dump header/footer text to file
        handle, modules_footer = tempfile.mkstemp(prefix='modules-footer-')
        os.close(handle)
        write_file(modules_footer, modules_footer_txt)
        handle, modules_header = tempfile.mkstemp(prefix='modules-header-')
        os.close(handle)
        write_file(modules_header, modules_header_txt)

        # use toy-0.0.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        # check log message with --skip for existing module
        args = [
            eb_file,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--debug',
            '--force',
            '--modules-header=%s' % modules_header,
            '--modules-footer=%s' % modules_footer,
        ]
        self.eb_main(args, do_build=True, raise_error=True)

        toy_module = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_module += '.lua'
        toy_module_txt = read_file(toy_module)

        regex = re.compile(r'%s$' % modules_header_txt.replace('(', '\\(').replace(')', '\\)'), re.M)
        msg = "modules header '%s' is present in '%s'" % (modules_header_txt, toy_module_txt)
        self.assertTrue(regex.search(toy_module_txt), msg)

        regex = re.compile(r'%s$' % modules_footer_txt.replace('(', '\\(').replace(')', '\\)'), re.M)
        msg = "modules footer '%s' is present in '%s'" % (modules_footer_txt, toy_module_txt)
        self.assertTrue(regex.search(toy_module_txt), msg)

        # cleanup
        os.remove(modules_footer)
        os.remove(modules_header)

    def test_recursive_module_unload(self):
        """Test generating recursively unloading modules."""

        # use toy-0.0.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-deps.eb')

        # check log message with --skip for existing module
        lastargs = ['--recursive-module-unload']
        if self.modtool.supports_depends_on:
            lastargs.append('--module-depends-on')
        for lastarg in lastargs:
            args = [
                eb_file,
                '--sourcepath=%s' % self.test_sourcepath,
                '--buildpath=%s' % self.test_buildpath,
                '--installpath=%s' % self.test_installpath,
                '--debug',
                '--force',
                lastarg,
            ]
            self.eb_main(args, do_build=True, verbose=True)

            toy_module = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0-deps')
            if get_module_syntax() == 'Lua':
                toy_module += '.lua'
            toy_module_txt = read_file(toy_module)
            is_loaded_regex = re.compile(r"if { !\[is-loaded gompi/1.3.12\] }", re.M)
            self.assertFalse(is_loaded_regex.search(toy_module_txt), "Recursive unloading is used: %s" % toy_module_txt)

    def test_tmpdir(self):
        """Test setting temporary directory to use by EasyBuild."""

        # use temporary paths for build/install paths, make sure sources can be found
        tmpdir = tempfile.mkdtemp()

        # use toy-0.0.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        # check log message with --skip for existing module
        args = [
            eb_file,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--debug',
            '--tmpdir=%s' % tmpdir,
        ]
        outtxt = self.eb_main(args, do_build=True, reset_env=False)

        tmpdir_msg = r"Using %s\S+ as temporary directory" % os.path.join(tmpdir, 'eb-')
        found = re.search(tmpdir_msg, outtxt, re.M)
        self.assertTrue(found, "Log message for tmpdir found in outtxt: %s" % outtxt)

        for var in ['TMPDIR', 'TEMP', 'TMP']:
            self.assertTrue(os.environ[var].startswith(os.path.join(tmpdir, 'eb-')))
        self.assertTrue(tempfile.gettempdir().startswith(os.path.join(tmpdir, 'eb-')))
        tempfile_tmpdir = tempfile.mkdtemp()
        self.assertTrue(tempfile_tmpdir.startswith(os.path.join(tmpdir, 'eb-')))
        fd, tempfile_tmpfile = tempfile.mkstemp()
        self.assertTrue(tempfile_tmpfile.startswith(os.path.join(tmpdir, 'eb-')))

        # cleanup
        os.close(fd)
        shutil.rmtree(tmpdir)

    def test_ignore_osdeps(self):
        """Test ignoring of listed OS dependencies."""
        txt = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"dummy", "version": "dummy"}',
            'osdependencies = ["nosuchosdependency", ("nosuchdep_option1", "nosuchdep_option2")]',
        ])
        fd, eb_file = tempfile.mkstemp(prefix='easyconfig_test_file_', suffix='.eb')
        os.close(fd)
        write_file(eb_file, txt)

        # check whether non-existing OS dependencies result in failure, by default
        args = [
            eb_file,
        ]
        outtxt = self.eb_main(args, do_build=True)

        regex = re.compile("Checking OS dependencies")
        self.assertTrue(regex.search(outtxt), "OS dependencies are checked, outtxt: %s" % outtxt)
        msg = "One or more OS dependencies were not found: "
        msg += "\[\('nosuchosdependency',\), \('nosuchdep_option1', 'nosuchdep_option2'\)\]"
        regex = re.compile(r'%s' % msg, re.M)
        self.assertTrue(regex.search(outtxt), "OS dependencies are honored, outtxt: %s" % outtxt)

        # check whether OS dependencies are effectively ignored
        args = [
            eb_file,
            '--ignore-osdeps',
            '--dry-run',
        ]
        outtxt = self.eb_main(args, do_build=True)

        regex = re.compile("Not checking OS dependencies", re.M)
        self.assertTrue(regex.search(outtxt), "OS dependencies are ignored with --ignore-osdeps, outtxt: %s" % outtxt)

        txt += "\nstop = 'notavalidstop'"
        write_file(eb_file, txt)
        args = [
            eb_file,
            '--dry-run',  # no explicit --ignore-osdeps, but implied by --dry-run
        ]
        outtxt = self.eb_main(args, do_build=True)

        regex = re.compile("stop provided 'notavalidstop' is not valid", re.M)
        self.assertTrue(regex.search(outtxt), "Validations are performed with --ignore-osdeps, outtxt: %s" % outtxt)

    def test_experimental(self):
        """Test the experimental option"""
        orig_value = easybuild.tools.build_log.EXPERIMENTAL
        # make sure it's off by default
        self.assertFalse(orig_value)

        log = fancylogger.getLogger()

        # force it to False
        topt = EasyBuildOptions(
            go_args=['--disable-experimental'],
        )
        try:
            log.experimental('x')
            # sanity check, should never be reached if it works.
            self.assertTrue(False, "Experimental logging should be disabled by setting the --disable-experimental option")
        except easybuild.tools.build_log.EasyBuildError, err:
            # check error message
            self.assertTrue('Experimental functionality.' in str(err))

        # toggle experimental
        topt = EasyBuildOptions(
            go_args=['--experimental'],
        )
        try:
            log.experimental('x')
        except easybuild.tools.build_log.EasyBuildError, err:
            self.assertTrue(False, 'Experimental logging should be allowed by the --experimental option.')

        # set it back
        easybuild.tools.build_log.EXPERIMENTAL = orig_value

    def test_deprecated(self):
        """Test the deprecated option"""
        if 'EASYBUILD_DEPRECATED' in os.environ:
            os.environ['EASYBUILD_DEPRECATED'] = str(VERSION)
            init_config()

        orig_value = easybuild.tools.build_log.CURRENT_VERSION

        # make sure it's off by default
        self.assertEqual(orig_value, VERSION)

        log = fancylogger.getLogger()

        # force it to lower version using 0.x, which should no result in any raised error (only deprecation logging)
        topt = EasyBuildOptions(
            go_args=['--deprecated=0.%s' % orig_value],
        )
        stderr = None
        try:
            self.mock_stderr(True)
            log.deprecated('x', str(orig_value))
            stderr = self.get_stderr()
            self.mock_stderr(False)
        except easybuild.tools.build_log.EasyBuildError, err:
            self.assertTrue(False, 'Deprecated logging should work')

        stderr_regex = re.compile("^Deprecated functionality, will no longer work in")
        self.assertTrue(stderr_regex.search(stderr), "Pattern '%s' found in: %s" % (stderr_regex.pattern, stderr))

        # force it to current version, which should result in deprecation
        topt = EasyBuildOptions(
            go_args=['--deprecated=%s' % orig_value],
        )
        try:
            log.deprecated('x', str(orig_value))
            # not supposed to get here
            self.assertTrue(False, 'Deprecated logging should throw EasyBuildError')
        except easybuild.tools.build_log.EasyBuildError, err2:
            self.assertTrue('DEPRECATED' in str(err2))

        # force higher version by prefixing it with 1, which should result in deprecation errors
        topt = EasyBuildOptions(
            go_args=['--deprecated=1%s' % orig_value],
        )
        try:
            log.deprecated('x', str(orig_value))
            # not supposed to get here
            self.assertTrue(False, 'Deprecated logging should throw EasyBuildError')
        except easybuild.tools.build_log.EasyBuildError, err3:
            self.assertTrue('DEPRECATED' in str(err3))

        # set it back
        easybuild.tools.build_log.CURRENT_VERSION = orig_value

    def test_allow_modules_tool_mismatch(self):
        """Test allowing mismatch of modules tool with 'module' function."""
        # make sure MockModulesTool is available
        from test.framework.modulestool import MockModulesTool

        # trigger that main() creates new instance of ModulesTool
        self.modtool = None

        topdir = os.path.abspath(os.path.dirname(__file__))
        ec_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        # keep track of original module definition so we can restore it
        orig_module = os.environ.get('module', None)

        # check whether mismatch between 'module' function and selected modules tool is detected
        os.environ['module'] = "() {  eval `/Users/kehoste/Modules/$MODULE_VERSION/bin/modulecmd bash $*`\n}"
        args = [
            ec_file,
            '--modules-tool=MockModulesTool',
            '--module-syntax=Tcl',  # Lua would require Lmod
        ]
        self.eb_main(args, do_build=True)
        outtxt = read_file(self.logfile)
        error_regex = re.compile("ERROR .*pattern .* not found in defined 'module' function")
        self.assertTrue(error_regex.search(outtxt), "Found error w.r.t. module function mismatch: %s" % outtxt[-600:])

        # check that --allow-modules-tool-mispatch transforms this error into a warning
        os.environ['module'] = "() {  eval `/Users/kehoste/Modules/$MODULE_VERSION/bin/modulecmd bash $*`\n}"
        args = [
            ec_file,
            '--modules-tool=MockModulesTool',
            '--module-syntax=Tcl',  # Lua would require Lmod
            '--allow-modules-tool-mismatch',
        ]
        self.eb_main(args, do_build=True)
        outtxt = read_file(self.logfile)
        warn_regex = re.compile("WARNING .*pattern .* not found in defined 'module' function")
        self.assertTrue(warn_regex.search(outtxt), "Found warning w.r.t. module function mismatch: %s" % outtxt[-600:])

        # check whether match between 'module' function and selected modules tool is detected
        os.environ['module'] = "() {  eval ` /bin/echo $*`\n}"
        args = [
            ec_file,
            '--modules-tool=MockModulesTool',
            '--module-syntax=Tcl',  # Lua would require Lmod
            '--debug',
        ]
        self.eb_main(args, do_build=True)
        outtxt = read_file(self.logfile)
        found_regex = re.compile("DEBUG Found pattern .* in defined 'module' function")
        self.assertTrue(found_regex.search(outtxt), "Found debug message w.r.t. module function: %s" % outtxt[-600:])

        # restore 'module' function
        if orig_module is not None:
            os.environ['module'] = orig_module
        else:
            del os.environ['module']

    def test_try(self):
        """Test whether --try options are taken into account."""
        ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        tweaked_toy_ec = os.path.join(self.test_buildpath, 'toy-0.0-tweaked.eb')
        copy_file(os.path.join(ecs_path, 't', 'toy', 'toy-0.0.eb'), tweaked_toy_ec)
        f = open(tweaked_toy_ec, 'a')
        f.write("easyblock = 'ConfigureMake'")
        f.close()

        args = [
            tweaked_toy_ec,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--dry-run',
            '--robot=%s' % ecs_path,
        ]

        test_cases = [
            ([], 'toy/0.0'),
            # combining --try-toolchain with other build options is too complicated, in this case the code defaults back
            # to doing a simple regex substitution on the toolchain
            (['--try-software=foo,1.2.3', '--try-toolchain=gompi,1.4.10'], 'foo/1.2.3-gompi-1.4.10'),
            (['--try-toolchain-name=gompi', '--try-toolchain-version=1.4.10'], 'toy/0.0-GCC-4.7.2'),
            # --try-toolchain is overridden by --toolchain
            (['--try-toolchain=gompi,1.3.12', '--toolchain=dummy,dummy'], 'toy/0.0'),
            (['--try-software-name=foo', '--try-software-version=1.2.3'], 'foo/1.2.3'),
            (['--try-toolchain-name=gompi', '--try-toolchain-version=1.4.10'], 'toy/0.0-GCC-4.7.2'),
            # combining --try-toolchain with other build options is too complicated, in this case the code defaults back
            # to doing a simple regex substitution on the toolchain
            (['--try-software-version=1.2.3', '--try-toolchain=gompi,1.4.10'], 'toy/1.2.3-gompi-1.4.10'),
            (['--try-amend=versionsuffix=-test'], 'toy/0.0-test'),
            # --try-amend is overridden by --amend
            (['--amend=versionsuffix=', '--try-amend=versionsuffix=-test'], 'toy/0.0'),
            (['--try-toolchain=gompi,1.3.12', '--toolchain=dummy,dummy'], 'toy/0.0'),
            # tweak existing list-typed value (patches)
            (['--try-amend=versionsuffix=-test2', '--try-amend=patches=1.patch,2.patch'], 'toy/0.0-test2'),
            # append to existing list-typed value (patches)
            (['--try-amend=versionsuffix=-test3', '--try-amend=patches=,extra.patch'], 'toy/0.0-test3'),
            # prepend to existing list-typed value (patches)
            (['--try-amend=versionsuffix=-test4', '--try-amend=patches=extra.patch,'], 'toy/0.0-test4'),
            # define extra list-typed parameter
            (['--try-amend=versionsuffix=-test5', '--try-amend=exts_list=1,2,3'], 'toy/0.0-test5'),
            # only --try causes other build specs to be included too
            # --try-toolchain* has a different branch to all other try options, combining defaults back to regex
            (['--try-software=foo,1.2.3', '--toolchain=gompi,1.4.10'], 'foo/1.2.3-gompi-1.4.10'),
            (['--software=foo,1.2.3', '--try-toolchain=gompi,1.4.10'], 'foo/1.2.3-gompi-1.4.10'),
            (['--software=foo,1.2.3', '--try-amend=versionsuffix=-test'], 'foo/1.2.3-test'),
        ]

        for extra_args, mod in test_cases:
            outtxt = self.eb_main(args + extra_args, verbose=True, raise_error=True)
            mod_regex = re.compile("\(module: %s\)$" % mod, re.M)
            self.assertTrue(mod_regex.search(outtxt), "Pattern %s found in %s" % (mod_regex.pattern, outtxt))

        for extra_arg in ['--try-software=foo', '--try-toolchain=gompi', '--try-toolchain=gomp,1.4.10,-no-OFED']:
            allargs = args + [extra_arg]
            self.assertErrorRegex(EasyBuildError, "problems validating the options", self.eb_main, allargs, raise_error=True)

        # no --try used, so no tweaked easyconfig files are generated
        allargs = args + ['--software-version=1.2.3', '--toolchain=gompi,1.4.10']
        self.assertErrorRegex(EasyBuildError, "version .* not available", self.eb_main, allargs, raise_error=True)

    def test_recursive_try(self):
        """Test whether recursive --try-X works."""
        ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        tweaked_toy_ec = os.path.join(self.test_buildpath, 'toy-0.0-tweaked.eb')
        copy_file(os.path.join(ecs_path, 't', 'toy', 'toy-0.0.eb'), tweaked_toy_ec)
        f = open(tweaked_toy_ec, 'a')
        f.write("dependencies = [('gzip', '1.4')]\n")  # add fictious dependency
        f.close()

        sourcepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox', 'sources')
        args = [
            tweaked_toy_ec,
            '--sourcepath=%s' % sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--try-toolchain=gompi,1.4.10',
            '--robot=%s' % ecs_path,
            '--ignore-osdeps',
            '--dry-run',
        ]

        for extra_args in [[], ['--module-naming-scheme=HierarchicalMNS']]:
            outtxt = self.eb_main(args + extra_args, verbose=True, raise_error=True)
            # toolchain GCC/4.7.2 (subtoolchain of gompi/1.4.10) should be listed (and present)

            tc_regex = re.compile("^ \* \[x\] .*/GCC-4.7.2.eb \(module: .*GCC/4.7.2\)$", re.M)
            self.assertTrue(tc_regex.search(outtxt), "Pattern %s found in %s" % (tc_regex.pattern, outtxt))

            # both toy and gzip dependency should be listed with new toolchains
            # in this case we map original toolchain `dummy` to the compiler-only GCC subtoolchain of gompi/1.4.10
            # since this subtoolchain already has sufficient capabilities (we do not map higher than necessary)
            for ec_name in ['gzip-1.4', 'toy-0.0']:
                ec = '%s-GCC-4.7.2.eb' % ec_name
                if extra_args:
                    mod = ec_name.replace('-', '/')
                else:
                    mod = '%s-GCC-4.7.2' % ec_name.replace('-', '/')
                mod_regex = re.compile("^ \* \[ \] \S+/eb-\S+/%s \(module: .*%s\)$" % (ec, mod), re.M)
                #mod_regex = re.compile("%s \(module: .*%s\)$" % (ec, mod), re.M)
                self.assertTrue(mod_regex.search(outtxt), "Pattern %s found in %s" % (mod_regex.pattern, outtxt))

        # clear fictious dependency
        f = open(tweaked_toy_ec, 'a')
        f.write("dependencies = []\n")
        f.close()

        # no recursive try if --(try-)software(-X) is involved
        for extra_args in [['--try-software-version=1.2.3'], ['--software-version=1.2.3']]:
            outtxt = self.eb_main(args + extra_args, raise_error=True)
            for mod in ['toy/1.2.3-gompi-1.4.10', 'gompi/1.4.10', 'GCC/4.7.2']:
                mod_regex = re.compile("\(module: %s\)$" % mod, re.M)
                self.assertTrue(mod_regex.search(outtxt), "Pattern %s found in %s" % (mod_regex.pattern, outtxt))
            for mod in ['gompi/1.2.3', 'GCC/1.2.3']:
                mod_regex = re.compile("\(module: %s\)$" % mod, re.M)
                self.assertFalse(mod_regex.search(outtxt), "Pattern %s found in %s" % (mod_regex.pattern, outtxt))

    def test_cleanup_builddir(self):
        """Test cleaning up of build dir and --disable-cleanup-builddir."""
        toy_ec = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        toy_buildpath = os.path.join(self.test_buildpath, 'toy', '0.0', 'dummy-dummy')

        args = [
            toy_ec,
            '--force',
        ]
        self.eb_main(args, do_build=True, verbose=True)

        # make sure build directory is properly cleaned up after a successful build (default behavior)
        self.assertFalse(os.path.exists(toy_buildpath), "Build dir %s removed after successful build" % toy_buildpath)
        # make sure --disable-cleanup-builddir works
        args.append('--disable-cleanup-builddir')
        self.eb_main(args, do_build=True, verbose=True)
        self.assertTrue(os.path.exists(toy_buildpath), "Build dir %s is retained when requested" % toy_buildpath)
        shutil.rmtree(toy_buildpath)

        # make sure build dir stays in case of failed build
        args = [
            toy_ec,
            '--force',
            '--try-amend=prebuildopts=nosuchcommand &&',
        ]
        self.eb_main(args, do_build=True)
        self.assertTrue(os.path.exists(toy_buildpath), "Build dir %s is retained after failed build" % toy_buildpath)

    def test_filter_deps(self):
        """Test use of --filter-deps."""
        test_dir = os.path.dirname(os.path.abspath(__file__))
        ec_file = os.path.join(test_dir, 'easyconfigs', 'test_ecs', 'g', 'goolf', 'goolf-1.4.10.eb')
        os.environ['MODULEPATH'] = os.path.join(test_dir, 'modules')
        args = [
            ec_file,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--robot=%s' % os.path.join(test_dir, 'easyconfigs'),
            '--dry-run',
        ]
        outtxt = self.eb_main(args, do_build=True, verbose=True, raise_error=True)
        self.assertTrue(re.search('module: FFTW/3.3.3-gompi', outtxt))
        self.assertTrue(re.search('module: ScaLAPACK/2.0.2-gompi', outtxt))
        self.assertFalse(re.search('module: zlib', outtxt))

        # clear log file
        open(self.logfile, 'w').write('')

        # filter deps (including a non-existing dep, i.e. zlib)
        args.append('--filter-deps=FFTW,ScaLAPACK,zlib')
        outtxt = self.eb_main(args, do_build=True, verbose=True, raise_error=True)
        self.assertFalse(re.search('module: FFTW/3.3.3-gompi', outtxt))
        self.assertFalse(re.search('module: ScaLAPACK/2.0.2-gompi', outtxt))
        self.assertFalse(re.search('module: zlib', outtxt))

    def test_hide_deps(self):
        """Test use of --hide-deps."""
        test_dir = os.path.dirname(os.path.abspath(__file__))
        ec_file = os.path.join(test_dir, 'easyconfigs', 'test_ecs', 'g', 'goolf', 'goolf-1.4.10.eb')
        os.environ['MODULEPATH'] = os.path.join(test_dir, 'modules')
        args = [
            ec_file,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--robot=%s' % os.path.join(test_dir, 'easyconfigs'),
            '--dry-run',
        ]
        outtxt = self.eb_main(args, do_build=True, verbose=True, raise_error=True)
        self.assertTrue(re.search('module: GCC/4.7.2', outtxt))
        self.assertTrue(re.search('module: OpenMPI/1.6.4-GCC-4.7.2', outtxt))
        self.assertTrue(re.search('module: OpenBLAS/0.2.6-GCC-4.7.2-LAPACK-3.4.2', outtxt))
        self.assertTrue(re.search('module: FFTW/3.3.3-gompi', outtxt))
        self.assertTrue(re.search('module: ScaLAPACK/2.0.2-gompi', outtxt))
        # zlib is not a dep at all
        self.assertFalse(re.search('module: zlib', outtxt))

        # clear log file
        open(self.logfile, 'w').write('')

        # hide deps (including a non-existing dep, i.e. zlib)
        args.append('--hide-deps=FFTW,ScaLAPACK,zlib')
        outtxt = self.eb_main(args, do_build=True, verbose=True, raise_error=True)
        self.assertTrue(re.search('module: GCC/4.7.2', outtxt))
        self.assertTrue(re.search('module: OpenMPI/1.6.4-GCC-4.7.2', outtxt))
        self.assertTrue(re.search('module: OpenBLAS/0.2.6-GCC-4.7.2-LAPACK-3.4.2', outtxt))
        self.assertFalse(re.search(r'module: FFTW/3\.3\.3-gompi', outtxt))
        self.assertTrue(re.search(r'module: FFTW/\.3\.3\.3-gompi', outtxt))
        self.assertFalse(re.search(r'module: ScaLAPACK/2\.0\.2-gompi', outtxt))
        self.assertTrue(re.search(r'module: ScaLAPACK/\.2\.0\.2-gompi', outtxt))
        # zlib is not a dep at all
        self.assertFalse(re.search(r'module: zlib', outtxt))

    def test_hide_toolchains(self):
        """Test use of --hide-toolchains."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        ec_file = os.path.join(test_ecs_dir, 'g', 'gzip', 'gzip-1.6-GCC-4.9.2.eb')
        args = [
            ec_file,
            '--dry-run',
            '--hide-toolchains=GCC',
        ]
        outtxt = self.eb_main(args)
        self.assertTrue(re.search('module: GCC/\.4\.9\.2', outtxt))
        self.assertTrue(re.search('module: gzip/1\.6-GCC-4\.9\.2', outtxt))

    def test_test_report_env_filter(self):
        """Test use of --test-report-env-filter."""

        def toy(extra_args=None):
            """Build & install toy, return contents of test report."""
            eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
            args = [
                eb_file,
                '--sourcepath=%s' % self.test_sourcepath,
                '--buildpath=%s' % self.test_buildpath,
                '--installpath=%s' % self.test_installpath,
                '--force',
                '--debug',
            ]
            if extra_args is not None:
                args.extend(extra_args)
            self.eb_main(args, do_build=True, raise_error=True, verbose=True)

            software_path = os.path.join(self.test_installpath, 'software', 'toy', '0.0')
            test_report_path_pattern = os.path.join(software_path, 'easybuild', 'easybuild-toy-0.0*test_report.md')
            f = open(glob.glob(test_report_path_pattern)[0], 'r')
            test_report_txt = f.read()
            f.close()
            return test_report_txt

        # define environment variables that should (not) show up in the test report
        test_var_secret = 'THIS_IS_JUST_A_SECRET_ENV_VAR_FOR_EASYBUILD'
        os.environ[test_var_secret] = 'thisshouldremainsecretonrequest'
        test_var_secret_regex = re.compile(test_var_secret)
        test_var_public = 'THIS_IS_JUST_A_PUBLIC_ENV_VAR_FOR_EASYBUILD'
        os.environ[test_var_public] = 'thisshouldalwaysbeincluded'
        test_var_public_regex = re.compile(test_var_public)

        # default: no filtering
        test_report_txt = toy()
        self.assertTrue(test_var_secret_regex.search(test_report_txt))
        self.assertTrue(test_var_public_regex.search(test_report_txt))

        # filter out env vars that match specified regex pattern
        filter_arg = "--test-report-env-filter=.*_SECRET_ENV_VAR_FOR_EASYBUILD"
        test_report_txt = toy(extra_args=[filter_arg])
        res = test_var_secret_regex.search(test_report_txt)
        self.assertFalse(res, "No match for %s in %s" % (test_var_secret_regex.pattern, test_report_txt))
        self.assertTrue(test_var_public_regex.search(test_report_txt))
        # make sure that used filter is reported correctly in test report
        filter_arg_regex = re.compile(r"--test-report-env-filter='.\*_SECRET_ENV_VAR_FOR_EASYBUILD'")
        tup = (filter_arg_regex.pattern, test_report_txt)
        self.assertTrue(filter_arg_regex.search(test_report_txt), "%s in %s" % tup)

    def test_robot(self):
        """Test --robot and --robot-paths command line options."""
        # unset $EASYBUILD_ROBOT_PATHS that was defined in setUp
        os.environ['EASYBUILD_ROBOT_PATHS'] = self.test_prefix

        test_ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        # includes 'toy/.0.0-deps' as a dependency
        eb_file = os.path.join(test_ecs_path, 'g', 'gzip', 'gzip-1.4-GCC-4.6.3.eb')

        # hide test modules
        self.reset_modulepath([])

        # dependency resolution is disabled by default, even if required paths are available
        args = [
            eb_file,
            '--robot-paths=%s' % test_ecs_path,
        ]
        error_regex = "Missing modules for one or more dependencies: .*"
        self.assertErrorRegex(EasyBuildError, error_regex, self.eb_main, args, raise_error=True, do_build=True)

        # enable robot, but without passing path required to resolve toy dependency => FAIL
        args = [
            eb_file,
            '--robot',
            '--dry-run',
        ]
        self.assertErrorRegex(EasyBuildError, 'Irresolvable dependencies', self.eb_main, args, raise_error=True)

        # add path to test easyconfigs to robot paths, so dependencies can be resolved
        self.eb_main(args + ['--robot-paths=%s' % test_ecs_path], raise_error=True)

        # copy test easyconfigs to easybuild/easyconfigs subdirectory of temp directory
        # to check whether easyconfigs install path is auto-included in robot path
        tmpdir = tempfile.mkdtemp(prefix='easybuild-easyconfigs-pkg-install-path')
        mkdir(os.path.join(tmpdir, 'easybuild'), parents=True)
        copy_dir(test_ecs_path, os.path.join(tmpdir, 'easybuild', 'easyconfigs'))

        # prepend path to test easyconfigs into Python search path, so it gets picked up as --robot-paths default
        del os.environ['EASYBUILD_ROBOT_PATHS']
        orig_sys_path = sys.path[:]
        sys.path.insert(0, tmpdir)
        self.eb_main(args, raise_error=True)

        shutil.rmtree(tmpdir)
        sys.path[:] = orig_sys_path

        # make sure that paths specified to --robot get preference over --robot-paths
        args = [
            eb_file,
            '--robot=%s' % test_ecs_path,
            '--robot-paths=%s' % os.path.join(tmpdir, 'easybuild', 'easyconfigs'),
            '--dry-run',
        ]
        outtxt = self.eb_main(args, raise_error=True)

        ecfiles = [
            'g/GCC/GCC-4.6.3.eb',
            'i/ictce/ictce-4.1.13.eb',
            't/toy/toy-0.0-deps.eb',
            'g/gzip/gzip-1.4-GCC-4.6.3.eb',
        ]
        for ecfile in ecfiles:
            ec_regex = re.compile(r'^\s\*\s\[[xF ]\]\s%s' % os.path.join(test_ecs_path, ecfile), re.M)
            self.assertTrue(ec_regex.search(outtxt), "Pattern %s found in %s" % (ec_regex.pattern, outtxt))

    def test_missing_cfgfile(self):
        """Test behaviour when non-existing config file is specified."""
        args = ['--configfiles=/no/such/cfgfile.foo']
        error_regex = "parseconfigfiles: configfile .* not found"
        self.assertErrorRegex(EasyBuildError, error_regex, self.eb_main, args, raise_error=True)

    def test_show_default_moduleclasses(self):
        """Test --show-default-moduleclasses."""
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        args = [
            '--unittest-file=%s' % self.logfile,
            '--show-default-moduleclasses',
        ]
        write_file(self.logfile, '')
        self.eb_main(args, logfile=dummylogfn, verbose=True)
        logtxt = read_file(self.logfile)

        lst = ["\t%s:[ ]*%s" % (c, d.replace('(', '\\(').replace(')', '\\)')) for (c, d) in DEFAULT_MODULECLASSES]
        regex = re.compile("Default available module classes:\n\n" + '\n'.join(lst), re.M)

        self.assertTrue(regex.search(logtxt), "Pattern '%s' found in %s" % (regex.pattern, logtxt))

    def test_show_default_configfiles(self):
        """Test --show-default-configfiles."""
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        home = os.environ['HOME']
        for envvar in ['XDG_CONFIG_DIRS', 'XDG_CONFIG_HOME']:
            if envvar in os.environ:
                del os.environ[envvar]
        reload(easybuild.tools.options)

        args = [
            '--unittest-file=%s' % self.logfile,
            '--show-default-configfiles',
        ]

        cfgtxt = '\n'.join([
            '[config]',
            'prefix = %s' % self.test_prefix,
        ])

        expected_tmpl = '\n'.join([
            "Default list of configuration files:",
            '',
            "[with $XDG_CONFIG_HOME: %s, $XDG_CONFIG_DIRS: %s]",
            '',
            "* user-level: ${XDG_CONFIG_HOME:-$HOME/.config}/easybuild/config.cfg",
            "  -> %s",
            "* system-level: ${XDG_CONFIG_DIRS:-/etc}/easybuild.d/*.cfg",
            "  -> %s/easybuild.d/*.cfg => ",
        ])

        write_file(self.logfile, '')
        self.eb_main(args, logfile=dummylogfn, verbose=True)
        logtxt = read_file(self.logfile)

        homecfgfile = os.path.join(os.environ['HOME'], '.config', 'easybuild', 'config.cfg')
        homecfgfile_str = homecfgfile
        if os.path.exists(homecfgfile):
            homecfgfile_str += " => found"
        else:
            homecfgfile_str += " => not found"
        expected = expected_tmpl % ('(not set)', '(not set)', homecfgfile_str, '{/etc}')
        self.assertTrue(expected in logtxt)

        # to predict the full output, we need to take control over $HOME and $XDG_CONFIG_DIRS
        os.environ['HOME'] = self.test_prefix
        xdg_config_dirs = os.path.join(self.test_prefix, 'etc')
        os.environ['XDG_CONFIG_DIRS'] = xdg_config_dirs

        expected_tmpl += '\n'.join([
            "%s",
            '',
            "Default list of existing configuration files (%d): %s",
        ])

        # put dummy cfgfile in place in $HOME (to predict last line of output which only lists *existing* files)
        mkdir(os.path.join(self.test_prefix, '.config', 'easybuild'), parents=True)
        homecfgfile = os.path.join(self.test_prefix, '.config', 'easybuild', 'config.cfg')
        write_file(homecfgfile, cfgtxt)

        reload(easybuild.tools.options)
        write_file(self.logfile, '')
        self.eb_main(args, logfile=dummylogfn, verbose=True)
        logtxt = read_file(self.logfile)
        expected = expected_tmpl % ('(not set)', xdg_config_dirs, "%s => found" % homecfgfile, '{%s}' % xdg_config_dirs,
                                    '(no matches)', 1, homecfgfile)
        self.assertTrue(expected in logtxt)

        xdg_config_home = os.path.join(self.test_prefix, 'home')
        os.environ['XDG_CONFIG_HOME'] = xdg_config_home
        xdg_config_dirs = [os.path.join(self.test_prefix, 'etc'), os.path.join(self.test_prefix, 'moaretc')]
        os.environ['XDG_CONFIG_DIRS'] = os.pathsep.join(xdg_config_dirs)

        # put various dummy cfgfiles in place
        cfgfiles = [
            os.path.join(self.test_prefix, 'etc', 'easybuild.d', 'config.cfg'),
            os.path.join(self.test_prefix, 'moaretc', 'easybuild.d', 'bar.cfg'),
            os.path.join(self.test_prefix, 'moaretc', 'easybuild.d', 'foo.cfg'),
            os.path.join(xdg_config_home, 'easybuild', 'config.cfg'),
        ]
        for cfgfile in cfgfiles:
            mkdir(os.path.dirname(cfgfile), parents=True)
            write_file(cfgfile, cfgtxt)
        reload(easybuild.tools.options)

        write_file(self.logfile, '')
        self.eb_main(args, logfile=dummylogfn, verbose=True)
        logtxt = read_file(self.logfile)
        expected = expected_tmpl % (xdg_config_home, os.pathsep.join(xdg_config_dirs),
                                    "%s => found" % os.path.join(xdg_config_home, 'easybuild', 'config.cfg'),
                                    '{' + ', '.join(xdg_config_dirs) + '}',
                                    ', '.join(cfgfiles[:-1]), 4, ', '.join(cfgfiles))
        self.assertTrue(expected in logtxt)

        del os.environ['XDG_CONFIG_DIRS']
        del os.environ['XDG_CONFIG_HOME']
        os.environ['HOME'] = home
        reload(easybuild.tools.options)

    def test_generate_cmd_line(self):
        """Test for generate_cmd_line."""
        self.purge_environment()

        def generate_cmd_line(ebopts):
            """Helper function to filter generated command line (to ignore $EASYBUILD_IGNORECONFIGFILES)."""
            return [x for x in ebopts.generate_cmd_line() if not x.startswith('--ignoreconfigfiles=')]

        ebopts = EasyBuildOptions(envvar_prefix='EASYBUILD')
        self.assertEqual(generate_cmd_line(ebopts), [])

        ebopts = EasyBuildOptions(go_args=['--force'], envvar_prefix='EASYBUILD')
        self.assertEqual(generate_cmd_line(ebopts), ['--force'])

        ebopts = EasyBuildOptions(go_args=['--search=bar', '--search', 'foobar'], envvar_prefix='EASYBUILD')
        self.assertEqual(generate_cmd_line(ebopts), ["--search='foobar'"])

        os.environ['EASYBUILD_DEBUG'] = '1'
        ebopts = EasyBuildOptions(go_args=['--force'], envvar_prefix='EASYBUILD')
        self.assertEqual(generate_cmd_line(ebopts), ['--debug', '--force'])

        args = [
            # install path with a single quote in it, iieeeuuuwww
            "--installpath=/this/is/a/weird'prefix",
            '--test-report-env-filter=(COOKIE|SESSION)',
            '--suffix-modules-path=',
            '--try-toolchain=foss,2015b',
            '--logfile-format=easybuild,eb-%(name)s.log',
            # option with spaces with value wrapped in double quotes, oh boy...
            '--optarch="O3 -mtune=generic"',
        ]
        expected = [
            '--debug',
            "--installpath='/this/is/a/weird\\'prefix'",
            "--logfile-format='easybuild,eb-%(name)s.log'",
            "--optarch='O3 -mtune=generic'",
            "--suffix-modules-path=''",
            "--test-report-env-filter='(COOKIE|SESSION)'",
            "--try-toolchain='foss,2015b'",
        ]
        ebopts = EasyBuildOptions(go_args=args, envvar_prefix='EASYBUILD')
        self.assertEqual(generate_cmd_line(ebopts), expected)

    # must be run after test for --list-easyblocks, hence the '_xxx_'
    # cleaning up the imported easyblocks is quite difficult...
    def test_xxx_include_easyblocks(self):
        """Test --include-easyblocks."""
        orig_local_sys_path = sys.path[:]

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # clear log
        write_file(self.logfile, '')

        # existing test EB_foo easyblock found without include a custom one
        args = [
            '--list-easyblocks=detailed',
            '--unittest-file=%s' % self.logfile,
        ]
        self.eb_main(args, logfile=dummylogfn, raise_error=True)
        logtxt = read_file(self.logfile)

        test_easyblocks = os.path.dirname(os.path.abspath(__file__))
        path_pattern = os.path.join(test_easyblocks, 'sandbox', 'easybuild', 'easyblocks', 'f', 'foo.py')
        foo_regex = re.compile(r"^\|-- EB_foo \(easybuild.easyblocks.foo @ %s\)" % path_pattern, re.M)
        self.assertTrue(foo_regex.search(logtxt), "Pattern '%s' found in: %s" % (foo_regex.pattern, logtxt))

        # 'undo' import of foo easyblock
        del sys.modules['easybuild.easyblocks.foo']
        sys.path = orig_local_sys_path
        import easybuild.easyblocks
        reload(easybuild.easyblocks)
        import easybuild.easyblocks.generic
        reload(easybuild.easyblocks.generic)

        # include extra test easyblocks
        foo_txt = '\n'.join([
            'from easybuild.framework.easyblock import EasyBlock',
            'class EB_foo(EasyBlock):',
            '   pass',
            ''
        ])
        write_file(os.path.join(self.test_prefix, 'foo.py'), foo_txt)

        # clear log
        write_file(self.logfile, '')

        args = [
            '--include-easyblocks=%s/*.py' % self.test_prefix,
            '--list-easyblocks=detailed',
            '--unittest-file=%s' % self.logfile,
        ]
        self.eb_main(args, logfile=dummylogfn, raise_error=True)
        logtxt = read_file(self.logfile)

        path_pattern = os.path.join(self.test_prefix, '.*', 'included-easyblocks', 'easybuild', 'easyblocks', 'foo.py')
        foo_regex = re.compile(r"^\|-- EB_foo \(easybuild.easyblocks.foo @ %s\)" % path_pattern, re.M)
        self.assertTrue(foo_regex.search(logtxt), "Pattern '%s' found in: %s" % (foo_regex.pattern, logtxt))

        # easyblock is found via get_easyblock_class
        klass = get_easyblock_class('EB_foo')
        self.assertTrue(issubclass(klass, EasyBlock), "%s is an EasyBlock derivative class" % klass)

        # 'undo' import of foo easyblock
        del sys.modules['easybuild.easyblocks.foo']

    # must be run after test for --list-easyblocks, hence the '_xxx_'
    # cleaning up the imported easyblocks is quite difficult...
    def test_xxx_include_generic_easyblocks(self):
        """Test --include-easyblocks with a generic easyblock."""
        orig_local_sys_path = sys.path[:]
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # clear log
        write_file(self.logfile, '')

        # generic easyblock FooBar is not there initially
        error_msg = "Failed to obtain class for FooBar easyblock"
        self.assertErrorRegex(EasyBuildError, error_msg, get_easyblock_class, 'FooBar')

        # include extra test easyblocks
        txt = '\n'.join([
            'from easybuild.framework.easyblock import EasyBlock',
            'class FooBar(EasyBlock):',
            '   pass',
            ''
        ])
        write_file(os.path.join(self.test_prefix, 'generic', 'foobar.py'), txt)

        args = [
            '--include-easyblocks=%s/generic/*.py' % self.test_prefix,
            '--list-easyblocks=detailed',
            '--unittest-file=%s' % self.logfile,
        ]
        self.eb_main(args, logfile=dummylogfn, raise_error=True)
        logtxt = read_file(self.logfile)

        path_pattern = os.path.join(self.test_prefix, '.*', 'included-easyblocks', 'easybuild', 'easyblocks',
                                    'generic', 'foobar.py')
        foo_regex = re.compile(r"^\|-- FooBar \(easybuild.easyblocks.generic.foobar @ %s\)" % path_pattern, re.M)
        self.assertTrue(foo_regex.search(logtxt), "Pattern '%s' found in: %s" % (foo_regex.pattern, logtxt))

        klass = get_easyblock_class('FooBar')
        self.assertTrue(issubclass(klass, EasyBlock), "%s is an EasyBlock derivative class" % klass)

        # 'undo' import of foobar easyblock
        del sys.modules['easybuild.easyblocks.generic.foobar']
        os.remove(os.path.join(self.test_prefix, 'generic', 'foobar.py'))
        sys.path = orig_local_sys_path
        import easybuild.easyblocks
        reload(easybuild.easyblocks)
        import easybuild.easyblocks.generic
        reload(easybuild.easyblocks.generic)

        error_msg = "Failed to obtain class for FooBar easyblock"
        self.assertErrorRegex(EasyBuildError, error_msg, get_easyblock_class, 'FooBar')

        # clear log
        write_file(self.logfile, '')

        # importing without specifying 'generic' also works, and generic easyblock can be imported as well
        # this works thanks to a fallback mechanism in get_easyblock_class
        txt = '\n'.join([
            'from easybuild.framework.easyblock import EasyBlock',
            'class GenericTest(EasyBlock):',
            '   pass',
            ''
        ])
        write_file(os.path.join(self.test_prefix, 'generictest.py'), txt)

        args[0] = '--include-easyblocks=%s/*.py' % self.test_prefix
        self.eb_main(args, logfile=dummylogfn, raise_error=True)
        logtxt = read_file(self.logfile)

        mod_pattern = 'easybuild.easyblocks.generic.generictest'
        path_pattern = os.path.join(self.test_prefix, '.*', 'included-easyblocks', 'easybuild', 'easyblocks',
                                    'generic', 'generictest.py')
        foo_regex = re.compile(r"^\|-- GenericTest \(%s @ %s\)" % (mod_pattern, path_pattern), re.M)
        self.assertTrue(foo_regex.search(logtxt), "Pattern '%s' found in: %s" % (foo_regex.pattern, logtxt))

        klass = get_easyblock_class('GenericTest')
        self.assertTrue(issubclass(klass, EasyBlock), "%s is an EasyBlock derivative class" % klass)

        # 'undo' import of foo easyblock
        del sys.modules['easybuild.easyblocks.generic.generictest']

    def test_include_module_naming_schemes(self):
        """Test --include-module-naming-schemes."""
        # make sure that calling out to 'eb' will work by restoring $PATH & $PYTHONPATH
        self.restore_env_path_pythonpath()

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # clear log
        write_file(self.logfile, '')

        mns_regex = re.compile(r'^\s*TestIncludedMNS', re.M)

        # TestIncludedMNS module naming scheme is not available by default
        args = [
            '--avail-module-naming-schemes',
        ]
        logtxt, _= run_cmd("cd %s; eb %s" % (self.test_prefix, ' '.join(args)), simple=False)
        self.assertFalse(mns_regex.search(logtxt), "Unexpected pattern '%s' found in: %s" % (mns_regex.pattern, logtxt))

        # include extra test MNS
        mns_txt = '\n'.join([
            'from easybuild.tools.module_naming_scheme import ModuleNamingScheme',
            'class TestIncludedMNS(ModuleNamingScheme):',
            '   pass',
        ])
        write_file(os.path.join(self.test_prefix, 'test_mns.py'), mns_txt)

        # clear log
        write_file(self.logfile, '')

        args = [
            '--avail-module-naming-schemes',
            '--include-module-naming-schemes=%s/*.py' % self.test_prefix,
        ]
        logtxt, _= run_cmd("cd %s; eb %s" % (self.test_prefix, ' '.join(args)), simple=False)
        self.assertTrue(mns_regex.search(logtxt), "Pattern '%s' *not* found in: %s" % (mns_regex.pattern, logtxt))

    def test_use_included_module_naming_scheme(self):
        """Test using an included module naming scheme."""
        # try selecting the added module naming scheme
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # include extra test MNS
        mns_txt = '\n'.join([
            'import os',
            'from easybuild.tools.module_naming_scheme import ModuleNamingScheme',
            'class AnotherTestIncludedMNS(ModuleNamingScheme):',
            '   def det_full_module_name(self, ec):',
            "       return os.path.join(ec['name'], ec['version'])",
        ])
        write_file(os.path.join(self.test_prefix, 'test_mns.py'), mns_txt)

        topdir = os.path.abspath(os.path.dirname(__file__))
        eb_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        args = [
            '--unittest-file=%s' % self.logfile,
            '--module-naming-scheme=AnotherTestIncludedMNS',
            '--force',
            eb_file,
        ]

        # selecting a module naming scheme that doesn't exist leads to 'invalid choice'
        error_regex = "Selected module naming scheme \'AnotherTestIncludedMNS\' is unknown"
        self.assertErrorRegex(EasyBuildError, error_regex, self.eb_main, args, logfile=dummylogfn,
                              raise_error=True, raise_systemexit=True)

        args.append('--include-module-naming-schemes=%s/*.py' % self.test_prefix)
        self.eb_main(args, logfile=dummylogfn, do_build=True, raise_error=True, raise_systemexit=True, verbose=True)
        toy_mod = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_mod += '.lua'
        self.assertTrue(os.path.exists(toy_mod), "Found %s" % toy_mod)

    def test_include_toolchains(self):
        """Test --include-toolchains."""
        # make sure that calling out to 'eb' will work by restoring $PATH & $PYTHONPATH
        self.restore_env_path_pythonpath()

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # clear log
        write_file(self.logfile, '')

        # set processed attribute to false, to trigger rescan in search_toolchain
        setattr(easybuild.tools.toolchain, '%s_PROCESSED' % TC_CONST_PREFIX, False)

        tc_regex = re.compile(r'^\s*test_included_toolchain: TestIncludedCompiler', re.M)

        # TestIncludedCompiler is not available by default
        args = [
            '--list-toolchains',
        ]
        logtxt, _= run_cmd("cd %s; eb %s" % (self.test_prefix, ' '.join(args)), simple=False)
        self.assertFalse(tc_regex.search(logtxt), "Pattern '%s' *not* found in: %s" % (tc_regex.pattern, logtxt))

        # include extra test toolchain
        comp_txt = '\n'.join([
            'from easybuild.tools.toolchain.compiler import Compiler',
            'class TestIncludedCompiler(Compiler):',
            "   COMPILER_MODULE_NAME = ['TestIncludedCompiler']",
        ])
        mkdir(os.path.join(self.test_prefix, 'compiler'))
        write_file(os.path.join(self.test_prefix, 'compiler', 'test_comp.py'), comp_txt)

        tc_txt = '\n'.join([
            'from easybuild.toolchains.compiler.test_comp import TestIncludedCompiler',
            'class TestIncludedToolchain(TestIncludedCompiler):',
            "   NAME = 'test_included_toolchain'",
        ])
        write_file(os.path.join(self.test_prefix, 'test_tc.py'), tc_txt)

        args = [
            '--include-toolchains=%s/*.py,%s/*/*.py' % (self.test_prefix, self.test_prefix),
            '--list-toolchains',
        ]
        logtxt, _= run_cmd("cd %s; eb %s" % (self.test_prefix, ' '.join(args)), simple=False)
        self.assertTrue(tc_regex.search(logtxt), "Pattern '%s' found in: %s" % (tc_regex.pattern, logtxt))

    def test_cleanup_tmpdir(self):
        """Test --cleanup-tmpdir."""
        topdir = os.path.dirname(os.path.abspath(__file__))
        args = [
            os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb'),
            '--dry-run',
            '--try-software-version=1.0',  # so we get a tweaked easyconfig
        ]

        tmpdir = tempfile.gettempdir()
        # just making sure this is empty before we get started
        self.assertEqual(os.listdir(tmpdir), [])

        # force silence (since we're not using testing mode)
        self.mock_stdout(True)

        # default: cleanup tmpdir & logfile
        self.eb_main(args, raise_error=True, testing=False)
        self.assertEqual(os.listdir(tmpdir), [])
        self.assertFalse(os.path.exists(self.logfile))

        # disable cleaning up tmpdir
        args.append('--disable-cleanup-tmpdir')
        self.eb_main(args, raise_error=True, testing=False)
        tmpdir_files = os.listdir(tmpdir)
        # tmpdir and logfile are still there \o/
        self.assertTrue(len(tmpdir_files) == 1)
        self.assertTrue(os.path.exists(self.logfile))
        # tweaked easyconfigs is still there \o/
        tweaked_dir = os.path.join(tmpdir, tmpdir_files[0], 'tweaked_easyconfigs')
        self.assertTrue(os.path.exists(os.path.join(tweaked_dir, 'toy-1.0.eb')))

    def test_preview_pr(self):
        """Test --preview-pr."""
        if self.github_token is None:
            print "Skipping test_preview_pr, no GitHub token available?"
            return

        self.mock_stdout(True)

        test_ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        eb_file = os.path.join(test_ecs_path, 'b', 'bzip2', 'bzip2-1.0.6-GCC-4.9.2.eb')
        args = [
            '--color=never',
            '--github-user=%s' % GITHUB_TEST_ACCOUNT,
            '--preview-pr',
            eb_file,
        ]
        self.eb_main(args, raise_error=True)
        txt = self.get_stdout()
        self.mock_stdout(False)
        regex = re.compile(r"^Comparing bzip2-1.0.6\S* with bzip2-1.0.6")
        self.assertTrue(regex.search(txt), "Pattern '%s' not found in: %s" % (regex.pattern, txt))

    def test_review_pr(self):
        """Test --review-pr."""
        if self.github_token is None:
            print "Skipping test_review_pr, no GitHub token available?"
            return

        self.mock_stdout(True)
        # PR for zlib 1.2.8 easyconfig, see https://github.com/easybuilders/easybuild-easyconfigs/pull/1484
        args = [
            '--color=never',
            '--github-user=%s' % GITHUB_TEST_ACCOUNT,
            '--review-pr=1484',
        ]
        self.eb_main(args, raise_error=True)
        txt = self.get_stdout()
        self.mock_stdout(False)
        regex = re.compile(r"^Comparing zlib-1.2.8\S* with zlib-1.2.8")
        self.assertTrue(regex.search(txt), "Pattern '%s' not found in: %s" % (regex.pattern, txt))

    def test_set_tmpdir(self):
        """Test set_tmpdir config function."""
        self.purge_environment()

        def check_tmpdir(tmpdir):
            """Test use of specified path for temporary directory"""
            parent = tmpdir
            if parent is None:
                parent = tempfile.gettempdir()

            mytmpdir = set_tmpdir(tmpdir=tmpdir)

            parent = re.sub('[^\w/.-]', 'X', parent)

            for var in ['TMPDIR', 'TEMP', 'TMP']:
                self.assertTrue(os.environ[var].startswith(os.path.join(parent, 'eb-')))
                self.assertEqual(os.environ[var], mytmpdir)
            self.assertTrue(tempfile.gettempdir().startswith(os.path.join(parent, 'eb-')))
            tempfile_tmpdir = tempfile.mkdtemp()
            self.assertTrue(tempfile_tmpdir.startswith(os.path.join(parent, 'eb-')))
            fd, tempfile_tmpfile = tempfile.mkstemp()
            self.assertTrue(tempfile_tmpfile.startswith(os.path.join(parent, 'eb-')))

            # tmp_logdir follows tmpdir
            self.assertEqual(get_build_log_path(), mytmpdir)

            # cleanup
            os.close(fd)
            shutil.rmtree(mytmpdir)
            modify_env(os.environ, self.orig_environ)
            tempfile.tempdir = None


        orig_tmpdir = tempfile.gettempdir()
        cand_tmpdirs = [
            None,
            os.path.join(orig_tmpdir, 'foo'),
            os.path.join(orig_tmpdir, '[1234]. bleh'),
            os.path.join(orig_tmpdir, '[ab @cd]%/#*'),
        ]
        for tmpdir in cand_tmpdirs:
            check_tmpdir(tmpdir)

    def test_minimal_toolchains(self):
        """End-to-end test for --minimal-toolchains."""
        # create test easyconfig specifically tailored for this test
        # include a dependency for which no easyconfig is available with parent toolchains, only with subtoolchain
        ec_file = os.path.join(self.test_prefix, 'test_minimal_toolchains.eb')
        ectxt = '\n'.join([
            "easyblock = 'ConfigureMake'",
            "name = 'test'",
            "version = '1.2.3'",
            "homepage = 'http://example.com'",
            "description = 'this is just a test'",
            "toolchain = {'name': 'gompi', 'version': '1.4.10'}",
            # hwloc-1.6.2-gompi-1.4.10.eb is *not* available, but hwloc-1.6.2-GCC-4.7.2.eb is,
            # and GCC/4.7.2 is a subtoolchain of gompi/1.4.10
            "dependencies = [('hwloc', '1.6.2'), ('SQLite', '3.8.10.2')]",
        ])
        write_file(ec_file, ectxt)

        # check requirements for test
        init_config([], build_options={'robot_path': os.environ['EASYBUILD_ROBOT_PATHS']})
        self.assertFalse(os.path.exists(robot_find_easyconfig('hwloc', '1.6.2-gompi-1.4.10') or 'nosuchfile'))
        self.assertTrue(os.path.exists(robot_find_easyconfig('hwloc', '1.6.2-GCC-4.7.2')))
        self.assertTrue(os.path.exists(robot_find_easyconfig('SQLite', '3.8.10.2-gompi-1.4.10')))
        self.assertTrue(os.path.exists(robot_find_easyconfig('SQLite', '3.8.10.2-GCC-4.7.2')))

        args = [
            ec_file,
            '--minimal-toolchains',
            '--module-naming-scheme=HierarchicalMNS',
            '--dry-run',
        ]
        self.mock_stdout(True)
        self.eb_main(args, do_build=True, raise_error=True, testing=False)
        txt = self.get_stdout()
        self.mock_stdout(False)
        sqlite_regex = re.compile("hwloc-1.6.2-GCC-4.7.2.eb \(module: Compiler/GCC/4.7.2 \| hwloc/", re.M)
        sqlite_regex = re.compile("SQLite-3.8.10.2-GCC-4.7.2.eb \(module: Compiler/GCC/4.7.2 \| SQLite/", re.M)
        self.assertTrue(sqlite_regex.search(txt), "Pattern '%s' found in: %s" % (sqlite_regex.pattern, txt))

    def test_extended_dry_run(self):
        """Test use of --extended-dry-run/-x."""
        ec_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        args = [
            ec_file,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--debug',
        ]
        # *no* output in testing mode (honor 'silent')
        self.mock_stdout(True)
        self.eb_main(args + ['--extended-dry-run'], do_build=True, raise_error=True, testing=True)
        stdout = self.get_stdout()
        self.mock_stdout(False)
        self.assertEqual(len(stdout), 0)

        msg_regexs = [
            re.compile(r"the actual build \& install procedure that will be performed may diverge", re.M),
            re.compile(r"^\*\*\* DRY RUN using 'EB_toy' easyblock", re.M),
            re.compile(r"^== COMPLETED: Installation ended successfully", re.M),
            re.compile(r"^\(no ignored errors during dry run\)", re.M),
        ]
        ignoring_error_regex = re.compile(r"WARNING: ignoring error", re.M)
        ignored_error_regex = re.compile(r"WARNING: One or more errors were ignored, see warnings above", re.M)

        for opt in ['--extended-dry-run', '-x']:
            # check for expected patterns in output of --extended-dry-run/-x
            self.mock_stdout(True)
            self.eb_main(args + [opt], do_build=True, raise_error=True, testing=False)
            stdout = self.get_stdout()
            self.mock_stdout(False)

            for msg_regex in msg_regexs:
                self.assertTrue(msg_regex.search(stdout), "Pattern '%s' found in: %s" % (msg_regex.pattern, stdout))

            # no ignored errors should occur
            for notthere_regex in [ignoring_error_regex, ignored_error_regex]:
                msg = "Pattern '%s' NOT found in: %s" % (notthere_regex.pattern, stdout)
                self.assertFalse(notthere_regex.search(stdout), msg)

    def test_last_log(self):
        """Test --last-log."""
        orig_tmpdir = os.environ['TMPDIR']
        tmpdir = os.path.join(tempfile.gettempdir(), 'eb-tmpdir1')
        current_log_path = os.path.join(tmpdir, 'easybuild-current.log')

        # $TMPDIR determines path to build log, we need to get it right to make the test check what we want it to
        os.environ['TMPDIR'] = tmpdir
        write_file(current_log_path, "this is a log message")
        self.assertEqual(find_last_log(current_log_path), None)
        os.environ['TMPDIR'] = orig_tmpdir

        self.mock_stdout(True)
        mkdir(os.path.dirname(current_log_path))
        self.eb_main(['--last-log'], logfile=current_log_path, raise_error=True)
        txt = self.get_stdout().strip()
        self.mock_stdout(False)

        self.assertEqual(txt, '(none)')

        # run something that fails first, we need a log file to find
        last_log_path = os.path.join(tempfile.gettempdir(), 'eb-tmpdir0', 'easybuild-last.log')
        mkdir(os.path.dirname(last_log_path))
        self.eb_main(['thisisaneasyconfigthatdoesnotexist.eb'], logfile=last_log_path, raise_error=False)

        # $TMPDIR determines path to build log, we need to get it right to make the test check what we want it to
        os.environ['TMPDIR'] = tmpdir
        write_file(current_log_path, "this is a log message")
        last_log = find_last_log(current_log_path)
        self.assertTrue(os.path.samefile(last_log, last_log_path), "%s != %s" % (last_log, last_log_path))
        os.environ['TMPDIR'] = orig_tmpdir

        self.mock_stdout(True)
        mkdir(os.path.dirname(current_log_path))
        self.eb_main(['--last-log'], logfile=current_log_path, raise_error=True)
        txt = self.get_stdout().strip()
        self.mock_stdout(False)

        self.assertTrue(os.path.samefile(txt, last_log_path), "%s != %s" % (txt, last_log_path))

    def test_fixed_installdir_naming_scheme(self):
        """Test use of --fixed-installdir-naming-scheme."""
        # by default, name of install dir match module naming scheme used
        topdir = os.path.abspath(os.path.dirname(__file__))
        eb_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        app = EasyBlock(EasyConfig(eb_file))
        app.gen_installdir()
        self.assertTrue(app.installdir.endswith('software/toy/0.0'))

        init_config(args=['--module-naming-scheme=HierarchicalMNS'])
        app = EasyBlock(EasyConfig(eb_file))
        app.gen_installdir()
        self.assertTrue(app.installdir.endswith('software/Core/toy/0.0'))

        # with --fixed-installdir-naming-scheme, the EasyBuild naming scheme is used
        build_options = {
            'fixed_installdir_naming_scheme': True,
            'valid_module_classes': module_classes(),
        }
        init_config(args=['--module-naming-scheme=HierarchicalMNS'], build_options=build_options)
        app = EasyBlock(EasyConfig(eb_file))
        app.gen_installdir()
        self.assertTrue(app.installdir.endswith('software/toy/0.0'))

    def _assert_regexs(self, regexs, txt, assert_true=True):
        """Helper function to assert presence/absence of list of regex patterns in a text"""
        for regex in regexs:
            regex = re.compile(regex, re.M)
            if assert_true:
                self.assertTrue(regex.search(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))
            else:
                self.assertFalse(regex.search(txt), "Pattern '%s' NOT found in: %s" % (regex.pattern, txt))

    def _run_mock_eb(self, args, strip=False, **kwargs):
        """Helper function to mock easybuild runs"""
        self.mock_stdout(True)
        self.mock_stderr(True)
        self.eb_main(args, **kwargs)
        stdout_txt = self.get_stdout()
        stderr_txt = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        if strip:
            stdout_txt = stdout_txt.strip()
            stderr_txt = stderr_txt.strip()
        return stdout_txt, stderr_txt

    def test_new_update_pr(self):
        """Test use of --new-pr (dry run only)."""
        if self.github_token is None:
            print "Skipping test_new_update_pr, no GitHub token available?"
            return

        # copy toy test easyconfig
        topdir = os.path.dirname(os.path.abspath(__file__))
        test_ecs = os.path.join(topdir, 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(self.test_prefix, 'toy.eb')
        toy_patch_fn = 'toy-0.0_fix-silly-typo-in-printf-statement.patch'
        toy_patch = os.path.join(topdir, 'sandbox', 'sources', 'toy', toy_patch_fn)
        # purposely picked one with non-default toolchain/versionsuffix
        copy_file(os.path.join(test_ecs, 't', 'toy', 'toy-0.0-gompi-1.3.12-test.eb'), toy_ec)

        # modify file to mock archived easyconfig
        toy_ec_txt = read_file(toy_ec)
        toy_ec_txt = '\n'.join([
            "# Built with EasyBuild version 3.1.2 on 2017-04-25_21-35-15",
            toy_ec_txt,
            "# Build statistics",
            "buildstats = [{",
            '   "build_time": 8.34,',
            '   "os_type": "Linux",',
            "}]",
        ])
        write_file(toy_ec, toy_ec_txt)

        args = [
            '--new-pr',
            '--github-user=%s' % GITHUB_TEST_ACCOUNT,
            toy_ec,
            '-D',
            '--disable-cleanup-tmpdir',
        ]
        txt, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False)

        # determine location of repo clone, can be used to test --git-working-dirs-path (and save time)
        dirs = glob.glob(os.path.join(self.test_prefix, 'eb-*', '*', 'git-working-dir*'))
        if len(dirs) == 1:
            git_working_dir = dirs[0]
        else:
            self.assertTrue(False, "Failed to find temporary git working dir: %s" % dirs)

        remote = 'git@github.com:%s/easybuild-easyconfigs.git' % GITHUB_TEST_ACCOUNT
        regexs = [
            r"^== fetching branch 'develop' from https://github.com/easybuilders/easybuild-easyconfigs.git...",
            r"^== pushing branch '.*' to remote '.*' \(%s\)" % remote,
            r"^Opening pull request \[DRY RUN\]",
            r"^\* target: easybuilders/easybuild-easyconfigs:develop",
            r"^\* from: %s/easybuild-easyconfigs:.*_new_pr_toy00" % GITHUB_TEST_ACCOUNT,
            r"^\* title: \"\{tools\}\[gompi/1.3.12\] toy v0.0\"",
            r"\(created using `eb --new-pr`\)",  # description
            r"^\* overview of changes:",
            r".*/toy-0.0-gompi-1.3.12-test.eb\s*\|",
            r"^\s*1 file(s?) changed",
        ]
        self._assert_regexs(regexs, txt)

        # a custom commit message is required when doing more than just adding new easyconfigs (e.g., deleting a file)
        args.extend([
            '--git-working-dirs-path=%s' % git_working_dir,
            ':bzip2-1.0.6.eb',
        ])
        error_msg = "A meaningful commit message must be specified via --pr-commit-msg"

        self.mock_stdout(True)
        self.assertErrorRegex(EasyBuildError, error_msg, self.eb_main, args, raise_error=True, testing=False)
        self.mock_stdout(False)

        # add required commit message, try again
        args.append('--pr-commit-msg=just a test')
        txt, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False)

        regexs[-1] = r"^\s*2 files changed"
        regexs.remove(r"^\* title: \"\{tools\}\[gompi/1.3.12\] toy v0.0\"")
        regexs.append(r"^\* title: \"just a test\"")
        regexs.append(r".*/bzip2-1.0.6.eb\s*\|")
        regexs.append(r".*[0-9]+ deletions\(-\)")
        self._assert_regexs(regexs, txt)

        GITHUB_TEST_ORG = 'test-organization'
        args.extend([
            '--git-working-dirs-path=%s' % git_working_dir,
            '--pr-branch-name=branch_name_for_new_pr_test',
            '--pr-commit-msg="this is a commit message. really!"',
            '--pr-descr="moar letters foar teh lettre box"',
            '--pr-target-branch=master',
            '--github-org=%s' % GITHUB_TEST_ORG,
            '--pr-target-account=boegel',  # we need to be able to 'clone' from here (via https)
            '--pr-title=test-1-2-3',
        ])
        txt, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False)

        regexs = [
            r"^== fetching branch 'master' from https://github.com/boegel/easybuild-easyconfigs.git...",
            r"^Opening pull request \[DRY RUN\]",
            r"^\* target: boegel/easybuild-easyconfigs:master",
            r"^\* from: %s/easybuild-easyconfigs:branch_name_for_new_pr_test" % GITHUB_TEST_ORG,
            r"\(created using `eb --new-pr`\)",  # description
            r"moar letters foar teh lettre box",  # also description (see --pr-descr)
            r"^\* title: \"test-1-2-3\"",
            r"^\* overview of changes:",
            r".*/toy-0.0-gompi-1.3.12-test.eb\s*\|",
            r".*/bzip2-1.0.6.eb\s*\|",
            r"^\s*2 files changed",
            r".*[0-9]+ deletions\(-\)",
        ]
        self._assert_regexs(regexs, txt)

        # should also work with a patch
        args.append(toy_patch)
        self.mock_stdout(True)
        self.eb_main(args, do_build=True, raise_error=True, testing=False)
        txt = self.get_stdout()
        self.mock_stdout(False)

        regexs[-2] = r"^\s*3 files changed"
        regexs.append(r".*_fix-silly-typo-in-printf-statement.patch\s*\|")
        for regex in regexs:
            regex = re.compile(regex, re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))

        # modifying an existing easyconfig requires a custom PR title
        gcc_ec = os.path.join(test_ecs, 'g', 'GCC', 'GCC-4.9.2.eb')
        self.assertTrue(os.path.exists(gcc_ec))

        args = [
            '--new-pr',
            '--github-user=%s' % GITHUB_TEST_ACCOUNT,
            toy_ec,
            gcc_ec,
            '-D',
        ]
        error_msg = "A meaningful commit message must be specified via --pr-commit-msg"
        self.mock_stdout(True)
        self.assertErrorRegex(EasyBuildError, error_msg, self.eb_main, args, raise_error=True)
        self.mock_stdout(False)

        # also specifying commit message is sufficient; PR title is inherited from commit message
        args.append('--pr-commit-msg=this is just a test')
        txt, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False)

        regex = re.compile('^\* title: "this is just a test"', re.M)
        self.assertTrue(regex.search(txt), "Pattern '%s' is found in: %s" % (regex.pattern, txt))

        args = [
            # PR for EasyBuild v2.5.0 release
            # we need a PR where the base branch is still available ('develop', in this case)
            '--update-pr=2237',
            '--github-user=%s' % GITHUB_TEST_ACCOUNT,
            toy_ec,
            '-D',
            # only to speed things up
            '--git-working-dirs-path=%s' % git_working_dir,
        ]

        error_msg = "A meaningful commit message must be specified via --pr-commit-msg when using --update-pr"
        self.mock_stdout(True)
        self.assertErrorRegex(EasyBuildError, error_msg, self.eb_main, args, raise_error=True)
        self.mock_stdout(False)

        args.append('--pr-commit-msg="just a test"')
        txt, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False)

        regexs = [
            r"^== Determined branch name corresponding to easybuilders/easybuild-easyconfigs PR #2237: develop",
            r"^== fetching branch 'develop' from https://github.com/easybuilders/easybuild-easyconfigs.git...",
            r".*/toy-0.0-gompi-1.3.12-test.eb\s*\|",
            r"^\s*1 file(s?) changed",
            "^== pushing branch 'develop' to remote '.*' \(git@github.com:easybuilders/easybuild-easyconfigs.git\)",
            r"^Updated easybuilders/easybuild-easyconfigs PR #2237 by pushing to branch easybuilders/develop \[DRY RUN\]",
        ]
        self._assert_regexs(regexs, txt)

        # also check behaviour under --extended-dry-run/-x
        args.remove('-D')
        args.append('-x')

        txt, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False)

        regexs.extend([
            r"Full patch:",
            r"^\+\+\+\s*.*toy-0.0-gompi-1.3.12-test.eb",
            r"^\+name = 'toy'",
        ])
        self._assert_regexs(regexs, txt)

        # check whether comments/buildstats get filtered out
        regexs = [
            "# Built with EasyBuild",
            "# Build statistics",
            "buildstats\s*=",
        ]
        self._assert_regexs(regexs, txt, assert_true=False)

    def test_new_pr_delete(self):
        """Test use of --new-pr to delete easyconfigs."""

        if self.github_token is None:
            print "Skipping test_new_pr_delete, no GitHub token available?"
            return

        args = [
            '--new-pr',
            '--github-user=%s' % GITHUB_TEST_ACCOUNT,
            ':bzip2-1.0.6.eb',
            '-D',
            '--disable-cleanup-tmpdir',
            '--pr-title=delete bzip2-1.6.0',
            '--pr-commit-msg="delete bzip2-1.6.0.eb"'
        ]
        txt, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False)

        regexs = [
            r"^== fetching branch 'develop' from https://github.com/easybuilders/easybuild-easyconfigs.git...",
            r'title: "delete bzip2-1.6.0"',
            r"1 file(s?) changed,( 0 insertions\(\+\),)? [0-9]+ deletions\(-\)",
        ]
        self._assert_regexs(regexs, txt)

    def test_new_pr_dependencies(self):
        """Test use of --new-pr with automatic dependency lookup."""

        if self.github_token is None:
            print "Skipping test_new_pr_dependencies, no GitHub token available?"
            return

        foo_eb = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "foo"',
            'version = "1.0"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"dummy", "version": "dummy"}',
            'dependencies = [("bar", "2.0")]'
        ])
        bar_eb = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "bar"',
            'version = "2.0"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"dummy", "version": "dummy"}',
        ])

        write_file(os.path.join(self.test_prefix, 'foo-1.0.eb'), foo_eb)
        write_file(os.path.join(self.test_prefix, 'bar-2.0.eb'), bar_eb)

        args = [
            '--new-pr',
            '--github-user=%s' % GITHUB_TEST_ACCOUNT,
            os.path.join(self.test_prefix, 'foo-1.0.eb'),
            '-D',
            '--disable-cleanup-tmpdir',
            '-r%s' % self.test_prefix,
        ]

        txt, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False)

        regexs = [
            r"^\* overview of changes:",
            r".*/foo-1\.0\.eb\s*\|",
            r".*/bar-2\.0\.eb\s*\|",
            r"^\s*2 files changed",
        ]

        self._assert_regexs(regexs, txt)

    def test_merge_pr(self):
        """
        Test use of --merge-pr (dry run)"""
        if self.github_token is None:
            print "Skipping test_merge_pr, no GitHub token available?"
            return

        args = [
            '--merge-pr',
            '4781',  # PR for easyconfig for EasyBuild-3.3.0.eb
            '-D',
            '--github-user=%s' % GITHUB_TEST_ACCOUNT,
        ]

        # merged PR for EasyBuild-3.3.0.eb, is missing approved review
        stdout, stderr = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False)

        expected_stdout = '\n'.join([
            "Checking eligibility of easybuilders/easybuild-easyconfigs PR #4781 for merging...",
            "* targets develop branch: OK",
            "* test suite passes: OK",
            "* last test report is successful: OK",
            "* milestone is set: OK (3.3.1)",
        ])
        expected_stderr = '\n'.join([
            "* approved review: MISSING => not eligible for merging!",
            '',
            "WARNING: Review indicates this PR should not be merged (use -f/--force to do so anyway)",
        ])
        self.assertEqual(stderr.strip(), expected_stderr)
        self.assertTrue(stdout.strip().endswith(expected_stdout), "'%s' ends with '%s'" % (stdout, expected_stdout))

        # full eligible merged PR
        args[1] = '4832'

        stdout, stderr = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False)

        expected_stdout = '\n'.join([
            "Checking eligibility of easybuilders/easybuild-easyconfigs PR #4832 for merging...",
            "* targets develop branch: OK",
            "* test suite passes: OK",
            "* last test report is successful: OK",
            "* approved review: OK (by wpoely86)",
            "* milestone is set: OK (3.3.1)",
            '',
            "Review OK, merging pull request!",
            '',
            "[DRY RUN] Adding comment to easybuild-easyconfigs issue #4832: 'Going in, thanks @boegel!'",
            "[DRY RUN] Merged easybuilders/easybuild-easyconfigs pull request #4832",
        ])
        expected_stderr = ''
        self.assertEqual(stderr.strip(), expected_stderr)
        self.assertTrue(stdout.strip().endswith(expected_stdout), "'%s' ends with '%s'" % (stdout, expected_stdout))

        # --merge-pr also works on easyblocks (& framework) PRs
        args = [
            '--merge-pr',
            '1206',
            '--pr-target-repo=easybuild-easyblocks',
            '-D',
            '--github-user=%s' % GITHUB_TEST_ACCOUNT,
        ]
        stdout, stderr = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False)
        self.assertEqual(stderr.strip(), '')
        expected_stdout = '\n'.join([
            "Checking eligibility of easybuilders/easybuild-easyblocks PR #1206 for merging...",
            "* targets develop branch: OK",
            "* test suite passes: OK",
            "* approved review: OK (by migueldiascosta)",
            "* milestone is set: OK (3.3.1)",
            '',
            "Review OK, merging pull request!",
        ])
        self.assertTrue(expected_stdout in stdout)

    def test_empty_pr(self):
        """Test use of --new-pr (dry run only) with no changes"""
        if self.github_token is None:
            print "Skipping test_empty_pr, no GitHub token available?"
            return

        # get file from develop branch
        full_url = URL_SEPARATOR.join([GITHUB_RAW, GITHUB_EB_MAIN, GITHUB_EASYCONFIGS_REPO,
                                       'develop/easybuild/easyconfigs/z/zlib/zlib-1.2.8.eb'])
        ec_fn = os.path.basename(full_url)
        ec = download_file(ec_fn, full_url, path=os.path.join(self.test_prefix, ec_fn))

        # try to open new pr with unchanged file
        args = [
            '--new-pr',
            ec,
            '-D',
            '--github-user=%s' % GITHUB_TEST_ACCOUNT,
            '--pr-commit-msg=blabla',
        ]

        self.mock_stdout(True)
        error_msg = "No changed files found when comparing to current develop branch."
        self.assertErrorRegex(EasyBuildError, error_msg, self.eb_main, args, do_build=True, raise_error=True)
        self.mock_stdout(False)

    def test_show_config(self):
        """"Test --show-config and --show-full-config."""

        # only retain $EASYBUILD_* environment variables we expect for this test
        retained_eb_env_vars = [
            'EASYBUILD_DEPRECATED',
            'EASYBUILD_IGNORECONFIGFILES',
            'EASYBUILD_INSTALLPATH',
            'EASYBUILD_ROBOT_PATHS',
            'EASYBUILD_SOURCEPATH',
        ]
        for key in os.environ.keys():
            if key.startswith('EASYBUILD_') and key not in retained_eb_env_vars:
                del os.environ[key]

        cfgfile = os.path.join(self.test_prefix, 'test.cfg')
        cfgtxt = '\n'.join([
            "[config]",
            "subdir-modules = mods",
        ])
        write_file(cfgfile, cfgtxt)

        args = ['--configfiles=%s' % cfgfile, '--show-config', '--buildpath=/weird/build/dir']
        txt, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False, strip=True)

        default_prefix = os.path.join(os.environ['HOME'], '.local', 'easybuild')

        test_dir = os.path.dirname(os.path.abspath(__file__))
        expected_lines = [
            r"#",
            r"# Current EasyBuild configuration",
            r"# \(C: command line argument, D: default value, E: environment variable, F: configuration file\)",
            r"#",
            r"buildpath\s* \(C\) = /weird/build/dir",
            r"configfiles\s* \(C\) = .*" + cfgfile,
            r"containerpath\s* \(D\) = %s" % os.path.join(default_prefix, 'containers'),
            r"deprecated\s* \(E\) = 10000000",
            r"ignoreconfigfiles\s* \(E\) = %s" % ', '.join(os.environ['EASYBUILD_IGNORECONFIGFILES'].split(',')),
            r"installpath\s* \(E\) = " + os.path.join(self.test_prefix, 'tmp.*'),
            r"repositorypath\s* \(D\) = " + os.path.join(default_prefix, 'ebfiles_repo'),
            r"robot-paths\s* \(E\) = " + os.path.join(test_dir, 'easyconfigs', 'test_ecs'),
            r"sourcepath\s* \(E\) = " + os.path.join(test_dir, 'sandbox', 'sources'),
            r"subdir-modules\s* \(F\) = mods",
        ]

        regex = re.compile('\n'.join(expected_lines))
        self.assertTrue(regex.match(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))

        args = ['--configfiles=%s' % cfgfile, '--show-full-config', '--buildpath=/weird/build/dir']
        txt, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False)

        # output of --show-full-config includes additional lines for options with default values
        expected_lines.extend([
            r"force\s* \(D\) = False",
            r"modules-tool\s* \(D\) = Lmod",
            r"module-syntax\s* \(D\) = Lua",
            r"umask\s* \(D\) = None",
        ])

        for expected_line in expected_lines:
            self.assertTrue(re.search(expected_line, txt, re.M), "Found '%s' in: %s" % (expected_line, txt))

        # --show-config should also work if no configuration files are available
        # (existing config files are ignored via $EASYBUILD_IGNORECONFIGFILES)
        self.assertFalse(os.environ.get('EASYBUILD_CONFIGFILES', False))
        args = ['--show-config', '--buildpath=/weird/build/dir']
        txt, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False, strip=True)
        self.assertTrue(re.search(r"buildpath\s* \(C\) = /weird/build/dir", txt))

        # --show-config should not break including of easyblocks via $EASYBUILD_INCLUDE_EASYBLOCKS (see bug #1696)
        txt = '\n'.join([
            'from easybuild.framework.easyblock import EasyBlock',
            'class EB_testeasyblocktoinclude(EasyBlock):',
            '   pass',
            ''
        ])
        testeasyblocktoinclude = os.path.join(self.test_prefix, 'testeasyblocktoinclude.py')
        write_file(testeasyblocktoinclude, txt)

        os.environ['EASYBUILD_INCLUDE_EASYBLOCKS'] = testeasyblocktoinclude
        args = ['--show-config']
        txt, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False, strip=True)
        regex = re.compile(r'^include-easyblocks \(E\) = .*/testeasyblocktoinclude.py$', re.M)
        self.assertTrue(regex.search(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))

    def test_show_config_cfg_levels(self):
        """Test --show-config in relation to how configuring across multiple configuration levels interacts with it."""

        # make sure default module syntax is used
        if 'EASYBUILD_MODULE_SYNTAX' in os.environ:
            del os.environ['EASYBUILD_MODULE_SYNTAX']

        # configuring --modules-tool and --module-syntax on different levels should NOT cause problems
        # cfr. bug report https://github.com/easybuilders/easybuild-framework/issues/2564
        os.environ['EASYBUILD_MODULES_TOOL'] = 'EnvironmentModulesC'
        args = [
            '--module-syntax=Tcl',
            '--show-config',
        ]
        # set init_config to False to avoid that eb_main (called by _run_mock_eb) re-initialises configuration
        # this fails because $EASYBUILD_MODULES_TOOL=EnvironmentModulesC conflicts with default module syntax (Lua)
        stdout, _ = self._run_mock_eb(args, raise_error=True, redo_init_config=False)

        patterns = [
            "^# Current EasyBuild configuration",
            "^module-syntax\s*\(C\) = Tcl",
            "^modules-tool\s*\(E\) = EnvironmentModulesC",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

    def test_modules_tool_vs_syntax_check(self):
        """Verify that check for modules tool vs syntax works."""

        # make sure default module syntax is used
        if 'EASYBUILD_MODULE_SYNTAX' in os.environ:
            del os.environ['EASYBUILD_MODULE_SYNTAX']

        # using EnvironmentModulesC modules tool with default module syntax (Lua) is a problem
        os.environ['EASYBUILD_MODULES_TOOL'] = 'EnvironmentModulesC'
        args = ['--show-full-config']
        error_pattern = "Generating Lua module files requires Lmod as modules tool"
        self.assertErrorRegex(EasyBuildError, error_pattern, self._run_mock_eb, args, raise_error=True)

        patterns = [
            "^# Current EasyBuild configuration",
            "^module-syntax\s*\(C\) = Tcl",
            "^modules-tool\s*\(E\) = EnvironmentModulesC",
        ]

        # EnvironmentModulesC modules tool + Tcl module syntax is fine
        args.append('--module-syntax=Tcl')
        stdout, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False, redo_init_config=False)
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        # default modules tool (Lmod) with Tcl module syntax is also fine
        del os.environ['EASYBUILD_MODULES_TOOL']
        patterns[-1] = "^modules-tool\s*\(D\) = Lmod"
        stdout, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False, redo_init_config=False)
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

    def test_prefix(self):
        """Test which configuration settings are affected by --prefix."""
        txt, _ = self._run_mock_eb(['--show-full-config', '--prefix=%s' % self.test_prefix], raise_error=True)

        regex = re.compile("(?P<cfg_opt>\S*).*%s.*" % self.test_prefix, re.M)

        expected = ['buildpath', 'containerpath', 'installpath', 'packagepath', 'prefix', 'repositorypath']
        self.assertEqual(sorted(regex.findall(txt)), expected)

    def test_dump_env_config(self):
        """Test for --dump-env-config."""

        fftw = 'FFTW-3.3.3-gompi-1.4.10'
        gcc = 'GCC-4.9.2'
        openmpi = 'OpenMPI-1.6.4-GCC-4.7.2'
        args = ['%s.eb' % ec for ec in [fftw, gcc, openmpi]] + ['--dump-env-script']

        os.chdir(self.test_prefix)
        txt, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False, strip=True)

        for name in [fftw, gcc, openmpi]:
            # check stdout
            regex = re.compile("^Script to set up build environment for %s.eb dumped to %s.env" % (name, name), re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))

            # check whether scripts were dumped
            env_script = os.path.join(self.test_prefix, '%s.env' % name)
            self.assertTrue(os.path.exists(env_script))

        # existing .env files are not overwritten, unless forced
        os.chdir(self.test_prefix)
        args = ['%s.eb' % openmpi, '--dump-env-script']
        error_msg = r"Script\(s\) already exists, not overwriting them \(unless --force is used\): %s.env" % openmpi
        self.assertErrorRegex(EasyBuildError, error_msg, self.eb_main, args, do_build=True, raise_error=True)

        os.chdir(self.test_prefix)
        args.append('--force')
        self._run_mock_eb(args, do_build=True, raise_error=True)

        # check contents of script
        env_script = os.path.join(self.test_prefix, '%s.env' % openmpi)
        txt = read_file(env_script)
        patterns = [
            "module load GCC/4.7.2",  # loading of toolchain module
            "module load hwloc/1.6.2-GCC-4.7.2",  # loading of dependency module
            # defining build env
            "export FC='gfortran'",
            "export CFLAGS='-O2 -ftree-vectorize -march=native -fno-math-errno'",
        ]
        for pattern in patterns:
            regex = re.compile("^%s$" % pattern, re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))

        out, ec = run_cmd("function module { echo $@; } && source %s && echo FC: $FC" % env_script, simple=False)
        expected_out = '\n'.join([
            "load GCC/4.7.2",
            "load hwloc/1.6.2-GCC-4.7.2",
            "FC: gfortran",
        ])
        self.assertEqual(out.strip(), expected_out)

    def test_stop(self):
        """Test use of --stop."""
        args = ['toy-0.0.eb', '--force', '--stop=configure']
        txt, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False, strip=True)

        regex = re.compile("COMPLETED: Installation STOPPED successfully", re.M)
        self.assertTrue(regex.search(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))

    def test_fetch(self):
        options = EasyBuildOptions(go_args=['--fetch'])

        self.assertTrue(options.options.fetch)
        self.assertEqual(options.options.stop, 'fetch')
        self.assertEqual(options.options.modules_tool, None)
        self.assertTrue(options.options.ignore_osdeps)

        # in this test we want to fake the case were no modules tool are in the system so teak it
        self.modtool = None
        args = ['toy-0.0.eb', '--fetch']
        stdout, stderr = self._run_mock_eb(args, raise_error=True, strip=True, testing=False)

        patterns = [
            "^== fetching files\.\.\.$",
            "^== COMPLETED: Installation STOPPED successfully$",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' not found in: %s" % (regex.pattern, stdout))

        regex = re.compile("^== creating build dir, resetting environment\.\.\.$")
        self.assertFalse(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

    def test_parse_external_modules_metadata(self):
        """Test parse_external_modules_metadata function."""
        # by default, provided external module metadata cfg files are picked up
        metadata = parse_external_modules_metadata(None)

        # just a selection
        for mod in ['cray-libsci/13.2.0', 'cray-netcdf/4.3.2', 'fftw/3.3.4.3']:
            self.assertTrue(mod in metadata)

        netcdf = {
            'name': ['netCDF', 'netCDF-Fortran'],
            'version': ['4.3.2', '4.3.2'],
            'prefix': 'NETCDF_DIR',
        }
        self.assertEqual(metadata['cray-netcdf/4.3.2'], netcdf)

        libsci = {
            'name': ['LibSci'],
            'version': ['13.2.0'],
            'prefix': 'CRAY_LIBSCI_PREFIX_DIR',
        }
        self.assertEqual(metadata['cray-libsci/13.2.0'], libsci)

        testcfgtxt = EXTERNAL_MODULES_METADATA
        testcfg = os.path.join(self.test_prefix, 'test_external_modules_metadata.cfg')
        write_file(testcfg, testcfgtxt)

        metadata = parse_external_modules_metadata([testcfg])

        # default metadata is overruled, and not available anymore
        for mod in ['cray-libsci/13.2.0', 'cray-netcdf/4.3.2', 'fftw/3.3.4.3']:
            self.assertFalse(mod in metadata)

        foobar1 = {
            'name': ['foo', 'bar'],
            'version': ['1.2.3', '3.2.1'],
            'prefix': 'FOOBAR_DIR',
        }
        self.assertEqual(metadata['foobar/1.2.3'], foobar1)

        foobar2 = {
            'name': ['foobar'],
            'version': ['2.0'],
            'prefix': 'FOOBAR_PREFIX',
        }
        self.assertEqual(metadata['foobar/2.0'], foobar2)

        # impartial metadata is fine
        self.assertEqual(metadata['foo'], {'name': ['Foo'], 'prefix': '/foo'})
        self.assertEqual(metadata['bar/1.2.3'], {'name': ['bar'], 'version': ['1.2.3']})

        # if both names and versions are specified, lists must have same lengths
        write_file(testcfg, '\n'.join(['[foo/1.2.3]', 'name = foo,bar', 'version = 1.2.3']))
        err_msg = "Different length for lists of names/versions in metadata for external module"
        self.assertErrorRegex(EasyBuildError, err_msg, parse_external_modules_metadata, [testcfg])

    def test_zip_logs(self):
        """Test use of --zip-logs"""

        toy_eb_install_dir = os.path.join(self.test_installpath, 'software', 'toy', '0.0', 'easybuild')
        for zip_logs in ['', '--zip-logs', '--zip-logs=gzip', '--zip-logs=bzip2']:

            shutil.rmtree(self.test_installpath)

            args = ['toy-0.0.eb', '--force', '--debug']
            if zip_logs:
                args.append(zip_logs)
            out = self.eb_main(args, do_build=True)

            logs = glob.glob(os.path.join(toy_eb_install_dir, 'easybuild-toy-0.0*log*'))
            self.assertEqual(len(logs), 1, "Found exactly 1 log file in %s: %s" % (toy_eb_install_dir, logs))

            zip_logs_arg = zip_logs.split('=')[-1]
            if zip_logs == '--zip-logs' or zip_logs_arg == 'gzip':
                ext = 'log.gz'
            elif zip_logs_arg == 'bzip2':
                ext = 'log.bz2'
            else:
                ext = 'log'

            self.assertTrue(logs[0].endswith(ext), "%s has correct '%s' extension for %s" % (logs[0], ext, zip_logs))

    def test_debug_lmod(self):
        """Test use of --debug-lmod."""
        if isinstance(self.modtool, Lmod):
            init_config(build_options={'debug_lmod': True})
            out = self.modtool.run_module('avail', return_output=True)

            for pattern in [r"^Lmod version", r"^lmod\(--terse -D avail\)\{", "Master:avail"]:
                regex = re.compile(pattern, re.M)
                self.assertTrue(regex.search(out), "Pattern '%s' found in: %s" % (regex.pattern, out))
        else:
            print "Skipping test_debug_lmod, required Lmod as modules tool"

    def test_use_color(self):
        """Test use_color function."""
        self.assertTrue(use_color('always'))
        self.assertFalse(use_color('never'))
        easybuild.tools.options.terminal_supports_colors = lambda _: True
        self.assertTrue(use_color('auto'))
        easybuild.tools.options.terminal_supports_colors = lambda _: False
        self.assertFalse(use_color('auto'))

    def test_list_software(self):
        """Test --list-software and --list-installed-software."""
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'v1.0')
        args = [
            '--list-software',
            '--robot-paths=%s' % test_ecs,
        ]
        txt, _ = self._run_mock_eb(args, do_build=True, raise_error=True, testing=False)
        expected = '\n'.join([
            "== Processed 5/5 easyconfigs...",
            "== Found 2 different software packages",
            '',
            "* GCC",
            "* gzip",
            '',
        ])
        self.assertTrue(txt.endswith(expected))

        args = [
            '--list-software=detailed',
            '--output-format=rst',
            '--robot-paths=%s' % test_ecs,
        ]
        txt, _ = self._run_mock_eb(args, testing=False)
        self.assertTrue(re.search('^\*GCC\*', txt, re.M))
        self.assertTrue(re.search('^``4.6.3``\s+``dummy``', txt, re.M))
        self.assertTrue(re.search('^\*gzip\*', txt, re.M))
        self.assertTrue(re.search('^``1.5``\s+``goolf/1.4.10``,\s+``ictce/4.1.13``', txt, re.M))

        args = [
            '--list-installed-software',
            '--output-format=rst',
            '--robot-paths=%s' % test_ecs,
        ]
        txt, _ = self._run_mock_eb(args, testing=False)
        self.assertTrue(re.search('== Processed 5/5 easyconfigs...', txt, re.M))
        self.assertTrue(re.search('== Found 2 different software packages', txt, re.M))
        self.assertTrue(re.search('== Retained 1 installed software packages', txt, re.M))
        self.assertTrue(re.search('^\* GCC', txt, re.M))
        self.assertFalse(re.search('gzip', txt, re.M))

        args = [
            '--list-installed-software=detailed',
            '--robot-paths=%s' % test_ecs,
        ]
        txt, _ = self._run_mock_eb(args, testing=False)
        self.assertTrue(re.search('^== Retained 1 installed software packages', txt, re.M))
        self.assertTrue(re.search('^\* GCC', txt, re.M))
        self.assertTrue(re.search('^\s+\* GCC v4.6.3: dummy', txt, re.M))
        self.assertFalse(re.search('gzip', txt, re.M))

    def test_parse_optarch(self):
        """Test correct parsing of optarch option."""

        # Check that it is not parsed if we are submitting a job
        options = EasyBuildOptions(go_args=['--job'])
        optarch_string = 'Intel:something;GCC:somethinglese'
        options.options.optarch = optarch_string
        options.postprocess()
        self.assertEqual(options.options.optarch, optarch_string)

        # Use no arguments for the rest of the tests
        options = EasyBuildOptions()

        # Check for EasyBuildErrors
        error_msg = "The optarch option has an incorrect syntax"
        options.options.optarch = 'Intel:something;GCC'
        self.assertErrorRegex(EasyBuildError, error_msg, options.postprocess)

        options.options.optarch = 'Intel:something;'
        self.assertErrorRegex(EasyBuildError, error_msg, options.postprocess)

        options.options.optarch = 'Intel:something:somethingelse'
        self.assertErrorRegex(EasyBuildError, error_msg, options.postprocess)

        error_msg = "The optarch option contains duplicated entries for compiler"
        options.options.optarch = 'Intel:something;GCC:somethingelse;Intel:anothersomething'
        self.assertErrorRegex(EasyBuildError, error_msg, options.postprocess)

        # Check the parsing itself
        gcc_generic_flags = "march=x86-64 -mtune=generic"
        test_cases = [
            ('',''),
            ('xHost','xHost'),
            ('GENERIC','GENERIC'),
            ('Intel:xHost', {'Intel': 'xHost'}),
            ('Intel:GENERIC', {'Intel': 'GENERIC'}),
            ('Intel:xHost;GCC:%s' % gcc_generic_flags, {'Intel': 'xHost', 'GCC': gcc_generic_flags}),
            ('Intel:;GCC:%s' % gcc_generic_flags, {'Intel': '', 'GCC': gcc_generic_flags}),
        ]

        for optarch_string, optarch_parsed in test_cases:
            options.options.optarch = optarch_string
            options.postprocess()
            self.assertEqual(options.options.optarch, optarch_parsed)

    def test_check_contrib_style(self):
        """Test style checks performed by --check-contrib + dedicated --check-style option."""
        try:
            import pycodestyle
        except ImportError:
            try:
                import pep8
            except ImportError:
                print "Skipping test_check_contrib_style, since pycodestyle or pep8 is not available"
                return

        regex = re.compile(r"Running style check on 2 easyconfig\(s\)(.|\n)*>> All style checks PASSed!", re.M)
        args = [
            '--check-style',
            'GCC-4.9.2.eb',
            'toy-0.0.eb',
        ]
        stdout, _ = self._run_mock_eb(args, raise_error=True)
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        # --check-contrib fails because of missing checksums, but style test passes
        args[0] = '--check-contrib'
        self.mock_stdout(True)
        error_pattern = "One or more contribution checks FAILED"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.eb_main, args, raise_error=True)
        stdout = self.get_stdout().strip()
        self.mock_stdout(False)
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        # copy toy-0.0.eb test easyconfig, fiddle with it to make style check fail
        toy = os.path.join(self.test_prefix, 'toy.eb')
        copy_file(os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb'), toy)

        toytxt = read_file(toy)
        # introduce whitespace issues
        toytxt = toytxt.replace("name = 'toy'", "name\t='toy'    ")
        # introduce long line
        toytxt = toytxt.replace('description = "Toy C program, 100% toy."', 'description = "%s"' % ('toy ' * 30))
        write_file(toy, toytxt)

        for check_type in ['contribution', 'style']:
            args = [
                '--check-%s' % check_type[:7],
                toy,
            ]
            self.mock_stdout(True)
            error_pattern = "One or more %s checks FAILED!" % check_type
            self.assertErrorRegex(EasyBuildError, error_pattern, self.eb_main, args, raise_error=True)
            stdout = self.get_stdout()
            self.mock_stdout(False)
            patterns = [
                "toy.eb:1:5: E223 tab before operator",
                "toy.eb:1:7: E225 missing whitespace around operator",
                "toy.eb:1:12: W299 trailing whitespace",
                r"toy.eb:5:121: E501 line too long \(136 > 120 characters\)",
            ]
            for pattern in patterns:
                self.assertTrue(re.search(pattern, stdout, re.M), "Pattern '%s' found in: %s" % (pattern, stdout))

    def test_check_contrib_non_style(self):
        """Test non-style checks performed by --check-contrib."""
        args = [
            '--check-contrib',
            'toy-0.0.eb',
        ]
        self.mock_stdout(True)
        self.mock_stderr(True)
        error_pattern = "One or more contribution checks FAILED"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.eb_main, args, raise_error=True)
        stdout = self.get_stdout().strip()
        stderr = self.get_stderr().strip()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(stderr, '')

        # SHA256 checksum checks fail
        patterns = [
            r"\[FAIL\] .*/toy-0.0.eb$",
            r"^Checksums missing for one or more sources/patches in toy-0.0.eb: "
            r"found 1 sources \+ 2 patches vs 1 checksums$",
            r"^>> One or more SHA256 checksums checks FAILED!",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(re.search(pattern, stdout, re.M), "Pattern '%s' found in: %s" % (pattern, stdout))

    def test_allow_use_as_root(self):
        """Test --allow-use-as-root-and-accept-consequences"""

        # pretend we're running as root by monkey patching os.getuid used in main
        easybuild.main.os.getuid = lambda: 0

        # running as root is disallowed by default
        error_msg = "You seem to be running EasyBuild with root privileges which is not wise, so let's end this here"
        self.assertErrorRegex(EasyBuildError, error_msg, self.eb_main, ['toy-0.0.eb'], raise_error=True)

        # running as root is allowed under --allow-use-as-root, but does result in a warning being printed to stderr
        args = ['toy-0.0.eb', '--allow-use-as-root-and-accept-consequences']
        _, stderr = self._run_mock_eb(args, raise_error=True, strip=True)

        expected = "WARNING: Using EasyBuild as root is NOT recommended, please proceed with care!\n"
        expected += "(this is only allowed because EasyBuild was configured with "
        expected += "--allow-use-as-root-and-accept-consequences)"
        self.assertEqual(stderr, expected)

    def test_verify_easyconfig_filenames(self):
        """Test --verify-easyconfig-filename"""
        test_easyconfigs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        toy_ec = os.path.join(test_easyconfigs_dir, 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        copy_file(toy_ec, test_ec)

        args = [
            test_ec,
            '--dry-run',  # implies enabling dependency resolution
            '--unittest-file=%s' % self.logfile,
        ]

        # filename of provided easyconfig doesn't matter by default
        self.eb_main(args, logfile=dummylogfn, raise_error=True)
        logtxt = read_file(self.logfile)
        self.assertTrue('module: toy/0.0' in logtxt)

        write_file(self.logfile, '')

        # when --verify-easyconfig-filenames is enabled, EB gets picky about the easyconfig filename
        args.append('--verify-easyconfig-filenames')
        error_pattern = "Easyconfig filename 'test.eb' does not match with expected filename 'toy-0.0.eb' \(specs: "
        error_pattern += "name: 'toy'; version: '0.0'; versionsuffix: ''; toolchain name, version: 'dummy', 'dummy'\)"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.eb_main, args, logfile=dummylogfn, raise_error=True)

        write_file(self.logfile, '')

        args[0] = toy_ec
        self.eb_main(args, logfile=dummylogfn, raise_error=True)
        logtxt = read_file(self.logfile)
        self.assertTrue('module: toy/0.0' in logtxt)

    def test_set_default_module(self):
        """Test use of --set-default-module"""
        topdir = os.path.dirname(os.path.abspath(__file__))
        toy_ec = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-deps.eb')

        self.eb_main([toy_ec, '--set-default-module'], do_build=True, raise_error=True)

        toy_mod_dir = os.path.join(self.test_installpath, 'modules', 'all', 'toy')
        toy_mod = os.path.join(toy_mod_dir, '0.0-deps')
        if get_module_syntax() == 'Lua':
            toy_mod += '.lua'

        self.assertTrue(os.path.exists(toy_mod))

        if get_module_syntax() == 'Lua':
            self.assertTrue(os.path.islink(os.path.join(toy_mod_dir, 'default')))
            toy_mod_filename = '0.0-deps.lua'
            self.assertEqual(os.readlink(os.path.join(toy_mod_dir, 'default')), '0.0-deps.lua')
        elif get_module_syntax() == 'Tcl':
            toy_dot_version = os.path.join(toy_mod_dir, '.version')
            self.assertTrue(os.path.exists(toy_dot_version))
            toy_dot_version_txt = read_file(toy_dot_version)
            self.assertTrue("set ModulesVersion 0.0-deps" in toy_dot_version_txt)
        else:
            self.assertTrue(False, "Uknown module syntax: %s" % get_module_syntax())

    def test_inject_checksums(self):
        """Test for --inject-checksums"""
        topdir = os.path.dirname(os.path.abspath(__file__))
        toy_ec = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-gompi-1.3.12-test.eb')

        # checksums are injected in existing easyconfig, so test with a copy
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        copy_file(toy_ec, test_ec)

        # if existing checksums are found, --force is required
        args = [test_ec, '--inject-checksums']
        self.mock_stdout(True)
        self.mock_stderr(True)
        self.assertErrorRegex(EasyBuildError, "Found existing checksums", self.eb_main, args, raise_error=True)
        stdout = self.get_stdout().strip()
        stderr = self.get_stderr().strip()
        self.mock_stdout(False)
        self.mock_stderr(False)

        # SHA256 is default type of checksums used
        self.assertTrue("injecting sha256 checksums in" in stdout)
        self.assertEqual(stderr, '')

        args.append('--force')
        stdout, stderr = self._run_mock_eb(args, raise_error=True, strip=True)

        toy_source_sha256 = '44332000aa33b99ad1e00cbd1a7da769220d74647060a10e807b916d73ea27bc'
        toy_patch_sha256 = '45b5e3f9f495366830e1869bb2b8f4e7c28022739ce48d9f9ebb159b439823c5'
        bar_tar_gz_sha256 = 'f3676716b610545a4e8035087f5be0a0248adee0abb3930d3edb76d498ae91e7'
        bar_patch = 'bar-0.0_fix-silly-typo-in-printf-statement.patch'
        bar_patch_sha256 = '84db53592e882b5af077976257f9c7537ed971cb2059003fd4faa05d02cae0ab'
        patterns = [
            "^== injecting sha256 checksums in .*/test\.eb$",
            "^== fetching sources & patches for test\.eb\.\.\.$",
            "^== backup of easyconfig file saved to .*/test\.eb\.bak_[0-9]+\.\.\.$",
            "^== injecting sha256 checksums for sources & patches in test\.eb\.\.\.$",
            "^== \* toy-0.0\.tar\.gz: %s$" % toy_source_sha256,
            "^== \* toy-0\.0_fix-silly-typo-in-printf-statement\.patch: %s$" % toy_patch_sha256,
            "^== injecting sha256 checksums for extensions in test\.eb\.\.\.$",
            "^==  \* bar-0\.0\.tar\.gz: %s$" % bar_tar_gz_sha256,
            "^==  \* %s: %s$" % (bar_patch, bar_patch_sha256),
            "^==  \* barbar-0\.0\.tar\.gz: a33100d1837d6d54edff7d19f195056c4bd9a4c8d399e72feaf90f0216c4c91c$",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        warning_msg = "WARNING: Found existing checksums in test.eb, overwriting them (due to use of --force)..."
        self.assertEqual(stderr, warning_msg)

        ec_txt = read_file(test_ec)

        # some checks on 'raw' easyconfig contents
        # single-line checksum for barbar extension since there's only one
        self.assertTrue("'checksums': ['a33100d1837d6d54edff7d19f195056c4bd9a4c8d399e72feaf90f0216c4c91c']," in ec_txt)

        # single-line checksum entry for bar source tarball
        regex = re.compile("^[ ]*'%s',  # bar-0.0.tar.gz$" % bar_tar_gz_sha256, re.M)
        self.assertTrue(regex.search(ec_txt), "Pattern '%s' found in: %s" % (regex.pattern, ec_txt))

        # no single-line checksum entry for bar*.patch, since line would be > 120 chars
        regex = re.compile("^[ ]*# %s\n[ ]*'%s',$" % (bar_patch, bar_patch_sha256), re.M)
        self.assertTrue(regex.search(ec_txt), "Pattern '%s' found in: %s" % (regex.pattern, ec_txt))

        # name/version of toy should NOT be hardcoded in exts_list, 'name'/'version' parameters should be used
        self.assertTrue('    (name, version, {' in ec_txt)

        # make sure checksums are only there once...
        # exactly one definition of 'checksums' easyconfig parameter
        self.assertEqual(re.findall('^checksums', ec_txt, re.M), ['checksums'])
        # exactly three checksum specs for extensions, one list of checksums for each extension
        self.assertEqual(re.findall("[ ]*'checksums'", ec_txt, re.M), ["        'checksums'"] * 3)

        # there should be only one hit for 'source_urls', i.e. the one in exts_default_options
        self.assertEqual(len(re.findall('source_urls*.*$', ec_txt, re.M)), 1)

        # no parse errors for updated easyconfig file...
        ec = EasyConfigParser(test_ec).get_config_dict()
        self.assertEqual(ec['sources'], ['%(name)s-%(version)s.tar.gz'])
        self.assertEqual(ec['patches'], ['toy-0.0_fix-silly-typo-in-printf-statement.patch'])
        self.assertEqual(ec['checksums'], [toy_source_sha256, toy_patch_sha256])
        self.assertEqual(ec['exts_default_options'], {'source_urls': ['http://example.com/%(name)s']})
        self.assertEqual(ec['exts_list'][0], 'ls')
        self.assertEqual(ec['exts_list'][1], ('bar', '0.0', {
            'buildopts': " && gcc bar.c -o anotherbar",
            'checksums': [
                bar_tar_gz_sha256,
                bar_patch_sha256,
            ],
            'exts_filter': ("cat | grep '^bar$'", '%(name)s'),
            'patches': [bar_patch],
            'toy_ext_param': "mv anotherbar bar_bis",
            'unknowneasyconfigparameterthatshouldbeignored': 'foo',
        }))
        self.assertEqual(ec['exts_list'][2], ('barbar', '0.0', {
            'checksums': ['a33100d1837d6d54edff7d19f195056c4bd9a4c8d399e72feaf90f0216c4c91c'],
        }))

        # backup of easyconfig was created
        ec_backups = glob.glob(test_ec + '.bak_*')
        self.assertEqual(len(ec_backups), 1)
        self.assertEqual(read_file(toy_ec), read_file(ec_backups[0]))

        self.assertTrue("injecting sha256 checksums in" in stdout)
        self.assertEqual(stderr, warning_msg)

        remove_file(ec_backups[0])

        # if any checksums are present already, it doesn't matter if they're wrong (since they will be replaced)
        ectxt = read_file(test_ec)
        for chksum in ec['checksums'] + [c for e in ec['exts_list'][1:] for c in e[2]['checksums']]:
            ectxt = ectxt.replace(chksum, chksum[::-1])
        write_file(test_ec, ectxt)

        stdout, stderr = self._run_mock_eb(args, raise_error=True, strip=True)

        ec = EasyConfigParser(test_ec).get_config_dict()
        self.assertEqual(ec['checksums'], [toy_source_sha256, toy_patch_sha256])

        ec_backups = glob.glob(test_ec + '.bak_*')
        self.assertEqual(len(ec_backups), 1)
        remove_file(ec_backups[0])

        # also test injecting of MD5 checksums into easyconfig that doesn't include checksums already
        toy_ec = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec)

        # get rid of existing checksums
        regex = re.compile('^checksums(?:.|\n)*?\]\s*$', re.M)
        toy_ec_txt = regex.sub('', toy_ec_txt)
        self.assertFalse('checksums = ' in toy_ec_txt)

        write_file(test_ec, toy_ec_txt)
        args = [test_ec, '--inject-checksums=md5']

        stdout, stderr = self._run_mock_eb(args, raise_error=True, strip=True)

        patterns = [
            "^== injecting md5 checksums in .*/test\.eb$",
            "^== fetching sources & patches for test\.eb\.\.\.$",
            "^== backup of easyconfig file saved to .*/test\.eb\.bak_[0-9]+\.\.\.$",
            "^== injecting md5 checksums for sources & patches in test\.eb\.\.\.$",
            "^== \* toy-0.0\.tar\.gz: be662daa971a640e40be5c804d9d7d10$",
            "^== \* toy-0\.0_fix-silly-typo-in-printf-statement\.patch: e6785e1a721fc8bf79892e3ef41557c0$",
            "^== \* toy-extra\.txt: 3b0787b3bf36603ae1398c4a49097893$",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        self.assertEqual(stderr, '')

        # backup of easyconfig was created
        ec_backups = glob.glob(test_ec + '.bak_*')
        self.assertEqual(len(ec_backups), 1)
        self.assertEqual(toy_ec_txt, read_file(ec_backups[0]))

        # no parse errors for updated easyconfig file...
        ec = EasyConfigParser(test_ec).get_config_dict()
        checksums = [
            'be662daa971a640e40be5c804d9d7d10',
            'e6785e1a721fc8bf79892e3ef41557c0',
            '3b0787b3bf36603ae1398c4a49097893',
        ]
        self.assertEqual(ec['checksums'], checksums)

        args = ['--inject-checksums', test_ec]
        self.mock_stdout(True)
        self.mock_stderr(True)
        self.assertErrorRegex(SystemExit, '.*', self.eb_main, args, raise_error=True, raise_systemexit=True)
        stdout = self.get_stdout().strip()
        stderr = self.get_stderr().strip()
        self.mock_stdout(False)
        self.mock_stderr(False)

        self.assertEqual(stdout, '')
        self.assertTrue("option --inject-checksums: invalid choice" in stderr)

    def test_force_download(self):
        """Test --force-download"""
        topdir = os.path.dirname(os.path.abspath(__file__))
        toy_ec = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        toy_srcdir = os.path.join(topdir, 'sandbox', 'sources', 'toy')

        copy_file(toy_ec, self.test_prefix)
        toy_tar = 'toy-0.0.tar.gz'
        copy_file(os.path.join(toy_srcdir, toy_tar), os.path.join(self.test_prefix, 't', 'toy', toy_tar))

        toy_ec = os.path.join(self.test_prefix, os.path.basename(toy_ec))
        write_file(toy_ec, "\nsource_urls = ['file://%s']" % toy_srcdir, append=True)

        args = [
            toy_ec,
            '--force',
            '--force-download',
            '--sourcepath=%s' % self.test_prefix,
        ]
        stdout, stderr = self._run_mock_eb(args, do_build=True, raise_error=True, verbose=True, strip=True)
        self.assertEqual(stdout, '')
        regex = re.compile("^WARNING: Found file toy-0.0.tar.gz at .*, but re-downloading it anyway\.\.\.$")
        self.assertTrue(regex.match(stderr), "Pattern '%s' matches: %s" % (regex.pattern, stderr))

        # check that existing source tarball was backed up
        toy_tar_backups = glob.glob(os.path.join(self.test_prefix, 't', 'toy', '*.bak_*'))
        self.assertEqual(len(toy_tar_backups), 1)
        self.assertTrue(os.path.basename(toy_tar_backups[0]).startswith('toy-0.0.tar.gz.bak_'))

    def test_enforce_checksums(self):
        """Test effect of --enforce-checksums"""
        topdir = os.path.dirname(os.path.abspath(__file__))
        toy_ec = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-gompi-1.3.12-test.eb')
        test_ec = os.path.join(self.test_prefix, 'test.eb')

        args = [
            test_ec,
            '--stop=source',
            '--enforce-checksums',
        ]

        # checksum is missing for patch of 'bar' extension, so --enforce-checksums should result in an error
        copy_file(toy_ec, test_ec)
        error_pattern = "Missing checksum for bar-0.0[^ ]*\.patch"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.eb_main, args, do_build=True, raise_error=True)

        # get rid of checksums for extensions, should result in different error message
        # because of missing checksum for source of 'bar' extension
        regex = re.compile("^.*'checksums':.*$", re.M)
        test_ec_txt = regex.sub('', read_file(test_ec))
        self.assertFalse("'checksums':" in test_ec_txt)
        write_file(test_ec, test_ec_txt)
        error_pattern = "Missing checksum for bar-0\.0\.tar\.gz"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.eb_main, args, do_build=True, raise_error=True)

        # wipe both exts_list and checksums, so we can check whether missing checksum for main source is caught
        test_ec_txt = read_file(test_ec)
        for param in ['checksums', 'exts_list']:
            regex = re.compile('^%s(?:.|\n)*?\]\s*$' % param, re.M)
            test_ec_txt = regex.sub('', test_ec_txt)
            self.assertFalse('%s = ' % param in test_ec_txt)

        write_file(test_ec, test_ec_txt)
        error_pattern = "Missing checksum for toy-0.0.tar.gz"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.eb_main, args, do_build=True, raise_error=True)


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(CommandLineOptionsTest, sys.argv[1:])

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
