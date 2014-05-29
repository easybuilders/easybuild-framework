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
from easybuild.tools.environment import modify_env
from easybuild.tools.filetools import read_file, write_file
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

        # use temporary paths for build/install paths, make sure sources can be found
        buildpath = tempfile.mkdtemp()
        installpath = tempfile.mkdtemp()
        sourcepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox', 'sources')

        # use toy-0.0.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb')

        # check log message with --skip for existing module
        args = [
            eb_file,
            '--sourcepath=%s' % sourcepath,
            '--buildpath=%s' % buildpath,
            '--installpath=%s' % installpath,
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
            '--sourcepath=%s' % sourcepath,
            '--buildpath=%s' % buildpath,
            '--installpath=%s' % installpath,
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

        # cleanup
        shutil.rmtree(buildpath)
        shutil.rmtree(installpath)

    def test_job(self):
        """Test submitting build as a job."""

        # use gzip-1.4.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'gzip-1.4.eb')

        # check log message with --job
        for job_args in [  # options passed are reordered, so order here matters to make tests pass
                         ['--debug'],
                         ['--debug', '--stop=configure', '--try-software-name=foo'],
                        ]:

            # clear log file
            write_file(self.logfile, '')

            args = [
                    eb_file,
                    '--job',
                   ] + job_args
            outtxt = self.eb_main(args)

            job_msg = "INFO.* Command template for jobs: .* && eb %%\(spec\)s.* %s.*\n" % ' .*'.join(job_args)
            assertmsg = "Info log message with job command template when using --job (job_msg: %s, outtxt: %s)" % (job_msg, outtxt)
            self.assertTrue(re.search(job_msg, outtxt), assertmsg)

            modify_env(os.environ, self.orig_environ)
            tempfile.tempdir = None

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
        for tc in ["dummy", "goalf", "ictce"]:
            res = re.findall("^\s*%s: " % tc, outtxt, re.M)
            self.assertTrue(res, "Toolchain %s is included in list of known compiler toolchains" % tc)
            # every toolchain should only be mentioned once
            n = len(res)
            self.assertEqual(n, 1, "Toolchain %s is only mentioned once (count: %d)" % (tc, n))

        if os.path.exists(dummylogfn):
            os.remove(dummylogfn)

    def test_avail_lists(self):
        """Test listing available values of certain types."""

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        name_items = {
            'modules-tools': ['EnvironmentModulesC', 'Lmod'],
            'module-naming-schemes': ['EasyBuildModuleNamingScheme'],
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
                '--robot=%s' % os.path.join(os.path.dirname(__file__), 'easyconfigs'),
                '--unittest-file=%s' % self.logfile,
            ]
            outtxt = self.eb_main(args, logfile=dummylogfn)

            info_msg = r"Searching \(case-insensitive\) for 'toy-0.0' in"
            self.assertTrue(re.search(info_msg, outtxt), "Info message when searching for easyconfigs in '%s'" % outtxt)
            self.assertTrue(re.search('INFO CFGS\d+=', outtxt), "CFGS line message found in '%s'" % outtxt)
            for ec in ["toy-0.0.eb", "toy-0.0-multiple.eb"]:
                self.assertTrue(re.search(" \* \$CFGS\d+/*%s" % ec, outtxt), "Found easyconfig %s in '%s'" % (ec, outtxt))

            if os.path.exists(dummylogfn):
                os.remove(dummylogfn)

    def test_dry_run(self):
        """Test dry runs."""

        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        args = [
            os.path.join(os.path.dirname(__file__), 'easyconfigs', 'gzip-1.4-GCC-4.6.3.eb'),
            '--dry-run',
            '--robot=%s' % os.path.join(os.path.dirname(__file__), 'easyconfigs'),
            '--unittest-file=%s' % self.logfile,
        ]
        outtxt = self.eb_main(args, logfile=dummylogfn)

        info_msg = r"Dry run: printing build status of easyconfigs and dependencies"
        self.assertTrue(re.search(info_msg, outtxt, re.M), "Info message dry running in '%s'" % outtxt)
        ecs_mods = [
            ("gzip-1.4-GCC-4.6.3.eb", "gzip/1.4-GCC-4.6.3"),
            ("GCC-4.6.3.eb", "GCC/4.6.3"),
        ]
        for ec, mod in ecs_mods:
            regex = re.compile(r" \* \[.\] \S+%s \(module: %s\)" % (ec, mod), re.M)
            self.assertTrue(regex.search(outtxt), "Found match for pattern %s in '%s'" % (regex.pattern, outtxt))

        for dry_run_arg in ['-D', '--dry-run-short']:
            open(self.logfile, 'w').write('')
            args = [
                os.path.join(os.path.dirname(__file__), 'easyconfigs', 'gzip-1.4-GCC-4.6.3.eb'),
                dry_run_arg,
                '--robot=%s' % os.path.join(os.path.dirname(__file__), 'easyconfigs'),
                '--unittest-file=%s' % self.logfile,
            ]
            outtxt = self.eb_main(args, logfile=dummylogfn)

            info_msg = r"Dry run: printing build status of easyconfigs and dependencies"
            self.assertTrue(re.search(info_msg, outtxt, re.M), "Info message dry running in '%s'" % outtxt)
            self.assertTrue(re.search('CFGS=', outtxt), "CFGS line message found in '%s'" % outtxt)
            ecs_mods = [
                ("gzip-1.4-GCC-4.6.3.eb", "gzip/1.4-GCC-4.6.3"),
                ("GCC-4.6.3.eb", "GCC/4.6.3"),
            ]
            for ec, mod in ecs_mods:
                regex = re.compile(r" \* \[.\] \$CFGS\S+%s \(module: %s\)" % (ec, mod), re.M)
                self.assertTrue(regex.search(outtxt), "Found match for pattern %s in '%s'" % (regex.pattern, outtxt))

        if os.path.exists(dummylogfn):
            os.remove(dummylogfn)

    def test_from_pr(self):
        """Test fetching easyconfigs from a PR."""
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        args = [
            # PR for ictce/6.2.5, see https://github.com/hpcugent/easybuild-easyconfigs/pull/726/files
            '--from-pr=726',
            '--dry-run',
            '--robot=%s' % os.path.join(os.path.dirname(__file__), 'easyconfigs'),
            '--unittest-file=%s' % self.logfile,
            '--github-user=easybuild_test',  # a GitHub token should be available for this user
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
        # use temporary paths for build/install paths, make sure sources can be found
        buildpath = tempfile.mkdtemp()
        installpath = tempfile.mkdtemp()
        tmpdir = tempfile.mkdtemp()
        sourcepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox', 'sources')

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
            '--sourcepath=%s' % sourcepath,
            '--buildpath=%s' % buildpath,
            '--installpath=%s' % installpath,
            '--debug',
            '--force',
            '--modules-footer=%s' % modules_footer,
        ]
        self.eb_main(args, do_build=True)

        toy_module = os.path.join(installpath, 'modules', 'all', 'toy', '0.0')
        toy_module_txt = read_file(toy_module)
        footer_regex = re.compile(r'%s$' % module_footer_txt, re.M)
        msg = "modules footer '%s' is present in '%s'" % (module_footer_txt, toy_module_txt)
        self.assertTrue(footer_regex.search(toy_module_txt), msg)

        # cleanup
        shutil.rmtree(buildpath)
        shutil.rmtree(installpath)
        shutil.rmtree(tmpdir)
        os.remove(modules_footer)

    def test_recursive_module_unload(self):
        """Test generating recursively unloading modules."""

        # use temporary paths for build/install paths, make sure sources can be found
        buildpath = tempfile.mkdtemp()
        installpath = tempfile.mkdtemp()
        tmpdir = tempfile.mkdtemp()
        sourcepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox', 'sources')

        # use toy-0.0.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0-deps.eb')

        # check log message with --skip for existing module
        args = [
            eb_file,
            '--sourcepath=%s' % sourcepath,
            '--buildpath=%s' % buildpath,
            '--installpath=%s' % installpath,
            '--debug',
            '--force',
            '--recursive-module-unload',
        ]
        self.eb_main(args, do_build=True, verbose=True)

        toy_module = os.path.join(installpath, 'modules', 'all', 'toy', '0.0-deps')
        toy_module_txt = read_file(toy_module)
        is_loaded_regex = re.compile(r"if { !\[is-loaded gompi/1.3.12\] }", re.M)
        self.assertFalse(is_loaded_regex.search(toy_module_txt), "Recursive unloading is used: %s" % toy_module_txt)

        # cleanup
        shutil.rmtree(buildpath)
        shutil.rmtree(installpath)
        shutil.rmtree(tmpdir)

    def test_tmpdir(self):
        """Test setting temporary directory to use by EasyBuild."""

        # use temporary paths for build/install paths, make sure sources can be found
        buildpath = tempfile.mkdtemp()
        installpath = tempfile.mkdtemp()
        tmpdir = tempfile.mkdtemp()
        sourcepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox', 'sources')

        # use toy-0.0.eb easyconfig file that comes with the tests
        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb')

        # check log message with --skip for existing module
        args = [
            eb_file,
            '--sourcepath=%s' % sourcepath,
            '--buildpath=%s' % buildpath,
            '--installpath=%s' % installpath,
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
        shutil.rmtree(buildpath)
        shutil.rmtree(installpath)
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
            '--dry-run',
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
            '--ignore-osdeps',
            '--dry-run',
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

    def test_recursive_try(self):
        """Test whether recursive --try-X works."""
        ecs_path = os.path.join(os.path.dirname(__file__), 'easyconfigs')
        tweaked_toy_ec = os.path.join(self.test_buildpath, 'toy-0.0-tweaked.eb')
        shutil.copy2(os.path.join(ecs_path, 'toy-0.0.eb'), tweaked_toy_ec)
        f = open(tweaked_toy_ec, 'a')
        f.write("dependencies = [('gzip', '1.4')]")  # add fictious dependency
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
        outtxt = self.eb_main(args, do_build=True, verbose=True)

        # toolchain gompi/1.4.10 should be listed
        tc_regex = re.compile("^\s*\*\s*\[.\]\s*\S*%s/gompi-1.4.10.eb\s\(module: gompi/1.4.10\)\s*$" % ecs_path, re.M)
        self.assertTrue(tc_regex.search(outtxt), "Pattern %s found in %s" % (tc_regex.pattern, outtxt))

        # both toy and gzip dependency should be listed with gompi/1.4.10 toolchain
        for ec_name in ['gzip-1.4', 'toy-0.0']:
            ec = '%s-gompi-1.4.10.eb' % ec_name
            mod = '%s-gompi-1.4.10' % ec_name.replace('-', '/')
            mod_regex = re.compile("^\s*\*\s*\[.\]\s*\S*/easybuild-\S*/%s\s\(module: %s\)\s*$" % (ec, mod), re.M)
            self.assertTrue(mod_regex.search(outtxt), "Pattern %s found in %s" % (mod_regex.pattern, outtxt))

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

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(CommandLineOptionsTest)

if __name__ == '__main__':
    unittestmain()
