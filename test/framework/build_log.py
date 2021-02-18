# #
# Copyright 2015-2021 Ghent University
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
Unit tests for EasyBuild log infrastructure

@author: Kenneth Hoste (Ghent University)
"""
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from unittest import TextTestRunner

from easybuild.base.fancylogger import getLogger, logToFile, setLogFormat
from easybuild.tools.build_log import (
    LOGGING_FORMAT, EasyBuildError, EasyBuildLog, dry_run_msg, dry_run_warning, init_logging, print_error, print_msg,
    print_warning, stop_logging, time_str_since, raise_nosupport)
from easybuild.tools.filetools import read_file, write_file


def raise_easybuilderror(msg, *args, **kwargs):
    """Utility function: just raise a EasyBuildError."""
    raise EasyBuildError(msg, *args, **kwargs)


class BuildLogTest(EnhancedTestCase):
    """Tests for EasyBuild log infrastructure."""

    def tearDown(self):
        """Cleanup after test."""
        super(BuildLogTest, self).tearDown()
        # restore default logging format
        setLogFormat(LOGGING_FORMAT)

    def test_easybuilderror(self):
        """Tests for EasyBuildError."""
        fd, tmplog = tempfile.mkstemp()
        os.close(fd)

        # set log format, for each regex searching
        setLogFormat("%(name)s :: %(message)s")

        # if no logger is available, and no logger is specified, use default 'root' fancylogger
        logToFile(tmplog, enable=True)
        self.assertErrorRegex(EasyBuildError, 'BOOM', raise_easybuilderror, 'BOOM')
        logToFile(tmplog, enable=False)

        log_re = re.compile(r"^fancyroot ::.* BOOM \(at .*:[0-9]+ in [a-z_]+\)$", re.M)
        logtxt = read_file(tmplog, 'r')
        self.assertTrue(log_re.match(logtxt), "%s matches %s" % (log_re.pattern, logtxt))

        # test formatting of message
        self.assertErrorRegex(EasyBuildError, 'BOOMBAF', raise_easybuilderror, 'BOOM%s', 'BAF')

        # a '%s' in a value used to template the error message should not print a traceback!
        self.mock_stderr(True)
        self.assertErrorRegex(EasyBuildError, 'err: msg: %s', raise_easybuilderror, "err: %s", "msg: %s")
        stderr = self.get_stderr()
        self.mock_stderr(False)
        # stderr should be *empty* (there should definitely not be a traceback)
        self.assertEqual(stderr, '')

        os.remove(tmplog)

    def test_easybuildlog(self):
        """Tests for EasyBuildLog."""
        fd, tmplog = tempfile.mkstemp()
        os.close(fd)

        # compose versions older/newer than current version
        depr_ver = int(os.environ['EASYBUILD_DEPRECATED'])
        older_ver = str(depr_ver - 1)
        newer_ver = str(depr_ver + 1)

        # set log format, for each regex searching
        setLogFormat("%(name)s [%(levelname)s] :: %(message)s")

        # test basic log methods
        logToFile(tmplog, enable=True)
        log = getLogger('test_easybuildlog')
        self.mock_stderr(True)
        log.setLevelName('DEBUG')
        log.debug("123 debug")
        log.info("foobar info")
        log.warning("justawarning")
        log.deprecated("anotherwarning", newer_ver)
        log.deprecated("onemorewarning", '1.0', '2.0')
        log.deprecated("lastwarning", '1.0', max_ver='2.0')
        log.deprecated("thisisnotprinted", '1.0', max_ver='2.0', silent=True)
        log.error("kaput")
        log.error("err: %s", 'msg: %s')
        stderr = self.get_stderr()
        self.mock_stderr(False)

        more_info = "see http://easybuild.readthedocs.org/en/latest/Deprecated-functionality.html for more information"
        expected_stderr = '\n\n'.join([
            "\nWARNING: Deprecated functionality, will no longer work in v10000001: anotherwarning; " + more_info,
            "\nWARNING: Deprecated functionality, will no longer work in v2.0: onemorewarning",
            "\nWARNING: Deprecated functionality, will no longer work in v2.0: lastwarning",
        ]) + '\n\n'
        self.assertEqual(stderr, expected_stderr)

        try:
            log.exception("oops")
        except EasyBuildError:
            pass
        logToFile(tmplog, enable=False)
        logtxt = read_file(tmplog)

        expected_logtxt = '\n'.join([
            r"fancyroot.test_easybuildlog \[DEBUG\] :: 123 debug",
            r"fancyroot.test_easybuildlog \[INFO\] :: foobar info",
            r"fancyroot.test_easybuildlog \[WARNING\] :: justawarning",
            r"fancyroot.test_easybuildlog \[WARNING\] :: Deprecated functionality.*anotherwarning.*",
            r"fancyroot.test_easybuildlog \[WARNING\] :: Deprecated functionality.*onemorewarning.*",
            r"fancyroot.test_easybuildlog \[WARNING\] :: Deprecated functionality.*lastwarning.*",
            r"fancyroot.test_easybuildlog \[WARNING\] :: Deprecated functionality.*thisisnotprinted.*",
            r"fancyroot.test_easybuildlog \[ERROR\] :: EasyBuild crashed with an error \(at .* in .*\): kaput",
            r"fancyroot.test_easybuildlog \[ERROR\] :: EasyBuild crashed with an error \(at .* in .*\): err: msg: %s",
            r"fancyroot.test_easybuildlog \[ERROR\] :: .*EasyBuild encountered an exception \(at .* in .*\): oops",
            '',
        ])
        logtxt_regex = re.compile(r'^%s' % expected_logtxt, re.M)
        self.assertTrue(logtxt_regex.search(logtxt), "Pattern '%s' found in %s" % (logtxt_regex.pattern, logtxt))

        self.assertErrorRegex(EasyBuildError, r"DEPRECATED \(since .*: kaput", log.deprecated, "kaput", older_ver)
        self.assertErrorRegex(EasyBuildError, r"DEPRECATED \(since .*: 2>1", log.deprecated, "2>1", '2.0', '1.0')
        self.assertErrorRegex(EasyBuildError, r"DEPRECATED \(since .*: 2>1", log.deprecated, "2>1", '2.0',
                              max_ver='1.0')

        # wipe log so we can reuse it
        write_file(tmplog, '')

        # test formatting log messages by providing extra arguments
        logToFile(tmplog, enable=True)
        log.warning("%s", "bleh")
        log.info("%s+%s = %d", '4', '2', 42)
        args = ['this', 'is', 'just', 'a', 'test']
        log.debug("%s %s %s %s %s", *args)
        log.error("foo %s baz", 'baz')
        logToFile(tmplog, enable=False)
        logtxt = read_file(tmplog)
        expected_logtxt = '\n'.join([
            r"fancyroot.test_easybuildlog \[WARNING\] :: bleh",
            r"fancyroot.test_easybuildlog \[INFO\] :: 4\+2 = 42",
            r"fancyroot.test_easybuildlog \[DEBUG\] :: this is just a test",
            r"fancyroot.test_easybuildlog \[ERROR\] :: EasyBuild crashed with an error \(at .* in .*\): foo baz baz",
            '',
        ])
        logtxt_regex = re.compile(r'^%s' % expected_logtxt, re.M)
        self.assertTrue(logtxt_regex.search(logtxt), "Pattern '%s' found in %s" % (logtxt_regex.pattern, logtxt))

        write_file(tmplog, '')
        logToFile(tmplog, enable=True)

        # also test use of 'more_info' named argument for log.deprecated
        self.mock_stderr(True)
        log.deprecated("\nthis is just a test\n", newer_ver, more_info="(see URLGOESHERE for more information)")
        self.mock_stderr(False)
        logtxt = read_file(tmplog)
        expected_logtxt = '\n'.join([
            "[WARNING] :: Deprecated functionality, will no longer work in v10000001: ",
            "this is just a test",
            "(see URLGOESHERE for more information)",
        ])
        self.assertTrue(logtxt.strip().endswith(expected_logtxt))

    def test_log_levels(self):
        """Test whether log levels are respected"""
        fd, tmplog = tempfile.mkstemp()
        os.close(fd)

        # set log format, for each regex searching
        setLogFormat("%(name)s [%(levelname)s] :: %(message)s")

        # test basic log methods
        logToFile(tmplog, enable=True)
        log = getLogger('test_easybuildlog')

        self.mock_stderr(True)  # avoid that some log statement spit out stuff to stderr while tests are running
        for level in ['ERROR', 'WARNING', 'INFO', 'DEBUG', 'DEVEL']:
            log.setLevelName(level)
            log.raiseError = False
            log.error('kaput')
            log.deprecated('almost kaput', '10000000000000')
            log.raiseError = True
            log.warn('this is a warning')
            log.info('fyi')
            log.debug('gdb')
            log.devel('tmi')
        self.mock_stderr(False)

        logToFile(tmplog, enable=False)
        logtxt = read_file(tmplog)

        prefix = 'fancyroot.test_easybuildlog'
        devel_msg = r"%s \[DEVEL\] :: tmi" % prefix
        debug_msg = r"%s \[DEBUG\] :: gdb" % prefix
        info_msg = r"%s \[INFO\] :: fyi" % prefix
        warning_msg = r"%s \[WARNING\] :: this is a warning" % prefix
        deprecated_msg = r"%s \[WARNING\] :: Deprecated functionality, .*: almost kaput; see .*" % prefix
        error_msg = r"%s \[ERROR\] :: EasyBuild crashed with an error \(at .* in .*\): kaput" % prefix

        expected_logtxt = '\n'.join([
            error_msg,
            error_msg, deprecated_msg, warning_msg,
            error_msg, deprecated_msg, warning_msg, info_msg,
            error_msg, deprecated_msg, warning_msg, info_msg, debug_msg,
            error_msg, deprecated_msg, warning_msg, info_msg, debug_msg, devel_msg,
        ])
        logtxt_regex = re.compile(r'^%s' % expected_logtxt, re.M)
        self.assertTrue(logtxt_regex.search(logtxt), "Pattern '%s' found in %s" % (logtxt_regex.pattern, logtxt))

    def test_print_warning(self):
        """Test print_warning"""
        def run_check(args, silent=False, expected_stderr='', **kwargs):
            """Helper function to check stdout/stderr produced via print_warning."""
            self.mock_stderr(True)
            self.mock_stdout(True)
            print_warning(*args, silent=silent, **kwargs)
            stderr = self.get_stderr()
            stdout = self.get_stdout()
            self.mock_stdout(False)
            self.mock_stderr(False)
            self.assertEqual(stdout, '')
            self.assertEqual(stderr, expected_stderr)

        run_check(['You have been warned.'], expected_stderr="\nWARNING: You have been warned.\n\n")
        run_check(['You have been %s.', 'warned'], expected_stderr="\nWARNING: You have been warned.\n\n")
        run_check(['You %s %s %s.', 'have', 'been', 'warned'], expected_stderr="\nWARNING: You have been warned.\n\n")
        run_check(['You have been warned.'], silent=True)
        run_check(['You have been %s.', 'warned'], silent=True)
        run_check(['You %s %s %s.', 'have', 'been', 'warned'], silent=True)

        self.assertErrorRegex(EasyBuildError, "Unknown named arguments", print_warning, 'foo', unknown_arg='bar')

        # test passing of logger to print_warning
        tmp_logfile = os.path.join(self.test_prefix, 'test.log')
        logger, _ = init_logging(tmp_logfile, silent=True)
        expected = "\nWARNING: Test log message with a logger involved.\n\n"
        run_check(["Test log message with a logger involved."], expected_stderr=expected, log=logger)
        log_txt = read_file(tmp_logfile)
        self.assertTrue("WARNING Test log message with a logger involved." in log_txt)

    def test_print_error(self):
        """Test print_error"""
        def run_check(args, silent=False, expected_stderr=''):
            """Helper function to check stdout/stderr produced via print_error."""
            self.mock_stderr(True)
            self.mock_stdout(True)
            self.assertErrorRegex(SystemExit, '1', print_error, *args, silent=silent)
            stderr = self.get_stderr()
            stdout = self.get_stdout()
            self.mock_stdout(False)
            self.mock_stderr(False)
            self.assertEqual(stdout, '')
            self.assertTrue(stderr.startswith(expected_stderr))

        run_check(['You have failed.'], expected_stderr="ERROR: You have failed.\n")
        run_check(['You have %s.', 'failed'], expected_stderr="ERROR: You have failed.\n")
        run_check(['%s %s %s.', 'You', 'have', 'failed'], expected_stderr="ERROR: You have failed.\n")
        run_check(['You have failed.'], silent=True)
        run_check(['You have %s.', 'failed'], silent=True)
        run_check(['%s %s %s.', 'You', 'have', 'failed'], silent=True)

        self.assertErrorRegex(EasyBuildError, "Unknown named arguments", print_error, 'foo', unknown_arg='bar')

    def test_print_msg(self):
        """Test print_msg"""
        def run_check(msg, args, expected_stdout='', expected_stderr='', **kwargs):
            """Helper function to check stdout/stderr produced via print_msg."""
            self.mock_stdout(True)
            self.mock_stderr(True)
            print_msg(msg, *args, **kwargs)
            stdout = self.get_stdout()
            stderr = self.get_stderr()
            self.mock_stdout(False)
            self.mock_stderr(False)
            self.assertEqual(stdout, expected_stdout)
            self.assertEqual(stderr, expected_stderr)

        run_check("testing, 1, 2, 3", [], expected_stdout="== testing, 1, 2, 3\n")
        run_check("testing, %s", ['1, 2, 3'], expected_stdout="== testing, 1, 2, 3\n")
        run_check("testing, %s, %s, %s", ['1', '2', '3'], expected_stdout="== testing, 1, 2, 3\n")
        run_check("testing, 1, 2, 3", [], expected_stdout="== testing, 1, 2, 3", newline=False)
        run_check("testing, %s, 2, %s", ['1', '3'], expected_stdout="== testing, 1, 2, 3", newline=False)
        run_check("testing, 1, 2, 3", [], expected_stdout="testing, 1, 2, 3\n", prefix=False)
        run_check("testing, 1, 2, 3", [], expected_stdout="testing, 1, 2, 3", prefix=False, newline=False)
        run_check("testing, 1, 2, 3", [], expected_stderr="== testing, 1, 2, 3\n", stderr=True)
        run_check("testing, 1, 2, 3", [], expected_stderr="== testing, 1, 2, 3", stderr=True, newline=False)
        run_check("testing, 1, %s, 3", ['2'], expected_stderr="== testing, 1, 2, 3", stderr=True, newline=False)
        run_check("testing, 1, 2, 3", [], expected_stderr="testing, 1, 2, 3\n", stderr=True, prefix=False)
        run_check("testing, 1, 2, 3", [], expected_stderr="testing, 1, 2, 3", stderr=True, prefix=False, newline=False)
        run_check("testing, 1, 2, 3", [], silent=True)
        run_check("testing, 1, %s, %s", ['2', '3'], silent=True)
        run_check("testing, 1, 2, 3", [], silent=True, stderr=True)
        run_check("testing, %s, %s, 3", ['1', '2'], silent=True, stderr=True)

        self.assertErrorRegex(EasyBuildError, "Unknown named arguments", print_msg, 'foo', unknown_arg='bar')

    def test_time_str_since(self):
        """Test time_str_since"""
        self.assertEqual(time_str_since(datetime.now()), '< 1s')
        self.assertEqual(time_str_since(datetime.now() - timedelta(seconds=1.1)), '00h00m01s')
        self.assertEqual(time_str_since(datetime.now() - timedelta(seconds=37.1)), '00h00m37s')
        self.assertEqual(time_str_since(datetime.now() - timedelta(seconds=60.1)), '00h01m00s')
        self.assertEqual(time_str_since(datetime.now() - timedelta(seconds=81.1)), '00h01m21s')
        self.assertEqual(time_str_since(datetime.now() - timedelta(seconds=1358.1)), '00h22m38s')
        self.assertEqual(time_str_since(datetime.now() - timedelta(seconds=3600.1)), '01h00m00s')
        self.assertEqual(time_str_since(datetime.now() - timedelta(seconds=3960.1)), '01h06m00s')
        self.assertEqual(time_str_since(datetime.now() - timedelta(seconds=4500.1)), '01h15m00s')
        self.assertEqual(time_str_since(datetime.now() - timedelta(seconds=12305.1)), '03h25m05s')
        self.assertEqual(time_str_since(datetime.now() - timedelta(seconds=54321.1)), '15h05m21s')

    def test_dry_run_msg(self):
        """Test dry_run_msg"""
        def run_check(msg, args, expected_stdout='', **kwargs):
            """Helper function to check stdout/stderr produced via dry_run_msg."""
            self.mock_stdout(True)
            self.mock_stderr(True)
            dry_run_msg(msg, *args, **kwargs)
            stdout = self.get_stdout()
            stderr = self.get_stderr()
            self.mock_stdout(False)
            self.mock_stderr(False)
            self.assertEqual(stdout, expected_stdout)
            self.assertEqual(stderr, '')

        run_check("test 123", [], expected_stdout="test 123\n")
        run_check("test %s", ['123'], expected_stdout="test 123\n")
        run_check("test 123", [], silent=True)
        run_check("test %s", ['123'], silent=True)

        self.assertErrorRegex(EasyBuildError, "Unknown named arguments", dry_run_msg, 'foo', unknown_arg='bar')

    def test_dry_run_warning(self):
        """Test dry_run_warningmsg"""
        def run_check(msg, args, expected_stdout='', **kwargs):
            """Helper function to check stdout/stderr produced via dry_run_warningmsg."""
            self.mock_stdout(True)
            self.mock_stderr(True)
            dry_run_warning(msg, *args, **kwargs)
            stdout = self.get_stdout()
            stderr = self.get_stderr()
            self.mock_stdout(False)
            self.mock_stderr(False)
            self.assertEqual(stdout, expected_stdout)
            self.assertEqual(stderr, '')

        run_check("test 123", [], expected_stdout="\n!!!\n!!! WARNING: test 123\n!!!\n\n")
        run_check("test %s", ['123'], expected_stdout="\n!!!\n!!! WARNING: test 123\n!!!\n\n")
        run_check("test 123", [], silent=True)
        run_check("test %s", ['123'], silent=True)

        self.assertErrorRegex(EasyBuildError, "Unknown named arguments", dry_run_warning, 'foo', unknown_arg='bar')

    def test_init_logging(self):
        """Test init_logging function."""
        # first, make very sure $TMPDIR is a subdir of self.test_prefix
        tmpdir = os.getenv('TMPDIR')
        self.assertTrue(tmpdir.startswith(self.test_prefix))

        # use provided path for log file
        tmp_logfile = os.path.join(self.test_prefix, 'test.log')
        log, logfile = init_logging(tmp_logfile, silent=True)
        self.assertEqual(logfile, tmp_logfile)
        self.assertTrue(os.path.exists(logfile))
        self.assertTrue(isinstance(log, EasyBuildLog))

        stop_logging(logfile)

        # no log provided, so create one (should be file in $TMPDIR)
        log, logfile = init_logging(None, silent=True)
        self.assertTrue(os.path.exists(logfile))
        self.assertEqual(os.path.dirname(logfile), tmpdir)
        self.assertTrue(isinstance(log, EasyBuildLog))

        stop_logging(logfile)

        # no problem with specifying a different directory to put log file in (even if it doesn't exist yet)
        tmp_logdir = os.path.join(self.test_prefix, 'tmp_logs')
        self.assertFalse(os.path.exists(tmp_logdir))

        log, logfile = init_logging(None, silent=True, tmp_logdir=tmp_logdir)
        self.assertEqual(os.path.dirname(logfile), tmp_logdir)
        self.assertTrue(isinstance(log, EasyBuildLog))

        stop_logging(logfile)

        # by default, path to tmp log file is printed
        self.mock_stdout(True)
        log, logfile = init_logging(None)
        stdout = self.get_stdout()
        self.mock_stdout(False)
        self.assertTrue(os.path.exists(logfile))
        self.assertEqual(os.path.dirname(logfile), tmpdir)
        self.assertTrue(isinstance(log, EasyBuildLog))
        self.assertTrue(stdout.startswith("== Temporary log file in case of crash"))

        stop_logging(logfile)

        # logging to stdout implies no log file
        self.mock_stdout(True)
        log, logfile = init_logging(None, logtostdout=True)
        self.mock_stdout(False)
        self.assertEqual(logfile, None)
        self.assertTrue(isinstance(log, EasyBuildLog))

        stop_logging(logfile, logtostdout=True)

    def test_raise_nosupport(self):
        self.assertErrorRegex(EasyBuildError, 'NO LONGER SUPPORTED since v42: foobar;',
                              raise_nosupport, 'foobar', 42)


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(BuildLogTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
