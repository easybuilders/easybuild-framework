# -*- coding: utf-8 -*-
##
# Copyright 2013-2025 Ghent University
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
Toy build unit test

@author: Kenneth Hoste (Ghent University)
@author: Damian Alvarez (Forschungszentrum Juelich GmbH)
"""
import glob
import grp
import os
import re
import shutil
import signal
import stat
import sys
import tempfile
import textwrap
import filecmp
from easybuild.tools import LooseVersion
from importlib import reload
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, cleanup
from test.framework.package import mock_fpm
from unittest import TextTestRunner

import easybuild.tools.hooks  # so we can reset cached hooks
import easybuild.tools.module_naming_scheme  # required to dynamically load test module naming scheme(s)
from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.framework.easyconfig.parser import EasyConfigParser
from easybuild.main import main_with_hooks
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import get_module_syntax, get_repositorypath, update_build_option
from easybuild.tools.environment import setvar
from easybuild.tools.filetools import adjust_permissions, change_dir, copy_file, mkdir, move_file
from easybuild.tools.filetools import read_file, remove_dir, remove_file, which, write_file
from easybuild.tools.module_generator import ModuleGeneratorTcl
from easybuild.tools.modules import EnvironmentModules, Lmod
from easybuild.tools.run import run_shell_cmd
from easybuild.tools.utilities import nub
from easybuild.tools.systemtools import get_shared_lib_ext
from easybuild.tools.version import VERSION as EASYBUILD_VERSION


class ToyBuildTest(EnhancedTestCase):
    """Toy build unit test."""

    def setUp(self):
        """Test setup."""
        super().setUp()

        fd, self.dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # clear log
        write_file(self.logfile, '')

    def tearDown(self):
        """Cleanup."""

        # kick out any paths for included easyblocks from sys.path,
        # to avoid infected any other tests
        for path in sys.path[:]:
            if '/included-easyblocks' in path:
                sys.path.remove(path)

        # reload toy easyblock (and generic toy_extension easyblock that imports it) after cleaning up sys.path,
        # to avoid trouble in other tests due to included toy easyblock that is cached somewhere
        # (despite the cleanup in sys.modules);
        # important for tests that include a customised copy of the toy easyblock
        # (like test_toy_build_enhanced_sanity_check)
        import easybuild.easyblocks.toy
        reload(easybuild.easyblocks.toy)
        import easybuild.easyblocks.toytoy
        reload(easybuild.easyblocks.toytoy)
        import easybuild.easyblocks.generic.toy_extension
        reload(easybuild.easyblocks.generic.toy_extension)

        del sys.modules['easybuild.easyblocks.toy']
        del sys.modules['easybuild.easyblocks.toytoy']
        del sys.modules['easybuild.easyblocks.generic.toy_extension']

        # reset cached hooks
        easybuild.tools.hooks._cached_hooks.clear()

        super().tearDown()

        # remove logs
        if os.path.exists(self.dummylogfn):
            os.remove(self.dummylogfn)

    def check_toy(self, installpath, outtxt, name='toy', version='0.0', versionprefix='', versionsuffix='', error=None):
        """Check whether toy build succeeded."""

        full_version = ''.join([versionprefix, version, versionsuffix])

        if error is not None:
            error_msg = '\nNote: Caught error: %s' % error
        else:
            error_msg = ''

        # check for success
        success = re.compile(r"COMPLETED: Installation (ended|STOPPED) successfully \(took .* secs?\)")
        self.assertTrue(success.search(outtxt), "COMPLETED message found in '%s'%s" % (outtxt, error_msg))

        # if the module exists, it should be fine
        toy_module = os.path.join(installpath, 'modules', 'all', name, full_version)
        msg = "module for toy build toy/%s found (path %s)" % (full_version, toy_module)
        if get_module_syntax() == 'Lua':
            toy_module += '.lua'
        self.assertExists(toy_module, msg + error_msg)

        # module file is symlinked according to moduleclass
        toy_module_symlink = os.path.join(installpath, 'modules', 'tools', name, full_version)
        if get_module_syntax() == 'Lua':
            toy_module_symlink += '.lua'
        self.assertTrue(os.path.islink(toy_module_symlink))
        self.assertExists(toy_module_symlink)

        # make sure installation log file and easyconfig file are copied to install dir
        software_path = os.path.join(installpath, 'software', name, full_version)
        install_log_path_pattern = os.path.join(software_path, 'easybuild', 'easybuild-%s-%s*.log' % (name, version))
        self.assertTrue(len(glob.glob(install_log_path_pattern)) >= 1,
                        "Found  at least 1 file at %s" % install_log_path_pattern)

        # make sure test report is available
        report_name = 'easybuild-%s-%s*test_report.md' % (name, version)
        test_report_path_pattern = os.path.join(software_path, 'easybuild', report_name)
        self.assertTrue(len(glob.glob(test_report_path_pattern)) >= 1,
                        "Found  at least 1 file at %s" % test_report_path_pattern)

        ec_file_path = os.path.join(software_path, 'easybuild', '%s-%s.eb' % (name, full_version))
        self.assertExists(ec_file_path)

        devel_module_path = os.path.join(software_path, 'easybuild', '%s-%s-easybuild-devel' % (name, full_version))
        self.assertExists(devel_module_path)

    def _test_toy_build(self, extra_args=None, ec_file=None, tmpdir=None, verify=True, fails=False, verbose=True,
                        raise_error=False, test_report=None, name='toy', versionsuffix='', testing=True,
                        raise_systemexit=False, force=True, test_report_regexs=None, debug=True, trace=True):
        """Perform a toy build."""
        if extra_args is None:
            extra_args = []
        test_readme = False
        if ec_file is None:
            ec_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
            test_readme = True
        full_ver = '0.0%s' % versionsuffix
        args = [
            ec_file,
            '--unittest-file=%s' % self.logfile,
            '--robot=%s' % os.pathsep.join([self.test_buildpath, os.path.dirname(__file__)]),
        ]
        if debug:
            args.append('--debug')
        if trace:
            args.append('--trace')
        if force:
            args.append('--force')
        if tmpdir is not None:
            args.append('--tmpdir=%s' % tmpdir)
        if test_report is not None:
            args.append('--dump-test-report=%s' % test_report)
        args.extend(extra_args)
        myerr = None
        try:
            outtxt = self.eb_main(args, logfile=self.dummylogfn, do_build=True, verbose=verbose,
                                  raise_error=raise_error, testing=testing, raise_systemexit=raise_systemexit)
        except Exception as err:
            myerr = err
            if raise_error:
                raise myerr

        if verify:
            self.check_toy(self.test_installpath, outtxt, name=name, versionsuffix=versionsuffix, error=myerr)

        if test_readme:
            # make sure postinstallcmds were used
            toy_install_path = os.path.join(self.test_installpath, 'software', 'toy', full_ver)
            self.assertEqual(read_file(os.path.join(toy_install_path, 'README')), "TOY\n")

        # make sure full test report was dumped, and contains sensible information
        if test_report is not None:
            self.assertExists(test_report)
            if test_report_regexs:
                regex_patterns = test_report_regexs
            else:
                if fails:
                    test_result = 'FAIL'
                else:
                    test_result = 'SUCCESS'
                regex_patterns = [
                    r"Test result[\S\s]*Build succeeded for %d out of 1" % (not fails),
                    r"Overview of tested easyconfig[\S\s]*%s[\S\s]*%s" % (test_result, os.path.basename(ec_file)),
                ]
            regex_patterns.extend([
                r"Time info[\S\s]*start:[\S\s]*end:",
                r"EasyBuild info[\S\s]*framework version:[\S\s]*easyblocks ver[\S\s]*command line[\S\s]*configuration",
                r"System info[\S\s]*cpu model[\S\s]*os name[\S\s]*os version[\S\s]*python version",
                r"List of loaded modules",
                r"Environment",
            ])
            test_report_txt = read_file(test_report)
            for regex_pattern in regex_patterns:
                regex = re.compile(regex_pattern, re.M)
                msg = "Pattern %s found in full test report: %s" % (regex.pattern, test_report_txt)
                self.assertTrue(regex.search(test_report_txt), msg)

        return outtxt

    def run_test_toy_build_with_output(self, *args, **kwargs):
        """Run test_toy_build with specified arguments, catch stdout/stderr and return it."""

        self.mock_stderr(True)
        self.mock_stdout(True)
        self._test_toy_build(*args, **kwargs)
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        return stdout, stderr

    def run_eb_main_capture_output(self, *args, **kwargs):
        """Run eb_main with specified arguments, capture stdout, and return output from eb_main"""
        self.mock_stdout(True)
        outtxt = self.eb_main(*args, **kwargs)
        self.mock_stdout(False)
        return outtxt

    def test_toy_build(self):
        """Base level test build"""
        with self.mocked_stdout_stderr():
            self._test_toy_build()

    def test_toy_broken(self):
        """Test deliberately broken toy build."""
        tmpdir = tempfile.mkdtemp()
        broken_toy_ec = os.path.join(tmpdir, "toy-broken.eb")
        toy_ec_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        broken_toy_ec_txt = read_file(toy_ec_file)
        broken_toy_ec_txt += "checksums = ['clearywrongSHA256checksumoflength64-0123456789012345678901234567']"
        write_file(broken_toy_ec, broken_toy_ec_txt)
        error_regex = "Checksum verification .* failed"
        self.assertErrorRegex(EasyBuildError, error_regex, self.run_test_toy_build_with_output, ec_file=broken_toy_ec,
                              tmpdir=tmpdir, verify=False, fails=True, verbose=False, raise_error=True)

        # make sure log file is retained, also for failed build
        log_path_pattern = os.path.join(tmpdir, 'eb-*', 'easybuild-toy-0.0*.log')
        self.assertTrue(len(glob.glob(log_path_pattern)) == 1, "Log file found at %s" % log_path_pattern)

        # make sure individual test report is retained, also for failed build
        test_report_fp_pattern = os.path.join(tmpdir, 'eb-*', 'easybuild-toy-0.0*test_report.md')
        self.assertTrue(len(glob.glob(test_report_fp_pattern)) == 1, "Test report %s found" % test_report_fp_pattern)

        # test dumping full test report (doesn't raise an exception)
        test_report_fp = os.path.join(self.test_buildpath, 'full_test_report.md')
        self.run_test_toy_build_with_output(ec_file=broken_toy_ec, tmpdir=tmpdir, verify=False, fails=True,
                                            verbose=False, raise_error=True, test_report=test_report_fp)

        # cleanup
        shutil.rmtree(tmpdir)

    def test_toy_broken_copy_log_build_dir(self):
        """
        Test whether log files and the build directory are copied to a permanent location
        after a failed installation.
        """
        toy_ec = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec)

        test_ec_txt = re.sub(
            r'toy-0\.0_fix-silly-typo-in-printf-statement\.patch',
            r'toy-0.0_add-bug.patch',
            toy_ec_txt
        )
        test_ec = os.path.join(self.test_prefix, 'toy-0.0-buggy.eb')
        write_file(test_ec, test_ec_txt)

        # set up subdirectories where stuff should go
        tmpdir = os.path.join(self.test_prefix, 'tmp')
        tmp_log_dir = os.path.join(self.test_prefix, 'tmp-logs')
        failed_install_build_dirs_path = os.path.join(self.test_prefix, 'failed-install-build-dirs')
        failed_install_logs_path = os.path.join(self.test_prefix, 'failed-install-logs')

        extra_args = [
            f'--failed-install-build-dirs-path={failed_install_build_dirs_path}',
            f'--failed-install-logs-path={failed_install_logs_path}',
            f'--tmp-logdir={tmp_log_dir}',
        ]
        with self.mocked_stdout_stderr():
            outtxt = self._test_toy_build(ec_file=test_ec, extra_args=extra_args, tmpdir=tmpdir,
                                          verify=False, fails=True, verbose=False)

        # find path to temporary log file
        log_files = glob.glob(os.path.join(tmp_log_dir, '*.log'))
        self.assertTrue(len(log_files) == 1, f"Expected exactly one log file, found {len(log_files)}: {log_files}")
        log_file = log_files[0]

        # check that log files were copied
        saved_log_files = glob.glob(os.path.join(failed_install_logs_path, log_file))
        self.assertTrue(len(saved_log_files) == 1, f"Unique copy of log file '{log_file}' made")
        saved_log_file = saved_log_files[0]
        self.assertTrue(filecmp.cmp(log_file, saved_log_file, shallow=False),
                        f"Log file '{log_file}' copied successfully")

        # check that build directories were copied
        build_dir = self.test_buildpath
        topdir = failed_install_build_dirs_path

        app_build_dir = os.path.join(build_dir, 'toy', '0.0', 'system-system')
        # pattern: <datestamp>-<timestamp>-<salt>
        subdir_pattern = '????????-??????-?????'

        # find path to toy.c
        toy_c_files = glob.glob(os.path.join(app_build_dir, '**', 'toy.c'))
        self.assertTrue(len(toy_c_files) == 1, f"Exactly one toy.c file found: {toy_c_files}")
        toy_c_file = toy_c_files[0]

        path = os.path.join(topdir, 'toy-0.0', subdir_pattern, 'toy-0.0', os.path.basename(toy_c_file))
        res = glob.glob(path)
        self.assertTrue(len(res) == 1, f"Exactly one hit found for {path}: {res}")
        copied_toy_c_file = res[0]
        self.assertTrue(filecmp.cmp(toy_c_file, copied_toy_c_file, shallow=False),
                        f"Copy of {toy_c_file} should be found under {topdir}")

        # check whether compiler error messages are present in build log

        # compiler error because of missing semicolon at end of line, could be:
        # "error: expected ; before ..."
        # "error: expected ';' after expression"
        output_regexs = [r"^\s*toy\.c:5:44: error: expected (;|.;.)"]

        log_txt = read_file(log_file)
        for regex_pattern in output_regexs:
            regex = re.compile(regex_pattern, re.M)
            self.assertRegex(outtxt, regex)
            self.assertRegex(log_txt, regex)

    def test_toy_tweaked(self):
        """Test toy build with tweaked easyconfig, for testing extra easyconfig parameters."""
        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs')
        ec_file = os.path.join(self.test_buildpath, 'toy-0.0-tweaked.eb')
        shutil.copy2(os.path.join(test_ecs_dir, 'test_ecs', 't', 'toy', 'toy-0.0.eb'), ec_file)

        modloadmsg = 'THANKS FOR LOADING ME\\nI AM %(name)s v%(version)s'
        modloadmsg_regex_tcl = r'THANKS.*\n\s*I AM toy v0.0\n\s*"'
        modloadmsg_regex_lua = r'\[==\[THANKS.*\n\s*I AM toy v0.0\n\s*\]==\]'

        # tweak easyconfig by appending to it
        ec_extra = '\n'.join([
            "versionsuffix = '-tweaked'",
            "modextrapaths = {",
            "    'SOMEPATH': ['foo/bar', 'baz', ''],",
            "    'SOMEPATH_APPEND': {'paths': ['qux/fred', 'thud', ''], 'prepend': False},",
            "}",
            "modextravars = {'FOO': 'bar'}",
            "modloadmsg =  '%s'" % modloadmsg,
            "modtclfooter = 'puts stderr \"oh hai!\"'",  # ignored when module syntax is Lua
            "modluafooter = 'io.stderr:write(\"oh hai!\")'",  # ignored when module syntax is Tcl
            "usage = 'This toy is easy to use, 100%!'",
            "examples = 'No example available, 0% complete'",
            "citing = 'If you use this package, please cite our paper https://ieeexplore.ieee.org/document/6495863'",
            "docpaths = ['share/doc/toy/readme.txt', 'share/doc/toy/html/index.html']",
            "docurls = ['https://easybuilders.github.io/easybuild/toy/docs.html']",
            "upstream_contacts = 'support@toy.org'",
            "site_contacts = ['Jim Admin', 'Jane Admin']",
            "postinstallcmds = [",
            "    'mkdir \"%(installdir)s/foo\"',"
            "    'touch \"%(installdir)s/foo/bar\"',"
            "    'touch \"%(installdir)s/baz\"',"
            "    'mkdir \"%(installdir)s/qux\"',"
            "    'touch \"%(installdir)s/qux/fred\"',"
            "    'touch \"%(installdir)s/thud\"',"
            "]",
        ])
        write_file(ec_file, ec_extra, append=True)

        # populate test install dir
        toy_installdir = os.path.join(self.test_installpath, 'software', 'toy', '0.0-tweaked')
        mkdir(os.path.join(toy_installdir, 'foo'), parents=True)
        write_file(os.path.join(toy_installdir, 'foo', 'bar'), "Test install file")
        mkdir(os.path.join(toy_installdir, 'baz'), parents=True)

        args = [
            ec_file,
            '--debug',
            '--force',
        ]
        outtxt = self.run_eb_main_capture_output(args, do_build=True, verbose=True, raise_error=True)
        self.check_toy(self.test_installpath, outtxt, versionsuffix='-tweaked')
        toy_module = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0-tweaked')
        if get_module_syntax() == 'Lua':
            toy_module += '.lua'
        toy_module_txt = read_file(toy_module)

        if get_module_syntax() == 'Tcl':
            self.assertTrue(re.search(r'^setenv\s*FOO\s*"bar"$', toy_module_txt, re.M))
            self.assertTrue(re.search(r'^prepend-path\s*SOMEPATH\s*\$root/foo/bar$', toy_module_txt, re.M))
            self.assertTrue(re.search(r'^prepend-path\s*SOMEPATH\s*\$root/baz$', toy_module_txt, re.M))
            self.assertTrue(re.search(r'^prepend-path\s*SOMEPATH\s*\$root$', toy_module_txt, re.M))
            self.assertTrue(re.search(r'^append-path\s*SOMEPATH_APPEND\s*\$root/qux/fred$', toy_module_txt, re.M))
            self.assertTrue(re.search(r'^append-path\s*SOMEPATH_APPEND\s*\$root/thud$', toy_module_txt, re.M))
            self.assertTrue(re.search(r'^append-path\s*SOMEPATH_APPEND\s*\$root$', toy_module_txt, re.M))
            mod_load_msg = r'module-info mode load.*\n\s*puts stderr\s*.*%s$' % modloadmsg_regex_tcl
            self.assertTrue(re.search(mod_load_msg, toy_module_txt, re.M))
            self.assertTrue(re.search(r'^puts stderr "oh hai!"$', toy_module_txt, re.M))
        elif get_module_syntax() == 'Lua':
            self.assertTrue(re.search(r'^setenv\("FOO", "bar"\)', toy_module_txt, re.M))
            pattern = r'^prepend_path\("SOMEPATH", pathJoin\(root, "foo", "bar"\)\)$'
            self.assertTrue(re.search(pattern, toy_module_txt, re.M))
            pattern = r'^append_path\("SOMEPATH_APPEND", pathJoin\(root, "qux", "fred"\)\)$'
            self.assertTrue(re.search(pattern, toy_module_txt, re.M))
            pattern = r'^append_path\("SOMEPATH_APPEND", pathJoin\(root, "thud"\)\)$'
            self.assertTrue(re.search(pattern, toy_module_txt, re.M))
            self.assertTrue(re.search(r'^append_path\("SOMEPATH_APPEND", root\)$', toy_module_txt, re.M))
            self.assertTrue(re.search(r'^prepend_path\("SOMEPATH", pathJoin\(root, "baz"\)\)$', toy_module_txt, re.M))
            self.assertTrue(re.search(r'^prepend_path\("SOMEPATH", root\)$', toy_module_txt, re.M))
            mod_load_msg = r'^if mode\(\) == "load" then\n\s*io.stderr:write\(%s\)$' % modloadmsg_regex_lua
            regex = re.compile(mod_load_msg, re.M)
            self.assertTrue(regex.search(toy_module_txt), "Pattern '%s' found in: %s" % (regex.pattern, toy_module_txt))
        else:
            self.fail("Unknown module syntax: %s" % get_module_syntax())

        # newline between "I AM toy v0.0" (modloadmsg) and "oh hai!" (mod*footer) is added automatically
        expected = "\nTHANKS FOR LOADING ME\nI AM toy v0.0\n"

        # with module files in Tcl syntax, a newline is added automatically
        if get_module_syntax() == 'Tcl':
            expected += "\n"

        expected += "oh hai!"

        # setting $LMOD_QUIET results in suppression of printed message with Lmod & module files in Tcl syntax
        os.environ.pop('LMOD_QUIET', None)

        self.modtool.use(os.path.join(self.test_installpath, 'modules', 'all'))
        out = self.modtool.run_module('load', 'toy/0.0-tweaked', return_output=True)
        self.assertTrue(out.strip().endswith(expected))

    def test_toy_buggy_easyblock(self):
        """Test build using a buggy/broken easyblock, make sure a traceback is reported."""
        ec_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        kwargs = {
            'ec_file': ec_file,
            'extra_args': ['--easyblock=EB_toy_buggy'],
            'raise_error': True,
            'verify': False,
            'verbose': False,
        }
        err_regex = r"name 'run_shell_cmd' is not defined"
        self.assertErrorRegex(NameError, err_regex, self.run_test_toy_build_with_output, **kwargs)

    def test_toy_build_formatv2(self):
        """Perform a toy build (format v2)."""
        # set $MODULEPATH such that modules for specified dependencies are found
        modulepath = os.environ.get('MODULEPATH')
        os.environ['MODULEPATH'] = os.path.abspath(os.path.join(os.path.dirname(__file__), 'modules'))

        args = [
            os.path.join(os.path.dirname(__file__), 'easyconfigs', 'v2.0', 'toy.eb'),
            '--debug',
            '--unittest-file=%s' % self.logfile,
            '--force',
            '--robot=%s' % os.pathsep.join([self.test_buildpath, os.path.dirname(__file__)]),
            '--software-version=0.0',
            '--toolchain=system,system',
            '--experimental',
        ]
        outtxt = self.run_eb_main_capture_output(args, logfile=self.dummylogfn, do_build=True, verbose=True)

        self.check_toy(self.test_installpath, outtxt)

        # restore
        if modulepath is not None:
            os.environ['MODULEPATH'] = modulepath
        else:
            del os.environ['MODULEPATH']

    def test_toy_build_with_blocks(self):
        """Test a toy build with multiple blocks."""
        orig_sys_path = sys.path[:]
        # add directory in which easyconfig file can be found to Python search path,
        # since we're not specifying it full path below
        tmpdir = tempfile.mkdtemp()
        # note get_paths_for expects easybuild/easyconfigs subdir
        ecs_path = os.path.join(tmpdir, "easybuild", "easyconfigs")
        os.makedirs(ecs_path)
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        shutil.copy2(os.path.join(test_ecs, 't', 'toy', 'toy-0.0-multiple.eb'), ecs_path)
        sys.path.append(tmpdir)

        args = [
            'toy-0.0-multiple.eb',
            '--debug',
            '--unittest-file=%s' % self.logfile,
            '--force',
        ]
        with self.mocked_stdout_stderr():
            outtxt = self.eb_main(args, logfile=self.dummylogfn, do_build=True, verbose=True)

        for toy_prefix, toy_version, toy_suffix in [
            ('', '0.0', '-somesuffix'),
            ('someprefix-', '0.0', '-somesuffix')
        ]:
            self.check_toy(self.test_installpath, outtxt, version=toy_version,
                           versionprefix=toy_prefix, versionsuffix=toy_suffix)

        # cleanup
        shutil.rmtree(tmpdir)
        sys.path[:] = orig_sys_path

    def test_toy_build_formatv2_sections(self):
        """Perform a toy build (format v2, using sections)."""
        versions = {
            '0.0': {'versionprefix': '', 'versionsuffix': ''},
            '1.0': {'versionprefix': '', 'versionsuffix': ''},
            '1.1': {'versionprefix': 'stable-', 'versionsuffix': ''},
            '1.5': {'versionprefix': 'stable-', 'versionsuffix': '-early'},
            '1.6': {'versionprefix': 'stable-', 'versionsuffix': '-early'},
            '2.0': {'versionprefix': 'stable-', 'versionsuffix': '-early'},
            '3.0': {'versionprefix': 'stable-', 'versionsuffix': '-mature'},
        }

        for version, specs in versions.items():
            args = [
                os.path.join(os.path.dirname(__file__), 'easyconfigs', 'v2.0', 'toy-with-sections.eb'),
                '--debug',
                '--unittest-file=%s' % self.logfile,
                '--force',
                '--robot=%s' % os.pathsep.join([self.test_buildpath, os.path.dirname(__file__)]),
                '--software-version=%s' % version,
                '--toolchain=system,system',
                '--experimental',
            ]
            outtxt = self.run_eb_main_capture_output(args, logfile=self.dummylogfn, do_build=True, verbose=True,
                                                     raise_error=True)

            specs['version'] = version

            self.check_toy(self.test_installpath, outtxt, **specs)

    def test_toy_download_sources(self):
        """Test toy build with sources that still need to be 'downloaded'."""
        tmpdir = tempfile.mkdtemp()
        # copy toy easyconfig file, and append source_urls to it
        topdir = os.path.dirname(os.path.abspath(__file__))
        shutil.copy2(os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb'), tmpdir)
        source_url = os.path.join(topdir, 'sandbox', 'sources', 'toy')
        ec_file = os.path.join(tmpdir, 'toy-0.0.eb')
        write_file(ec_file, '\nsource_urls = ["file://%s"]\n' % source_url, append=True)

        # unset $EASYBUILD_XPATH env vars, to make sure --prefix is picked up
        for cfg_opt in ['build', 'install', 'source']:
            del os.environ['EASYBUILD_%sPATH' % cfg_opt.upper()]
        sourcepath = os.path.join(tmpdir, 'mysources')
        args = [
            ec_file,
            '--prefix=%s' % tmpdir,
            '--sourcepath=%s' % ':'.join([sourcepath, '/bar']),  # include senseless path which should be ignored
            '--debug',
            '--unittest-file=%s' % self.logfile,
            '--force',
        ]
        outtxt = self.run_eb_main_capture_output(args, logfile=self.dummylogfn, do_build=True, verbose=True)

        self.check_toy(tmpdir, outtxt)

        self.assertExists(os.path.join(sourcepath, 't', 'toy', 'toy-0.0.tar.gz'))

        shutil.rmtree(tmpdir)

    def test_toy_permissions(self):
        """Test toy build with custom umask settings."""
        toy_ec_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        test_ec_txt = read_file(toy_ec_file)

        # remove exec perms on bin subdirectory for others, to check whether correct dir permissions are set
        test_ec_txt += "\npostinstallcmds += ['chmod o-x %(installdir)s/bin']"

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, test_ec_txt)

        args = [
            '--debug',
            '--unittest-file=%s' % self.logfile,
            '--force',
        ]

        # set umask hard to verify default reliably
        orig_umask = os.umask(0o022)

        # test specifying a non-existing group
        allargs = [test_ec] + args + ['--group=thisgroupdoesnotexist']
        outtxt, err = self.run_eb_main_capture_output(allargs, logfile=self.dummylogfn, do_build=True,
                                                      return_error=True)
        err_regex = re.compile("Failed to get group ID .* group does not exist")
        self.assertTrue(err_regex.search(outtxt), "Pattern '%s' found in '%s'" % (err_regex.pattern, outtxt))

        # determine current group name (at least we can use that)
        gid = os.getgid()
        curr_grp = grp.getgrgid(gid).gr_name

        for umask, cfg_group, ec_group, dir_perms, fil_perms, bin_perms in [
            (None, None, None, 0o755, 0o644, 0o755),  # default: inherit session umask
            (None, None, curr_grp, 0o750, 0o640, 0o750),  # default umask, but with specified group in ec
            (None, curr_grp, None, 0o750, 0o640, 0o750),  # default umask, but with specified group in cfg
            (None, 'notagrp', curr_grp, 0o750, 0o640, 0o750),  # default umask, but with specified group in cfg/ec
            ('000', None, None, 0o777, 0o666, 0o777),  # stupid empty umask
            ('032', None, None, 0o745, 0o644, 0o745),  # no write/execute for group, no write for other
            ('030', None, curr_grp, 0o740, 0o640, 0o740),  # no write for group, with specified group
            ('077', None, None, 0o700, 0o600, 0o700),  # no access for other/group
        ]:
            # empty the install directory, to ensure any created directories adher to the permissions
            shutil.rmtree(self.test_installpath)

            if cfg_group is None and ec_group is None:
                allargs = [test_ec]
            elif ec_group is not None:
                shutil.copy2(test_ec, self.test_buildpath)
                tmp_ec_file = os.path.join(self.test_buildpath, os.path.basename(test_ec))
                write_file(tmp_ec_file, "\ngroup = '%s'" % ec_group, append=True)
                allargs = [tmp_ec_file]
            allargs.extend(args)
            if umask is not None:
                allargs.append("--umask=%s" % umask)
            if cfg_group is not None:
                allargs.append("--group=%s" % cfg_group)
            outtxt = self.run_eb_main_capture_output(allargs, logfile=self.dummylogfn, do_build=True, verbose=True)

            # verify that installation was correct
            self.check_toy(self.test_installpath, outtxt)

            # group specified in easyconfig overrules configured group
            group = cfg_group
            if ec_group is not None:
                group = ec_group

            # verify permissions
            paths_perms = [
                # no write permissions for group/other, regardless of umask
                (('software', 'toy', '0.0'), dir_perms & ~ 0o022),
                (('software', 'toy', '0.0', 'bin'), dir_perms & ~ 0o022),
                (('software', 'toy', '0.0', 'bin', 'toy'), bin_perms & ~ 0o022),
            ]
            # only software subdirs are chmod'ed for 'protected' installs, so don't check those if a group is specified
            if group is None:
                paths_perms.extend([
                    (('software', ), dir_perms),
                    (('software', 'toy'), dir_perms),
                    (('software', 'toy', '0.0', 'easybuild', '*.log'), fil_perms),
                    (('modules', ), dir_perms),
                    (('modules', 'all'), dir_perms),
                    (('modules', 'all', 'toy'), dir_perms),
                ])
                if get_module_syntax() == 'Tcl':
                    paths_perms.append((('modules', 'all', 'toy', '0.0'), fil_perms))
                elif get_module_syntax() == 'Lua':
                    paths_perms.append((('modules', 'all', 'toy', '0.0.lua'), fil_perms))

            for path, correct_perms in paths_perms:
                fullpath = glob.glob(os.path.join(self.test_installpath, *path))[0]
                perms = os.stat(fullpath).st_mode & 0o777
                tup = (fullpath, oct(correct_perms), oct(perms), umask, cfg_group, ec_group)
                msg = "Path %s has %s permissions: %s (umask: %s, group: %s - %s)" % tup
                self.assertEqual(oct(perms), oct(correct_perms), msg)
                if group is not None:
                    path_gid = os.stat(fullpath).st_gid
                    self.assertEqual(path_gid, grp.getgrnam(group).gr_gid)

        # restore original umask
        os.umask(orig_umask)

    def test_toy_permissions_installdir(self):
        """Test --read-only-installdir and --group-write-installdir."""
        # Avoid picking up the already prepared fake module
        try:
            del os.environ['MODULEPATH']
        except KeyError:
            pass
        # set umask hard to verify default reliably
        orig_umask = os.umask(0o022)

        toy_ec = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        test_ec_txt = read_file(toy_ec)
        # take away read permissions, to check whether they are correctly restored by EasyBuild after installation
        test_ec_txt += "\npostinstallcmds += ['chmod -R og-r %(installdir)s']"

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, test_ec_txt)

        # first check default behaviour
        self.run_test_toy_build_with_output(ec_file=test_ec)

        toy_install_dir = os.path.join(self.test_installpath, 'software', 'toy', '0.0')
        toy_bin = os.path.join(toy_install_dir, 'bin', 'toy')

        installdir_perms = os.stat(toy_install_dir).st_mode & 0o777
        self.assertEqual(installdir_perms, 0o755, "%s has default permissions" % toy_install_dir)

        toy_bin_perms = os.stat(toy_bin).st_mode & 0o777
        self.assertEqual(toy_bin_perms, 0o755, "%s has default permissions" % toy_bin_perms)

        shutil.rmtree(self.test_installpath)

        # check whether --read-only-installdir works as intended
        # Tested 5 times:
        # 1. Non existing build -> Install and set read-only
        # 2. Existing build with --rebuild -> Reinstall and set read-only
        # 3. Existing build with --force -> Reinstall and set read-only
        # 4-5: Same as 2-3 but with --skip
        # 6. Existing build with --fetch -> Test that logs can be written
        test_cases = (
            [],
            ['--rebuild'],
            ['--force'],
            ['--skip', '--rebuild'],
            ['--skip', '--force'],
            ['--rebuild', '--fetch'],
        )
        for extra_args in test_cases:
            self.run_test_toy_build_with_output(ec_file=test_ec, extra_args=['--read-only-installdir'] + extra_args,
                                                force=False)

            installdir_perms = os.stat(os.path.dirname(toy_install_dir)).st_mode & 0o777
            self.assertEqual(installdir_perms, 0o755, "%s has default permissions" % os.path.dirname(toy_install_dir))

            installdir_perms = os.stat(toy_install_dir).st_mode & 0o777
            self.assertEqual(installdir_perms, 0o555, "%s has read-only permissions" % toy_install_dir)
            toy_bin_perms = os.stat(toy_bin).st_mode & 0o777
            self.assertEqual(toy_bin_perms, 0o555, "%s has read-only permissions" % toy_bin_perms)
            toy_bin_perms = os.stat(os.path.join(toy_install_dir, 'README')).st_mode & 0o777
            self.assertEqual(toy_bin_perms, 0o444, "%s has read-only permissions" % toy_bin_perms)

            # also log file copied into install dir should be read-only (not just the 'easybuild/' subdir itself)
            log_path = glob.glob(os.path.join(toy_install_dir, 'easybuild', '*log'))[0]
            log_perms = os.stat(log_path).st_mode & 0o777
            self.assertEqual(log_perms, 0o444, "%s has read-only permissions" % log_path)

        adjust_permissions(toy_install_dir, stat.S_IWUSR, add=True)
        shutil.rmtree(self.test_installpath)

        # also check --group-writable-installdir
        self.run_test_toy_build_with_output(ec_file=test_ec, extra_args=['--group-writable-installdir'])
        installdir_perms = os.stat(toy_install_dir).st_mode & 0o777
        self.assertEqual(installdir_perms, 0o775, "%s has group write permissions" % self.test_installpath)

        toy_bin_perms = os.stat(toy_bin).st_mode & 0o777
        self.assertEqual(toy_bin_perms, 0o775, "%s has group write permissions" % toy_bin_perms)

        # make sure --read-only-installdir is robust against not having the 'easybuild/' subdir after installation
        # this happens when for example using ModuleRC easyblock (because no devel module is created)
        test_ec_txt += "\nmake_module = False"
        write_file(test_ec, test_ec_txt)
        self.run_test_toy_build_with_output(ec_file=test_ec, extra_args=['--read-only-installdir'], verify=False,
                                            raise_error=True)

        # restore original umask
        os.umask(orig_umask)

    def test_toy_gid_sticky_bits(self):
        """Test setting gid and sticky bits."""
        subdirs = [
            (('',), False),
            (('software',), False),
            (('software', 'toy'), False),
            (('software', 'toy', '0.0'), True),
            (('modules', 'all'), False),
            (('modules', 'all', 'toy'), False),
        ]
        # no gid/sticky bits by default
        self.run_test_toy_build_with_output()
        for subdir, _ in subdirs:
            fullpath = os.path.join(self.test_installpath, *subdir)
            perms = os.stat(fullpath).st_mode
            self.assertFalse(perms & stat.S_ISGID, "no gid bit on %s" % fullpath)
            self.assertFalse(perms & stat.S_ISVTX, "no sticky bit on %s" % fullpath)

        # git/sticky bits are set, but only on (re)created directories
        self.run_test_toy_build_with_output(extra_args=['--set-gid-bit', '--sticky-bit'])
        for subdir, bits_set in subdirs:
            fullpath = os.path.join(self.test_installpath, *subdir)
            perms = os.stat(fullpath).st_mode
            if bits_set:
                self.assertTrue(perms & stat.S_ISGID, "gid bit set on %s" % fullpath)
                self.assertTrue(perms & stat.S_ISVTX, "sticky bit set on %s" % fullpath)
            else:
                self.assertFalse(perms & stat.S_ISGID, "no gid bit on %s" % fullpath)
                self.assertFalse(perms & stat.S_ISVTX, "no sticky bit on %s" % fullpath)

        # start with a clean slate, now gid/sticky bits should be set on everything
        shutil.rmtree(self.test_installpath)
        self.run_test_toy_build_with_output(extra_args=['--set-gid-bit', '--sticky-bit'])
        for subdir, _ in subdirs:
            fullpath = os.path.join(self.test_installpath, *subdir)
            perms = os.stat(fullpath).st_mode
            self.assertTrue(perms & stat.S_ISGID, "gid bit set on %s" % fullpath)
            self.assertTrue(perms & stat.S_ISVTX, "sticky bit set on %s" % fullpath)

    def test_toy_group_check(self):
        """Test presence of group check in generated (Lua) modules"""
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # figure out a group that we're a member of to use in the test
        with self.mocked_stdout_stderr():
            res = run_shell_cmd('groups')
        self.assertEqual(res.exit_code, 0, "Failed to select group to use in test")
        group_name = res.output.split(' ')[0].strip()

        toy_ec = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        args = [
            test_ec,
            '--force',
            '--module-only',
        ]

        for group in [group_name, (group_name, "Hey, you're not in the '%s' group!" % group_name)]:

            if isinstance(group, str):
                write_file(test_ec, read_file(toy_ec) + "\ngroup = '%s'\n" % group)
            else:
                write_file(test_ec, read_file(toy_ec) + "\ngroup = %s\n" % str(group))

            self.mock_stdout(True)
            outtxt = self.eb_main(args, logfile=dummylogfn, do_build=True, raise_error=True, raise_systemexit=True)
            self.mock_stdout(False)

            if get_module_syntax() == 'Tcl':
                module_version = LooseVersion(self.modtool.version)
                if isinstance(self.modtool, EnvironmentModules) and module_version >= LooseVersion('4.6.0'):
                    toy_mod = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0')
                    toy_mod_txt = read_file(toy_mod)

                    if isinstance(group, tuple):
                        group_name = group[0]
                        error_msg_pattern = "Hey, you're not in the '%s' group!" % group_name
                    else:
                        group_name = group
                        error_msg_pattern = "You are not part of '%s' group of users" % group_name

                    pattern = '\n'.join([
                        r'^if \{ \!\[ module-info usergroups %s \] \} \{' % group_name,
                        r'    error "%s[^"]*"' % error_msg_pattern,
                        r'\}$',
                    ])
                    regex = re.compile(pattern, re.M)
                    self.assertTrue(regex.search(outtxt), "Pattern '%s' found in: %s" % (regex.pattern, toy_mod_txt))
                else:
                    pattern = "Can't generate robust check in Tcl modules for users belonging to group %s." % group_name
                    regex = re.compile(pattern, re.M)
                    self.assertTrue(regex.search(outtxt), "Pattern '%s' found in: %s" % (regex.pattern, outtxt))

            elif get_module_syntax() == 'Lua':
                toy_mod = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0.lua')
                toy_mod_txt = read_file(toy_mod)

                if isinstance(group, tuple):
                    group_name = group[0]
                    error_msg_pattern = "Hey, you're not in the '%s' group!" % group_name
                else:
                    group_name = group
                    error_msg_pattern = "You are not part of '%s' group of users" % group_name

                pattern = '\n'.join([
                    r'^if not \( userInGroup\("%s"\) \) then' % group_name,
                    r'    LmodError\("%s[^"]*"\)' % error_msg_pattern,
                    r'end$',
                ])
                regex = re.compile(pattern, re.M)
                self.assertTrue(regex.search(outtxt), "Pattern '%s' found in: %s" % (regex.pattern, toy_mod_txt))
            else:
                self.fail("Unknown module syntax: %s" % get_module_syntax())

        write_file(test_ec, read_file(toy_ec) + "\ngroup = ('%s', 'custom message', 'extra item')\n" % group_name)
        self.assertErrorRegex(SystemExit, '.*', self.eb_main, args, do_build=True,
                              raise_error=True, raise_systemexit=True)

    def test_allow_system_deps(self):
        """Test allow_system_deps easyconfig parameter."""
        tmpdir = tempfile.mkdtemp()
        # copy toy easyconfig file, and append source_urls to it
        topdir = os.path.dirname(os.path.abspath(__file__))
        shutil.copy2(os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb'), tmpdir)
        ec_file = os.path.join(tmpdir, 'toy-0.0.eb')
        write_file(ec_file, "\nallow_system_deps = [('Python', SYS_PYTHON_VERSION)]\n", append=True)
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=ec_file)
        shutil.rmtree(tmpdir)

    def test_toy_hierarchical(self):
        """Test toy build under example hierarchical module naming scheme."""

        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        self.setup_hierarchical_modules()
        mod_prefix = os.path.join(self.test_installpath, 'modules', 'all')

        args = [
            os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb'),
            '--debug',
            '--unittest-file=%s' % self.logfile,
            '--force',
            '--robot=%s' % test_easyconfigs,
            '--module-naming-scheme=HierarchicalMNS',
        ]

        # test module paths/contents with foss build
        extra_args = [
            '--try-toolchain=foss,2018a',
            # This test was created for the regex substitution of toolchains, to trigger this (rather than subtoolchain
            # resolution) we must add an additional build option
            '--disable-map-toolchains',
        ]
        with self.mocked_stdout_stderr():
            self.eb_main(args + extra_args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)

        # make sure module file is installed in correct path
        toy_module_path = os.path.join(mod_prefix, 'MPI', 'GCC', '6.4.0-2.28', 'OpenMPI', '2.1.2', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_module_path += '.lua'
        self.assertExists(toy_module_path)

        # check that toolchain load is expanded to loads for toolchain dependencies,
        # except for the ones that extend $MODULEPATH to make the toy module available
        if get_module_syntax() == 'Tcl':
            load_regex_template = "(load|depends-on) %s"
        elif get_module_syntax() == 'Lua':
            load_regex_template = r'(load|depends_on)\("%s/.*"\)'
        else:
            self.fail("Unknown module syntax: %s" % get_module_syntax())

        modtxt = read_file(toy_module_path)
        for dep in ['foss', 'GCC', 'OpenMPI']:
            load_regex = re.compile(load_regex_template % dep)
            self.assertFalse(load_regex.search(modtxt), "Pattern '%s' not found in %s" % (load_regex.pattern, modtxt))
        for dep in ['OpenBLAS', 'FFTW', 'ScaLAPACK']:
            load_regex = re.compile(load_regex_template % dep)
            self.assertTrue(load_regex.search(modtxt), "Pattern '%s' found in %s" % (load_regex.pattern, modtxt))

        os.remove(toy_module_path)

        # test module path with GCC/6.4.0-2.28 build
        extra_args = [
            '--try-toolchain=GCC,6.4.0-2.28',
        ]
        with self.mocked_stdout_stderr():
            self.eb_main(args + extra_args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)

        # make sure module file is installed in correct path
        toy_module_path = os.path.join(mod_prefix, 'Compiler', 'GCC', '6.4.0-2.28', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_module_path += '.lua'
        self.assertExists(toy_module_path)

        # no dependencies or toolchain => no module load statements in module file
        modtxt = read_file(toy_module_path)
        self.assertFalse(re.search("module load", modtxt))
        os.remove(toy_module_path)
        # test module path with GCC/6.4.0-2.28 build, pretend to be an MPI lib by setting moduleclass
        extra_args = [
            '--try-toolchain=GCC,6.4.0-2.28',
            '--try-amend=moduleclass=mpi',
        ]
        with self.mocked_stdout_stderr():
            self.eb_main(args + extra_args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)

        # make sure module file is installed in correct path
        toy_module_path = os.path.join(mod_prefix, 'Compiler', 'GCC', '6.4.0-2.28', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_module_path += '.lua'
        self.assertExists(toy_module_path)

        # 'module use' statements to extend $MODULEPATH are present
        modtxt = read_file(toy_module_path)
        modpath_extension = os.path.join(mod_prefix, 'MPI', 'GCC', '6.4.0-2.28', 'toy', '0.0')
        if get_module_syntax() == 'Tcl':
            self.assertTrue(re.search(r'^module\s*use\s*"%s"' % modpath_extension, modtxt, re.M))
        elif get_module_syntax() == 'Lua':
            fullmodpath_extension = os.path.join(self.test_installpath, modpath_extension)
            regex = re.compile(r'^prepend_path\("MODULEPATH", "%s"\)' % fullmodpath_extension, re.M)
            self.assertTrue(regex.search(modtxt), "Pattern '%s' found in %s" % (regex.pattern, modtxt))
        else:
            self.fail("Unknown module syntax: %s" % get_module_syntax())
        os.remove(toy_module_path)

        # ... unless they shouldn't be
        extra_args.append('--try-amend=include_modpath_extensions=')  # pass empty string as equivalent to False
        with self.mocked_stdout_stderr():
            self.eb_main(args + extra_args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)
        modtxt = read_file(toy_module_path)
        modpath_extension = os.path.join(mod_prefix, 'MPI', 'GCC', '6.4.0-2.28', 'toy', '0.0')
        if get_module_syntax() == 'Tcl':
            self.assertFalse(re.search(r'^module\s*use\s*"%s"' % modpath_extension, modtxt, re.M))
        elif get_module_syntax() == 'Lua':
            fullmodpath_extension = os.path.join(self.test_installpath, modpath_extension)
            regex = re.compile(r'^prepend_path\("MODULEPATH", "%s"\)' % fullmodpath_extension, re.M)
            self.assertFalse(regex.search(modtxt), "Pattern '%s' found in %s" % (regex.pattern, modtxt))
        else:
            self.fail("Unknown module syntax: %s" % get_module_syntax())
        os.remove(toy_module_path)

        # test module path with system/system build
        extra_args = [
            '--try-toolchain=system,system',
        ]
        with self.mocked_stdout_stderr():
            self.eb_main(args + extra_args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)

        # make sure module file is installed in correct path
        toy_module_path = os.path.join(mod_prefix, 'Core', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_module_path += '.lua'
        self.assertExists(toy_module_path)

        # no dependencies or toolchain => no module load statements in module file
        modtxt = read_file(toy_module_path)
        self.assertFalse(re.search("module load", modtxt))
        os.remove(toy_module_path)

        # test module path with system/system build, pretend to be a compiler by setting moduleclass
        extra_args = [
            '--try-toolchain=system,system',
            '--try-amend=moduleclass=compiler',
        ]
        with self.mocked_stdout_stderr():
            self.eb_main(args + extra_args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)

        # make sure module file is installed in correct path
        toy_module_path = os.path.join(mod_prefix, 'Core', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_module_path += '.lua'
        self.assertExists(toy_module_path)

        # no dependencies or toolchain => no module load statements in module file
        modtxt = read_file(toy_module_path)
        modpath_extension = os.path.join(mod_prefix, 'Compiler', 'toy', '0.0')
        if get_module_syntax() == 'Tcl':
            self.assertTrue(re.search(r'^module\s*use\s*"%s"' % modpath_extension, modtxt, re.M))
        elif get_module_syntax() == 'Lua':
            fullmodpath_extension = os.path.join(self.test_installpath, modpath_extension)
            regex = re.compile(r'^prepend_path\("MODULEPATH", "%s"\)' % fullmodpath_extension, re.M)
            self.assertTrue(regex.search(modtxt), "Pattern '%s' found in %s" % (regex.pattern, modtxt))
        else:
            self.fail("Unknown module syntax: %s" % get_module_syntax())
        os.remove(toy_module_path)

        # building a toolchain module should also work
        gompi_module_path = os.path.join(mod_prefix, 'Core', 'gompi', '2018a')

        # make sure Core/gompi/2018a module that may already be there is removed (both Tcl/Lua variants)
        for modfile in glob.glob(gompi_module_path + '*'):
            os.remove(modfile)

        if get_module_syntax() == 'Lua':
            gompi_module_path += '.lua'

        args[0] = os.path.join(test_easyconfigs, 'g', 'gompi', 'gompi-2018a.eb')
        self.modtool.purge()
        with self.mocked_stdout_stderr():
            self.eb_main(args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)
        self.assertExists(gompi_module_path)

    def test_toy_hierarchical_subdir_user_modules(self):
        """
        Test toy build under example hierarchical module naming scheme that was created using --subidr-user-modules
        """

        # redefine $HOME to a temporary location we can fiddle with
        home = os.path.join(self.test_prefix, 'HOME')
        mkdir(home)
        os.environ['HOME'] = home

        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        self.setup_hierarchical_modules()
        mod_prefix = os.path.join(self.test_installpath, 'modules', 'all')

        gcc_mod_subdir = os.path.join('Compiler', 'GCC', '6.4.0-2.28')
        openmpi_mod_subdir = os.path.join('MPI', 'GCC', '6.4.0-2.28', 'OpenMPI', '2.1.2')

        # include guarded 'module use' statement in GCC & OpenMPI modules,
        # like there would be when --subdir-user-modules=modules/all is used
        extra_modtxt = '\n'.join([
            'if { [ file isdirectory [ file join $env(HOME) "modules/all/%s" ] ] } {' % gcc_mod_subdir,
            '    module use [ file join $env(HOME) "modules/all/%s" ]' % gcc_mod_subdir,
            '}',
        ])
        gcc_mod = os.path.join(mod_prefix, 'Core', 'GCC', '6.4.0-2.28')
        write_file(gcc_mod, extra_modtxt, append=True)

        extra_modtxt = '\n'.join([
            'if { [ file isdirectory [ file join $env(HOME) "modules/all/%s" ] ] } {' % openmpi_mod_subdir,
            '    module use [ file join $env(HOME) "modules/all/%s" ]' % openmpi_mod_subdir,
            '}',
        ])
        openmpi_mod = os.path.join(mod_prefix, gcc_mod_subdir, 'OpenMPI', '2.1.2')
        write_file(openmpi_mod, extra_modtxt, append=True)

        args = [
            os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0-gompi-2018a.eb'),
            '--installpath=%s' % home,
            '--unittest-file=%s' % self.logfile,
            '--force',
            '--module-naming-scheme=HierarchicalMNS',
            '--try-toolchain=foss,2018a',
        ]
        with self.mocked_stdout_stderr():
            self.eb_main(args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)

        mod_ext = ''
        if get_module_syntax() == 'Lua':
            mod_ext = '.lua'

        toy_mod = os.path.join(home, 'modules', 'all', openmpi_mod_subdir, 'toy', '0.0' + mod_ext)
        toy_modtxt = read_file(toy_mod)

        # No math libs in original toolchain, --try-toolchain is too clever to upgrade it beyond necessary
        for modname in ['FFTW', 'OpenBLAS', 'ScaLAPACK']:
            regex = re.compile('load.*' + modname, re.M)
            self.assertFalse(regex.search(toy_modtxt), "Pattern '%s' not found in: %s" % (regex.pattern, toy_modtxt))

        for modname in ['GCC', 'OpenMPI']:
            regex = re.compile('load.*' + modname, re.M)
            self.assertFalse(regex.search(toy_modtxt), "Pattern '%s' not found in: %s" % (regex.pattern, toy_modtxt))

        # also check with Lua GCC/OpenMPI modules in case of Lmod
        if isinstance(self.modtool, Lmod):

            # remove Tcl modules for GCC/OpenMPI in hierarchy
            remove_file(gcc_mod)
            remove_file(openmpi_mod)

            # we also need to clear the 'module show' cache since we're replacing modules in the same $MODULEPATH
            from easybuild.tools.modules import MODULE_SHOW_CACHE
            MODULE_SHOW_CACHE.clear()

            # make very sure toy module is regenerated
            remove_file(toy_mod)

            mod_prefix = os.path.join(self.test_installpath, 'modules', 'all')

            # create minimal GCC module that extends $MODULEPATH with Compiler/GCC/6.4.0-2.28 in both locations
            gcc_mod_txt = '\n'.join([
                'setenv("EBROOTGCC", "/tmp/software/Core/GCC/6.4.0-2.28")',
                'setenv("EBVERSIONGCC", "6.4.0-2.28")',
                'prepend_path("MODULEPATH", "%s/%s")' % (mod_prefix, gcc_mod_subdir),
                'if isDir(pathJoin(os.getenv("HOME"), "modules/all/%s")) then' % gcc_mod_subdir,
                '    prepend_path("MODULEPATH", pathJoin(os.getenv("HOME"), "modules/all/%s"))' % gcc_mod_subdir,
                'end',
            ])
            write_file(gcc_mod + '.lua', gcc_mod_txt)

            # create minimal OpenMPI module that extends $MODULEPATH
            # with MPI/GCC/6.4.0-2.28/OpenMPi/2.1.2 in both locations
            openmpi_mod_txt = '\n'.join([
                'setenv("EBROOTOPENMPI", "/tmp/software/Compiler/GCC/6.4.0-2.28/OpenMPI/2.1.2")',
                'setenv("EBVERSIONOPENMPI", "2.1.2")',
                'prepend_path("MODULEPATH", "%s/%s")' % (mod_prefix, openmpi_mod_subdir),
                'if isDir(pathJoin(os.getenv("HOME"), "modules/all/%s")) then' % openmpi_mod_subdir,
                '    prepend_path("MODULEPATH", pathJoin(os.getenv("HOME"), "modules/all/%s"))' % openmpi_mod_subdir,
                'end',
            ])
            write_file(openmpi_mod + '.lua', openmpi_mod_txt)

            with self.mocked_stdout_stderr():
                self.eb_main(args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)
            toy_modtxt = read_file(toy_mod)

            # No math libs in original toolchain, --try-toolchain is too clever to upgrade it beyond necessary
            for modname in ['FFTW', 'OpenBLAS', 'ScaLAPACK']:
                regex = re.compile('load.*' + modname, re.M)
                self.assertFalse(regex.search(toy_modtxt), "Pattern '%s' not found in: %s" % (regex.pattern,
                                                                                              toy_modtxt))

            for modname in ['GCC', 'OpenMPI']:
                regex = re.compile('load.*' + modname, re.M)
                self.assertFalse(regex.search(toy_modtxt),
                                 "Pattern '%s' not found in: %s" % (regex.pattern, toy_modtxt))

    def test_toy_advanced(self):
        """Test toy build with extensions and non-system toolchain."""
        test_dir = os.path.abspath(os.path.dirname(__file__))
        os.environ['MODULEPATH'] = os.path.join(test_dir, 'modules')
        test_ec = os.path.join(test_dir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-gompi-2018a-test.eb')
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, versionsuffix='-gompi-2018a-test', extra_args=['--debug'])

        toy_module = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0-gompi-2018a-test')
        if get_module_syntax() == 'Lua':
            toy_module += '.lua'
        toy_mod_txt = read_file(toy_module)

        patterns = [
            '^setenv.*EBEXTSLISTTOY.*ulimit,bar-0.0,barbar-1.2',
            # set by ToyExtension easyblock used to install extensions
            '^setenv.*TOY_EXT_BAR.*bar',
            '^setenv.*TOY_EXT_BARBAR.*barbar',
        ]
        for pattern in patterns:
            self.assertTrue(re.search(pattern, toy_mod_txt, re.M), "Pattern '%s' found in: %s" % (pattern, toy_mod_txt))

        toy_installdir = os.path.join(self.test_installpath, 'software', 'toy', '0.0-gompi-2018a-test')
        toy_libs_path = os.path.join(toy_installdir, 'toy_libs_path.txt')
        self.assertTrue(os.path.exists(toy_libs_path))
        txt = read_file(toy_libs_path)
        regex = re.compile('^TOY_EXAMPLES=examples$')
        self.assertTrue(regex.match(txt), f"Pattern '{regex.pattern}' should match in: {txt}")

    def test_toy_advanced_filter_deps(self):
        """Test toy build with extensions, and filtered build dependency."""
        # test case for bug https://github.com/easybuilders/easybuild-framework/pull/2515

        test_dir = os.path.abspath(os.path.dirname(__file__))
        os.environ['MODULEPATH'] = os.path.join(test_dir, 'modules')
        toy_ec = os.path.join(test_dir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-gompi-2018a-test.eb')

        toy_ec_txt = read_file(toy_ec)
        # add FFTW as build dependency, just to filter it out again
        toy_ec_txt += "\nbuilddependencies = [('FFTW', '3.3.3')]"

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, toy_ec_txt)

        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, versionsuffix='-gompi-2018a-test', extra_args=["--filter-deps=FFTW"])

        toy_module = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0-gompi-2018a-test')
        if get_module_syntax() == 'Lua':
            toy_module += '.lua'
        self.assertExists(toy_module)

    def test_toy_hidden_cmdline(self):
        """Test installing a hidden module using the '--hidden' command line option."""
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        ec_file = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=ec_file, extra_args=['--hidden'], verify=False)
        # module file is hidden
        toy_module = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '.0.0')
        if get_module_syntax() == 'Lua':
            toy_module += '.lua'
        self.assertExists(toy_module, 'Found hidden module %s' % toy_module)
        # installed software is not hidden
        toybin = os.path.join(self.test_installpath, 'software', 'toy', '0.0', 'bin', 'toy')
        self.assertExists(toybin)

    def test_toy_hidden_easyconfig(self):
        """Test installing a hidden module using the 'hidden = True' easyconfig parameter."""
        # copy toy easyconfig file, and add hiding option to it
        topdir = os.path.dirname(os.path.abspath(__file__))
        ec_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        shutil.copy2(ec_file, self.test_prefix)
        ec_file = os.path.join(self.test_prefix, 'toy-0.0.eb')
        write_file(ec_file, "\nhidden = True\n", append=True)
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=ec_file, verify=False)
        # module file is hidden
        toy_module = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '.0.0')
        if get_module_syntax() == 'Lua':
            toy_module += '.lua'
        self.assertExists(toy_module, 'Found hidden module %s' % toy_module)
        # installed software is not hidden
        toybin = os.path.join(self.test_installpath, 'software', 'toy', '0.0', 'bin', 'toy')
        self.assertExists(toybin)

    def test_module_filepath_tweaking(self):
        """Test using --suffix-modules-path."""
        mns_path = "easybuild.tools.module_naming_scheme.test_module_naming_scheme"
        __import__(mns_path, globals(), locals(), [''])

        topdir = os.path.dirname(os.path.abspath(__file__))
        eb_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        args = [
            eb_file,
            '--force',
            '--debug',
            '--suffix-modules-path=foobarbaz',
            '--module-naming-scheme=TestModuleNamingScheme',
        ]
        with self.mocked_stdout_stderr():
            self.eb_main(args, do_build=True, verbose=True)
        mod_file_prefix = os.path.join(self.test_installpath, 'modules')
        mod_file_suffix = ''
        if get_module_syntax() == 'Lua':
            mod_file_suffix += '.lua'

        self.assertExists(os.path.join(mod_file_prefix, 'foobarbaz', 'toy', '0.0' + mod_file_suffix))
        self.assertExists(os.path.join(mod_file_prefix, 'TOOLS', 'toy', '0.0' + mod_file_suffix))
        self.assertTrue(os.path.islink(os.path.join(mod_file_prefix, 'TOOLS', 'toy', '0.0' + mod_file_suffix)))
        self.assertExists(os.path.join(mod_file_prefix, 't', 'toy', '0.0' + mod_file_suffix))
        self.assertTrue(os.path.islink(os.path.join(mod_file_prefix, 't', 'toy', '0.0' + mod_file_suffix)))

    def test_toy_archived_easyconfig(self):
        """Test archived easyconfig for a succesful build."""
        repositorypath = os.path.join(self.test_installpath, 'easyconfigs_archive')
        extra_args = [
            '--repository=FileRepository',
            '--repositorypath=%s' % repositorypath,
        ]
        with self.mocked_stdout_stderr():
            self._test_toy_build(raise_error=True, extra_args=extra_args)

        archived_ec = os.path.join(repositorypath, 'toy', 'toy-0.0.eb')
        self.assertExists(archived_ec)
        ec = EasyConfig(archived_ec)
        self.assertEqual(ec.name, 'toy')
        self.assertEqual(ec.version, '0.0')

    def test_toy_patches(self):
        """Test whether patches are being copied to install directory and easyconfigs archive"""
        repositorypath = os.path.join(self.test_installpath, 'easyconfigs_archive')
        extra_args = [
            '--repository=FileRepository',
            '--repositorypath=%s' % repositorypath,
        ]
        with self.mocked_stdout_stderr():
            self._test_toy_build(raise_error=True, extra_args=extra_args)

        installdir = os.path.join(self.test_installpath, 'software', 'toy', '0.0')

        patch_file = os.path.join(installdir, 'easybuild', 'toy-0.0_fix-silly-typo-in-printf-statement.patch')
        self.assertExists(patch_file)

        archived_patch_file = os.path.join(repositorypath, 'toy', 'toy-0.0_fix-silly-typo-in-printf-statement.patch')
        self.assertTrue(os.path.isfile(archived_patch_file))

    def test_toy_extension_patches_postinstallcmds(self):
        """Test install toy that includes extensions with patches and postinstallcmds."""
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec)

        # create file that we'll copy via 'patches'
        write_file(os.path.join(self.test_prefix, 'test.txt'), 'test123')

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ec_txt = f"{toy_ec_txt}\n" + textwrap.dedent("""
            exts_defaultclass = "DummyExtension"
            exts_list = [
               ("bar", "0.0", {
                   "buildopts": " && ls -l test.txt",
                   "patches": [
                       "bar-0.0_fix-silly-typo-in-printf-statement.patch",  # normal patch
                       ("bar-0.0_fix-very-silly-typo-in-printf-statement.patch", 0), # patch with patch level
                       ("test.txt", "."),  # file to copy to build dir (not a real patch file)
                   ],
                   "post_install_cmds": ["touch %(installdir)s/created-via-postinstallcmds.txt"],
                   "post_install_patches": [("test.txt", "test_ext.txt")],
                   "post_install_msgs": ["Hello World!"],
               }),
            ]
        """)
        write_file(test_ec, test_ec_txt)

        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, extra_args=['--disable-cleanup-builddir'])
            self.assertIn("Hello World!", self.get_stdout())

        installdir = os.path.join(self.test_installpath, 'software', 'toy', '0.0')

        # make sure that patches were actually applied (without them the message producded by 'bar' is different)
        bar_bin = os.path.join(installdir, 'bin', 'bar')
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(bar_bin)
        self.assertEqual(res.output, "I'm a bar, and very very proud of it.\n")

        # verify that post-install command for 'bar' extension was executed
        fn = 'created-via-postinstallcmds.txt'
        self.assertExists(os.path.join(installdir, fn))
        # Same for all patches
        self.assertExists(os.path.join(self.test_buildpath, 'toy', '0.0', 'system-system',
                                       'bar', 'bar-0.0', 'test.txt'))
        self.assertExists(os.path.join(installdir, 'test_ext.txt'))

        # make sure that patch file for extension was copied to 'easybuild' subdir in installation directory
        easybuild_subdir = os.path.join(installdir, 'easybuild')
        patches = sorted(os.path.basename(x) for x in glob.glob(os.path.join(easybuild_subdir, '*.patch')))
        expected_patches = [
            'bar-0.0_fix-silly-typo-in-printf-statement.patch',
            'bar-0.0_fix-very-silly-typo-in-printf-statement.patch',
            'toy-0.0_fix-silly-typo-in-printf-statement.patch',
        ]
        self.assertEqual(patches, expected_patches)

    def test_toy_extension_sources(self):
        """Test install toy that includes extensions with 'sources' spec (as single-item list)."""
        topdir = os.path.dirname(os.path.abspath(__file__))
        test_ecs = os.path.join(topdir, 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec)

        test_ec = os.path.join(self.test_prefix, 'test.eb')

        bar_sources_specs = [
            '["bar-%(version)s.tar.gz"]',  # single-element list
            '"bar-%(version)s.tar.gz"',  # string value
        ]

        for bar_sources_spec in bar_sources_specs:

            # test use of single-element list in 'sources' with just the filename
            test_ec_txt = '\n'.join([
                toy_ec_txt,
                'exts_defaultclass = "DummyExtension"',
                'exts_list = [',
                '   ("bar", "0.0", {',
                '       "sources": %s,' % bar_sources_spec,
                '   }),',
                ']',
            ])
            write_file(test_ec, test_ec_txt)
            with self.mocked_stdout_stderr():
                self._test_toy_build(ec_file=test_ec)

            # copy bar-0.0.tar.gz to <tmpdir>/bar-0.0-local.tar.gz, to be used below
            test_source_path = os.path.join(self.test_prefix, 'sources')
            toy_ext_sources = os.path.join(topdir, 'sandbox', 'sources', 'toy', 'extensions')

            bar_source = os.path.join(toy_ext_sources, 'bar-0.0.tar.gz')
            copy_file(bar_source, os.path.join(test_source_path, 'bar-0.0-local.tar.gz'))

            bar_patch = os.path.join(toy_ext_sources, 'bar-0.0_fix-silly-typo-in-printf-statement.patch')
            copy_file(bar_patch, os.path.join(self.test_prefix, 'bar-0.0_fix-local.patch'))

            # verify that source_urls and patches are picked up and taken into account
            # when 'sources' is used to specify extension sources

            bar_sources_spec = bar_sources_spec.replace('bar-%(version)s.tar.gz', 'bar-0.0-local.tar.gz')

            test_ec_txt = '\n'.join([
                toy_ec_txt,
                'exts_defaultclass = "DummyExtension"',
                'exts_list = [',
                '   ("bar", "0.0", {',
                '       "source_urls": ["file://%s"],' % test_source_path,
                '       "sources": %s,' % bar_sources_spec,
                '       "patches": ["bar-%(version)s_fix-local.patch"],',
                '   }),',
                ']',
            ])
            write_file(test_ec, test_ec_txt)
            with self.mocked_stdout_stderr():
                self._test_toy_build(ec_file=test_ec, raise_error=True)

            # check that checksums are picked up and verified
            test_ec_txt = '\n'.join([
                toy_ec_txt,
                'exts_defaultclass = "DummyExtension"',
                'exts_list = [',
                '   ("bar", "0.0", {',
                '       "source_urls": ["file://%s"],' % test_source_path,
                '       "sources": %s,' % bar_sources_spec,
                '       "patches": ["bar-%(version)s_fix-local.patch"],',
                # note: purposely incorrect (SHA256) checksums! (to check if checksum verification works)
                '       "checksums": [',
                '           "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",',
                '           "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",',
                '       ],',
                '   }),',
                ']',
            ])
            write_file(test_ec, test_ec_txt)

            error_pattern = r"Checksum verification for extension source bar-0.0-local.tar.gz failed"
            with self.mocked_stdout_stderr():
                self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, ec_file=test_ec,
                                      raise_error=True, verbose=False)

            # test again with correct checksum for bar-0.0.tar.gz, but faulty checksum for patch file
            test_ec_txt = '\n'.join([
                toy_ec_txt,
                'exts_defaultclass = "DummyExtension"',
                'exts_list = [',
                '   ("bar", "0.0", {',
                '       "source_urls": ["file://%s"],' % test_source_path,
                '       "sources": %s,' % bar_sources_spec,
                '       "patches": ["bar-%(version)s_fix-local.patch"],',
                '       "checksums": [',
                '           "f3676716b610545a4e8035087f5be0a0248adee0abb3930d3edb76d498ae91e7",',
                # note: purposely incorrect checksum for patch!
                '           "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",',
                '       ],',
                '   }),',
                ']',
            ])
            write_file(test_ec, test_ec_txt)

            error_pattern = r"Checksum verification for extension patch bar-0.0_fix-local.patch failed"
            with self.mocked_stdout_stderr():
                self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, ec_file=test_ec,
                                      raise_error=True, verbose=False)

            # test again with correct checksums
            test_ec_txt = '\n'.join([
                toy_ec_txt,
                'exts_defaultclass = "DummyExtension"',
                'exts_list = [',
                '   ("bar", "0.0", {',
                '       "source_urls": ["file://%s"],' % test_source_path,
                '       "sources": %s,' % bar_sources_spec,
                '       "patches": ["bar-%(version)s_fix-local.patch"],',
                '       "checksums": [',
                '           "f3676716b610545a4e8035087f5be0a0248adee0abb3930d3edb76d498ae91e7",',
                '           "84db53592e882b5af077976257f9c7537ed971cb2059003fd4faa05d02cae0ab",',
                '       ],',
                '   }),',
                ']',
            ])
            write_file(test_ec, test_ec_txt)
            with self.mocked_stdout_stderr():
                self._test_toy_build(ec_file=test_ec, raise_error=True)

    def test_toy_extension_extract_cmd(self):
        """Test for custom extract_cmd specified for an extension."""
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec)

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ec_txt = '\n'.join([
            toy_ec_txt,
            'exts_defaultclass = "DummyExtension"',
            'exts_list = [',
            '   ("bar", "0.0", {',
            # deliberately incorrect custom extract command, just to verify that it's picked up
            '       "sources": [{',
            '           "filename": "bar-%(version)s.tar.gz",',
            '           "extract_cmd": "unzip %s",',
            '       }],',
            '   }),',
            ']',
        ])
        write_file(test_ec, test_ec_txt)

        error_pattern = r"shell command 'unzip \.\.\.' failed with exit code 9 in extensions step for test.eb"
        with self.mocked_stdout_stderr():
            # for now, we expect subprocess.CalledProcessError, but eventually 'run' function will
            # do proper error reporting
            self.assertErrorRegex(EasyBuildError, error_pattern,
                                  self._test_toy_build, ec_file=test_ec, raise_error=True, verbose=False)

    def test_toy_extension_sources_git_config(self):
        """Test install toy that includes extensions with 'sources' spec including 'git_config'."""
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec)

        # Tar-ball which should be created via 'git_config', and one file
        ext_tgz = 'exts-git.tar.gz'
        ext_tarball = os.path.join(self.test_sourcepath, 't', 'toy', ext_tgz)
        ext_tarfile = 'a_directory/a_file.txt'

        # Dummy source code required for extensions build_step to pass
        ext_code = 'int main() { return 0; }'
        ext_cfile = 'exts-git.c'

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ec_txt = '\n'.join([
            toy_ec_txt,
            'prebuildopts = "echo \\\"%s\\\" > %s && ",' % (ext_code, ext_cfile),
            'exts_defaultclass = "DummyExtension"',
            'exts_list = [',
            '   ("exts-git", "0.0", {',
            '       "buildopts": "&& ls -l %s %s",' % (ext_tarball, ext_tarfile),
            '       "sources": {',
            '           "filename": "%(name)s.tar.gz",',
            '           "git_config": {',
            '               "repo_name": "testrepository",',
            '               "url": "https://github.com/easybuilders",',
            '               "tag": "main",',
            '           },',
            '       },',
            '   }),',
            ']',
        ])
        write_file(test_ec, test_ec_txt)
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec)

    def test_toy_module_fulltxt(self):
        """Strict text comparison of generated module file."""
        self.test_toy_tweaked()

        toy_module = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0-tweaked')
        if get_module_syntax() == 'Lua':
            toy_module += '.lua'
        toy_mod_txt = read_file(toy_module)

        modloadmsg_tcl = [
            r'puts stderr "THANKS FOR LOADING ME',
            r'I AM toy v0.0',
            '"',
        ]
        modloadmsg_lua = [
            r'io.stderr:write\(\[==\[THANKS FOR LOADING ME',
            r'I AM toy v0.0',
            r'\]==\]\)',
        ]

        help_txt = '\n'.join([
            r'Description',
            r'===========',
            r'Toy C program, 100% toy.',
            r'',
            r'',
            r'Usage',
            r'=====',
            r'This toy is easy to use, 100%!',
            r'',
            r'',
            r'Examples',
            r'========',
            r'No example available, 0% complete',
            r'',
            r'',
            r'Citing',
            r'======',
            r'If you use this package, please cite our paper https://ieeexplore.ieee.org/document/6495863',
            r'',
            r'',
            r'More information',
            r'================',
            r' - Homepage: https://easybuilders.github.io/easybuild',
            r' - Documentation:',
            r'    - \$EBROOTTOY/share/doc/toy/readme.txt',
            r'    - \$EBROOTTOY/share/doc/toy/html/index.html',
            r'    - https://easybuilders.github.io/easybuild/toy/docs.html',
            r' - Upstream contact: support@toy.org',
            r' - Site contacts:',
            r'    - Jim Admin',
            r'    - Jane Admin',
        ])
        if get_module_syntax() == 'Lua':
            mod_txt_regex_pattern = '\n'.join([
                r'help\(\[==\[',
                r'',
                help_txt,
                r'\]==\]\)',
                r'',
                r'whatis\(\[==\[Description: Toy C program, 100% toy.\]==\]\)',
                r'whatis\(\[==\[Homepage: https://easybuilders.github.io/easybuild\]==\]\)',
                r'whatis\(\[==\[URL: https://easybuilders.github.io/easybuild\]==\]\)',
                r'',
                r'local root = "%s/software/toy/0.0-tweaked"' % self.test_installpath,
                r'',
                r'conflict\("toy"\)',
                r'',
                r'prepend_path\("CMAKE_PREFIX_PATH", root\)',
                r'prepend_path\("LD_LIBRARY_PATH", pathJoin\(root, "lib"\)\)',
                r'prepend_path\("LIBRARY_PATH", pathJoin\(root, "lib"\)\)',
                r'prepend_path\("PATH", pathJoin\(root, "bin"\)\)',
                r'prepend_path\("SOMEPATH", pathJoin\(root, "foo", "bar"\)\)',
                r'prepend_path\("SOMEPATH", pathJoin\(root, "baz"\)\)',
                r'prepend_path\("SOMEPATH", root\)',
                r'append_path\("SOMEPATH_APPEND", pathJoin\(root, "qux", "fred"\)\)',
                r'append_path\("SOMEPATH_APPEND", pathJoin\(root, "thud"\)\)',
                r'append_path\("SOMEPATH_APPEND", root\)',
                r'setenv\("EBROOTTOY", root\)',
                r'setenv\("EBVERSIONTOY", "0.0"\)',
                r'setenv\("EBDEVELTOY", pathJoin\(root, "easybuild", "toy-0.0-tweaked-easybuild-devel"\)\)',
                r'',
                r'setenv\("FOO", "bar"\)',
                r'',
                r'if mode\(\) == "load" then',
            ] + modloadmsg_lua + [
                r'end',
                r'setenv\("TOY", "toy-0.0"\)',
                r'-- Built with EasyBuild version .*',
                r'io.stderr:write\("oh hai\!"\)$',
            ])
        elif get_module_syntax() == 'Tcl':
            mod_txt_regex_pattern = '\n'.join([
                r'^#%Module',
                r'proc ModulesHelp { } {',
                r'    puts stderr {',
                r'',
                help_txt,
                r'    }',
                r'}',
                r'',
                r'module-whatis {Description: Toy C program, 100% toy.}',
                r'module-whatis {Homepage: https://easybuilders.github.io/easybuild}',
                r'module-whatis {URL: https://easybuilders.github.io/easybuild}',
                r'',
                r'set root %s/software/toy/0.0-tweaked' % self.test_installpath,
                r'',
                r'conflict toy',
                r'',
                r'prepend-path	CMAKE_PREFIX_PATH		\$root',
                r'prepend-path	LD_LIBRARY_PATH		\$root/lib',
                r'prepend-path	LIBRARY_PATH		\$root/lib',
                r'prepend-path	PATH		\$root/bin',
                r'prepend-path	SOMEPATH		\$root/foo/bar',
                r'prepend-path	SOMEPATH		\$root/baz',
                r'prepend-path	SOMEPATH		\$root',
                r'append-path	SOMEPATH_APPEND		\$root/qux/fred',
                r'append-path	SOMEPATH_APPEND		\$root/thud',
                r'append-path	SOMEPATH_APPEND		\$root',
                r'setenv	EBROOTTOY		"\$root"',
                r'setenv	EBVERSIONTOY		"0.0"',
                r'setenv	EBDEVELTOY		"\$root/easybuild/toy-0.0-tweaked-easybuild-devel"',
                r'',
                r'setenv	FOO		"bar"',
                r'',
                r'if { \[ module-info mode load \] } {',
            ] + modloadmsg_tcl + [
                r'}',
                r'setenv	TOY		"toy-0.0"',
                r'# Built with EasyBuild version .*',
                r'puts stderr "oh hai\!"$',
            ])
        else:
            self.fail("Unknown module syntax: %s" % get_module_syntax())

        mod_txt_regex = re.compile(mod_txt_regex_pattern)
        msg = "Pattern '%s' matches with: %s" % (mod_txt_regex.pattern, toy_mod_txt)
        self.assertTrue(mod_txt_regex.match(toy_mod_txt), msg)

    def test_external_dependencies(self):
        """Test specifying external (build) dependencies."""

        topdir = os.path.dirname(os.path.abspath(__file__))
        ectxt = read_file(os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-deps.eb'))
        toy_ec = os.path.join(self.test_prefix, 'toy-0.0-external-deps.eb')

        # just specify some of the test modules we ship, doesn't matter where they come from
        extraectxt = "\ndependencies += [('foobar/1.2.3', EXTERNAL_MODULE)]"
        extraectxt += "\nbuilddependencies = [('somebuilddep/0.1', EXTERNAL_MODULE)]"
        extraectxt += "\nversionsuffix = '-external-deps'"
        write_file(toy_ec, ectxt + extraectxt)

        # install dummy modules
        modulepath = os.path.join(self.test_prefix, 'modules')
        for mod in ['intel/2018a', 'GCC/6.4.0-2.28', 'foobar/1.2.3', 'somebuilddep/0.1']:
            mkdir(os.path.join(modulepath, os.path.dirname(mod)), parents=True)
            write_file(os.path.join(modulepath, mod), "#%Module")

        installed_test_modules = os.path.join(self.test_installpath, 'modules', 'all')
        self.reset_modulepath([modulepath, installed_test_modules])

        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=toy_ec, versionsuffix='-external-deps', verbose=True, raise_error=True)

        with self.saved_env():
            self.modtool.load(['toy/0.0-external-deps'])
            # note build dependency is not loaded
            mods = ['intel/2018a', 'GCC/6.4.0-2.28', 'foobar/1.2.3', 'toy/0.0-external-deps']
            self.assertEqual([x['mod_name'] for x in self.modtool.list()], mods)

        # check behaviour when a non-existing external (build) dependency is included
        extraectxt = "\nbuilddependencies = [('nosuchbuilddep/0.0.0', EXTERNAL_MODULE)]"
        extraectxt += "\nversionsuffix = '-external-deps-broken1'"
        write_file(toy_ec, ectxt + extraectxt)

        if isinstance(self.modtool, Lmod):
            err_msg = r"Module command \\'.*load nosuchbuilddep/0.0.0\\' failed"
        else:
            err_msg = r"Unable to locate a modulefile for 'nosuchbuilddep/0.0.0'"

        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, err_msg, self._test_toy_build, ec_file=toy_ec,
                                  raise_error=True, verbose=False)

        extraectxt = "\ndependencies += [('nosuchmodule/1.2.3', EXTERNAL_MODULE)]"
        extraectxt += "\nversionsuffix = '-external-deps-broken2'"
        write_file(toy_ec, ectxt + extraectxt)

        if isinstance(self.modtool, Lmod):
            err_msg = r"Module command \\'.*load nosuchmodule/1.2.3\\' failed"
        else:
            err_msg = r"Unable to locate a modulefile for 'nosuchmodule/1.2.3'"

        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, err_msg, self._test_toy_build, ec_file=toy_ec,
                                  raise_error=True, verbose=False)

        # --dry-run still works when external modules are missing; external modules are treated as if they were there
        with self.mocked_stdout_stderr():
            outtxt = self._test_toy_build(ec_file=toy_ec, verbose=True, extra_args=['--dry-run'], verify=False)
        regex = re.compile(r"^ \* \[ \] .* \(module: toy/0.0-external-deps-broken2\)", re.M)
        self.assertTrue(regex.search(outtxt), "Pattern '%s' found in: %s" % (regex.pattern, outtxt))

    def test_module_only(self):
        """Test use of --module-only."""
        ec_files_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        ec_file = os.path.join(ec_files_path, 't', 'toy', 'toy-0.0-deps.eb')
        toy_mod = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0-deps')

        # only consider provided test modules
        self.reset_modulepath([os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modules')])

        # sanity check fails without --force if software is not installed yet
        common_args = [
            ec_file,
            '--debug',
            '--unittest-file=%s' % self.logfile,
            '--robot=%s' % ec_files_path,
            '--module-syntax=Tcl',
        ]
        args = common_args + ['--module-only']
        err_msg = "Sanity check failed"
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, err_msg, self.eb_main, args, do_build=True, raise_error=True)
        self.assertNotExists(toy_mod)

        with self.mocked_stdout_stderr():
            self.eb_main(args + ['--force'], do_build=True, raise_error=True)
        self.assertExists(toy_mod)

        # make sure load statements for dependencies are included in additional module file generated with --module-only
        modtxt = read_file(toy_mod)
        self.assertTrue(re.search('(load|depends[-_]on).*intel/2018a', modtxt),
                        "load statement for intel/2018a found in module")
        self.assertTrue(re.search('(load|depends[-_]on).*GCC/6.4.0-2.28', modtxt),
                        "load statement for GCC/6.4.0-2.28 found in module")

        os.remove(toy_mod)

        # --module-only --rebuild should run sanity check
        rebuild_args = args + ['--rebuild']
        err_msg = "Sanity check failed"
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, err_msg, self.eb_main, rebuild_args, do_build=True, raise_error=True)
        self.assertNotExists(toy_mod)

        # installing another module under a different naming scheme and using Lua module syntax works fine

        # first actually build and install toy software + module
        prefix = os.path.join(self.test_installpath, 'software', 'toy', '0.0-deps')
        with self.mocked_stdout_stderr():
            self.eb_main(common_args + ['--force'], do_build=True, raise_error=True)
        self.assertExists(toy_mod)
        self.assertExists(os.path.join(self.test_installpath, 'software', 'toy', '0.0-deps', 'bin'))
        modtxt = read_file(toy_mod)
        self.assertTrue(re.search("set root %s" % prefix, modtxt))
        self.assertEqual(len(os.listdir(os.path.join(self.test_installpath, 'software'))), 2)
        self.assertEqual(len(os.listdir(os.path.join(self.test_installpath, 'software', 'toy'))), 1)

        # install (only) additional module under a hierarchical MNS
        args = common_args + [
            '--module-only',
            '--module-naming-scheme=MigrateFromEBToHMNS',
        ]
        toy_core_mod = os.path.join(self.test_installpath, 'modules', 'all', 'Core', 'toy', '0.0-deps')
        self.assertNotExists(toy_core_mod)
        with self.mocked_stdout_stderr():
            self.eb_main(args, do_build=True, raise_error=True)
        self.assertExists(toy_core_mod)
        # existing install is reused
        modtxt2 = read_file(toy_core_mod)
        self.assertTrue(re.search("set root %s" % prefix, modtxt2))
        self.assertEqual(len(os.listdir(os.path.join(self.test_installpath, 'software'))), 3)
        self.assertEqual(len(os.listdir(os.path.join(self.test_installpath, 'software', 'toy'))), 1)

        # make sure load statements for dependencies are included
        modtxt = read_file(toy_core_mod)
        self.assertTrue(re.search('(load|depends[-_]on).*intel/2018a', modtxt),
                        "load statement for intel/2018a found in module")

        # Test we can create a module even for an installation where we don't have write permissions
        os.remove(toy_core_mod)
        # remove the write permissions on the installation
        adjust_permissions(prefix, stat.S_IRUSR | stat.S_IXUSR, relative=False)
        self.assertNotExists(toy_core_mod)
        with self.mocked_stdout_stderr():
            self.eb_main(args, do_build=True, raise_error=True)
        self.assertExists(toy_core_mod)
        # existing install is reused
        modtxt2 = read_file(toy_core_mod)
        self.assertTrue(re.search("set root %s" % prefix, modtxt2))
        self.assertEqual(len(os.listdir(os.path.join(self.test_installpath, 'software'))), 3)
        self.assertEqual(len(os.listdir(os.path.join(self.test_installpath, 'software', 'toy'))), 1)

        # make sure load statements for dependencies are included
        modtxt = read_file(toy_core_mod)
        self.assertTrue(re.search('(load|depends[-_]on).*intel/2018a', modtxt),
                        "load statement for intel/2018a found in module")

        os.remove(toy_core_mod)
        os.remove(toy_mod)

        # test installing (only) additional module in Lua syntax (if Lmod is available)
        lmod_abspath = os.environ.get('LMOD_CMD') or which('lmod')
        if lmod_abspath is not None:
            args = common_args[:-1] + [
                '--allow-modules-tool-mismatch',
                '--module-only',
                '--module-syntax=Lua',
                '--modules-tool=Lmod',
            ]
            self.assertNotExists(toy_mod + '.lua')
            with self.mocked_stdout_stderr():
                self.eb_main(args, do_build=True, raise_error=True)
            self.assertExists(toy_mod + '.lua')
            # existing install is reused
            modtxt3 = read_file(toy_mod + '.lua')
            self.assertTrue(re.search('local root = "%s"' % prefix, modtxt3))
            self.assertEqual(len(os.listdir(os.path.join(self.test_installpath, 'software'))), 3)
            self.assertEqual(len(os.listdir(os.path.join(self.test_installpath, 'software', 'toy'))), 1)

            # make sure load statements for dependencies are included
            modtxt = read_file(toy_mod + '.lua')
            self.assertTrue(re.search('(load|depends[-_]on).*intel/2018a', modtxt),
                            "load statement for intel/2018a found in module")

    def test_module_only_extensions(self):
        """
        Test use of --module-only with extensions involved.
        Sanity check should catch problems with extensions,
        extensions can be skipped using --skip-exts.
        """
        topdir = os.path.abspath(os.path.dirname(__file__))
        toy_ec = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        toy_mod = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_mod += '.lua'

        test_ec = os.path.join(self.test_prefix, 'test.ec')
        test_ec_txt = read_file(toy_ec)
        test_ec_txt += '\n' + '\n'.join([
            "sanity_check_commands = ['barbar', 'toy']",
            "sanity_check_paths = {'files': ['bin/barbar', 'bin/toy'], 'dirs': ['bin']}",
            "exts_defaultclass = 'DummyExtension'",
            "exts_list = [",
            "    ('barbar', '0.0', {",
            "        'start_dir': 'src',",
            "        'exts_filter': ('ls -l lib/lib%(ext_name)s.a', ''),",
            "    })",
            "]",
        ])
        write_file(test_ec, test_ec_txt)

        # clean up $MODULEPATH so only modules in test prefix dir are found
        self.reset_modulepath([os.path.join(self.test_installpath, 'modules', 'all')])
        self.assertEqual(self.modtool.available('toy'), [])

        # install toy/0.0
        with self.mocked_stdout_stderr():
            self.eb_main([test_ec], do_build=True, raise_error=True)

        # remove module file so we can try --module-only
        remove_file(toy_mod)

        # make sure that sources for extensions can't be found,
        # they should not be needed when using --module-only
        # (cfr. https://github.com/easybuilders/easybuild-framework/issues/3849)
        del os.environ['EASYBUILD_SOURCEPATH']

        # first try normal --module-only, should work fine
        with self.mocked_stdout_stderr():
            self.eb_main([test_ec, '--module-only'], do_build=True, raise_error=True)
        self.assertExists(toy_mod)
        remove_file(toy_mod)

        # rename file required for barbar extension, so we can check whether sanity check catches it
        libbarbar = os.path.join(self.test_installpath, 'software', 'toy', '0.0', 'lib', 'libbarbar.a')
        move_file(libbarbar, libbarbar + '.foobar')

        # check whether sanity check fails now when using --module-only
        error_pattern = 'Sanity check failed: command "ls -l lib/libbarbar.a" failed'
        for extra_args in (['--module-only'], ['--module-only', '--rebuild']):
            with self.mocked_stdout_stderr():
                self.assertErrorRegex(EasyBuildError, error_pattern, self.eb_main, [test_ec] + extra_args,
                                      do_build=True, raise_error=True)
        self.assertNotExists(toy_mod)

        # failing sanity check for barbar extension is ignored when using --module-only --skip-extensions
        for extra_args in (['--module-only'], ['--module-only', '--rebuild']):
            with self.mocked_stdout_stderr():
                self.eb_main([test_ec, '--skip-extensions'] + extra_args, do_build=True, raise_error=True)
            self.assertExists(toy_mod)
            remove_file(toy_mod)

        # we can force module generation via --force (which skips sanity check entirely)
        with self.mocked_stdout_stderr():
            self.eb_main([test_ec, '--module-only', '--force'], do_build=True, raise_error=True)
        self.assertExists(toy_mod)

    def test_toy_exts_parallel(self):
        """
        Test parallel installation of extensions (--parallel-extensions-install)
        """
        topdir = os.path.abspath(os.path.dirname(__file__))
        toy_ec = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        toy_mod = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_mod += '.lua'

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ec_txt = read_file(toy_ec)
        test_ec_txt += '\n' + '\n'.join([
            "exts_defaultclass = 'DummyExtension'",
            "exts_list = [",
            "    ('ls'),",
            "    ('bar', '0.0'),",
            "    ('barbar', '0.0', {",
            "        'start_dir': 'src',",
            "    }),",
            "    ('toy', '0.0'),",
            "]",
            "sanity_check_commands = ['barbar', 'toy']",
            "sanity_check_paths = {'files': ['bin/barbar', 'bin/toy'], 'dirs': ['bin']}",
        ])
        write_file(test_ec, test_ec_txt)

        args = ['--parallel-extensions-install', '--experimental', '--force', '--parallel=3']
        stdout, stderr = self.run_test_toy_build_with_output(ec_file=test_ec, extra_args=args, raise_error=True)
        self.assertEqual(stderr, '')

        # take into account that each of these lines may appear multiple times,
        # in case no progress was made between checks
        patterns = [
            r"== 0 out of 4 extensions installed \(2 queued, 2 running: ls, bar\)$",
            r"== 2 out of 4 extensions installed \(1 queued, 1 running: barbar\)$",
            r"== 3 out of 4 extensions installed \(0 queued, 1 running: toy\)$",
            r"== 4 out of 4 extensions installed \(0 queued, 0 running: \)$",
            '',
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            error_msg = "Expected pattern '%s' should be found in %s'" % (regex.pattern, stdout)
            self.assertTrue(regex.search(stdout), error_msg)

        # also test skipping of extensions in parallel
        args.append('--skip')
        stdout, stderr = self.run_test_toy_build_with_output(ec_file=test_ec, extra_args=args, raise_error=True)
        self.assertEqual(stderr, '')

        # order in which these patterns occur is not fixed, so check them one by one
        patterns = [
            r"^== skipping installed extensions \(in parallel\)$",
            r"^== skipping extension ls$",
            r"^== skipping extension bar$",
            r"^== skipping extension barbar$",
            r"^== skipping extension toy$",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            error_msg = "Expected pattern '%s' should be found in %s'" % (regex.pattern, stdout)
            self.assertTrue(regex.search(stdout), error_msg)

        # check behaviour when using Toy_Extension easyblock that doesn't implement required_deps method;
        # framework should fall back to installing extensions sequentially
        toy_ext_eb = os.path.join(topdir, 'sandbox', 'easybuild', 'easyblocks', 'generic', 'toy_extension.py')
        copy_file(toy_ext_eb, self.test_prefix)
        toy_ext_eb = os.path.join(self.test_prefix, 'toy_extension.py')
        toy_ext_eb_txt = read_file(toy_ext_eb)
        toy_ext_eb_txt = toy_ext_eb_txt.replace('def required_deps', 'def xxx_required_deps')
        write_file(toy_ext_eb, toy_ext_eb_txt)

        args[-1] = '--include-easyblocks=%s' % toy_ext_eb
        stdout, stderr = self.run_test_toy_build_with_output(ec_file=test_ec, extra_args=args, raise_error=True)
        self.assertEqual(stderr, '')
        # take into account that each of these lines may appear multiple times,
        # in case no progress was made between checks
        patterns = [
            r"^== 0 out of 4 extensions installed \(3 queued, 1 running: ls\)$",
            r"^== 1 out of 4 extensions installed \(2 queued, 1 running: bar\)$",
            r"^== 2 out of 4 extensions installed \(1 queued, 1 running: barbar\)$",
            r"^== 3 out of 4 extensions installed \(0 queued, 1 running: toy\)$",
            r"^== 4 out of 4 extensions installed \(0 queued, 0 running: \)$",
            '',
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            error_msg = "Expected pattern '%s' should be found in %s'" % (regex.pattern, stdout)
            self.assertTrue(regex.search(stdout), error_msg)

    def test_backup_modules(self):
        """Test use of backing up of modules with --module-only."""

        ec_files_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        ec_file = os.path.join(ec_files_path, 't', 'toy', 'toy-0.0-deps.eb')
        toy_mod = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0-deps')
        toy_mod_dir, toy_mod_fn = os.path.split(toy_mod)

        common_args = [
            ec_file,
            '--debug',
            '--unittest-file=%s' % self.logfile,
            '--robot=%s' % ec_files_path,
            '--force',
            '--disable-cleanup-tmpdir'
        ]
        args = common_args + ['--module-syntax=Tcl']

        # install module once (without --module-only), so it can be backed up
        with self.mocked_stdout_stderr():
            self.eb_main(args, do_build=True, raise_error=True)
        self.assertExists(toy_mod)

        # forced reinstall, no backup of module file because --backup-modules (or --module-only) is not used
        with self.mocked_stdout_stderr():
            self.eb_main(args, do_build=True, raise_error=True)
        self.assertExists(toy_mod)
        toy_mod_backups = glob.glob(os.path.join(toy_mod_dir, '.' + toy_mod_fn + '.bak_*'))
        self.assertEqual(len(toy_mod_backups), 0)

        self.mock_stderr(True)
        self.mock_stdout(True)
        # note: no need to specificy --backup-modules, enabled automatically under --module-only
        self.eb_main(args + ['--module-only'], do_build=True, raise_error=True)
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertExists(toy_mod)
        toy_mod_backups = glob.glob(os.path.join(toy_mod_dir, '.' + toy_mod_fn + '.bak_*'))
        self.assertEqual(len(toy_mod_backups), 1)
        first_toy_mod_backup = toy_mod_backups[0]
        # check that backup module is hidden (required for Tcl syntax)
        self.assertTrue(os.path.basename(first_toy_mod_backup).startswith('.'))

        toy_mod_bak = r".*/toy/\.0\.0-deps\.bak_[0-9]+_[0-9]+"
        regex = re.compile("^== backup of existing module file stored at %s" % toy_mod_bak, re.M)
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))
        regex = re.compile("^== comparing module file with backup %s; no differences found$" % toy_mod_bak, re.M)
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        self.assertEqual(stderr, '')

        # no backup of existing module file if --disable-backup-modules is used
        with self.mocked_stdout_stderr():
            self.eb_main(args + ['--disable-backup-modules'], do_build=True, raise_error=True)
        toy_mod_backups = glob.glob(os.path.join(toy_mod_dir, '.' + toy_mod_fn + '.bak_*'))
        self.assertEqual(len(toy_mod_backups), 1)

        # inject additional lines in module file to generate diff
        write_file(toy_mod, "some difference\n", append=True)

        self.mock_stderr(True)
        self.mock_stdout(True)
        self.eb_main(args + ['--module-only'], do_build=True, raise_error=True, verbose=True)
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        toy_mod_backups = glob.glob(os.path.join(toy_mod_dir, '.' + toy_mod_fn + '.bak_*'))
        self.assertEqual(len(toy_mod_backups), 2)

        regex = re.compile("^== backup of existing module file stored at %s" % toy_mod_bak, re.M)
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))
        regex = re.compile("^== comparing module file with backup %s; diff is:$" % toy_mod_bak, re.M)
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))
        regex = re.compile("^-some difference$", re.M)
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))
        self.assertEqual(stderr, '')

        # Test also with Lua syntax if Lmod is available.
        # In particular, that the backup is not hidden (except when using Lmod < 7.0)
        if isinstance(self.modtool, Lmod):
            args = common_args + ['--module-syntax=Lua', '--backup-modules']

            remove_dir(toy_mod_dir)
            toy_mod = os.path.join(toy_mod_dir, toy_mod_fn + '.lua')

            # initial installation of Lua module file
            with self.mocked_stdout_stderr():
                self.eb_main(args, do_build=True, raise_error=True)
            self.assertExists(toy_mod)
            lua_toy_mods = glob.glob(os.path.join(toy_mod_dir, '*.lua*'))
            self.assertEqual(len(lua_toy_mods), 1)
            self.assertEqual(os.path.basename(toy_mod), os.path.basename(lua_toy_mods[0]))
            # no backups yet
            toy_mod_backups = glob.glob(os.path.join(toy_mod_dir, toy_mod_fn + '.bak_*'))
            self.assertEqual(len(toy_mod_backups), 0)
            hidden_toy_mod_backups = glob.glob(os.path.join(toy_mod_dir, '.' + toy_mod_fn + '.bak_*'))
            self.assertEqual(len(hidden_toy_mod_backups), 0)

            # 2nd installation: backup module is created
            self.mock_stderr(True)
            self.mock_stdout(True)
            self.eb_main(args, do_build=True, raise_error=True, verbose=True)
            stderr = self.get_stderr()
            stdout = self.get_stdout()
            self.mock_stderr(False)
            self.mock_stdout(False)

            self.assertExists(toy_mod)
            lua_toy_mods = glob.glob(os.path.join(toy_mod_dir, '*.lua*'))
            self.assertEqual(len(lua_toy_mods), 1)
            self.assertEqual(os.path.basename(toy_mod), os.path.basename(lua_toy_mods[0]))

            # backup module is only hidden for old Lmod versions
            lmod_version = os.getenv('LMOD_VERSION', 'NOT_FOUND')
            if LooseVersion(lmod_version) < LooseVersion('7.0.0'):
                backups_visible, backups_hidden = 0, 1
                toy_mod_bak = r".*/toy/\.0\.0-deps\.bak_[0-9]+_[0-9]+"
            else:
                backups_visible, backups_hidden = 1, 0
                toy_mod_bak = r".*/toy/0\.0-deps\.bak_[0-9]+_[0-9]+"

            toy_mod_backups = glob.glob(os.path.join(toy_mod_dir, toy_mod_fn + '.bak_*'))
            self.assertEqual(len(toy_mod_backups), backups_visible)
            hidden_toy_mod_backups = glob.glob(os.path.join(toy_mod_dir, '.' + toy_mod_fn + '.bak_*'))
            self.assertEqual(len(hidden_toy_mod_backups), backups_hidden)

            first_toy_lua_mod_backup = (toy_mod_backups or hidden_toy_mod_backups)[0]
            self.assertIn('.bak_', os.path.basename(first_toy_lua_mod_backup))

            # check messages in stdout/stderr
            regex = re.compile("^== backup of existing module file stored at %s" % toy_mod_bak, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))
            regex = re.compile("^== comparing module file with backup %s; no differences found$" % toy_mod_bak, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))
            self.assertEqual(stderr, '')

            # tweak existing module file so we can verify diff of installed module with backup in stdout
            write_file(toy_mod, "some difference\n", append=True)

            self.mock_stderr(True)
            self.mock_stdout(True)
            self.eb_main(args, do_build=True, raise_error=True, verbose=True)
            stderr = self.get_stderr()
            stdout = self.get_stdout()
            self.mock_stderr(False)
            self.mock_stdout(False)

            if LooseVersion(lmod_version) < LooseVersion('7.0.0'):
                backups_hidden += 1
            else:
                backups_visible += 1

            lua_toy_mods = glob.glob(os.path.join(toy_mod_dir, '*.lua*'))
            self.assertEqual(len(lua_toy_mods), 1)
            self.assertEqual(os.path.basename(toy_mod), os.path.basename(lua_toy_mods[0]))
            toy_mod_backups = glob.glob(os.path.join(toy_mod_dir, toy_mod_fn + '.bak_*'))
            self.assertEqual(len(toy_mod_backups), backups_visible)
            hidden_toy_mod_backups = glob.glob(os.path.join(toy_mod_dir, '.' + toy_mod_fn + '.bak_*'))
            self.assertEqual(len(hidden_toy_mod_backups), backups_hidden)

            regex = re.compile("^== backup of existing module file stored at %s" % toy_mod_bak, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))
            regex = re.compile("^== comparing module file with backup %s; diff is:$" % toy_mod_bak, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))
            regex = re.compile("^-some difference$", re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))
            self.assertEqual(stderr, '')

    def test_package(self):
        """Test use of --package and accompanying package configuration settings."""
        mock_fpm(self.test_prefix)
        pkgpath = os.path.join(self.test_prefix, 'pkgs')

        extra_args = [
            '--package',
            '--package-release=321',
            '--package-tool=fpm',
            '--package-type=foo',
            '--packagepath=%s' % pkgpath,
        ]

        with self.mocked_stdout_stderr():
            self._test_toy_build(extra_args=extra_args)

        toypkg = os.path.join(pkgpath, 'toy-0.0-eb-%s.321.foo' % EASYBUILD_VERSION)
        self.assertExists(toypkg)

    def test_package_skip(self):
        """Test use of --package with --skip."""
        mock_fpm(self.test_prefix)
        pkgpath = os.path.join(self.test_prefix, 'packages')  # default path

        with self.mocked_stdout_stderr():
            self._test_toy_build(['--packagepath=%s' % pkgpath])
        self.assertNotExists(pkgpath, "%s is not created without use of --package" % pkgpath)

        self.mock_stdout(True)
        self._test_toy_build(extra_args=['--package', '--skip'], verify=False)
        self.mock_stdout(False)

        toypkg = os.path.join(pkgpath, 'toy-0.0-eb-%s.1.rpm' % EASYBUILD_VERSION)
        self.assertExists(toypkg)

    def test_regtest(self):
        """Test use of --regtest."""
        with self.mocked_stdout_stderr():
            self._test_toy_build(extra_args=['--regtest', '--sequential'], verify=False)

        # just check whether module exists
        toy_module = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_module += '.lua'
        self.assertExists(toy_module)

    def test_minimal_toolchains(self):
        """Test toy build with --minimal-toolchains."""
        # this test doesn't check for anything specific to using minimal toolchains, only side-effects
        with self.mocked_stdout_stderr():
            self._test_toy_build(extra_args=['--minimal-toolchains'])

    def test_reproducibility(self):
        """Test toy build produces expected reproducibility files"""

        # We need hooks for a complete test
        hooks_filename = 'my_hooks.py'
        hooks_file = os.path.join(self.test_prefix, hooks_filename)
        hooks_file_txt = '\n'.join([
            "import os",
            '',
            "def start_hook():",
            "   print('start hook triggered')",
            '',
            "def pre_configure_hook(self):",
            "    print('pre-configure: toy.source: %s' % os.path.exists('toy.source'))",
            '',
        ])
        write_file(hooks_file, hooks_file_txt)

        # also use the easyblock with inheritance to fully test
        self.mock_stdout(True)
        self._test_toy_build(extra_args=['--minimal-toolchains', '--easyblock=EB_toytoy', '--hooks=%s' % hooks_file])
        self.mock_stdout(False)

        # Check whether easyconfig is dumped to reprod/ subdir
        reprod_dir = os.path.join(self.test_installpath, 'software', 'toy', '0.0', 'easybuild', 'reprod')
        reprod_ec = os.path.join(reprod_dir, 'toy-0.0.eb')

        self.assertExists(reprod_ec)

        # Also check that the dumpenv script is placed alongside it
        dumpenv_script = '%s.env' % os.path.splitext(reprod_ec)[0]
        reprod_dumpenv = os.path.join(reprod_dir, dumpenv_script)
        self.assertExists(reprod_dumpenv)

        # Check contents of the dumpenv script
        patterns = [
            """#!/bin/bash""",
            """# usage: source toy-0.0.env""",
            # defining build env
            """# (no modules loaded)""",
            """# (no build environment defined)""",
        ]
        env_file = read_file(reprod_dumpenv)
        for pattern in patterns:
            self.assertIn(pattern, env_file)

        # Check that the toytoy easyblock is recorded in the reprod easyconfig
        ec = EasyConfig(reprod_ec)
        self.assertEqual(ec.parser.get_config_dict()['easyblock'], 'EB_toytoy')

        # make sure start_dir is not recorded in the dumped easyconfig, this does not appear in the original easyconfig
        # and is representative of values that are (typically) set by the easyblock steps (which are also dumped)
        self.assertNotIn('start_dir', ec.parser.get_config_dict())

        # Check for child easyblock existence
        child_easyblock = os.path.join(reprod_dir, 'easyblocks', 'toytoy.py')
        self.assertExists(child_easyblock)
        # Check for parent easyblock existence
        parent_easyblock = os.path.join(reprod_dir, 'easyblocks', 'toy.py')
        self.assertExists(parent_easyblock)

        # Make sure framework easyblock modules are not included
        for framework_easyblock in ['easyblock.py', 'extensioneasyblock.py']:
            path = os.path.join(reprod_dir, 'easyblocks', framework_easyblock)
            self.assertNotExists(path)

        # Make sure hooks are also copied
        reprod_hooks = os.path.join(reprod_dir, 'hooks', hooks_filename)
        self.assertExists(reprod_hooks)

    def test_reproducibility_ext_easyblocks(self):
        """Test toy build produces expected reproducibility files also when extensions are used"""

        topdir = os.path.dirname(os.path.abspath(__file__))
        toy_ec_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec_file)

        ec1 = os.path.join(self.test_prefix, 'toy1.eb')
        ec1_txt = '\n'.join([
            toy_ec_txt,
            "exts_defaultclass = 'DummyExtension'",
            "exts_list = [('barbar', '1.2', {'start_dir': 'src'})]",
            "",
        ])
        write_file(ec1, ec1_txt)

        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=ec1, verify=False,
                                 extra_args=['--minimal-toolchains', '--easyblock=EB_toytoy'])

        # Check whether easyconfig is dumped to reprod/ subdir
        reprod_dir = os.path.join(self.test_installpath, 'software', 'toy', '0.0', 'easybuild', 'reprod')
        reprod_ec = os.path.join(reprod_dir, 'toy-0.0.eb')

        self.assertExists(reprod_ec)

        # Check for child easyblock existence
        child_easyblock = os.path.join(reprod_dir, 'easyblocks', 'toytoy.py')
        self.assertExists(child_easyblock)
        # Check for parent easyblock existence
        parent_easyblock = os.path.join(reprod_dir, 'easyblocks', 'toy.py')
        self.assertExists(parent_easyblock)
        # Check for extension easyblock existence
        ext_easyblock = os.path.join(reprod_dir, 'easyblocks', 'toy_extension.py')
        self.assertExists(ext_easyblock)

        # Make sure framework easyblock modules are not included
        for framework_easyblock in ['easyblock.py', 'extensioneasyblock.py']:
            path = os.path.join(reprod_dir, 'easyblocks', framework_easyblock)
            self.assertNotExists(path)

    def test_toy_toy(self):
        """Test building two easyconfigs in a single go, with one depending on the other."""

        topdir = os.path.dirname(os.path.abspath(__file__))
        toy_ec_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec_file)

        ec1 = os.path.join(self.test_prefix, 'toy1.eb')
        ec1_txt = '\n'.join([
            toy_ec_txt,
            "versionsuffix = '-one'",
        ])
        write_file(ec1, ec1_txt)

        # adapt toy easyconfig for toy2 to produce a modulefile with a dedicated
        # name ('toy2' instead of 'toy')
        ec2 = os.path.join(self.test_prefix, 'toy2.eb')
        ec2_txt = '\n'.join([
            toy_ec_txt,
            "name = 'toy2'",
            "easyblock = 'EB_toy'",
            "sources = ['toy/toy-0.0.tar.gz']",
            "patches = []",
            "sanity_check_paths = { 'files': ['bin/toy2'], 'dirs': ['bin']}",
            "prebuildopts = 'mv toy.source toy2.c &&'",
            "versionsuffix = '-two'",
            "dependencies = [('toy', '0.0', '-one')]",
        ])
        write_file(ec2, ec2_txt)

        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=self.test_prefix, verify=False)

        mod1 = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0-one')
        mod2 = os.path.join(self.test_installpath, 'modules', 'all', 'toy2', '0.0-two')
        if get_module_syntax() == 'Lua':
            mod1 += '.lua'
            mod2 += '.lua'
        self.assertExists(mod1)
        self.assertExists(mod2)

        mod2_txt = read_file(mod2)

        load1_regex = re.compile('(load|depends[-_]on).*toy/0.0-one', re.M)
        self.assertTrue(load1_regex.search(mod2_txt), "Pattern '%s' found in: %s" % (load1_regex.pattern, mod2_txt))

        # Check the contents of the dumped env in the reprod dir to ensure it contains the dependency load
        reprod_dir = os.path.join(self.test_installpath, 'software', 'toy2', '0.0-two', 'easybuild', 'reprod')
        dumpenv_script = os.path.join(reprod_dir, 'toy2-0.0-two.env')
        reprod_dumpenv = os.path.join(reprod_dir, dumpenv_script)
        self.assertExists(reprod_dumpenv)

        # Check contents of the dumpenv script
        patterns = [
            """#!/bin/bash""",
            """# usage: source toy2-0.0-two.env""",
            # defining build env
            """module load toy/0.0-one""",
            """# (no build environment defined)""",
        ]
        env_file = read_file(reprod_dumpenv)
        for pattern in patterns:
            self.assertIn(pattern, env_file)

    def test_toy_sanity_check_commands(self):
        """Test toy build with extra sanity check commands."""

        self.setup_hierarchical_modules()

        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec_txt = read_file(os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb'))

        out_file = os.path.join(self.test_prefix, 'out.txt')

        toy_ec_txt = '\n'.join([
            toy_ec_txt,
            "toolchain = {'name': 'foss', 'version': '2018a'}",
            # specially construct (sort of senseless) sanity check commands,
            # that will fail if the corresponding modules are not loaded
            # cfr. https://github.com/easybuilders/easybuild-framework/pull/1754
            "sanity_check_commands = [",
            "   'env | grep EBROOTFFTW',",
            "   'env | grep EBROOTGCC',",
            # tuple format (kinda weird but kept in place for backward compatibility)
            "   ('env | grep EBROOTFOSS', ''),",
            # True implies running 'toy -h', should work (although pretty senseless in this case)
            "   True,",
            # test command to make sure that '-h' is not passed to commands specified as string ('env -h' fails)
            "   'env',"
            # print current working directory, should *not* be software install directory, but empty dir
            f"   '(pwd && ls | wc -l) > {out_file}',",
            "]",
        ])

        tweaked_toy_ec = os.path.join(self.test_prefix, 'toy-0.0-tweaked.eb')
        write_file(tweaked_toy_ec, toy_ec_txt)

        args = [
            tweaked_toy_ec,
            '--debug',
            '--unittest-file=%s' % self.logfile,
            '--force',
            '--robot=%s' % test_easyconfigs,
            '--module-naming-scheme=HierarchicalMNS',
        ]
        with self.mocked_stdout_stderr():
            self.eb_main(args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)

        modpath = os.path.join(self.test_installpath, 'modules', 'all')
        toy_modfile = os.path.join(modpath, 'MPI', 'GCC', '6.4.0-2.28', 'OpenMPI', '2.1.2', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_modfile += '.lua'

        self.assertExists(toy_modfile)

        # check contents of output file created by sanity check commands
        self.assertExists(out_file)
        out_txt = read_file(out_file)
        # working dir for sanity check command should be an empty custom temporary directory
        regex = re.compile('^.*/eb-[^/]+/eb-sanity-check-[^/]+\n[ ]*0$')
        self.assertTrue(regex.match(out_txt), f"Pattern '{regex.pattern}' should match in: {out_txt}")

    def test_sanity_check_paths_lib64(self):
        """Test whether fallback in sanity check for lib64/ equivalents of library files works."""
        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs')
        ec_file = os.path.join(test_ecs_dir, 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        ectxt = read_file(ec_file)

        # modify test easyconfig: move lib/libtoy.a to lib64/libtoy.a
        ectxt = re.sub(r"\s*'files'.*", "'files': ['bin/toy', ('lib/libtoy.a', 'lib/libfoo.a')],", ectxt)
        postinstallcmd = ' && '.join([
            # remove lib64 symlink (if it's there)
            "rm -f %(installdir)s/lib64",
            # create empty lib64 dir
            "mkdir %(installdir)s/lib64",
            # move libtoy*.a
            "mv %(installdir)s/lib/libtoy*.a %(installdir)s/lib64/",
        ])
        ectxt = re.sub("postinstallcmds.*", "postinstallcmds = ['%s']" % postinstallcmd, ectxt)

        test_ec = os.path.join(self.test_prefix, 'toy-0.0.eb')
        write_file(test_ec, ectxt)

        # sanity check fails if lib64 fallback in sanity check is disabled
        error_pattern = r"Sanity check failed: no file found at 'lib/libtoy.a' or 'lib/libfoo.a' in "
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, ec_file=test_ec,
                                  extra_args=['--disable-lib64-fallback-sanity-check', '--disable-lib64-lib-symlink'],
                                  raise_error=True, verbose=False)

        # all is fine is lib64 fallback check is enabled (which it is by default)
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, raise_error=True)

        # also check with 'lib' in sanity check dirs (special case)
        ectxt = re.sub(r"\s*'files'.*", "'files': ['bin/toy'],", ectxt)
        ectxt = re.sub(r"\s*'dirs'.*", "'dirs': ['lib'],", ectxt)
        write_file(test_ec, ectxt)

        error_pattern = r"Sanity check failed: no \(non-empty\) directory found at 'lib' in "
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, ec_file=test_ec,
                                  extra_args=['--disable-lib64-fallback-sanity-check', '--disable-lib64-lib-symlink'],
                                  raise_error=True, verbose=False)

        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, extra_args=['--disable-lib64-lib-symlink'], raise_error=True)

        # also check other way around (lib64 -> lib)
        ectxt = read_file(ec_file)
        ectxt = re.sub(r"\s*'files'.*", "'files': ['bin/toy', 'lib64/libtoy.a'],", ectxt)
        write_file(test_ec, ectxt)

        # sanity check fails if lib64 fallback in sanity check is disabled, since lib64/libtoy.a is not there
        error_pattern = r"Sanity check failed: no file found at 'lib64/libtoy.a' in "
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, ec_file=test_ec,
                                  extra_args=['--disable-lib64-fallback-sanity-check', '--disable-lib64-lib-symlink'],
                                  raise_error=True, verbose=False)

        # sanity check passes when lib64 fallback is enabled (by default), since lib/libtoy.a is also considered
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, extra_args=['--disable-lib64-lib-symlink'], raise_error=True)

        # also check with 'lib64' in sanity check dirs (special case)
        ectxt = re.sub(r"\s*'files'.*", "'files': ['bin/toy'],", ectxt)
        ectxt = re.sub(r"\s*'dirs'.*", "'dirs': ['lib64'],", ectxt)
        write_file(test_ec, ectxt)

        error_pattern = r"Sanity check failed: no \(non-empty\) directory found at 'lib64' in "
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, ec_file=test_ec,
                                  extra_args=['--disable-lib64-fallback-sanity-check', '--disable-lib64-lib-symlink'],
                                  raise_error=True, verbose=False)

        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, extra_args=['--disable-lib64-lib-symlink'], raise_error=True)

        # check whether fallback works for files that's more than 1 subdir deep
        ectxt = read_file(ec_file)
        ectxt = re.sub(r"\s*'files'.*", "'files': ['bin/toy', 'lib/test/libtoy.a'],", ectxt)
        postinstallcmd = "mkdir -p %(installdir)s/lib64/test && "
        postinstallcmd += "mv %(installdir)s/lib/libtoy.a %(installdir)s/lib64/test/libtoy.a"
        ectxt = re.sub("postinstallcmds.*", "postinstallcmds = ['%s']" % postinstallcmd, ectxt)
        write_file(test_ec, ectxt)
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, extra_args=['--disable-lib64-lib-symlink'], raise_error=True)

    def test_toy_build_enhanced_sanity_check(self):
        """Test enhancing of sanity check."""

        # if toy easyblock was imported, get rid of corresponding entry in sys.modules,
        # to avoid that it messes up the use of --include-easyblocks=toy.py below...
        if 'easybuild.easyblocks.toy' in sys.modules:
            del sys.modules['easybuild.easyblocks.toy']

        test_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)))
        toy_ec = os.path.join(test_dir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec)

        test_ec = os.path.join(self.test_prefix, 'test.eb')

        # get rid of custom sanity check paths in test easyconfig
        regex = re.compile(r'^sanity_check_paths\s*=\s*{[^}]+}', re.M)
        test_ec_txt = regex.sub('', toy_ec_txt)
        write_file(test_ec, test_ec_txt)

        self.assertNotIn('sanity_check_', test_ec_txt)

        # create custom easyblock for toy that has a custom sanity_check_step
        toy_easyblock = os.path.join(test_dir, 'sandbox', 'easybuild', 'easyblocks', 't', 'toy.py')

        toy_easyblock_txt = read_file(toy_easyblock)

        toy_custom_sanity_check_step = '\n'.join([
            '',
            "    def sanity_check_step(self):",
            "        paths = {",
            "            'files': ['bin/toy'],",
            "            'dirs': [],",
            "        }",
            "        cmds = ['toy']",
            "        return super().sanity_check_step(custom_paths=paths, custom_commands=cmds)",
        ])
        test_toy_easyblock = os.path.join(self.test_prefix, 'toy.py')
        write_file(test_toy_easyblock, toy_easyblock_txt + toy_custom_sanity_check_step)

        eb_args = [
            '--extended-dry-run',
            '--include-easyblocks=%s' % test_toy_easyblock,
        ]

        # by default, sanity check commands & paths specified by easyblock are used
        self.mock_stdout(True)
        self._test_toy_build(ec_file=test_ec, extra_args=eb_args, verify=False, testing=False, raise_error=True)
        stdout = self.get_stdout()
        self.mock_stdout(False)

        pattern_lines = [
            r"Sanity check paths - file.*",
            r"\s*\* bin/toy",
            r"Sanity check paths - \(non-empty\) directory.*",
            r"\s*\(none\)",
            r"Sanity check commands",
            r"\s*\* toy",
            r'',
        ]
        regex = re.compile(r'\n'.join(pattern_lines), re.M)
        self.assertTrue(regex.search(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

        # we need to manually wipe the entry for the included toy easyblock,
        # to avoid trouble with subsequent EasyBuild sessions in this test
        del sys.modules['easybuild.easyblocks.toy']

        # easyconfig specifies custom sanity_check_paths & sanity_check_commands,
        # the ones defined by the easyblock are skipped by default
        test_ec_txt = test_ec_txt + '\n'.join([
            '',
            "sanity_check_paths = {",
            "    'files': ['README'],",
            "    'dirs': ['bin/']",
            "}",
            "sanity_check_commands = ['ls %(installdir)s']",
        ])
        write_file(test_ec, test_ec_txt)

        self.mock_stdout(True)
        self._test_toy_build(ec_file=test_ec, extra_args=eb_args, verify=False, testing=False, raise_error=True)
        stdout = self.get_stdout()
        self.mock_stdout(False)

        pattern_lines = [
            r"Sanity check paths - file.*",
            r"\s*\* README",
            r"Sanity check paths - \(non-empty\) directory.*",
            r"\s*\* bin/",
            r"Sanity check commands",
            r"\s*\* ls .*/software/toy/0.0",
            r'',
        ]
        regex = re.compile(r'\n'.join(pattern_lines), re.M)
        self.assertTrue(regex.search(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

        del sys.modules['easybuild.easyblocks.toy']

        # if enhance_sanity_check is enabled, then sanity check paths/commands specified in easyconfigs
        # are used in addition to those defined in easyblock
        test_ec_txt = test_ec_txt + '\nenhance_sanity_check = True'
        write_file(test_ec, test_ec_txt)

        self.mock_stdout(True)
        self._test_toy_build(ec_file=test_ec, extra_args=eb_args, verify=False, testing=False, raise_error=True)
        stdout = self.get_stdout()
        self.mock_stdout(False)

        # now 'bin/toy' file and 'toy' command should also be part of sanity check
        pattern_lines = [
            r"Sanity check paths - file.*",
            r"\s*\* README",
            r"\s*\* bin/toy",
            r"Sanity check paths - \(non-empty\) directory.*",
            r"\s*\* bin/",
            r"Sanity check commands",
            r"\s*\* ls .*/software/toy/0.0",
            r"\s*\* toy",
            r'',
        ]
        regex = re.compile(r'\n'.join(pattern_lines), re.M)
        self.assertTrue(regex.search(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

        del sys.modules['easybuild.easyblocks.toy']

        # sanity_check_paths with only one key is allowed if enhance_sanity_check is enabled;
        test_ec_txt = test_ec_txt + "\nsanity_check_paths = {'files': ['README']}"
        write_file(test_ec, test_ec_txt)

        # we need to do a non-dry run here, to ensure the code we want to test is triggered
        # (EasyConfig.dump called by 'reproduce_build' function from 'build_and_install_one')
        eb_args = [
            '--include-easyblocks=%s' % test_toy_easyblock,
            '--trace',
        ]

        self.mock_stdout(True)
        self._test_toy_build(ec_file=test_ec, extra_args=eb_args, verify=False, testing=False, raise_error=True)
        stdout = self.get_stdout()
        self.mock_stdout(False)

        pattern_lines = [
            r"^== sanity checking\.\.\.",
            r"  >> file 'bin/toy' found: OK",
        ]
        regex = re.compile(r'\n'.join(pattern_lines), re.M)
        self.assertTrue(regex.search(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

        # no directories are checked in sanity check now, only files (since dirs is an empty list)
        regex = re.compile(r"directory .* found:", re.M)
        self.assertFalse(regex.search(stdout), "Pattern '%s' should be not found in: %s" % (regex.pattern, stdout))

        del sys.modules['easybuild.easyblocks.toy']

        # if enhance_sanity_check is disabled, both files/dirs keys are strictly required in sanity_check_paths
        test_ec_txt = test_ec_txt + '\nenhance_sanity_check = False'
        write_file(test_ec, test_ec_txt)

        error_pattern = r"Missing mandatory key 'dirs' in sanity_check_paths."
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, ec_file=test_ec,
                                  extra_args=eb_args, raise_error=True, verbose=False)

        del sys.modules['easybuild.easyblocks.toy']

    def test_toy_build_enhanced_sanity_check_templated_multi_dep(self):
        """Test enhancing of sanity check by easyblocks with templates and in the presence of multi_deps."""

        # if toy easyblock was imported, get rid of corresponding entry in sys.modules,
        # to avoid that it messes up the use of --include-easyblocks=toy.py below...
        if 'easybuild.easyblocks.toy' in sys.modules:
            del sys.modules['easybuild.easyblocks.toy']

        test_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)))
        toy_ec = os.path.join(test_dir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec)

        test_ec = os.path.join(self.test_prefix, 'test.eb')

        # get rid of custom sanity check paths in test easyconfig
        regex = re.compile(r'^sanity_check_paths\s*=\s*{[^}]+}', re.M)
        test_ec_txt = regex.sub('', toy_ec_txt)
        self.assertNotIn('sanity_check_', test_ec_txt)

        test_ec_txt += "\nmulti_deps = {'Python': ['3.7.2', '2.7.15']}"
        write_file(test_ec, test_ec_txt)

        # create custom easyblock for toy that has a custom sanity_check_step
        toy_easyblock = os.path.join(test_dir, 'sandbox', 'easybuild', 'easyblocks', 't', 'toy.py')

        toy_easyblock_txt = read_file(toy_easyblock)

        toy_custom_sanity_check_step = textwrap.dedent("""
            # Add to class to indent
                def sanity_check_step(self):
                    paths = {
                        'files': ['bin/python%(pyshortver)s'],
                        'dirs': ['lib/py-%(pyshortver)s'],
                    }
                    cmds = ['python%(pyshortver)s']
                    return super().sanity_check_step(custom_paths=paths, custom_commands=cmds)
        """)
        test_toy_easyblock = os.path.join(self.test_prefix, 'toy.py')
        write_file(test_toy_easyblock, toy_easyblock_txt + toy_custom_sanity_check_step)

        eb_args = [
            '--extended-dry-run',
            '--include-easyblocks=%s' % test_toy_easyblock,
        ]

        # by default, sanity check commands & paths specified by easyblock are used
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, extra_args=eb_args, verify=False, testing=False, raise_error=True)
            stdout = self.get_stdout()
            # Cut output to start of the toy-ec, after the Python installations
            stdout = stdout[stdout.index(test_ec):]

        pattern_template = textwrap.dedent(r"""
            Sanity check paths - file.*
            \s*\* bin/python{pyshortver}
            Sanity check paths - \(non-empty\) directory.*
            \s*\* lib/py-{pyshortver}
            Sanity check commands
            \s*\* python{pyshortver}
        """)
        for pyshortver in ('2.7', '3.7'):
            regex = re.compile(pattern_template.format(pyshortver=pyshortver), re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

        # Enhance sanity check by extra paths to check for, the ones from the easyblock should be kept
        test_ec_txt += textwrap.dedent("""
            enhance_sanity_check = True
            sanity_check_paths = {
                'files': ['bin/pip%(pyshortver)s'],
                'dirs': ['bin'],
            }
        """)
        write_file(test_ec, test_ec_txt)
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, extra_args=eb_args, verify=False, testing=False, raise_error=True)
            stdout = self.get_stdout()
            # Cut output to start of the toy-ec, after the Python installations
            stdout = stdout[stdout.index(test_ec):]

        pattern_template = textwrap.dedent(r"""
            Sanity check paths - file.*
            \s*\* bin/pip{pyshortver}
            \s*\* bin/python{pyshortver}
            Sanity check paths - \(non-empty\) directory.*
            \s*\* bin
            \s*\* lib/py-{pyshortver}
            Sanity check commands
            \s*\* python{pyshortver}
        """)
        for pyshortver in ('2.7', '3.7'):
            regex = re.compile(pattern_template.format(pyshortver=pyshortver), re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

    def test_toy_dumped_easyconfig(self):
        """ Test dumping of file in eb_filerepo in both .eb format """
        filename = 'toy-0.0'
        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs')
        paths = [
            os.path.join(test_ecs_dir, 'test_ecs', 't', 'toy', '%s.eb' % filename),
        ]

        for path in paths:

            args = [
                path,
                '--experimental',
                '--force',
            ]
            with self.mocked_stdout_stderr():
                self.eb_main(args, do_build=True)

            # test eb build with dumped file
            args[0] = os.path.join(get_repositorypath()[0], 'toy', 'toy-0.0%s' % os.path.splitext(path)[-1])
            with self.mocked_stdout_stderr():
                self.eb_main(args, do_build=True)
            easybuild.tools.build_log.EXPERIMENTAL = True
            ec = EasyConfig(args[0])
            buildstats = ec.parser.get_config_dict()['buildstats']

            self.assertTrue(all(isinstance(bs, dict) for bs in buildstats))

    def test_toy_filter_env_vars(self):
        """Test use of --filter-env-vars on generated module file"""
        toy_mod_path = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_mod_path += '.lua'

        regexs = [
            re.compile("prepend[-_]path.*LD_LIBRARY_PATH.*lib", re.M),
            re.compile("prepend[-_]path.*LIBRARY_PATH.*lib", re.M),
            re.compile("prepend[-_]path.*PATH.*bin", re.M),
        ]

        with self.mocked_stdout_stderr():
            self._test_toy_build()
        toy_mod_txt = read_file(toy_mod_path)
        for regex in regexs:
            self.assertTrue(regex.search(toy_mod_txt), "Pattern '%s' found in: %s" % (regex.pattern, toy_mod_txt))

        with self.mocked_stdout_stderr():
            self._test_toy_build(extra_args=['--filter-env-vars=LD_LIBRARY_PATH,PATH'])
        toy_mod_txt = read_file(toy_mod_path)
        self.assertFalse(regexs[0].search(toy_mod_txt), "Pattern '%s' found in: %s" % (regexs[0].pattern, toy_mod_txt))
        self.assertTrue(regexs[1].search(toy_mod_txt), "Pattern '%s' found in: %s" % (regexs[1].pattern, toy_mod_txt))
        self.assertFalse(regexs[2].search(toy_mod_txt), "Pattern '%s' found in: %s" % (regexs[2].pattern, toy_mod_txt))

    def test_toy_iter(self):
        """Test toy build that involves iterating over buildopts."""
        topdir = os.path.abspath(os.path.dirname(__file__))
        toy_ec = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-iter.eb')

        expected_buildopts = ['', '-O2; mv %(name)s toy_O2_$EBVERSIONGCC', '-O1; mv %(name)s toy_O1_$EBVERSIONGCC']

        for extra_args in [None, ['--minimal-toolchains']]:
            # sanity check will make sure all entries in buildopts list were taken into account
            with self.mocked_stdout_stderr():
                self._test_toy_build(ec_file=toy_ec, extra_args=extra_args, versionsuffix='-iter')

            # verify whether dumped easyconfig contains original value for buildopts
            dumped_toy_ec = os.path.join(self.test_prefix, 'ebfiles_repo', 'toy', os.path.basename(toy_ec))
            ec = EasyConfigParser(dumped_toy_ec).get_config_dict()
            self.assertEqual(ec['buildopts'], expected_buildopts)

    def test_toy_rpath(self):
        """Test toy build using --rpath."""

        # find_eb_script function used to find rpath_args.py requires that location where easybuild/scripts
        # resides is listed in sys.path via absolute path;
        # this is only needed to make this test pass when it's being called from that same location...
        top_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sys.path.insert(0, top_path)

        def grab_gcc_rpath_wrapper_args():
            """Helper function to grab arguments from last RPATH wrapper for 'gcc'."""
            rpath_wrappers_dir = glob.glob(os.path.join(os.getenv('TMPDIR'), '*', '*', 'rpath_wrappers'))[0]
            gcc_rpath_wrapper_txt = read_file(glob.glob(os.path.join(rpath_wrappers_dir, '*', 'gcc'))[0])

            # First get the filter argument
            rpath_args_regex = re.compile(r"^rpath_args_out=.*rpath_args.py \$CMD '([^ ]*)'.*", re.M)
            res_filter = rpath_args_regex.search(gcc_rpath_wrapper_txt)
            self.assertTrue(res_filter, "Pattern '%s' found in: %s" % (rpath_args_regex.pattern, gcc_rpath_wrapper_txt))

            # Now get the include argument
            rpath_args_regex = re.compile(r"^rpath_args_out=.*rpath_args.py \$CMD '.*' '([^ ]*)'.*", re.M)
            res_include = rpath_args_regex.search(gcc_rpath_wrapper_txt)
            self.assertTrue(res_include, "Pattern '%s' found in: %s" % (rpath_args_regex.pattern,
                                                                        gcc_rpath_wrapper_txt))

            shutil.rmtree(rpath_wrappers_dir)

            return {'filter_paths': res_filter.group(1), 'include_paths': res_include.group(1)}

        args = ['--rpath']
        with self.mocked_stdout_stderr():
            self._test_toy_build(extra_args=args, raise_error=True)

        # by default, /lib and /usr are included in RPATH filter,
        # together with temporary directory and build directory
        rpath_filter_paths = grab_gcc_rpath_wrapper_args()['filter_paths'].split(',')
        self.assertIn('/lib.*', rpath_filter_paths)
        self.assertIn('/usr.*', rpath_filter_paths)
        self.assertTrue(any(p.startswith(os.getenv('TMPDIR')) for p in rpath_filter_paths))
        self.assertTrue(any(p.startswith(self.test_buildpath) for p in rpath_filter_paths))

        # Check that we can use --rpath-override-dirs
        args = ['--rpath', '--rpath-override-dirs=/opt/eessi/2021.03/lib:/opt/eessi/lib']
        with self.mocked_stdout_stderr():
            self._test_toy_build(extra_args=args, raise_error=True)
        rpath_include_paths = grab_gcc_rpath_wrapper_args()['include_paths'].split(',')
        # Make sure our directories appear in dirs to be included in the rpath (and in the right order)
        self.assertEqual(rpath_include_paths[0], '/opt/eessi/2021.03/lib')
        self.assertEqual(rpath_include_paths[1], '/opt/eessi/lib')

        # Check that when we use --rpath-override-dirs empty values are filtered
        args = ['--rpath', '--rpath-override-dirs=/opt/eessi/2021.03/lib::/opt/eessi/lib']
        with self.mocked_stdout_stderr():
            self._test_toy_build(extra_args=args, raise_error=True)
        rpath_include_paths = grab_gcc_rpath_wrapper_args()['include_paths'].split(',')
        # Make sure our directories appear in dirs to be included in the rpath (and in the right order)
        self.assertEqual(rpath_include_paths[0], '/opt/eessi/2021.03/lib')
        self.assertEqual(rpath_include_paths[1], '/opt/eessi/lib')

        # Check that when we use --rpath-override-dirs we can only provide absolute paths
        eb_args = ['--rpath', '--rpath-override-dirs=/opt/eessi/2021.03/lib:eessi/lib']
        error_pattern = r"Path used in rpath_override_dirs is not an absolute path: eessi/lib"
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, extra_args=eb_args,
                                  raise_error=True, verbose=False)

        # also test use of --rpath-filter
        args.extend(['--rpath-filter=/test.*,/foo/bar.*', '--disable-cleanup-tmpdir'])
        with self.mocked_stdout_stderr():
            self._test_toy_build(extra_args=args, raise_error=True)

        # check whether rpath filter was set correctly
        rpath_filter_paths = grab_gcc_rpath_wrapper_args()['filter_paths'].split(',')
        self.assertIn('/test.*', rpath_filter_paths)
        self.assertIn('/foo/bar.*', rpath_filter_paths)
        self.assertTrue(any(p.startswith(os.getenv('TMPDIR')) for p in rpath_filter_paths))
        self.assertTrue(any(p.startswith(self.test_buildpath) for p in rpath_filter_paths))

        # test use of rpath toolchain option with SYSTEM and gompi 2018b toolchains
        for toolchain in ['', '-gompi-2018a']:
            test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
            toy_ec_txt = read_file(os.path.join(test_ecs, 't', 'toy', f'toy-0.0{toolchain}.eb'))
            toy_ec_txt += "\ntoolchainopts = {'rpath': False}\n"  # overwrites existing toolchainopts
            toy_ec = os.path.join(self.test_prefix, 'toy.eb')
            write_file(toy_ec, toy_ec_txt)
            with self.mocked_stdout_stderr():
                self._test_toy_build(ec_file=toy_ec, extra_args=['--rpath'], raise_error=True)

        # test check_readelf_rpath easyconfig parameter
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec_txt = read_file(os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb'))
        toy_ec_txt += "\ncheck_readelf_rpath = False\n"
        toy_ec = os.path.join(self.test_prefix, 'toy.eb')
        write_file(toy_ec, toy_ec_txt)
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=toy_ec, extra_args=['--rpath'], raise_error=True)

    def test_toy_filter_rpath_sanity_libs(self):
        """Test use of --filter-rpath-sanity-libs."""

        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy-app', 'toy-app-0.0.eb')

        # This should just build succesfully
        rpath_args = ['--rpath', '--strict-rpath-sanity-check']
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=toy_ec, name='toy-app', extra_args=rpath_args, raise_error=True)

        libtoy_libdir = os.path.join(self.test_installpath, 'software', 'libtoy', '0.0', 'lib')
        toyapp_bin = os.path.join(self.test_installpath, 'software', 'toy-app', '0.0', 'bin', 'toy-app')
        rpath_regex = re.compile(r"\(RPATH\).*" + libtoy_libdir, re.M)
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(f"readelf -d {toyapp_bin}")
        self.assertTrue(rpath_regex.search(res.output),
                        f"Pattern '{rpath_regex.pattern}' should be found in: {res.output}")

        with self.mocked_stdout_stderr():
            res = run_shell_cmd(f"ldd {toyapp_bin}")
        out = res.output
        libtoy_regex = re.compile(r"libtoy.so => /.*/libtoy.so", re.M)
        notfound = re.compile(r"libtoy\.so\s*=>\s*not found", re.M)
        self.assertTrue(libtoy_regex.search(out), f"Pattern '{libtoy_regex.pattern}' should be found in: {out}")
        self.assertFalse(notfound.search(out), f"Pattern '{notfound.pattern}' should not be found in: {out}")

        # test sanity error when --rpath-filter is used to filter a required library
        # In this test, libtoy.so will be linked, but not RPATH-ed due to the --rpath-filter
        # Thus, the RPATH sanity check is expected to fail with libtoy.so not being found
        args = rpath_args + ['--rpath-filter=.*libtoy.*']
        error_pattern = r"Sanity check failed\: Library libtoy\.so not found"
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, ec_file=toy_ec,
                                  extra_args=args, name='toy-app', raise_error=True, verbose=False)

        # test use of --filter-rpath-sanity-libs option. In this test, we use --rpath-filter to make sure libtoy.so is
        # not rpath-ed. Then, we use --filter-rpath-sanity-libs to make sure the RPATH sanity checks ignores
        # the fact that libtoy.so is not found. Thus, this build should complete succesfully
        args = rpath_args + ['--rpath-filter=.*libtoy.*', '--filter-rpath-sanity-libs=libtoy.so']
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=toy_ec, name='toy-app', extra_args=args, raise_error=True)

        with self.mocked_stdout_stderr():
            res = run_shell_cmd(f"readelf -d {toyapp_bin}")
        self.assertFalse(rpath_regex.search(res.output),
                         f"Pattern '{rpath_regex.pattern}' should not be found in: {res.output}")

        with self.mocked_stdout_stderr():
            res = run_shell_cmd(f"ldd {toyapp_bin}")
        self.assertFalse(libtoy_regex.search(res.output),
                         f"Pattern '{libtoy_regex.pattern}' should not be found in: {res.output}")
        self.assertTrue(notfound.search(res.output),
                        f"Pattern '{notfound.pattern}' should be found in: {res.output}")

        # test again with list of library names passed to --filter-rpath-sanity-libs
        args = rpath_args + ['--rpath-filter=.*libtoy.*', '--filter-rpath-sanity-libs=libfoo.so,libtoy.so,libbar.so']
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=toy_ec, name='toy-app', extra_args=args, raise_error=True)

        with self.mocked_stdout_stderr():
            res = run_shell_cmd(f"readelf -d {toyapp_bin}")
        self.assertFalse(rpath_regex.search(out),
                         f"Pattern '{rpath_regex.pattern}' should not be found in: {res.output}")

        with self.mocked_stdout_stderr():
            res = run_shell_cmd(f"ldd {toyapp_bin}")
        self.assertFalse(libtoy_regex.search(res.output),
                         f"Pattern '{libtoy_regex.pattern}' should not be found in: {res.output}")
        self.assertTrue(notfound.search(res.output),
                        f"Pattern '{notfound.pattern}' should be found in: {res.output}")

        # by default, without using --strict-rpath-sanity-check, there's no failure since RPATH sanity check
        # doesn't check for missing libraries with $LD_LIBRARY_PATH unset
        args = ['--rpath', '--rpath-filter=.*libtoy.*']
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=toy_ec, name='toy-app', extra_args=args, raise_error=True, verbose=False)

        # trouble again when $LD_LIBRARY_PATH is not used in generated module file
        args = ['libtoy-0.0.eb', '--rebuild', '--rpath', '--rpath-filter=.*libtoy.*',
                '--filter-env-vars=LD_LIBRARY_PATH']
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, ec_file=toy_ec,
                                  extra_args=args, name='toy-app', raise_error=True, verbose=False)

    def test_toy_cuda_sanity_check(self):
        """Test the CUDA sanity check"""
        update_build_option('trace', True)
        # Define the toy_ec file we want to use
        topdir = os.path.dirname(os.path.abspath(__file__))
        toy_ec = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        toy_bin = '%(installdir)s/bin/toy'
        py_site_pkgs = '%(installdir)s/lib/python3.9/site-packages'
        shlib_ext = get_shared_lib_ext()

        toy_ec_cuda = os.path.join(self.test_prefix, 'toy-0.0-cuda.eb')
        toy_ec_txt = read_file(toy_ec)
        toy_ec_txt += '\n' + '\n'.join([
            "dependencies = [('CUDA', '5.5.22', '', SYSTEM)]",
            "postinstallcmds += [",
            "    'mkdir -p %(installdir)s/lib/python3.9/site-packages/plugins',",
            # copy 'toy' binary, must be something that passes 'file' check in get_cuda_object_dump_raw
            "    'cp %s %s/pytoy-cuda.cpython-39-x86_64-linux-gnu.%s'," % (toy_bin, py_site_pkgs, shlib_ext),
            "    'cp %s %s/plugins/libpytoy_cuda.%s'," % (toy_bin, py_site_pkgs, shlib_ext),
            "]",
        ])
        write_file(toy_ec_cuda, toy_ec_txt)

        # Create mock cuobjdump
        # First, lets define sections of echo's for cuobjdump for various scenarios

        # Shebang for cuobjdump
        cuobjdump_txt_shebang = "#!/bin/bash\n"

        # Section for cuobjdump printing output for sm_70 architecture
        cuobjdump_txt_sm70 = '\n'.join([
            "echo 'Fatbin elf code:'",
            "echo '================'",
            "echo 'arch = sm_70'",
            "echo 'code version = [1,7]'",
            "echo 'host = linux'",
            "echo 'compile_size = 64bit'",
            "echo ''\n"
        ])

        # Section for cuobjdump printing output for sm_70 architecture
        cuobjdump_txt_sm80 = '\n'.join([
            "echo 'Fatbin elf code:'",
            "echo '================'",
            "echo 'arch = sm_80'",
            "echo 'code version = [1,7]'",
            "echo 'host = linux'",
            "echo 'compile_size = 64bit'",
            "echo ''\n"
        ])

        # Section for cuobjdump printing output for sm_90 architecture
        cuobjdump_txt_sm90 = '\n'.join([
            "echo 'Fatbin elf code:'",
            "echo '================'",
            "echo 'arch = sm_90'",
            "echo 'code version = [1,7]'",
            "echo 'host = linux'",
            "echo 'compile_size = 64bit'",
            "echo ''\n"
        ])

        # Section for cuobjdump printing output for sm_90a architecture
        cuobjdump_txt_sm90a = '\n'.join([
            "echo 'Fatbin elf code:'",
            "echo '================'",
            "echo 'arch = sm_90a'",
            "echo 'code version = [1,7]'",
            "echo 'host = linux'",
            "echo 'compile_size = 64bit'",
            "echo ''\n"
        ])

        # Section for cuobjdump printing output for sm_80 PTX code
        cuobjdump_txt_sm80_ptx = '\n'.join([
            "echo 'Fatbin ptx code:'",
            "echo '================'",
            "echo 'arch = sm_80'",
            "echo 'code version = [8,1]'",
            "echo 'host = linux'",
            "echo 'compile_size = 64bit'",
            "echo 'compressed'",
            "echo ''\n"
        ])

        # Section for cuobjdump printing output for sm_90a PTX code
        cuobjdump_txt_sm90a_ptx = '\n'.join([
            "echo 'Fatbin ptx code:'",
            "echo '================'",
            "echo 'arch = sm_90a'",
            "echo 'code version = [8,1]'",
            "echo 'host = linux'",
            "echo 'compile_size = 64bit'",
            "echo 'compressed'",
            "echo ''\n"
        ])

        # Section for cuobjdump printing output that toy doesn't contain device code
        cuobjdump_txt_no_cuda = "echo 'cuobjdump info    : File '/mock/path/to/toy' does not contain device code'"

        # Created regex for success and failures
        device_code_regex_success_pattern = r"DEBUG Output of 'cuobjdump' checked for '.*/bin/toy'; device code "
        device_code_regex_success_pattern += "architectures match those in cuda_compute_capabilities"
        device_code_regex_success = re.compile(device_code_regex_success_pattern, re.M)

        device_missing_80_code_regex_pattern = r"Missing compute capabilities: 8.0."
        device_missing_80_code_regex = re.compile(device_missing_80_code_regex_pattern, re.M)

        device_additional_70_code_regex_pattern = r"Additional compute capabilities: 7.0."
        device_additional_70_code_regex = re.compile(device_additional_70_code_regex_pattern, re.M)
        device_additional_70_90_code_regex_pattern = r"Additional compute capabilities: 7.0, 9.0."
        device_additional_70_90_code_regex = re.compile(device_additional_70_90_code_regex_pattern, re.M)

        ptx_code_regex_success_pattern = r"DEBUG Output of 'cuobjdump' checked for '.*/bin/toy'; ptx code was "
        ptx_code_regex_success_pattern += r"present for \(at least\) the highest CUDA compute capability in "
        ptx_code_regex_success_pattern += "cuda_compute_capabilities"
        ptx_code_regex_success = re.compile(ptx_code_regex_success_pattern, re.M)

        # Create temporary subdir for cuobjdump, so that we don't have to add self.test_prefix itself to the PATH
        cuobjdump_dir = os.path.join(self.test_prefix, 'cuobjdump_dir')
        mkdir(cuobjdump_dir, parents=True)

        # Add cuobjdump_dir to the path
        setvar('PATH', '%s:%s' % (cuobjdump_dir, os.getenv('PATH')))

        # Pretend the CUDA dep is already installed
        module_dir = os.path.join(self.test_prefix, 'modules', 'all')
        mkdir(module_dir, parents=True)
        cuda_mod_dir = os.path.join(module_dir, 'CUDA')
        cuda_mod_file = os.path.join(cuda_mod_dir, '5.5.22.lua')
        cuda_mod_file_tcl = os.path.join(cuda_mod_dir, '5.5.22')
        write_file(cuda_mod_file, "-- Fake module content for CUDA")
        write_file(cuda_mod_file_tcl, "#%Module1.0")
        write_file(cuda_mod_file_tcl, "#This is a fake module file for CUDA", append=True)
        setvar('MODULEPATH', module_dir)

        # Filepath to cuobjdump
        cuobjdump_file = os.path.join(cuobjdump_dir, 'cuobjdump')

        # Predefine a function that takes a pattern, creates a regex, searches if it's found in the log
        # Also, check if it's found in stdout, if defined
        # If either of these fail their assert, print an informative, standardized message
        def assert_regex(pattern, log, stdout=None):
            regex = re.compile(pattern, re.M)
            msg = "Pattern '%s' not found in full build log: %s" % (pattern, log)
            self.assertTrue(regex.search(log), msg)
            if stdout is not None:
                msg2 = "Pattern '%s' not found in standard output: %s" % (pattern, stdout)
                self.assertTrue(regex.search(stdout), msg2)

        def assert_cuda_report(missing_cc, additional_cc, missing_ptx, log, stdout=None, missing_cc_but_ptx=None,
                               num_checked=None):
            if num_checked is not None:
                num_checked_str = r"Number of CUDA files checked: %s" % num_checked
                assert_regex(num_checked_str, outtxt, stdout)
            if missing_cc_but_ptx is not None:
                missing_cc_but_ptx_str = r"Number of files missing one or more CUDA Compute Capabilities, but having "
                missing_cc_but_ptx_str += r"suitable PTX code that can be JIT compiled for the requested CUDA Compute "
                missing_cc_but_ptx_str += r"Capabilities: %s" % additional_cc
                assert_regex(missing_cc_but_ptx_str, outtxt, stdout)
            missing_cc_str = r"Number of files missing one or more CUDA Compute Capabilities: %s" % missing_cc
            additional_cc_str = r"Number of files with device code for more CUDA Compute Capabilities than requested: "
            additional_cc_str += r"%s" % additional_cc
            missing_ptx_str = r"Number of files missing PTX code for the highest configured CUDA Compute Capability: "
            missing_ptx_str += r"%s" % missing_ptx
            assert_regex(missing_cc_str, outtxt, stdout)
            assert_regex(additional_cc_str, outtxt, stdout)
            assert_regex(missing_ptx_str, outtxt, stdout)

        # Test case 1a: test with default options, --cuda-compute-capabilities=8.0 and a binary that contains
        # 8.0 device code
        # This should succeed (since the default for --cuda-sanity-check-error-on-failed-checks is False)
        # as to not break backwards compatibility
        write_file(cuobjdump_file, cuobjdump_txt_shebang),
        write_file(cuobjdump_file, cuobjdump_txt_sm80, append=True)
        adjust_permissions(cuobjdump_file, stat.S_IXUSR, add=True)  # Make sure our mock cuobjdump is executable
        args = ['--cuda-compute-capabilities=8.0']
        # We expect this to pass, so no need to check errors
        with self.mocked_stdout_stderr():
            outtxt = self._test_toy_build(ec_file=toy_ec_cuda, extra_args=args, raise_error=True)
            stdout = self.get_stdout()
        assert_cuda_report(missing_cc=0, additional_cc=0, missing_ptx=3, log=outtxt, stdout=stdout)

        # Test case 1b: test with default options, --cuda-compute-capabilities=8.0 and a binary that contains
        # 7.0 and 9.0 device code and 8.0 PTX code.
        # Note that the difference with 1a is the presense of additional device code, PTX code foor the right
        # architecture, but missing device code for the requested architecture
        # It should not matter for the result, but triggers slightly different code paths in easyblock.py
        # This should succeed (since the default for --cuda-sanity-check-error-on-failed-checks is False)
        # as to not break backwards compatibility
        write_file(cuobjdump_file, cuobjdump_txt_shebang),
        write_file(cuobjdump_file, cuobjdump_txt_sm90, append=True)
        write_file(cuobjdump_file, cuobjdump_txt_sm80_ptx, append=True)
        write_file(cuobjdump_file, cuobjdump_txt_sm70, append=True)
        adjust_permissions(cuobjdump_file, stat.S_IXUSR, add=True)  # Make sure our mock cuobjdump is executable
        args = ['--cuda-compute-capabilities=8.0']
        # We expect this to pass, so no need to check errors
        with self.mocked_stdout_stderr():
            outtxt = self._test_toy_build(ec_file=toy_ec_cuda, extra_args=args, raise_error=True)
            stdout = self.get_stdout()
        msg = "Pattern '%s' not found in full build log: %s" % (device_additional_70_90_code_regex.pattern, outtxt)
        self.assertTrue(device_additional_70_90_code_regex.search(outtxt), msg)
        msg = "Pattern '%s' not found in full build log: %s" % (device_missing_80_code_regex.pattern, outtxt)
        self.assertTrue(device_missing_80_code_regex.search(outtxt), msg)
        assert_cuda_report(missing_cc=3, additional_cc=3, missing_ptx=0, log=outtxt, stdout=stdout)

        # Test case 2: same as Test case 1, but add --cuda-sanity-check-error-on-failed-checks
        # This is expected to fail since there is missing device code for CC80
        args = ['--cuda-compute-capabilities=8.0', '--cuda-sanity-check-error-on-failed-checks']
        # We expect this to fail, so first check error, then run again to check output
        error_pattern = r"Files missing CUDA device code: 3."
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, ec_file=toy_ec_cuda,
                                  extra_args=args, raise_error=True)
            outtxt = self._test_toy_build(ec_file=toy_ec_cuda, extra_args=args, raise_error=False, verify=False)
            stdout = self.get_stdout()
        msg = "Pattern '%s' not found in full build log: %s" % (device_additional_70_90_code_regex.pattern, outtxt)
        self.assertTrue(device_additional_70_90_code_regex.search(outtxt), msg)
        msg = "Pattern '%s' not found in full build log: %s" % (device_missing_80_code_regex.pattern, outtxt)
        self.assertTrue(device_missing_80_code_regex.search(outtxt), msg)
        assert_cuda_report(missing_cc=3, additional_cc=3, missing_ptx=0, log=outtxt, stdout=stdout)

        # Test case 3: same as Test case 2, but add --cuda-sanity-check-accept-ptx-as-devcode
        # This is expected to succeed, since now the PTX code for CC80 will be accepted as
        # device code. Note that also PTX code for the highest requested compute architecture (also CC80)
        # is present, so also this part of the sanity check passes
        args = ['--cuda-compute-capabilities=8.0', '--cuda-sanity-check-error-on-failed-checks',
                '--cuda-sanity-check-accept-ptx-as-devcode']
        # We expect this to pass, so no need to check errors
        with self.mocked_stdout_stderr():
            outtxt = self._test_toy_build(ec_file=toy_ec_cuda, extra_args=args, raise_error=True)
            stdout = self.get_stdout()
        msg = "Pattern '%s' not found in full build log: %s" % (device_additional_70_90_code_regex.pattern, outtxt)
        self.assertTrue(device_additional_70_90_code_regex.search(outtxt), msg)
        msg = "Pattern '%s' not found in full build log: %s" % (device_missing_80_code_regex.pattern, outtxt)
        self.assertTrue(device_missing_80_code_regex.search(outtxt), msg)
        assert_cuda_report(missing_cc=0, additional_cc=3, missing_ptx=0, log=outtxt, stdout=stdout,
                           missing_cc_but_ptx=3)

        # Test case 4: same as Test case 2, but run with --cuda-compute-capabilities=9.0
        # This is expected to fail: device code is present, but PTX code for the highest CC (9.0) is missing
        args = ['--cuda-compute-capabilities=9.0', '--cuda-sanity-check-error-on-failed-checks']
        # We expect this to fail, so first check error, then run again to check output
        error_pattern = r"Files missing CUDA PTX code: 3"
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, ec_file=toy_ec_cuda,
                                  extra_args=args, raise_error=True)
            outtxt = self._test_toy_build(ec_file=toy_ec_cuda, extra_args=args, raise_error=False, verify=False)
            stdout = self.get_stdout()
        msg = "Pattern '%s' not found in full build log: %s" % (device_additional_70_code_regex.pattern, outtxt)
        self.assertTrue(device_additional_70_code_regex.search(outtxt), msg)
        assert_cuda_report(missing_cc=0, additional_cc=3, missing_ptx=3, log=outtxt, stdout=stdout)

        # Test case 5: same as Test case 4, but add --cuda-sanity-check-accept-missing-ptx
        # This is expected to succeed: device code is present, PTX code is missing, but that's accepted
        args = ['--cuda-compute-capabilities=9.0', '--cuda-sanity-check-error-on-failed-checks',
                '--cuda-sanity-check-accept-missing-ptx']
        # We expect this to pass, so no need to check errors
        warning_pattern = r"Configured highest compute capability was '9\.0', "
        warning_pattern += r"but no PTX code for this compute capability was found in '.*/bin/toy' "
        warning_pattern += r"\(PTX architectures supported in that file: \['8\.0'\]\)"
        warning_pattern_regex = re.compile(warning_pattern, re.M)
        with self.mocked_stdout_stderr():
            outtxt = self._test_toy_build(ec_file=toy_ec_cuda, extra_args=args, raise_error=True)
            stdout = self.get_stdout()
        msg = "Pattern '%s' not found in full build log: %s" % (device_additional_70_code_regex.pattern, outtxt)
        self.assertTrue(device_additional_70_code_regex.search(outtxt), msg)
        msg = "Pattern '%s' not found in full build log: %s" % (warning_pattern, outtxt)
        self.assertTrue(warning_pattern_regex.search(outtxt), msg)
        assert_cuda_report(missing_cc=0, additional_cc=3, missing_ptx=3, log=outtxt, stdout=stdout)

        # Test case 6: same as Test case 5, but add --cuda-sanity-check-strict
        # This is expected to fail: device code is present, PTX code is missing (but accepted due to option)
        # but additional device code is present, which is not allowed by --cuda-sanity-check-strict
        args = ['--cuda-compute-capabilities=9.0', '--cuda-sanity-check-error-on-failed-checks',
                '--cuda-sanity-check-accept-missing-ptx', '--cuda-sanity-check-strict']
        # We expect this to fail, so first check error, then run again to check output
        error_pattern = r"Files with additional CUDA device code: 3"
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, ec_file=toy_ec_cuda,
                                  extra_args=args, raise_error=True)
            outtxt = self._test_toy_build(ec_file=toy_ec_cuda, extra_args=args, raise_error=False, verify=False)
            stdout = self.get_stdout()
        msg = "Pattern '%s' not found in full build log: %s" % (device_additional_70_code_regex.pattern, outtxt)
        self.assertTrue(device_additional_70_code_regex.search(outtxt), msg)
        assert_cuda_report(missing_cc=0, additional_cc=3, missing_ptx=3, log=outtxt, stdout=stdout)

        # Test case 7: same as Test case 6, but add the failing file to the cuda_sanity_ignore_files
        # This is expected to succeed: the individual file which _would_ cause the sanity check to fail is
        # now on the ignore list
        toy_whitelist_ec = os.path.join(self.test_prefix, 'toy-0.0-cuda-whitelist.eb')
        toy_ec_txt = read_file(toy_ec)
        toy_ec_txt += '\n' + '\n'.join([
            "dependencies = [('CUDA', '5.5.22', '', SYSTEM)]",
            "cuda_sanity_ignore_files = ['bin/toy']",
        ])
        write_file(toy_ec_cuda, toy_ec_txt)
        write_file(toy_whitelist_ec, toy_ec_txt)

        args = ['--cuda-compute-capabilities=9.0', '--cuda-sanity-check-error-on-failed-checks',
                '--cuda-sanity-check-accept-missing-ptx', '--cuda-sanity-check-strict']
        # We expect this to succeed, so check output for expected patterns
        with self.mocked_stdout_stderr():
            outtxt = self._test_toy_build(ec_file=toy_whitelist_ec, extra_args=args, raise_error=True, verify=False)
            stdout = self.get_stdout()
        msg = "Pattern '%s' not found in full build log: %s" % (device_additional_70_code_regex.pattern, outtxt)
        self.assertTrue(device_additional_70_code_regex.search(outtxt), msg)
        assert_cuda_report(missing_cc=0, additional_cc=1, missing_ptx=1, log=outtxt, stdout=stdout)

        # Test case 8: try with --cuda-sanity-check-error-on-failed-checks --cuda-compute-capabilities=9.0,9.0a
        # and --cuda-sanity-check-strict
        # on a binary that contains 9.0 and 9.0a device code, and 9.0a ptx code. This tests the correct
        # ordering (i.e. 9.0a > 9.0). It should pass, since device code is present for both CCs and PTX
        # code is present for the highest CC, and there is no additiona device code present
        # This also tests a case with multiple compute capabilities.
        write_file(cuobjdump_file, cuobjdump_txt_shebang),
        write_file(cuobjdump_file, cuobjdump_txt_sm90, append=True)
        write_file(cuobjdump_file, cuobjdump_txt_sm90a, append=True)
        write_file(cuobjdump_file, cuobjdump_txt_sm90a_ptx, append=True)
        adjust_permissions(cuobjdump_file, stat.S_IXUSR, add=True)  # Make sure our mock cuobjdump is executable
        args = ['--cuda-compute-capabilities=9.0,9.0a', '--cuda-sanity-check-error-on-failed-checks',
                '--cuda-sanity-check-strict']
        # We expect this to pass, so no need to check errors
        with self.mocked_stdout_stderr():
            outtxt = self._test_toy_build(ec_file=toy_ec_cuda, extra_args=args, raise_error=True)
            stdout = self.get_stdout()
        msg = "Pattern '%s' not found in full build log: %s" % (device_code_regex_success.pattern, outtxt)
        self.assertTrue(device_code_regex_success.search(outtxt), msg)
        msg = "Pattern '%s' not found in full build log: %s" % (ptx_code_regex_success.pattern, outtxt)
        self.assertTrue(ptx_code_regex_success.search(outtxt), msg)
        expected_result_pattern = "INFO Sanity check for toy successful"
        expected_result = re.compile(expected_result_pattern, re.M)
        msg = "Pattern '%s' not found in full build log: %s" % (expected_result, outtxt)
        self.assertTrue(expected_result.search(outtxt), msg)
        assert_cuda_report(missing_cc=0, additional_cc=0, missing_ptx=0, log=outtxt, stdout=stdout)

        # Test case 9: same as 8, but no --cuda-compute-capabilities are defined
        # We expect this to lead to a skip of the CUDA sanity check, and a success for the overall sanity check
        args = ['--cuda-sanity-check-error-on-failed-checks', '--cuda-sanity-check-strict']
        # We expect this to pass, so no need to check errors
        with self.mocked_stdout_stderr():
            outtxt = self._test_toy_build(ec_file=toy_ec_cuda, extra_args=args, raise_error=True)
            stdout = self.get_stdout()
        cuda_sanity_skipped = r"INFO Skipping CUDA sanity check, as no CUDA compute capabilities were configured"
        cuda_sanity_skipped_regex = re.compile(cuda_sanity_skipped, re.M)
        msg = "Pattern '%s' not found in full build log: %s" % (cuda_sanity_skipped, outtxt)
        self.assertTrue(cuda_sanity_skipped_regex.search(outtxt), msg)
        expected_result_pattern = "INFO Sanity check for toy successful"
        expected_result = re.compile(expected_result_pattern, re.M)
        msg = "Pattern '%s' not found in full build log: %s" % (expected_result, outtxt)
        self.assertTrue(expected_result.search(outtxt), msg)

        # Test case 10: running with default options and a binary that does not contain ANY CUDA device code
        # This is expected to succeed, since the default is --disable-cuda-sanity-check-error-on-failed-checks
        write_file(cuobjdump_file, cuobjdump_txt_shebang)
        write_file(cuobjdump_file, cuobjdump_txt_no_cuda, append=True)
        adjust_permissions(cuobjdump_file, stat.S_IXUSR, add=True)  # Make sure our mock cuobjdump is executable
        args = ['--cuda-compute-capabilities=9.0']
        # We expect this to pass, so no need to check errors
        with self.mocked_stdout_stderr():
            outtxt = self._test_toy_build(ec_file=toy_ec_cuda, extra_args=args, raise_error=True)
            stdout = self.get_stdout()
        no_cuda_pattern = r".*/bin/toy does not appear to be a CUDA executable \(no CUDA device code found\), "
        no_cuda_pattern += r"so skipping CUDA sanity check"
        no_cuda_regex = re.compile(no_cuda_pattern, re.M)
        msg = "Pattern '%s' not found in full build log: %s" % (no_cuda_pattern, outtxt)
        self.assertTrue(no_cuda_regex.search(outtxt), msg)
        expected_result_pattern = "INFO Sanity check for toy successful"
        expected_result = re.compile(expected_result_pattern, re.M)
        msg = "Pattern '%s' not found in full build log: %s" % (expected_result, outtxt)
        self.assertTrue(expected_result.search(outtxt), msg)
        assert_cuda_report(missing_cc=0, additional_cc=0, missing_ptx=0, log=outtxt, stdout=stdout, num_checked=0)

        # Test case 11: same as Test case 10, but add --cuda-sanity-check-error-on-failed-checks
        # This should pass: if it's not a CUDA binary, it shouldn't fail the CUDA sanity check
        args = ['--cuda-compute-capabilities=9.0', '--cuda-sanity-check-error-on-failed-checks']
        # We expect this to pass, so no need to check errors
        with self.mocked_stdout_stderr():
            outtxt = self._test_toy_build(ec_file=toy_ec_cuda, extra_args=args, raise_error=True)
            stdout = self.get_stdout()
        no_cuda_pattern = r".*/bin/toy does not appear to be a CUDA executable \(no CUDA device code found\), "
        no_cuda_pattern += r"so skipping CUDA sanity check"
        no_cuda_regex = re.compile(no_cuda_pattern, re.M)
        msg = "Pattern '%s' not found in full build log: %s" % (no_cuda_pattern, outtxt)
        self.assertTrue(no_cuda_regex.search(outtxt), msg)
        expected_result_pattern = "INFO Sanity check for toy successful"
        expected_result = re.compile(expected_result_pattern, re.M)
        msg = "Pattern '%s' not found in full build log: %s" % (expected_result, outtxt)
        self.assertTrue(expected_result.search(outtxt), msg)
        assert_cuda_report(missing_cc=0, additional_cc=0, missing_ptx=0, log=outtxt, stdout=stdout, num_checked=0)

    def test_toy_modaltsoftname(self):
        """Build two dependent toys as in test_toy_toy but using modaltsoftname"""
        topdir = os.path.dirname(os.path.abspath(__file__))
        toy_ec_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec_file)

        self.assertFalse(re.search('^modaltsoftname', toy_ec_txt, re.M))

        ec1 = os.path.join(self.test_prefix, 'toy-0.0-one.eb')
        ec1_txt = '\n'.join([
            toy_ec_txt,
            "versionsuffix = '-one'",
            "modaltsoftname = 'yot'"
        ])
        write_file(ec1, ec1_txt)

        ec2 = os.path.join(self.test_prefix, 'toy-0.0-two.eb')
        ec2_txt = '\n'.join([
            toy_ec_txt,
            "versionsuffix = '-two'",
            "dependencies = [('toy', '0.0', '-one')]",
            "modaltsoftname = 'toytwo'",
        ])
        write_file(ec2, ec2_txt)

        extra_args = [
            '--module-naming-scheme=HierarchicalMNS',
            '--robot-paths=%s' % self.test_prefix,
        ]
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=self.test_prefix, verify=False, extra_args=extra_args, raise_error=True)

        software_path = os.path.join(self.test_installpath, 'software')
        modules_path = os.path.join(self.test_installpath, 'modules', 'all', 'Core')

        # install dirs for both installations should be there (using original software name)
        self.assertExists(os.path.join(software_path, 'toy', '0.0-one', 'bin', 'toy'))
        self.assertExists(os.path.join(software_path, 'toy', '0.0-two', 'bin', 'toy'))

        toytwo_name = '0.0-two'
        yot_name = '0.0-one'
        if get_module_syntax() == 'Lua':
            toytwo_name += '.lua'
            yot_name += '.lua'

        # modules for both installations with alternative name should be there
        self.assertExists(os.path.join(modules_path, 'toytwo', toytwo_name))
        self.assertExists(os.path.join(modules_path, 'yot', yot_name))

        # only subdirectories for software should be created
        self.assertEqual(sorted(os.listdir(software_path)), sorted(['toy', '.locks']))
        self.assertEqual(sorted(os.listdir(os.path.join(software_path, 'toy'))), ['0.0-one', '0.0-two'])

        # only subdirectories for modules with alternative names should be created
        self.assertEqual(sorted(os.listdir(modules_path)), ['toytwo', 'yot'])
        self.assertEqual(os.listdir(os.path.join(modules_path, 'toytwo')), [toytwo_name])
        self.assertEqual(os.listdir(os.path.join(modules_path, 'yot')), [yot_name])

    def test_toy_build_trace(self):
        """Test use of --trace"""

        topdir = os.path.dirname(os.path.abspath(__file__))
        toy_ec_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, read_file(toy_ec_file) + '\nsanity_check_commands = ["toy"]')

        self.mock_stderr(True)
        self.mock_stdout(True)
        self._test_toy_build(ec_file=test_ec, extra_args=['--trace'], verify=False, testing=False)
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        self.assertEqual(stderr, '')

        patterns = [
            r"^  >> installation prefix: .*/software/toy/0\.0$",
            r"^== fetching files and verifying checksums\.\.\.\n"
            r"  >> sources:\n  >> .*/toy-0\.0\.tar\.gz \[SHA256: 44332000.*\]$",
            r"^  >> applying patch toy-0\.0_fix-silly-typo-in-printf-statement\.patch$",
            r'\n'.join([
                r"^  >> running shell command:",
                r"\tgcc toy.c -o toy\n"
                r"\t\[started at: .*\]",
                r"\t\[working dir: .*\]",
                r"\t\[output and state saved to .*\]",
                r'',
            ]),
            r"  >> command completed: exit 0, ran in .*",
            r'^' + r'\n'.join([
                r"== sanity checking\.\.\.",
                r"  >> file 'bin/yot' or 'bin/toy' found: OK",
                r"  >> \(non-empty\) directory 'bin' found: OK",
                r"  >> loading modules: toy/0.0\.\.\.",
                r"  >> running command 'toy' \.\.\.",
                r"  >> result for command 'toy': OK",
            ]) + r'$',
            r"^== creating module\.\.\.\n  >> generating module file @ .*/modules/all/toy/0\.0(?:\.lua)?$",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

    def test_toy_build_hooks(self):
        """Test use of --hooks."""
        toy_ec = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ec_txt = read_file(toy_ec) + '\n'.join([
            "exts_list = [('bar', '0.0'), ('toy', '0.0')]",
            "exts_defaultclass = 'DummyExtension'",
        ])
        write_file(test_ec, test_ec_txt)

        hooks_file = os.path.join(self.test_prefix, 'my_hooks.py')
        hooks_file_txt = textwrap.dedent("""
            import os
            from easybuild.tools.filetools import change_dir, copy_file

            TOY_COMP_CMD = "gcc toy.c -o toy"

            def start_hook():
               print('start hook triggered')

            def parse_hook(ec):
               print('%s %s' % (ec.name, ec.version))
               # print sources value to check that raw untemplated strings are exposed in parse_hook
               print(ec['sources'])
               # try appending to postinstallcmd to see whether the modification is actually picked up
               # (required templating to be disabled before parse_hook is called)
               ec['postinstallcmds'].append('echo toy')
               print(ec['postinstallcmds'][-1])

            def pre_build_and_install_loop_hook(ecs):
                mod_names = ' '.join(ec['full_mod_name'] for ec in ecs)
                print(f"installing {len(ecs)} easyconfigs: {mod_names}")

            def pre_easyblock_hook(self):
                print(f'starting installation of {self.name} {self.version}')

            def pre_configure_hook(self):
                print('pre-configure: toy.source: %s' % os.path.exists('toy.source'))

            def post_configure_hook(self):
                print('post-configure: toy.source: %s' % os.path.exists('toy.source'))

            def post_install_hook(self):
                print('in post-install hook for %s v%s' % (self.name, self.version))
                print(', '.join(sorted(os.listdir(self.installdir))))

                copy_of_toy = os.path.join(self.start_dir, 'copy_of_toy')
                copy_file(copy_of_toy, os.path.join(self.installdir, 'bin'))

            def module_write_hook(self, module_path, module_txt):
                print('in module-write hook hook for %s' % os.path.basename(module_path))
                return module_txt.replace('Toy C program, 100% toy.', 'Not a toy anymore')

            def post_single_extension_hook(ext):
                print('installing of extension %s is done!' % ext.name)

            def pre_sanitycheck_hook(self):
                print('pre_sanity_check_hook')

            def end_hook():
               print('end hook triggered, all done!')

            def pre_run_shell_cmd_hook(cmd, *args, **kwargs):
                if isinstance(cmd, str) and cmd.strip() == TOY_COMP_CMD:
                    print("pre_run_shell_cmd_hook triggered for '%s'" % cmd)
                    # 'copy_toy_file' command doesn't exist, but don't worry,
                    # this problem will be fixed in post_run_shell_cmd_hook
                    cmd += " && copy_toy_file toy copy_of_toy"
                return cmd

            def post_run_shell_cmd_hook(cmd, *args, **kwargs):
                exit_code = kwargs['exit_code']
                output = kwargs['output']
                work_dir = kwargs['work_dir']
                if isinstance(cmd, str) and cmd.strip().startswith(TOY_COMP_CMD) and exit_code:
                    cwd = change_dir(work_dir)
                    copy_file('toy', 'copy_of_toy')
                    change_dir(cwd)
                    print("'%s' command failed (exit code %s), but I fixed it!" % (cmd, exit_code))

            def post_easyblock_hook(self):
                print(f'done with installation of {self.name} {self.version}')

            def post_build_and_install_loop_hook(ecs):
                mod_names = ' '.join(ec[0]['full_mod_name'] for ec in ecs)
                print(f"done with installing {len(ecs)} easyconfigs: {mod_names}")
        """)
        write_file(hooks_file, hooks_file_txt)

        extra_args = [
            '--hooks=%s' % hooks_file,
            # disable trace output to make checking of generated output produced by hooks easier
            '--disable-trace',
        ]

        self.mock_stderr(True)
        self.mock_stdout(True)
        self._test_toy_build(ec_file=test_ec, extra_args=extra_args, raise_error=True, debug=False)
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        test_mod_path = os.path.join(self.test_installpath, 'modules', 'all')
        toy_mod_file = os.path.join(test_mod_path, 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_mod_file += '.lua'
        mod_name = os.path.basename(toy_mod_file)

        warnings = nub([x for x in stderr.strip().splitlines() if x])
        self.assertEqual(warnings, ["WARNING: Command ' gcc toy.c -o toy ' failed, but we'll ignore it..."])

        # parse hook is triggered 3 times: once for main install, and then again for each extension;
        # module write hook is triggered 5 times:
        # - before installing extensions
        # - for fake module file being created during sanity check (triggered twice, for main + toy install)
        # - for final module file
        # - for devel module file
        expected_output = textwrap.dedent(f"""
            start hook triggered
            toy 0.0
            ['%(name)s-%(version)s.tar.gz']
            echo toy
            installing 1 easyconfigs: toy/0.0
            starting installation of toy 0.0
            pre-configure: toy.source: True
            post-configure: toy.source: False
            pre_run_shell_cmd_hook triggered for ' gcc toy.c -o toy '
            ' gcc toy.c -o toy  && copy_toy_file toy copy_of_toy' command failed (exit code 127), but I fixed it!
            in post-install hook for toy v0.0
            bin, lib
            toy 0.0
            ['%(name)s-%(version)s.tar.gz']
            echo toy
            toy 0.0
            ['%(name)s-%(version)s.tar.gz']
            echo toy
            in module-write hook hook for {mod_name}
            installing of extension bar is done!
            in module-write hook hook for {mod_name}
            pre_run_shell_cmd_hook triggered for ' gcc toy.c -o toy '
            ' gcc toy.c -o toy  && copy_toy_file toy copy_of_toy' command failed (exit code 127), but I fixed it!
            installing of extension toy is done!
            pre_sanity_check_hook
            in module-write hook hook for {mod_name}
            in module-write hook hook for {mod_name}
            in module-write hook hook for {mod_name}
            in module-write hook hook for {mod_name}
            done with installation of toy 0.0
            done with installing 1 easyconfigs: toy/0.0
            end hook triggered, all done!
        """).strip().format(mod_name=os.path.basename(toy_mod_file))
        self.assertEqual(stdout.strip(), expected_output)

        toy_mod = read_file(toy_mod_file)
        self.assertIn('Not a toy anymore', toy_mod)

        toy_bin_dir = os.path.join(self.test_installpath, 'software', 'toy', '0.0', 'bin')
        toy_bins = sorted(os.listdir(toy_bin_dir))
        self.assertEqual(toy_bins, ['bar', 'copy_of_toy', 'toy'])

    def test_toy_multi_deps(self):
        """Test installation of toy easyconfig that uses multi_deps."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0.eb')
        test_ec_txt = read_file(toy_ec)

        test_ec = os.path.join(self.test_prefix, 'test.eb')

        # also inject (minimal) list of extensions to test iterative installation of extensions
        test_ec_txt += "\nexts_defaultclass = 'DummyExtension'"
        test_ec_txt += "\nexts_list = [('barbar', '1.2', {'start_dir': 'src'})]"

        test_ec_txt += "\nmulti_deps = {'GCC': ['4.6.3', '7.3.0-2.30']}"

        write_file(test_ec, test_ec_txt)

        test_mod_path = os.path.join(self.test_installpath, 'modules', 'all')

        # create empty modules for both GCC versions
        # (in Tcl syntax, because we're lazy since that works for all supported module tools)
        gcc463_modfile = os.path.join(test_mod_path, 'GCC', '4.6.3')
        write_file(gcc463_modfile, ModuleGeneratorTcl.MODULE_SHEBANG)
        write_file(os.path.join(test_mod_path, 'GCC', '7.3.0-2.30'), ModuleGeneratorTcl.MODULE_SHEBANG)

        self.modtool.use(test_mod_path)

        # instruct Lmod to disallow auto-swapping of already loaded module with same name as module being loaded
        # to make situation where GCC/7.3.0-2.30 is loaded when GCC/4.6.3 is already loaded (by default) fail
        os.environ['LMOD_DISABLE_SAME_NAME_AUTOSWAP'] = 'yes'

        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec)

        toy_mod_file = os.path.join(test_mod_path, 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_mod_file += '.lua'

        toy_mod_txt = read_file(toy_mod_file)

        # check whether (guarded) load statement for first version listed in multi_deps is there
        if get_module_syntax() == 'Lua':
            expected = '\n'.join([
                'if mode() == "unload" or isloaded("GCC/7.3.0-2.30") then',
                '    depends_on("GCC")',
                'else',
                '    depends_on("GCC/4.6.3")',
                'end',
            ])
        else:
            if isinstance(self.modtool, EnvironmentModules):
                load_stmt = "module load"
            else:
                load_stmt = "depends-on"
            expected = '\n'.join([
                '',
                "if { [ module-info mode remove ] || [ is-loaded GCC/7.3.0-2.30 ] } {",
                "    %s GCC" % load_stmt,
                '} else {',
                "    %s GCC/4.6.3" % load_stmt,
                '}',
                '',
            ])

        self.assertIn(expected, toy_mod_txt)

        # also check relevant parts of "module help" and whatis bits
        expected_descr = '\n'.join([
            "Compatible modules",
            "==================",
            "This module is compatible with the following modules, one of each line is required:",
            "* GCC/4.6.3 (default), GCC/7.3.0-2.30",
        ])
        error_msg_descr = "Pattern '%s' should be found in: %s" % (expected_descr, toy_mod_txt)
        self.assertIn(expected_descr, toy_mod_txt, error_msg_descr)

        if get_module_syntax() == 'Lua':
            expected_whatis = "whatis([==[Compatible modules: GCC/4.6.3 (default), GCC/7.3.0-2.30]==])"
        else:
            expected_whatis = "module-whatis {Compatible modules: GCC/4.6.3 (default), GCC/7.3.0-2.30}"

        error_msg_whatis = "Pattern '%s' should be found in: %s" % (expected_whatis, toy_mod_txt)
        self.assertIn(expected_whatis, toy_mod_txt, error_msg_whatis)

        def check_toy_load(depends_on=False):
            # by default, toy/0.0 should load GCC/4.6.3 (first listed GCC version in multi_deps)
            self.modtool.load(['toy/0.0'])
            loaded_mod_names = [x['mod_name'] for x in self.modtool.list()]
            self.assertIn('toy/0.0', loaded_mod_names)
            self.assertIn('GCC/4.6.3', loaded_mod_names)
            self.assertNotIn('GCC/7.3.0-2.30', loaded_mod_names)

            if depends_on:
                # check behaviour when unloading toy (should also unload GCC/4.6.3)
                self.modtool.unload(['toy/0.0'])
                loaded_mod_names = [x['mod_name'] for x in self.modtool.list()]
                self.assertNotIn('toy/0.0', loaded_mod_names)
                self.assertNotIn('GCC/4.6.3', loaded_mod_names)
            else:
                # just undo (don't use 'purge', make cause problems in test environment), to prepare for next test
                self.modtool.unload(['toy/0.0', 'GCC/4.6.3'])

            # if GCC/7.3.0-2.30 is loaded first, then GCC/4.6.3 is not loaded by loading toy/0.0
            self.modtool.load(['GCC/7.3.0-2.30'])
            loaded_mod_names = [x['mod_name'] for x in self.modtool.list()]
            self.assertIn('GCC/7.3.0-2.30', loaded_mod_names)

            self.modtool.load(['toy/0.0'])
            loaded_mod_names = [x['mod_name'] for x in self.modtool.list()]
            self.assertIn('toy/0.0', loaded_mod_names)
            self.assertIn('GCC/7.3.0-2.30', loaded_mod_names)
            self.assertNotIn('GCC/4.6.3', loaded_mod_names)

            if depends_on:
                # check behaviour when unloading toy (should *not* unload GCC/7.3.0-2.30)
                self.modtool.unload(['toy/0.0'])
                loaded_mod_names = [x['mod_name'] for x in self.modtool.list()]
                self.assertNotIn('toy/0.0', loaded_mod_names)
                self.assertIn('GCC/7.3.0-2.30', loaded_mod_names)
                self.modtool.unload(['GCC/7.3.0-2.30'])
            else:
                # just undo
                self.modtool.unload(['toy/0.0', 'GCC/7.3.0-2.30'])

            # having GCC/4.6.3 loaded already is also fine
            self.modtool.load(['GCC/4.6.3'])
            loaded_mod_names = [x['mod_name'] for x in self.modtool.list()]
            self.assertIn('GCC/4.6.3', loaded_mod_names)

            self.modtool.load(['toy/0.0'])
            loaded_mod_names = [x['mod_name'] for x in self.modtool.list()]
            self.assertIn('toy/0.0', loaded_mod_names)
            self.assertIn('GCC/4.6.3', loaded_mod_names)
            self.assertNotIn('GCC/7.3.0-2.30', loaded_mod_names)

            if depends_on:
                # check behaviour when unloading toy (should *not* unload GCC/4.6.3)
                self.modtool.unload(['toy/0.0'])
                loaded_mod_names = [x['mod_name'] for x in self.modtool.list()]
                self.assertNotIn('toy/0.0', loaded_mod_names)
                self.assertIn('GCC/4.6.3', loaded_mod_names)
            else:
                # just undo
                self.modtool.unload(['toy/0.0', 'GCC/4.6.3'])

        with self.saved_env():
            check_toy_load()

        # this behaviour can be disabled via "multi_dep_load_defaults = False"
        write_file(test_ec, test_ec_txt + "\nmulti_deps_load_default = False")

        remove_file(toy_mod_file)
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec)
        toy_mod_txt = read_file(toy_mod_file)

        self.assertNotIn(expected, toy_mod_txt)

        with self.saved_env():
            self.modtool.load(['toy/0.0'])
            loaded_mod_names = [x['mod_name'] for x in self.modtool.list()]
        self.assertIn('toy/0.0', loaded_mod_names)
        self.assertNotIn('GCC/4.6.3', loaded_mod_names)
        self.assertNotIn('GCC/7.3.0-2.30', loaded_mod_names)

        # also check relevant parts of "module help" and whatis bits (no '(default)' here!)
        expected_descr_no_default = '\n'.join([
            "Compatible modules",
            "==================",
            "This module is compatible with the following modules, one of each line is required:",
            "* GCC/4.6.3, GCC/7.3.0-2.30",
        ])
        error_msg_descr = "Pattern '%s' should be found in: %s" % (expected_descr_no_default, toy_mod_txt)
        self.assertIn(expected_descr_no_default, toy_mod_txt, error_msg_descr)

        if get_module_syntax() == 'Lua':
            expected_whatis_no_default = "whatis([==[Compatible modules: GCC/4.6.3, GCC/7.3.0-2.30]==])"
        else:
            expected_whatis_no_default = "module-whatis {Compatible modules: GCC/4.6.3, GCC/7.3.0-2.30}"

        error_msg_whatis = "Pattern '%s' should be found in: %s" % (expected_whatis_no_default, toy_mod_txt)
        self.assertIn(expected_whatis_no_default, toy_mod_txt, error_msg_whatis)

        # disable showing of progress bars (again), doesn't make sense when running tests
        os.environ['EASYBUILD_DISABLE_SHOW_PROGRESS_BAR'] = '1'

        write_file(test_ec, test_ec_txt)

        # also check behaviour when using 'depends_on' rather than 'load' statements (requires Lmod 7.6.1 or newer)
        if self.modtool.supports_depends_on:

            remove_file(toy_mod_file)
            with self.mocked_stdout_stderr():
                self._test_toy_build(ec_file=test_ec, extra_args=['--module-depends-on'], raise_error=True)

            toy_mod_txt = read_file(toy_mod_file)

            # check whether (guarded) load statement for first version listed in multi_deps is there
            if get_module_syntax() == 'Lua':
                expected = '\n'.join([
                    'if mode() == "unload" or isloaded("GCC/7.3.0-2.30") then',
                    '    depends_on("GCC")',
                    'else',
                    '    depends_on("GCC/4.6.3")',
                    'end',
                ])
            else:
                expected = '\n'.join([
                    'if { [ module-info mode remove ] || [ is-loaded GCC/7.3.0-2.30 ] } {',
                    '    depends-on GCC',
                    '} else {',
                    '    depends-on GCC/4.6.3',
                    '}',
                ])

            self.assertIn(expected, toy_mod_txt)
            error_msg_descr = "Pattern '%s' should be found in: %s" % (expected_descr, toy_mod_txt)
            self.assertIn(expected_descr, toy_mod_txt, error_msg_descr)
            error_msg_whatis = "Pattern '%s' should be found in: %s" % (expected_whatis, toy_mod_txt)
            self.assertIn(expected_whatis, toy_mod_txt, error_msg_whatis)

            check_toy_load(depends_on=True)

    def test_fix_shebang(self):
        """Test use of fix_python_shebang_for & co."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec_txt = read_file(os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0.eb'))

        test_ec = os.path.join(self.test_prefix, 'test.eb')

        test_ec_txt = '\n'.join([
            toy_ec_txt,
            "postinstallcmds = ["
            # copy of bin/toy to use in fix_python_shebang_for and fix_perl_shebang_for
            "    'cp -a %(installdir)s/bin/toy %(installdir)s/bin/toy.python',",
            "    'cp -a %(installdir)s/bin/toy %(installdir)s/bin/toy.perl',",
            "    'cp -a %(installdir)s/bin/toy %(installdir)s/bin/toy.sh',",

            # hardcoded path to bin/python
            "    'echo \"#!/usr/bin/python\\n# test\" > %(installdir)s/bin/t1.py',",
            # hardcoded path to bin/python3.6
            "    'echo \"#!/software/Python/3.6.6-foss-2018b/bin/python3.6\\n# test\" > %(installdir)s/bin/t2.py',",
            # already OK, should remain the same
            "    'echo \"#!/usr/bin/env python\\n# test\" > %(installdir)s/bin/t3.py',",
            # space after #! + 'env python3'
            "    'echo \"#! /usr/bin/env python3\\n# test\" > %(installdir)s/bin/t4.py',",
            # 'env python3.6'
            "    'echo \"#!/usr/bin/env python3.6\\n# test\" > %(installdir)s/bin/t5.py',",
            # shebang with space, should strip the space
            "    'echo \"#! /usr/bin/env python\\n# test\" > %(installdir)s/bin/t6.py',",
            # no shebang python
            "    'echo \"# test\" > %(installdir)s/bin/t7.py',",
            # shebang bash
            "    'echo \"#!/usr/bin/env bash\\n# test\" > %(installdir)s/bin/b1.sh',",
            # directory, should be skipped (not crash)
            "    'mkdir %(installdir)s/bin/testdir',",

            # tests for perl shebang
            # hardcoded path to bin/perl
            "    'echo \"#!/usr/bin/perl\\n# test\" > %(installdir)s/bin/t1.pl',",
            # hardcoded path to bin/perl5
            "    'echo \"#!/software/Perl/5.28.1-GCCcore-7.3.0/bin/perl5\\n# test\" > %(installdir)s/bin/t2.pl',",
            # already OK, should remain the same
            "    'echo \"#!/usr/bin/env perl\\n# test\" > %(installdir)s/bin/t3.pl',",
            # hardcoded perl with extra arguments
            "    'echo \"#!/usr/bin/perl -w\\n# test\" > %(installdir)s/bin/t4.pl',",
            # space after #! + 'env perl5'
            "    'echo \"#!/usr/bin/env perl5\\n# test\" > %(installdir)s/bin/t5.pl',",
            # shebang with space, should strip the space
            "    'echo \"#! /usr/bin/env perl\\n# test\" > %(installdir)s/bin/t6.pl',",
            # no shebang perl
            "    'echo \"# test\" > %(installdir)s/bin/t7.pl',",
            # shebang bash
            "    'echo \"#!/usr/bin/env bash\\n# test\" > %(installdir)s/bin/b2.sh',",

            # tests for bash shebang
            # hardcoded path to bin/bash
            "    'echo \"#!/bin/bash\\n# test\" > %(installdir)s/bin/t1.sh',",
            # hardcoded path to usr/bin/bash
            "    'echo \"#!/usr/bin/bash\\n# test\" > %(installdir)s/bin/t2.sh',",
            # already OK, should remain the same
            "    'echo \"#!/usr/bin/env bash\\n# test\" > %(installdir)s/bin/t3.sh',",
            # shebang with space, should strip the space
            "    'echo \"#! /usr/bin/env bash\\n# test\" > %(installdir)s/bin/t4.sh',",
            # no shebang sh
            "    'echo \"# test\" > %(installdir)s/bin/t5.sh',",
            # shebang python
            "    'echo \"#!/usr/bin/env python\\n# test\" > %(installdir)s/bin/b1.py',",
            # shebang perl
            "    'echo \"#!/usr/bin/env perl\\n# test\" > %(installdir)s/bin/b1.pl',",
            "]",
            "fix_python_shebang_for = ['bin/t1.py', 'bin/t*.py', 'nosuchdir/*.py', 'bin/toy.python', 'bin/b1.sh']",
            "fix_python_shebang_for += ['bin/testdir']",
            "fix_perl_shebang_for = ['bin/t*.pl', 'bin/b2.sh', 'bin/toy.perl']",
            "fix_bash_shebang_for = ['bin/t*.sh', 'bin/b1.py', 'bin/b1.pl', 'bin/toy.sh']",
        ])
        write_file(test_ec, test_ec_txt)
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, raise_error=True)

        toy_bindir = os.path.join(self.test_installpath, 'software', 'toy', '0.0', 'bin')

        # bin/toy and bin/toy2 should *not* be patched, since they're binary files
        toy_txt = read_file(os.path.join(toy_bindir, 'toy'), mode='rb')
        for fn in ['toy.sh', 'toy.perl', 'toy.python']:
            fn_txt = read_file(os.path.join(toy_bindir, fn), mode='rb')
            # no shebang added
            self.assertFalse(fn_txt.startswith(b"#!/"))
            # exact same file as original binary (untouched)
            self.assertEqual(toy_txt, fn_txt)

        regexes = {}
        # no re.M, this should match at start of file!
        regexes['py'] = re.compile(r'^#!/usr/bin/env python\n# test$')
        regexes['pl'] = re.compile(r'^#!/usr/bin/env perl\n# test$')
        regexes['sh'] = re.compile(r'^#!/usr/bin/env bash\n# test$')

        # all scripts should have a shebang that matches their extension
        scripts = {}
        scripts['py'] = ['t1.py', 't2.py', 't3.py', 't4.py', 't5.py', 't6.py', 't7.py', 'b1.py']
        scripts['pl'] = ['t1.pl', 't2.pl', 't3.pl', 't4.pl', 't5.pl', 't6.pl', 't7.pl', 'b1.pl']
        scripts['sh'] = ['t1.sh', 't2.sh', 't3.sh', 't4.sh', 't5.sh', 'b1.sh', 'b2.sh']

        for ext in ['sh', 'pl', 'py']:
            for script in scripts[ext]:
                bin_path = os.path.join(toy_bindir, script)
                bin_txt = read_file(bin_path)
                self.assertTrue(regexes[ext].match(bin_txt),
                                "Pattern '%s' found in %s: %s" % (regexes[ext].pattern, bin_path, bin_txt))

        # now test with a custom env command
        extra_args = ['--env-for-shebang=/usr/bin/env -S']
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, extra_args=extra_args, raise_error=True)

        toy_bindir = os.path.join(self.test_installpath, 'software', 'toy', '0.0', 'bin')

        # bin/toy and bin/toy2 should *not* be patched, since they're binary files
        toy_txt = read_file(os.path.join(toy_bindir, 'toy'), mode='rb')
        for fn in ['toy.sh', 'toy.perl', 'toy.python']:
            fn_txt = read_file(os.path.join(toy_bindir, fn), mode='rb')
            # no shebang added
            self.assertFalse(fn_txt.startswith(b"#!/"))
            # exact same file as original binary (untouched)
            self.assertEqual(toy_txt, fn_txt)

        regexes_shebang = {}

        def check_shebangs():
            for ext in ['sh', 'pl', 'py']:
                for script in scripts[ext]:
                    bin_path = os.path.join(toy_bindir, script)
                    bin_txt = read_file(bin_path)
                    # the scripts b1.py, b1.pl, b1.sh, b2.sh should keep their original shebang
                    if script.startswith('b'):
                        self.assertTrue(regexes[ext].match(bin_txt),
                                        "Pattern '%s' found in %s: %s" % (regexes[ext].pattern, bin_path, bin_txt))
                    else:
                        regex_shebang = regexes_shebang[ext]
                        self.assertTrue(regex_shebang.match(bin_txt),
                                        "Pattern '%s' found in %s: %s" % (regex_shebang.pattern, bin_path, bin_txt))

        # no re.M, this should match at start of file!
        regexes_shebang['py'] = re.compile(r'^#!/usr/bin/env -S python\n# test$')
        regexes_shebang['pl'] = re.compile(r'^#!/usr/bin/env -S perl\n# test$')
        regexes_shebang['sh'] = re.compile(r'^#!/usr/bin/env -S bash\n# test$')

        check_shebangs()

        # test again with EasyBuild configured with sysroot, which should be prepended
        # automatically to env-for-shebang value (unless it's prefixed with sysroot already)
        extra_args = [
            '--env-for-shebang=/usr/bin/env -S',
            '--sysroot=/usr/../',  # sysroot must exist, and so must /usr/bin/env when appended to it
        ]
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, extra_args=extra_args, raise_error=True)

        regexes_shebang['py'] = re.compile(r'^#!/usr/../usr/bin/env -S python\n# test$')
        regexes_shebang['pl'] = re.compile(r'^#!/usr/../usr/bin/env -S perl\n# test$')
        regexes_shebang['sh'] = re.compile(r'^#!/usr/../usr/bin/env -S bash\n# test$')

        check_shebangs()

        extra_args = [
            '--env-for-shebang=/usr/../usr/../usr/bin/env -S',
            '--sysroot=/usr/../',  # sysroot must exist, and so must /usr/bin/env when appended to it
        ]
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, extra_args=extra_args, raise_error=True)

        regexes_shebang['py'] = re.compile(r'^#!/usr/../usr/../usr/bin/env -S python\n# test$')
        regexes_shebang['pl'] = re.compile(r'^#!/usr/../usr/../usr/bin/env -S perl\n# test$')
        regexes_shebang['sh'] = re.compile(r'^#!/usr/../usr/../usr/bin/env -S bash\n# test$')

        check_shebangs()

    def test_toy_system_toolchain_alias(self):
        """Test use of 'system' toolchain alias."""
        toy_ec = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec)

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        tc_regex = re.compile('^toolchain = .*', re.M)

        test_tcs = [
            "toolchain = {'name': 'system', 'version': 'system'}",
            "toolchain = {'name': 'system', 'version': ''}",
            "toolchain = SYSTEM",
        ]

        for tc in test_tcs:
            test_ec_txt = tc_regex.sub(tc, toy_ec_txt)
            write_file(test_ec, test_ec_txt)

            with self.mocked_stdout_stderr():
                self._test_toy_build(ec_file=test_ec)

    def test_toy_ghost_installdir(self):
        """Test whether ghost installation directory is removed under --force."""

        toy_installdir = os.path.join(self.test_prefix, 'test123', 'toy', '0.0')
        mkdir(toy_installdir, parents=True)
        write_file(os.path.join(toy_installdir, 'bin', 'toy'), "#!/bin/bash\necho hello")

        toy_modfile = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_modfile += '.lua'
            dummy_toy_mod_txt = 'local root = "%s"\n' % toy_installdir
        else:
            dummy_toy_mod_txt = '\n'.join([
                "#%Module",
                "set root %s" % toy_installdir,
                '',
            ])
        write_file(toy_modfile, dummy_toy_mod_txt)

        stdout, stderr = self.run_test_toy_build_with_output()

        # by default, a warning is printed for ghost installation directories (but they're left untouched)
        regex = re.compile("WARNING: Likely ghost installation directory detected: %s" % toy_installdir)
        self.assertTrue(regex.search(stderr), "Pattern '%s' found in: %s" % (regex.pattern, stderr))
        self.assertExists(toy_installdir)

        # cleanup of ghost installation directories can be enable via --remove-ghost-install-dirs
        write_file(toy_modfile, dummy_toy_mod_txt)
        stdout, stderr = self.run_test_toy_build_with_output(extra_args=['--remove-ghost-install-dirs'])

        self.assertFalse(stderr)

        regex = re.compile("== Ghost installation directory %s removed" % toy_installdir)
        self.assertRegex(stdout, regex)

        self.assertNotExists(toy_installdir)

    def test_toy_build_lock(self):
        """Test toy installation when a lock is already in place."""

        locks_dir = os.path.join(self.test_installpath, 'software', '.locks')
        toy_installdir = os.path.join(self.test_installpath, 'software', 'toy', '0.0')
        toy_lock_fn = toy_installdir.replace(os.path.sep, '_') + '.lock'

        toy_lock_path = os.path.join(locks_dir, toy_lock_fn)
        mkdir(toy_lock_path, parents=True)

        error_pattern = "Lock .*_software_toy_0.0.lock already exists, aborting!"
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, raise_error=True, verbose=False)

        # lock should still be there after it was hit
        self.assertExists(toy_lock_path)

        # trying again should give same result
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, raise_error=True, verbose=False)
        self.assertExists(toy_lock_path)

        locks_dir = os.path.join(self.test_prefix, 'locks')

        # no lock in place, so installation proceeds as normal
        extra_args = ['--locks-dir=%s' % locks_dir]
        with self.mocked_stdout_stderr():
            self._test_toy_build(extra_args=extra_args, verify=True, raise_error=True)

        # put lock in place in custom locks dir, try again
        toy_lock_path = os.path.join(locks_dir, toy_lock_fn)
        mkdir(toy_lock_path, parents=True)
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build,
                                  extra_args=extra_args, raise_error=True, verbose=False)

        # also test use of --ignore-locks
        with self.mocked_stdout_stderr():
            self._test_toy_build(extra_args=extra_args + ['--ignore-locks'], verify=True, raise_error=True)

        orig_sigalrm_handler = signal.getsignal(signal.SIGALRM)

        # define a context manager that remove a lock after a while, so we can check the use of --wait-for-lock
        class RemoveLockAfter:
            def __init__(self, seconds, lock_fp):
                self.seconds = seconds
                self.lock_fp = lock_fp

            def remove_lock(self, *args):
                remove_dir(self.lock_fp)

            def __enter__(self):
                signal.signal(signal.SIGALRM, self.remove_lock)
                signal.alarm(self.seconds)

            def __exit__(self, type, value, traceback):
                # clean up SIGALRM signal handler, and cancel scheduled alarm
                signal.signal(signal.SIGALRM, orig_sigalrm_handler)
                signal.alarm(0)

        # wait for lock to be removed, with 1 second interval of checking;

        wait_regex = re.compile("^== lock .*_software_toy_0.0.lock exists, waiting 1 seconds", re.M)
        ok_regex = re.compile("^== COMPLETED: Installation ended successfully", re.M)

        test_cases = [
            ['--wait-on-lock-limit=100', '--wait-on-lock-interval=1'],
            ['--wait-on-lock-limit=-1', '--wait-on-lock-interval=1'],
        ]

        for opts in test_cases:

            if not os.path.exists(toy_lock_path):
                mkdir(toy_lock_path)

            self.assertExists(toy_lock_path)

            all_args = extra_args + opts

            # use context manager to remove lock after 3 seconds
            with RemoveLockAfter(3, toy_lock_path):
                self.mock_stderr(True)
                self.mock_stdout(True)
                self._test_toy_build(extra_args=all_args, verify=False, raise_error=True, testing=False)
                stderr, stdout = self.get_stderr(), self.get_stdout()
                self.mock_stderr(False)
                self.mock_stdout(False)

                self.assertEqual(stderr, '')

                wait_matches = wait_regex.findall(stdout)
                # we can't rely on an exact number of 'waiting' messages, so let's go with a range...
                self.assertIn(len(wait_matches), range(1, 5))

                self.assertTrue(ok_regex.search(stdout), "Pattern '%s' found in: %s" % (ok_regex.pattern, stdout))

        # check use of --wait-on-lock-limit: if lock is never removed, we should give up when limit is reached
        mkdir(toy_lock_path)
        all_args = extra_args + ['--wait-on-lock-limit=3', '--wait-on-lock-interval=1']
        self.mock_stderr(True)
        self.mock_stdout(True)
        error_pattern = r"Maximum wait time for lock /.*toy_0.0.lock to be released reached: [0-9]+ sec >= 3 sec"
        self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build, extra_args=all_args,
                              verify=False, raise_error=True, testing=False)
        stderr, stdout = self.get_stderr(), self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        wait_matches = wait_regex.findall(stdout)
        self.assertIn(len(wait_matches), range(2, 5))

        # when there is no lock in place, --wait-on-lock* has no impact
        remove_dir(toy_lock_path)
        for opt in ['--wait-on-lock-limit=3', '--wait-on-lock-interval=1']:
            all_args = extra_args + [opt]
            self.assertNotExists(toy_lock_path)
            self.mock_stderr(True)
            self.mock_stdout(True)
            self._test_toy_build(extra_args=all_args, verify=False, raise_error=True, testing=False)
            stderr, stdout = self.get_stderr(), self.get_stdout()
            self.mock_stderr(False)
            self.mock_stdout(False)

            self.assertEqual(stderr, '')
            self.assertTrue(ok_regex.search(stdout), "Pattern '%s' found in: %s" % (ok_regex.pattern, stdout))
            self.assertFalse(wait_regex.search(stdout), "Pattern '%s' not found in: %s" % (wait_regex.pattern, stdout))

        # check for clean error on creation of lock
        extra_args = ['--locks-dir=/']
        error_pattern = r"Failed to create lock /.*_software_toy_0.0.lock:.* "
        error_pattern += r"(Read-only file system|Permission denied)"
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, self._test_toy_build,
                                  extra_args=extra_args, raise_error=True, verbose=False)

    def test_toy_lock_cleanup_signals(self):
        """Test cleanup of locks after EasyBuild session gets a cancellation signal."""

        orig_wd = os.getcwd()

        locks_dir = os.path.join(self.test_installpath, 'software', '.locks')
        self.assertNotExists(locks_dir)

        orig_sigalrm_handler = signal.getsignal(signal.SIGALRM)

        # context manager which stops the function being called with the specified signal
        class WaitAndSignal:
            def __init__(self, seconds, signum):
                self.seconds = seconds
                self.signum = signum

            def send_signal(self, *args):
                os.kill(os.getpid(), self.signum)

            def __enter__(self):
                signal.signal(signal.SIGALRM, self.send_signal)
                signal.alarm(self.seconds)

            def __exit__(self, type, value, traceback):
                # clean up SIGALRM signal handler, and cancel scheduled alarm
                signal.signal(signal.SIGALRM, orig_sigalrm_handler)
                signal.alarm(0)

        # add extra sleep command to ensure session takes long enough
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec_txt = read_file(os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0.eb'))

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, toy_ec_txt + '\npostinstallcmds = ["sleep 10"]')

        extra_args = ['--locks-dir=%s' % locks_dir, '--wait-on-lock-limit=3', '--wait-on-lock-interval=3']

        signums = [
            (signal.SIGABRT, SystemExit),
            (signal.SIGINT, KeyboardInterrupt),
            (signal.SIGTERM, SystemExit),
            (signal.SIGQUIT, SystemExit),
        ]
        for (signum, exc) in signums:

            # avoid recycling stderr of previous test
            stderr = ''

            with WaitAndSignal(3, signum):

                # change back to original working directory before each test
                change_dir(orig_wd)

                self.mock_stderr(True)
                self.mock_stdout(True)
                self.assertErrorRegex(exc, '.*', self._test_toy_build, ec_file=test_ec, verify=False,
                                      extra_args=extra_args, raise_error=True, testing=False, raise_systemexit=True)

                stderr = self.get_stderr().strip()
                self.mock_stderr(False)
                self.mock_stdout(False)

                pattern = r"^WARNING: signal received \(%s\), " % int(signum)
                pattern += r"cleaning up locks \(.*software_toy_0.0\)\.\.\."
                regex = re.compile(pattern)
                self.assertTrue(regex.search(stderr), "Pattern '%s' found in: %s" % (regex.pattern, stderr))

    def test_toy_build_unicode_description(self):
        """Test installation of easyconfig file that has non-ASCII characters in description."""
        # cfr. https://github.com/easybuilders/easybuild-framework/issues/3284

        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec)

        # the tilde character included here is a Unicode tilde character, not a regular ASCII tilde (~)
        descr = "This description includes a unicode tilde character: ∼, for your entertainment."
        self.assertNotIn('~', descr)

        regex = re.compile(r'^description\s*=.*', re.M)
        test_ec_txt = regex.sub(r'description = "%s"' % descr, toy_ec_txt)

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, test_ec_txt)

        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, raise_error=True)

    def test_toy_build_lib64_lib_symlink(self):
        """Check whether lib64 symlink to lib subdirectory is created."""
        # this is done to ensure that <installdir>/lib64 is considered before /lib64 by GCC linker,
        # see https://github.com/easybuilders/easybuild-easyconfigs/issues/5776

        # by default, lib64 -> lib symlink is created (--lib64-lib-symlink is enabled by default)
        with self.mocked_stdout_stderr():
            self._test_toy_build()

        toy_installdir = os.path.join(self.test_installpath, 'software', 'toy', '0.0')
        lib_path = os.path.join(toy_installdir, 'lib')
        lib64_path = os.path.join(toy_installdir, 'lib64')

        # lib64 subdir exists, is not a symlink
        self.assertExists(lib_path)
        self.assertTrue(os.path.isdir(lib_path))
        self.assertFalse(os.path.islink(lib_path))

        # lib64 subdir is a symlink to lib subdir
        self.assertExists(lib64_path)
        self.assertTrue(os.path.islink(lib64_path))
        self.assertTrue(os.path.samefile(lib_path, lib64_path))

        # lib64 symlink should point to a relative path
        self.assertFalse(os.path.isabs(os.readlink(lib64_path)))

        # cleanup and try again with --disable-lib64-lib-symlink
        remove_dir(self.test_installpath)
        with self.mocked_stdout_stderr():
            self._test_toy_build(extra_args=['--disable-lib64-lib-symlink'])

        self.assertExists(lib_path)
        self.assertNotExists(lib64_path)
        self.assertNotIn('lib64', os.listdir(toy_installdir))
        self.assertTrue(os.path.isdir(lib_path))
        self.assertFalse(os.path.islink(lib_path))

    def test_toy_build_lib_lib64_symlink(self):
        """Check whether lib64 symlink to lib subdirectory is created."""

        test_ecs = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')

        test_ec_txt = read_file(toy_ec)

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, test_ec_txt)

        # by default, lib -> lib64 symlink is created (--lib-lib64-symlink is enabled by default)
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec)

        toy_installdir = os.path.join(self.test_installpath, 'software', 'toy', '0.0')
        lib_path = os.path.join(toy_installdir, 'lib')
        lib64_path = os.path.join(toy_installdir, 'lib64')

        # lib subdir exists, is not a symlink
        self.assertExists(lib_path)
        self.assertTrue(os.path.isdir(lib_path))
        self.assertFalse(os.path.islink(lib_path))

        # lib64 subdir is a symlink to lib subdir
        self.assertExists(lib64_path)
        self.assertTrue(os.path.isdir(lib64_path))
        self.assertTrue(os.path.islink(lib64_path))
        self.assertTrue(os.path.samefile(lib64_path, lib_path))

        # lib64 symlink should point to a relative path
        self.assertFalse(os.path.isabs(os.readlink(lib64_path)))

        # cleanup and try again with --disable-lib-lib64-symlink
        remove_dir(self.test_installpath)
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, extra_args=['--disable-lib64-lib-symlink'])

        self.assertExists(lib_path)
        self.assertNotExists(lib64_path)
        self.assertNotIn('lib64', os.listdir(toy_installdir))
        self.assertTrue(os.path.isdir(lib_path))
        self.assertFalse(os.path.islink(lib_path))

    def test_toy_build_sanity_check_linked_libs(self):
        """Test sanity checks for banned/requires libraries."""

        test_ecs = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs')
        libtoy_ec = os.path.join(test_ecs, 'l', 'libtoy', 'libtoy-0.0.eb')

        libtoy_modfile_path = os.path.join(self.test_installpath, 'modules', 'all', 'libtoy', '0.0')
        if get_module_syntax() == 'Lua':
            libtoy_modfile_path += '.lua'

        test_ec = os.path.join(self.test_prefix, 'test.eb')

        shlib_ext = get_shared_lib_ext()

        libtoy_fn = 'libtoy.%s' % shlib_ext
        error_msg = "Check for banned/required shared libraries failed for"

        # default check is done via EB_libtoy easyblock, which specifies several banned/required libraries
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=libtoy_ec, raise_error=True, verbose=False, verify=False)
        remove_file(libtoy_modfile_path)

        # we can make the check fail by defining environment variables picked up by the EB_libtoy easyblock
        os.environ['EB_LIBTOY_BANNED_SHARED_LIBS'] = 'libtoy'
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_msg, self._test_toy_build, force=False,
                                  ec_file=libtoy_ec, extra_args=['--module-only'], raise_error=True, verbose=False)
        del os.environ['EB_LIBTOY_BANNED_SHARED_LIBS']

        os.environ['EB_LIBTOY_REQUIRED_SHARED_LIBS'] = 'thisisnottheremostlikely'
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_msg, self._test_toy_build, force=False,
                                  ec_file=libtoy_ec, extra_args=['--module-only'], raise_error=True, verbose=False)
        del os.environ['EB_LIBTOY_REQUIRED_SHARED_LIBS']

        # make sure default check passes (so we know better what triggered a failing test)
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=libtoy_ec, extra_args=['--module-only'], force=False,
                                 raise_error=True, verbose=False, verify=False)
        remove_file(libtoy_modfile_path)

        # check specifying banned/required libraries via EasyBuild configuration option
        args = ['--banned-linked-shared-libs=%s,foobarbaz' % libtoy_fn, '--module-only']
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_msg, self._test_toy_build, force=False,
                                  ec_file=libtoy_ec, extra_args=args, raise_error=True, verbose=False)

        args = ['--required-linked-shared=libs=foobarbazisnotthereforsure', '--module-only']
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_msg, self._test_toy_build, force=False,
                                  ec_file=libtoy_ec, extra_args=args, raise_error=True, verbose=False)

        # check specifying banned/required libraries via easyconfig parameter
        test_ec_txt = read_file(libtoy_ec)
        test_ec_txt += "\nbanned_linked_shared_libs = ['toy']"
        write_file(test_ec, test_ec_txt)
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_msg, self._test_toy_build, force=False,
                                  ec_file=test_ec, extra_args=['--module-only'], raise_error=True, verbose=False)

        test_ec_txt = read_file(libtoy_ec)
        test_ec_txt += "\nrequired_linked_shared_libs = ['thereisnosuchlibraryyoudummy']"
        write_file(test_ec, test_ec_txt)
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_msg, self._test_toy_build, force=False,
                                  ec_file=test_ec, extra_args=['--module-only'], raise_error=True, verbose=False)

        # check behaviour when alternative subdirectories are specified
        test_ec_txt = read_file(libtoy_ec)
        test_ec_txt += "\nbin_lib_subdirs = ['', 'lib', 'lib64']"
        write_file(test_ec, test_ec_txt)
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, extra_args=['--module-only'], force=False,
                                 raise_error=True, verbose=False, verify=False)

        # one last time: supercombo (with patterns that should pass the check)
        test_ec_txt = read_file(libtoy_ec)
        test_ec_txt += "\nbanned_linked_shared_libs = ['yeahthisisjustatest', '/usr/lib/libssl.so']"
        test_ec_txt += "\nrequired_linked_shared_libs = ['/lib']"
        test_ec_txt += "\nbin_lib_subdirs = ['', 'lib', 'lib64']"
        write_file(test_ec, test_ec_txt)
        args = [
            '--banned-linked-shared-libs=the_forbidden_library',
            '--required-linked-shared-libs=.*',
            '--module-only',
        ]
        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, extra_args=args, force=False,
                                 raise_error=True, verbose=False, verify=False)

    def test_toy_mod_files(self):
        """Check detection of .mod files"""
        test_ecs = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')
        test_ec_txt = read_file(toy_ec)
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, test_ec_txt)

        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec)

        test_ec_txt += "\npostinstallcmds += ['touch %(installdir)s/lib/file.mod']"
        write_file(test_ec, test_ec_txt)

        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec)

        args = ['--try-toolchain=GCCcore,6.2.0', '--disable-map-toolchains']
        self.mock_stdout(True)
        self.mock_stderr(True)
        self._test_toy_build(ec_file=test_ec, extra_args=args)
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        pattern = r"WARNING: One or more \.mod files found in .*/software/toy/0.0-GCCcore-6.2.0: .*/lib64/file.mod"
        self.assertRegex(stderr.strip(), pattern)

        args += ['--fail-on-mod-files-gcccore']
        pattern = r"Sanity check failed: One or more \.mod files found in .*/toy/0.0-GCCcore-6.2.0: .*/lib/file.mod"
        self.assertErrorRegex(EasyBuildError, pattern, self.run_test_toy_build_with_output, ec_file=test_ec,
                              extra_args=args, verify=False, fails=True, verbose=False, raise_error=True)

        test_ec_txt += "\nskip_mod_files_sanity_check = True"
        write_file(test_ec, test_ec_txt)

        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, extra_args=args)

    def test_toy_ignore_test_failure(self):
        """Check whether use of --ignore-test-failure is mentioned in build output."""
        args = ['--ignore-test-failure']
        stdout, stderr = self.run_test_toy_build_with_output(extra_args=args, verify=False, testing=False)

        self.assertIn("Build succeeded (with --ignore-test-failure) for 1 out of 1", stdout)
        self.assertFalse(stderr)

    def test_toy_post_install_patches(self):
        """
        Test use of post-install patches
        """
        test_ecs = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')

        test_ec_txt = read_file(toy_ec)
        test_ec_txt += "\npostinstallpatches = ['toy-0.0_fix-README.patch']"
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, test_ec_txt)

        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec)

        toy_installdir = os.path.join(self.test_installpath, 'software', 'toy', '0.0')
        toy_readme_txt = read_file(os.path.join(toy_installdir, 'README'))
        # verify whether patch indeed got applied
        self.assertEqual(toy_readme_txt, "toy 0.0, a toy test program\n")

    def test_toy_unavailable_os_dep(self):
        """
        Test unavailable OS dep
        Existence of OS dependencies is checking during the parsing of the easyconfig.
        Test here that this problem is caught and a test report generated (#4102).
        """
        test_ecs = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')

        test_ec_txt = read_file(toy_ec)
        test_ec_txt += "\nosdependencies = [('package-does-not-exist')]"
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, test_ec_txt)

        test_report_fp = os.path.join(self.test_buildpath, 'full_test_report.md')

        self.mock_stderr(True)
        self.mock_stdout(True)
        self._test_toy_build(ec_file=test_ec, force=False, raise_error=False, verify=False,
                             test_report_regexs=[r"One or more OS dependencies were not found"],
                             test_report=test_report_fp)
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        patterns = [
            r"Failed to process easyconfig",
            r"One or more OS dependencies were not found",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

    def test_toy_post_install_messages(self):
        """
        Test use of post-install messages
        """
        test_ecs = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')

        test_ec_txt = read_file(toy_ec)
        test_ec_txt += "\npostinstallmsgs = ['This is post install message 1', 'This is post install message 2']"
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, test_ec_txt)

        test_report_fp = os.path.join(self.test_buildpath, 'full_test_report.md')

        self.mock_stderr(True)
        self.mock_stdout(True)
        self._test_toy_build(ec_file=test_ec, test_report=test_report_fp)
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        patterns = [
            r"== This is post install message 1",
            r"== This is post install message 2",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

    def test_toy_build_info_msg(self):
        """
        Test use of build info message
        """
        test_ecs = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')

        test_ec_txt = read_file(toy_ec)
        test_ec_txt += '\nbuild_info_msg = "Are you sure you want to install this toy software?"'
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, test_ec_txt)

        with self.mocked_stdout_stderr():
            self._test_toy_build(ec_file=test_ec, testing=False, verify=False, raise_error=True)
            stdout = self.get_stdout()

        pattern = '\n'.join([
            r"== This easyconfig provides the following build information:",
            r'',
            r"Are you sure you want to install this toy software\?",
        ])
        regex = re.compile(pattern, re.M)
        self.assertTrue(regex.search(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

    def test_toy_failing_test_step(self):
        """
        Test behaviour when test step fails, using toy easyconfig.
        """
        test_ecs = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')
        toy_mod_path = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_mod_path += '.lua'

        test_ec_txt = read_file(toy_ec)
        test_ec_txt += '\nruntest = "false"'
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, test_ec_txt)

        error_pattern = r"shell command 'false \.\.\.' failed in test step"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.run_test_toy_build_with_output,
                              ec_file=test_ec, raise_error=True)
        self.assertNotExists(toy_mod_path)

        # make sure that option to ignore test failures works
        self.run_test_toy_build_with_output(ec_file=test_ec, extra_args=['--ignore-test-failure'],
                                            raise_error=True, verbose=True)
        self.assertExists(toy_mod_path)
        remove_file(toy_mod_path)

        # ignoring test failure should also work if an EasyBuildError is raises from test step
        test_ec_txt = read_file(toy_ec)
        test_ec_txt += '\nruntest = "RAISE_ERROR"'
        write_file(test_ec, test_ec_txt)

        error_pattern = r"An error was raised during test step: 'TOY_TEST_FAIL'"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.run_test_toy_build_with_output,
                              ec_file=test_ec, raise_error=True)

        # make sure that option to ignore test failures works
        self.run_test_toy_build_with_output(ec_file=test_ec, extra_args=['--ignore-test-failure'],
                                            raise_error=True, verbose=True)
        self.assertExists(toy_mod_path)

    def test_eb_crash(self):
        """
        Test behaviour when EasyBuild crashes, for example due to a buggy hook
        """
        hooks_file = os.path.join(self.test_prefix, 'my_hooks.py')
        hooks_file_txt = textwrap.dedent("""
            def pre_configure_hook(self, *args, **kwargs):
                no_such_thing
        """)
        write_file(hooks_file, hooks_file_txt)

        topdir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        toy_eb = os.path.join(topdir, 'test', 'framework', 'sandbox', 'easybuild', 'easyblocks', 't', 'toy.py')
        toy_ec = os.path.join(topdir, 'test', 'framework', 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        args = [
            toy_ec,
            f'--hooks={hooks_file}',
            '--force',
            f'--installpath={self.test_prefix}',
            f'--include-easyblocks={toy_eb}',
        ]

        with self.mocked_stdout_stderr() as (_, stderr):
            cleanup()
            try:
                main_with_hooks(args=args)
                self.assertFalse("This should never be reached, main function should have crashed!")
            except NameError as err:
                self.assertEqual(str(err), "name 'no_such_thing' is not defined")

            regex = re.compile(r"EasyBuild crashed! Please consider reporting a bug, this should not happen")
            stderr = stderr.getvalue()
            self.assertTrue(regex.search(stderr), f"Pattern '{regex.pattern}' should be found in {stderr}")

    def test_eb_error(self):
        """
        Test whether main function as run by 'eb' command print error messages to stderr.
        """
        topdir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        toy_ec = os.path.join(topdir, 'test', 'framework', 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ec_txt = read_file(toy_ec)
        test_ec_txt += "\ndependencies = [('nosuchdep', '1.0')]"
        write_file(test_ec, test_ec_txt)

        with self.mocked_stdout_stderr() as (_, stderr):
            cleanup()
            try:
                main_with_hooks(args=[test_ec, '--robot', '--force'])
            except SystemExit:
                pass

            regex = re.compile("^ERROR: Missing dependencies", re.M)
            stderr = stderr.getvalue()
            self.assertTrue(regex.search(stderr), f"Pattern '{regex.pattern}' should be found in {stderr}")

    def test_toy_python(self):
        """
        Test whether $PYTHONPATH or $EBPYTHONPREFIXES are set correctly.
        """
        # generate fake Python modules that we can use as runtime dependency for toy
        # (required condition for use of $EBPYTHONPREFIXES)
        fake_mods_path = os.path.join(self.test_prefix, 'modules')
        for pyver in ('2.7', '3.6'):
            fake_python_mod = os.path.join(fake_mods_path, 'Python', pyver)
            if get_module_syntax() == 'Lua':
                fake_python_mod += '.lua'
                write_file(fake_python_mod, '')
            else:
                write_file(fake_python_mod, '#%Module')
        self.modtool.use(fake_mods_path)

        test_ecs = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')

        test_ec_txt = read_file(toy_ec)
        test_ec_txt += "\npostinstallcmds.append('mkdir -p %(installdir)s/lib/python3.6/site-packages')"
        test_ec_txt += "\npostinstallcmds.append('touch %(installdir)s/lib/python3.6/site-packages/foo.py')"

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, test_ec_txt)
        self.run_test_toy_build_with_output(ec_file=test_ec)

        toy_mod = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_mod += '.lua'
        toy_mod_txt = read_file(toy_mod)

        pythonpath_regex = re.compile('^prepend.path.*PYTHONPATH.*lib.*python3.6.*site-packages', re.M)

        self.assertTrue(pythonpath_regex.search(toy_mod_txt),
                        f"Pattern '{pythonpath_regex.pattern}' found in: {toy_mod_txt}")

        # also check when opting in to use $EBPYTHONPREFIXES instead of $PYTHONPATH
        args = ['--prefer-python-search-path=EBPYTHONPREFIXES']
        self.run_test_toy_build_with_output(ec_file=test_ec, extra_args=args)
        toy_mod_txt = read_file(toy_mod)
        # if Python is not listed as a runtime dependency then $PYTHONPATH is still used,
        # because the Python dependency used must be aware of $EBPYTHONPREFIXES
        # (see sitecustomize.py installed by Python easyblock)
        self.assertTrue(pythonpath_regex.search(toy_mod_txt),
                        f"Pattern '{pythonpath_regex.pattern}' found in: {toy_mod_txt}")

        # if Python is listed as runtime dependency, then $EBPYTHONPREFIXES is used if it's preferred
        write_file(test_ec, test_ec_txt + "\ndependencies = [('Python', '3.6', '', SYSTEM)]")
        self.run_test_toy_build_with_output(ec_file=test_ec, extra_args=args)
        toy_mod_txt = read_file(toy_mod)

        ebpythonprefixes_regex = re.compile('^prepend.path.*EBPYTHONPREFIXES.*root', re.M)
        self.assertTrue(ebpythonprefixes_regex.search(toy_mod_txt),
                        f"Pattern '{ebpythonprefixes_regex.pattern}' found in: {toy_mod_txt}")

        # if Python is listed in multi_deps, then $EBPYTHONPREFIXES is used, even if it's not explicitely preferred
        write_file(test_ec, test_ec_txt + "\nmulti_deps = {'Python': ['2.7', '3.6']}")
        self.run_test_toy_build_with_output(ec_file=test_ec)
        toy_mod_txt = read_file(toy_mod)

        self.assertTrue(ebpythonprefixes_regex.search(toy_mod_txt),
                        f"Pattern '{ebpythonprefixes_regex.pattern}' found in: {toy_mod_txt}")

    def test_toy_multiple_ecs_module(self):
        """
        Verify whether module file is correct when multiple easyconfigs are being installed.
        """
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')

        # modify 'toy' easyconfig so toy-headers subdirectory is created,
        # which is taken into account by EB_toy easyblock for $CPATH
        test_toy_ec = os.path.join(self.test_prefix, 'test-toy.eb')
        toy_ec_txt = read_file(toy_ec)
        toy_ec_txt += "\npostinstallcmds += ['mkdir %(installdir)s/toy-headers']"
        toy_ec_txt += "\npostinstallcmds += ['touch %(installdir)s/toy-headers/toy.h']"
        write_file(test_toy_ec, toy_ec_txt)

        # modify 'toy-app' easyconfig so toy-headers subdirectory is created,
        # which is consider by EB_toy easyblock for $CPATH,
        # but should *not* be actually used because software name is not 'toy'
        toy_app_ec = os.path.join(test_ecs, 't', 'toy-app', 'toy-app-0.0.eb')
        test_toy_app_ec = os.path.join(self.test_prefix, 'test-toy-app.eb')
        toy_ec_txt = read_file(toy_app_ec)
        toy_ec_txt += "\npostinstallcmds += ['mkdir %(installdir)s/toy-headers']"
        toy_ec_txt += "\npostinstallcmds += ['touch %(installdir)s/toy-headers/toy.h']"
        write_file(test_toy_app_ec, toy_ec_txt)

        self.run_test_toy_build_with_output(ec_file=test_toy_ec, extra_args=[test_toy_app_ec], raise_error=True)

        toy_mod = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0')
        if get_module_syntax() == 'Lua':
            toy_mod += '.lua'
        toy_modtxt = read_file(toy_mod)
        regex = re.compile('prepend[-_]path.*CPATH.*toy-headers', re.M)
        self.assertTrue(regex.search(toy_modtxt),
                        f"Pattern '{regex.pattern}' should be found in: {toy_modtxt}")

        toy_app_mod = os.path.join(self.test_installpath, 'modules', 'all', 'toy-app', '0.0')
        if get_module_syntax() == 'Lua':
            toy_app_mod += '.lua'
        toy_app_modtxt = read_file(toy_app_mod)
        self.assertFalse(regex.search(toy_app_modtxt),
                         f"Pattern '{regex.pattern}' should *not* be found in: {toy_app_modtxt}")


def suite(loader=None):
    """ return all the tests in this file """
    if loader:
        return loader.loadTestsFromTestCase(ToyBuildTest)
    else:
        return TestLoaderFiltered().loadTestsFromTestCase(ToyBuildTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
