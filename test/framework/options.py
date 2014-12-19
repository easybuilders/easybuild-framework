# #
# Copyright 2013-2014 Ghent University
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
from test.framework.utilities import EnhancedTestCase
from unittest import TestLoader
from unittest import main as unittestmain

import easybuild.tools.build_log
from easybuild.framework.easyconfig import BUILD, CUSTOM, DEPENDENCIES, EXTENSIONS, FILEMANAGEMENT, LICENSE
from easybuild.framework.easyconfig import MANDATORY, MODULES, OTHER, TOOLCHAIN
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.environment import modify_env
from easybuild.tools.filetools import mkdir, read_file, write_file
from easybuild.tools.modules import modules_tool
from easybuild.tools.options import EasyBuildOptions
from easybuild.tools.version import VERSION
from vsc.utils import fancylogger

class CommandLineOptionsTest(EnhancedTestCase):
    """Testcases for command line options."""

    logfile = None

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

        self.assertTrue(re.search("-H, --help", outtxt), "Long documentation expanded in long help")
        self.assertTrue(re.search("show short help message and exit", outtxt), "Documentation included in long help")
        self.assertTrue(re.search("Software search and build options", outtxt), "Not all option groups included in short help (1)")
        self.assertTrue(re.search("Regression test options", outtxt), "Not all option groups included in short help (2)")

    def test_no_args(self):
        """Test using no arguments."""

        outtxt = self.eb_main([])

        error_msg = "ERROR .* Please provide one or multiple easyconfig files,"
        error_msg += " or use software build options to make EasyBuild search for easyconfigs"
        self.assertTrue(re.search(error_msg, outtxt), "Error message when eb is run without arguments")

    def test_debug(self):
        """Test enabling debug logging."""

        for debug_arg in ['-d', '--debug']:
            args = [
                    '--software-name=somethingrandom',
                    debug_arg,
                   ]
            outtxt = self.eb_main(args)

            for log_msg_type in ['DEBUG', 'INFO', 'ERROR']:
                res = re.search(' %s ' % log_msg_type, outtxt)
                self.assertTrue(res, "%s log messages are included when using %s: %s" % (log_msg_type, debug_arg, outtxt))

            modify_env(os.environ, self.orig_environ)
            tempfile.tempdir = None

    def test_info(self):
        """Test enabling info logging."""

        for info_arg in ['--info']:
            args = [
                    '--software-name=somethingrandom',
                    info_arg,
                   ]
            outtxt = self.eb_main(args)

            for log_msg_type in ['INFO', 'ERROR']:
                res = re.search(' %s ' % log_msg_type, outtxt)
                self.assertTrue(res, "%s log messages are included when using %s ( out: %s)" % (log_msg_type, info_arg, outtxt))

            for log_msg_type in ['DEBUG']:
                res = re.search(' %s ' % log_msg_type, outtxt)
                self.assertTrue(not res, "%s log messages are *not* included when using %s" % (log_msg_type, info_arg))

            modify_env(os.environ, self.orig_environ)
            tempfile.tempdir = None

    def test_quiet(self):
        """Test enabling quiet logging (errors only)."""

        for quiet_arg in ['--quiet']:
            args = [
                    '--software-name=somethingrandom',
                    quiet_arg,
                   ]
            outtxt = self.eb_main(args)

            for log_msg_type in ['ERROR']:
                res = re.search(' %s ' % log_msg_type, outtxt)
                self.assertTrue(res, "%s log messages are included when using %s (outtxt: %s)" % (log_msg_type, quiet_arg, outtxt))

            for log_msg_type in ['DEBUG', 'INFO']:
                res = re.search(' %s ' % log_msg_type, outtxt)
                self.assertTrue(not res, "%s log messages are *not* included when using %s (outtxt: %s)" % (log_msg_type, quiet_arg, outtxt))

            modify_env(os.environ, self.orig_environ)
            tempfile.tempdir = None

    def test_force(self):
        """Test forcing installation even if the module is already available."""

        # use GCC-4.6.3.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'GCC-4.6.3.eb')

        # check log message without --force
        args = [
                eb_file,
                '--debug',
               ]
        outtxt, error_thrown = self.eb_main(args, return_error=True)

        self.assertTrue(not error_thrown, "No error is thrown if software is already installed (error_thrown: %s)" % error_thrown)

        already_msg = "GCC/4.6.3 is already installed"
        self.assertTrue(re.search(already_msg, outtxt), "Already installed message without --force, outtxt: %s" % outtxt)

        # clear log file, clean up environment
        write_file(self.logfile, '')
        modify_env(os.environ, self.orig_environ)
        tempfile.tempdir = None

        # check that --force works
        args = [
                eb_file,
                '--force',
                '--debug',
               ]
        outtxt = self.eb_main(args)

        self.assertTrue(not re.search(already_msg, outtxt), "Already installed message not there with --force")

    def test_skip(self):
        """Test skipping installation of module (--skip, -k)."""

        # use toy-0.0.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb')

        # check log message with --skip for existing module
        args = [
            eb_file,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--force',
            '--debug',
        ]
        self.eb_main(args, do_build=True)
        modules_tool().purge()

        args.append('--skip')
        outtxt = self.eb_main(args, do_build=True, verbose=True)

        found_msg = "Module toy/0.0 found.\n[^\n]+Going to skip actual main build"
        found = re.search(found_msg, outtxt, re.M)
        self.assertTrue(found, "Module found message present with --skip, outtxt: %s" % outtxt)

        # cleanup for next test
        write_file(self.logfile, '')
        os.chdir(self.cwd)
        modules_tool().purge()
        # reinitialize modules tool with original $MODULEPATH, to avoid problems with future tests
        modify_env(os.environ, self.orig_environ)
        os.environ['MODULEPATH'] = ''
        modules_tool()
        tempfile.tempdir = None

        # check log message with --skip for non-existing module
        args = [
            eb_file,
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

        modules_tool().purge()
        # reinitialize modules tool with original $MODULEPATH, to avoid problems with future tests
        modify_env(os.environ, self.orig_environ)
        modules_tool()

    def test_job(self):
        """Test submitting build as a job."""

        # use gzip-1.4.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'gzip-1.4.eb')

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

            modify_env(os.environ, self.orig_environ)
            tempfile.tempdir = None

        # options passed are reordered, so order here matters to make tests pass
        check_args(['--debug'])
        check_args(['--debug', '--stop=configure', '--try-software-name=foo'])
        check_args(['--debug', '--robot-paths=/tmp/foo:/tmp/bar'])
        # --robot has preference over --robot-paths, --robot is not passed down
        check_args(['--debug', '--robot-paths=/tmp/foo', '--robot=/tmp/bar'], passed_args=['--debug', '--robot-paths=/tmp/bar:/tmp/foo'])

    # 'zzz' prefix in the test name is intentional to make this test run last,
    # since it fiddles with the logging infrastructure which may break things
    def test_zzz_logtostdout(self):
        """Testing redirecting log to stdout."""

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        for stdout_arg in ['--logtostdout', '-l']:

            _stdout = sys.stdout

            fd, fn = tempfile.mkstemp()
            fh = os.fdopen(fd, 'w')
            sys.stdout = fh

            args = [
                    '--software-name=somethingrandom',
                    '--robot', '.',
                    '--debug',
                    stdout_arg,
                   ]
            self.eb_main(args, logfile=dummylogfn)

            # make sure we restore
            sys.stdout.flush()
            sys.stdout = _stdout
            fancylogger.logToScreen(enable=False, stdout=True)

            outtxt = read_file(fn)

            self.assertTrue(len(outtxt) > 100, "Log messages are printed to stdout when %s is used (outtxt: %s)" % (stdout_arg, outtxt))

            # cleanup
            os.remove(fn)
            modify_env(os.environ, self.orig_environ)
            tempfile.tempdir = None

        if os.path.exists(dummylogfn):
            os.remove(dummylogfn)
        fancylogger.logToFile(self.logfile)

    def test_avail_easyconfig_params(self):
        """Test listing available easyconfig parameters."""

        def run_test(custom=None, extra_params=[]):
            """Inner function to run actual test in current setting."""

            fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
            os.close(fd)

            for avail_arg in [
                              '-a',
                              '--avail-easyconfig-params',
                             ]:

                # clear log
                write_file(self.logfile, '')

                args = [
                    avail_arg,
                    '--unittest-file=%s' % self.logfile,
                ]
                if custom is not None:
                    args.extend(['-e', custom])

                outtxt = self.eb_main(args, logfile=dummylogfn, verbose=True)

                # check whether all parameter types are listed
                par_types = [BUILD, DEPENDENCIES, EXTENSIONS, FILEMANAGEMENT,
                             LICENSE, MANDATORY, MODULES, OTHER, TOOLCHAIN]
                if custom is not None:
                    par_types.append(CUSTOM)

                for param_type in [x[1] for x in par_types]:
                    self.assertTrue(re.search("%s\n%s" % (param_type.upper(), '-' * len(param_type)), outtxt),
                                    "Parameter type %s is featured in output of eb %s (args: %s): %s" %
                                    (param_type, avail_arg, args, outtxt))

                # check a couple of easyconfig parameters
                for param in ["name", "version", "toolchain", "versionsuffix", "buildopts", "sources", "start_dir",
                              "dependencies", "group", "exts_list", "moduleclass", "buildstats"] + extra_params:
                    self.assertTrue(re.search("%s(?:\(\*\))?:\s*\w.*" % param, outtxt),
                                    "Parameter %s is listed with help in output of eb %s (args: %s): %s" %
                                    (param, avail_arg, args, outtxt)
                                    )

                modify_env(os.environ, self.orig_environ)
                tempfile.tempdir = None

            if os.path.exists(dummylogfn):
                os.remove(dummylogfn)

        run_test()
        run_test(custom='EB_foo', extra_params=['foo_extra1', 'foo_extra2'])
        run_test(custom='bar', extra_params=['bar_extra1', 'bar_extra2'])
        run_test(custom='EB_foofoo', extra_params=['foofoo_extra1', 'foofoo_extra2'])

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
        self.assertTrue(re.search(info_msg, outtxt), "Info message with list of known compiler toolchains")
        # toolchain elements should be in alphabetical order
        tcs = {
            'dummy': [],
            'goalf': ['ATLAS', 'BLACS', 'FFTW', 'GCC', 'OpenMPI', 'ScaLAPACK'],
            'ictce': ['icc', 'ifort', 'imkl', 'impi'],
        }
        for tc, tcelems in tcs.items():
            res = re.findall("^\s*%s: .*" % tc, outtxt, re.M)
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
            'module-naming-schemes': ['EasyBuildMNS', 'HierarchicalMNS'],
        }
        for (name, items) in name_items.items():
            args = [
                    '--avail-%s' % name,
                    '--unittest-file=%s' % self.logfile,
                   ]
            outtxt = self.eb_main(args, logfile=dummylogfn)

            words = name.replace('-', ' ')
            info_msg = r"INFO List of supported %s:" % words
            self.assertTrue(re.search(info_msg, outtxt), "Info message with list of available %s" % words)
            for item in items:
                res = re.findall("^\s*%s" % item, outtxt, re.M)
                self.assertTrue(res, "%s is included in list of available %s" % (item, words))
                # every item should only be mentioned once
                n = len(res)
                self.assertEqual(n, 1, "%s is only mentioned once (count: %d)" % (item, n))

            modify_env(os.environ, self.orig_environ)
            tempfile.tempdir = None

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
        shutil.copytree(test_ecs_dir, os.path.join(tmpdir, 'easybuild', 'easyconfigs'))

        orig_sys_path = sys.path[:]
        sys.path.insert(0, tmpdir)  # prepend to give it preference over possible other installed easyconfigs pkgs

        args = [
            '--avail-cfgfile-constants',
            '--unittest-file=%s' % self.logfile,
        ]
        outtxt = self.eb_main(args, logfile=dummylogfn)
        cfgfile_constants = {
            'DEFAULT_ROBOT_PATHS': os.path.join(tmpdir, 'easybuild', 'easyconfigs'),
        }
        for cst_name, cst_value in cfgfile_constants.items():
            cst_regex = re.compile("^\*\s%s:\s.*\s\[value: .*%s.*\]" % (cst_name, cst_value), re.M)
            tup = (cst_regex.pattern, outtxt)
            self.assertTrue(cst_regex.search(outtxt), "Pattern '%s' in --avail-cfgfile_constants output: %s" % tup)

        if os.path.exists(dummylogfn):
            os.remove(dummylogfn)
        sys.path[:] = orig_sys_path

    def test_list_easyblocks(self):
        """Test listing easyblock hierarchy."""

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # adjust PYTHONPATH such that test easyblocks are found

        import easybuild
        eb_blocks_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'sandbox'))
        if not eb_blocks_path in sys.path:
            sys.path.append(eb_blocks_path)
            easybuild = reload(easybuild)

        import easybuild.easyblocks
        reload(easybuild.easyblocks)
        reload(easybuild.tools.module_naming_scheme)  # required to run options unit tests stand-alone

        # simple view
        for list_arg in ['--list-easyblocks', '--list-easyblocks=simple']:

            # clear log
            write_file(self.logfile, '')

            args = [
                    list_arg,
                    '--unittest-file=%s' % self.logfile,
                   ]
            outtxt = self.eb_main(args, logfile=dummylogfn)

            for pat in [
                        r"EasyBlock\n",
                        r"|--\s+EB_foo\n|\s+|--\s+EB_foofoo\n",
                        r"|--\s+bar\n",
                       ]:

                self.assertTrue(re.search(pat, outtxt), "Pattern '%s' is found in output of --list-easyblocks: %s" % (pat, outtxt))

            modify_env(os.environ, self.orig_environ)
            tempfile.tempdir = None

        # clear log
        write_file(self.logfile, '')

        # detailed view
        args = [
                '--list-easyblocks=detailed',
                '--unittest-file=%s' % self.logfile,
               ]
        outtxt = self.eb_main(args, logfile=dummylogfn)

        for pat in [
                    r"EasyBlock\s+\(easybuild.framework.easyblock\)\n",
                    r"|--\s+EB_foo\s+\(easybuild.easyblocks.foo\)\n|\s+|--\s+EB_foofoo\s+\(easybuild.easyblocks.foofoo\)\n",
                    r"|--\s+bar\s+\(easybuild.easyblocks.generic.bar\)\n",
                   ]:

            self.assertTrue(re.search(pat, outtxt), "Pattern '%s' is found in output of --list-easyblocks: %s" % (pat, outtxt))

        if os.path.exists(dummylogfn):
            os.remove(dummylogfn)

    def test_search(self):
        """Test searching for easyconfigs."""

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        args = [
            '--search=gzip',
            '--robot=%s' % os.path.join(os.path.dirname(__file__), 'easyconfigs'),
            '--unittest-file=%s' % self.logfile,
        ]
        outtxt = self.eb_main(args, logfile=dummylogfn)

        info_msg = r"Searching \(case-insensitive\) for 'gzip' in"
        self.assertTrue(re.search(info_msg, outtxt), "Info message when searching for easyconfigs in '%s'" % outtxt)
        for ec in ["gzip-1.4.eb", "gzip-1.4-GCC-4.6.3.eb"]:
            self.assertTrue(re.search(" \* \S*%s$" % ec, outtxt, re.M), "Found easyconfig %s in '%s'" % (ec, outtxt))

        if os.path.exists(dummylogfn):
            os.remove(dummylogfn)

        for search_arg in ['-S', '--search-short']:
            open(self.logfile, 'w').write('')
            args = [
                search_arg,
                'toy-0.0',
                '-r',
                os.path.join(os.path.dirname(__file__), 'easyconfigs'),
                '--unittest-file=%s' % self.logfile,
            ]
            outtxt = self.eb_main(args, logfile=dummylogfn, raise_error=True, verbose=True)

            info_msg = r"Searching \(case-insensitive\) for 'toy-0.0' in"
            self.assertTrue(re.search(info_msg, outtxt), "Info message when searching for easyconfigs in '%s'" % outtxt)
            self.assertTrue(re.search('INFO CFGS\d+=', outtxt), "CFGS line message found in '%s'" % outtxt)
            for ec in ["toy-0.0.eb", "toy-0.0-multiple.eb"]:
                self.assertTrue(re.search(" \* \$CFGS\d+/*%s" % ec, outtxt), "Found easyconfig %s in '%s'" % (ec, outtxt))

            if os.path.exists(dummylogfn):
                os.remove(dummylogfn)

    def test_dry_run(self):
        """Test dry run (long format)."""
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        args = [
            os.path.join(os.path.dirname(__file__), 'easyconfigs', 'gzip-1.4-GCC-4.6.3.eb'),
            '--dry-run',  # implies enabling dependency resolution
            '--unittest-file=%s' % self.logfile,
            '--robot-paths=%s' % os.path.join(os.path.dirname(__file__), 'easyconfigs'),
        ]
        outtxt = self.eb_main(args, logfile=dummylogfn)

        info_msg = r"Dry run: printing build status of easyconfigs and dependencies"
        self.assertTrue(re.search(info_msg, outtxt, re.M), "Info message dry running in '%s'" % outtxt)
        ecs_mods = [
            ("gzip-1.4-GCC-4.6.3.eb", "gzip/1.4-GCC-4.6.3", ' '),
            ("GCC-4.6.3.eb", "GCC/4.6.3", 'x'),
        ]
        for ec, mod, mark in ecs_mods:
            regex = re.compile(r" \* \[%s\] \S+%s \(module: %s\)" % (mark, ec, mod), re.M)
            self.assertTrue(regex.search(outtxt), "Found match for pattern %s in '%s'" % (regex.pattern, outtxt))

    def test_dry_run_short(self):
        """Test dry run (short format)."""
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # copy test easyconfigs to easybuild/easyconfigs subdirectory of temp directory
        # to check whether easyconfigs install path is auto-included in robot path
        tmpdir = tempfile.mkdtemp(prefix='easybuild-easyconfigs-pkg-install-path')
        mkdir(os.path.join(tmpdir, 'easybuild'), parents=True)

        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        shutil.copytree(test_ecs_dir, os.path.join(tmpdir, 'easybuild', 'easyconfigs'))

        orig_sys_path = sys.path[:]
        sys.path.insert(0, tmpdir)  # prepend to give it preference over possible other installed easyconfigs pkgs

        for dry_run_arg in ['-D', '--dry-run-short']:
            open(self.logfile, 'w').write('')
            args = [
                os.path.join(tmpdir, 'easybuild', 'easyconfigs', 'gzip-1.4-GCC-4.6.3.eb'),
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
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        eb_file1 = os.path.join(test_ecs_dir, 'FFTW-3.3.3-gompi-1.4.10.eb')
        eb_file2 = os.path.join(test_ecs_dir, 'ScaLAPACK-2.0.2-gompi-1.4.10-OpenBLAS-0.2.6-LAPACK-3.4.2.eb')

        # check log message with --skip for existing module
        args = [
            eb_file1,
            eb_file2,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--debug',
            '--force',
            '--robot=%s' % test_ecs_dir,
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
            # OpenBLAS dependency is there, but not listed => 'x'
            ("OpenBLAS-0.2.6-gompi-1.3.12-LAPACK-3.4.2.eb", "OpenBLAS/0.2.6-gompi-1.3.12-LAPACK-3.4.2", 'x'),
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

        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        args = [
            os.path.join(test_ecs, 'gzip-1.5-goolf-1.4.10.eb'),
            os.path.join(test_ecs, 'OpenMPI-1.6.4-GCC-4.7.2.eb'),
            '--dry-run',
            '--unittest-file=%s' % self.logfile,
            '--module-naming-scheme=HierarchicalMNS',
            '--ignore-osdeps',
            '--force',
            '--debug',
            '--robot-paths=%s' % os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs'),
        ]
        outtxt = self.eb_main(args, logfile=dummylogfn, verbose=True, raise_error=True)

        ecs_mods = [
            # easyconfig, module subdir, (short) module name
            ("GCC-4.7.2.eb", "Core", "GCC/4.7.2", 'x'),  # already present but not listed, so 'x'
            ("hwloc-1.6.2-GCC-4.7.2.eb", "Compiler/GCC/4.7.2", "hwloc/1.6.2", 'x'),
            ("OpenMPI-1.6.4-GCC-4.7.2.eb", "Compiler/GCC/4.7.2", "OpenMPI/1.6.4", 'F'),  # already present and listed, so 'F'
            ("gompi-1.4.10.eb", "Core", "gompi/1.4.10", 'x'),
            ("OpenBLAS-0.2.6-gompi-1.4.10-LAPACK-3.4.2.eb", "MPI/GCC/4.7.2/OpenMPI/1.6.4",
             "OpenBLAS/0.2.6-LAPACK-3.4.2", 'x'),
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

    def test_from_pr(self):
        """Test fetching easyconfigs from a PR."""
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        tmpdir = tempfile.mkdtemp()
        args = [
            # PR for ictce/6.2.5, see https://github.com/hpcugent/easybuild-easyconfigs/pull/726/files
            '--from-pr=726',
            '--dry-run',
            # an argument must be specified to --robot, since easybuild-easyconfigs may not be installed
            '--robot=%s' % os.path.join(os.path.dirname(__file__), 'easyconfigs'),
            '--unittest-file=%s' % self.logfile,
            '--github-user=easybuild_test',  # a GitHub token should be available for this user
            '--tmpdir=%s' % tmpdir,
        ]
        outtxt = self.eb_main(args, logfile=dummylogfn, verbose=True)

        modules = [
            'icc/2013_sp1.2.144',
            'ifort/2013_sp1.2.144',
            'impi/4.1.3.049',
            'imkl/11.1.2.144',
            'ictce/6.2.5',
            'gzip/1.6-ictce-6.2.5',
        ]
        for module in modules:
            ec_fn = "%s.eb" % '-'.join(module.split('/'))
            regex = re.compile(r"^ \* \[.\] .*/%s \(module: %s\)$" % (ec_fn, module), re.M)
            self.assertTrue(regex.search(outtxt), "Found pattern %s in %s" % (regex.pattern, outtxt))

        pr_tmpdir = os.path.join(tmpdir, 'easybuild-\S{6}', 'files_pr726')
        regex = re.compile("Prepended list of robot search paths with %s:" % pr_tmpdir, re.M)
        self.assertTrue(regex.search(outtxt), "Found pattern %s in %s" % (regex.pattern, outtxt))

        shutil.rmtree(tmpdir)

    def test_no_such_software(self):
        """Test using no arguments."""

        args = [
                '--software-name=nosuchsoftware',
                '--robot=.',
                '--debug',
               ]
        outtxt = self.eb_main(args)

        # error message when template is not found
        error_msg1 = "ERROR .* No easyconfig files found for software nosuchsoftware, and no templates available. I'm all out of ideas."
        # error message when template is found
        error_msg2 = "ERROR .* Unable to find an easyconfig for the given specifications"
        msg = "Error message when eb can't find software with specified name (outtxt: %s)" % outtxt
        self.assertTrue(re.search(error_msg1, outtxt) or re.search(error_msg2, outtxt), msg)

    def test_footer(self):
        """Test specifying a module footer."""

        # create file containing modules footer
        module_footer_txt = '\n'.join([
            "# test footer",
            "setenv SITE_SPECIFIC_ENV_VAR foobar",
        ])
        fd, modules_footer = tempfile.mkstemp(prefix='modules-footer-')
        os.close(fd)
        f = open(modules_footer, 'w')
        f.write(module_footer_txt)
        f.close()

        # use toy-0.0.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb')

        # check log message with --skip for existing module
        args = [
            eb_file,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--debug',
            '--force',
            '--modules-footer=%s' % modules_footer,
        ]
        self.eb_main(args, do_build=True)

        toy_module = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0')
        toy_module_txt = read_file(toy_module)
        footer_regex = re.compile(r'%s$' % module_footer_txt, re.M)
        msg = "modules footer '%s' is present in '%s'" % (module_footer_txt, toy_module_txt)
        self.assertTrue(footer_regex.search(toy_module_txt), msg)

        # cleanup
        os.remove(modules_footer)

    def test_recursive_module_unload(self):
        """Test generating recursively unloading modules."""

        # use toy-0.0.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0-deps.eb')

        # check log message with --skip for existing module
        args = [
            eb_file,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--debug',
            '--force',
            '--recursive-module-unload',
        ]
        self.eb_main(args, do_build=True, verbose=True)

        toy_module = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0-deps')
        toy_module_txt = read_file(toy_module)
        is_loaded_regex = re.compile(r"if { !\[is-loaded gompi/1.3.12\] }", re.M)
        self.assertFalse(is_loaded_regex.search(toy_module_txt), "Recursive unloading is used: %s" % toy_module_txt)

    def test_tmpdir(self):
        """Test setting temporary directory to use by EasyBuild."""

        # use temporary paths for build/install paths, make sure sources can be found
        tmpdir = tempfile.mkdtemp()

        # use toy-0.0.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb')

        # check log message with --skip for existing module
        args = [
            eb_file,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--debug',
            '--tmpdir=%s' % tmpdir,
        ]
        outtxt = self.eb_main(args, do_build=True)

        tmpdir_msg = r"Using %s\S+ as temporary directory" % os.path.join(tmpdir, 'easybuild-')
        found = re.search(tmpdir_msg, outtxt, re.M)
        self.assertTrue(found, "Log message for tmpdir found in outtxt: %s" % outtxt)

        for var in ['TMPDIR', 'TEMP', 'TMP']:
            self.assertTrue(os.environ[var].startswith(os.path.join(tmpdir, 'easybuild-')))
        self.assertTrue(tempfile.gettempdir().startswith(os.path.join(tmpdir, 'easybuild-')))
        tempfile_tmpdir = tempfile.mkdtemp()
        self.assertTrue(tempfile_tmpdir.startswith(os.path.join(tmpdir, 'easybuild-')))
        fd, tempfile_tmpfile = tempfile.mkstemp()
        self.assertTrue(tempfile_tmpfile.startswith(os.path.join(tmpdir, 'easybuild-')))

        # cleanup
        os.close(fd)
        shutil.rmtree(tmpdir)

    def test_ignore_osdeps(self):
        """Test ignoring of listed OS dependencies."""
        txt = '\n'.join([
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
        orig_value = easybuild.tools.build_log.CURRENT_VERSION

        # make sure it's off by default
        self.assertEqual(orig_value, VERSION)

        log = fancylogger.getLogger()

        # force it to lower version using 0.x, which should no result in any raised error (only deprecation logging)
        topt = EasyBuildOptions(
            go_args=['--deprecated=0.%s' % orig_value],
        )
        try:
            log.deprecated('x', str(orig_value))
        except easybuild.tools.build_log.EasyBuildError, err:
            self.assertTrue(False, 'Deprecated logging should work')

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

        # force higher version by prefixing it with 1, which should result in deprecation
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

        ec_file = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'toy-0.0.eb')

        # keep track of original module definition so we can restore it
        orig_module = os.environ.get('module', None)

        # check whether mismatch between 'module' function and selected modules tool is detected
        os.environ['module'] = "() {  eval `/Users/kehoste/Modules/$MODULE_VERSION/bin/modulecmd bash $*`\n}"
        args = [
            ec_file,
            '--modules-tool=MockModulesTool',
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
        ecs_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs')
        ec_file = os.path.join(ecs_path, 'toy-0.0.eb')
        args = [
            ec_file,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--dry-run',
            '--robot=%s' % ecs_path,
        ]

        test_cases = [
            ([], 'toy/0.0'),
            (['--try-software=foo,1.2.3', '--try-toolchain=gompi,1.4.10'], 'foo/1.2.3-gompi-1.4.10'),
            (['--try-toolchain-name=gompi', '--try-toolchain-version=1.4.10'], 'toy/0.0-gompi-1.4.10'),
            (['--try-software-name=foo', '--try-software-version=1.2.3'], 'foo/1.2.3'),
            (['--try-toolchain-name=gompi', '--try-toolchain-version=1.4.10'], 'toy/0.0-gompi-1.4.10'),
            (['--try-software-version=1.2.3', '--try-toolchain=gompi,1.4.10'], 'toy/1.2.3-gompi-1.4.10'),
            (['--try-amend=versionsuffix=-test'], 'toy/0.0-test'),
            # only --try causes other build specs to be included too
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
        ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        tweaked_toy_ec = os.path.join(self.test_buildpath, 'toy-0.0-tweaked.eb')
        shutil.copy2(os.path.join(ecs_path, 'toy-0.0.eb'), tweaked_toy_ec)
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

            # toolchain gompi/1.4.10 should be listed (but not present yet)
            if extra_args:
                mark = 'x'
            else:
                mark = ' '
            tc_regex = re.compile("^ \* \[%s\] %s/gompi-1.4.10.eb \(module: .*gompi/1.4.10\)$" % (mark, ecs_path), re.M)
            self.assertTrue(tc_regex.search(outtxt), "Pattern %s found in %s" % (tc_regex.pattern, outtxt))

            # both toy and gzip dependency should be listed with gompi/1.4.10 toolchain
            for ec_name in ['gzip-1.4', 'toy-0.0']:
                ec = '%s-gompi-1.4.10.eb' % ec_name
                if extra_args:
                    mod = ec_name.replace('-', '/')
                else:
                    mod = '%s-gompi-1.4.10' % ec_name.replace('-', '/')
                mod_regex = re.compile("^ \* \[ \] \S+/easybuild-\S+/%s \(module: .*%s\)$" % (ec, mod), re.M)
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
        toy_ec = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb')
        toy_buildpath = os.path.join(self.test_buildpath, 'toy', '0.0', 'dummy-dummy')

        args = [
            toy_ec,
            '--force',
        ]
        self.eb_main(args, do_build=True, verbose=True)

        # make sure build directory is properly cleaned up after a successful build (default behavior)
        self.assertFalse(os.path.exists(toy_buildpath), "Build dir %s removed after succesful build" % toy_buildpath)
        # make sure --disable-cleanup-builddir works
        args.append('--disable-cleanup-builddir')
        self.eb_main(args, do_build=True, verbose=True)
        self.assertTrue(os.path.exists(toy_buildpath), "Build dir %s is retained when requested" % toy_buildpath)
        shutil.rmtree(toy_buildpath)

        # make sure build dir stays in case of failed build
        args = [
            toy_ec,
            '--force',
            '--try-amend=premakeopts=nosuchcommand &&',
        ]
        self.eb_main(args, do_build=True)
        self.assertTrue(os.path.exists(toy_buildpath), "Build dir %s is retained after failed build" % toy_buildpath)

    def test_filter_deps(self):
        """Test use of --filter-deps."""
        test_dir = os.path.dirname(os.path.abspath(__file__))
        ec_file = os.path.join(test_dir, 'easyconfigs', 'goolf-1.4.10.eb')
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
    
    def test_test_report_env_filter(self):
        """Test use of --test-report-env-filter."""

        def toy(extra_args=None):
            """Build & install toy, return contents of test report."""
            eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb')
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
        filter_arg_regex = re.compile(filter_arg.replace('*', '\*'))
        tup = (filter_arg_regex.pattern, test_report_txt)
        self.assertTrue(filter_arg_regex.search(test_report_txt), "%s in %s" % tup)

    def test_robot(self):
        """Test --robot and --robot-paths command line options."""
        test_ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        eb_file = os.path.join(test_ecs_path, 'gzip-1.4-GCC-4.6.3.eb')  # includes 'toy/.0.0-deps' as a dependency

        # hide test modules
        self.reset_modulepath([])

        # dependency resolution is disabled by default, even if required paths are available
        args = [
            eb_file,
            '--robot-paths=%s' % test_ecs_path,
        ]
        error_regex ='no module .* found for dependency'
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
        shutil.copytree(test_ecs_path, os.path.join(tmpdir, 'easybuild', 'easyconfigs'))

        # prepend path to test easyconfigs into Python search path, so it gets picked up as --robot-paths default
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

        for ec in ['GCC-4.6.3.eb', 'ictce-4.1.13.eb', 'toy-0.0-deps.eb', 'gzip-1.4-GCC-4.6.3.eb']:
            ec_regex = re.compile('^\s\*\s\[[xF ]\]\s%s' % os.path.join(test_ecs_path, ec), re.M)
            self.assertTrue(ec_regex.search(outtxt), "Pattern %s found in %s" % (ec_regex.pattern, outtxt))


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(CommandLineOptionsTest)

if __name__ == '__main__':
    unittestmain()
