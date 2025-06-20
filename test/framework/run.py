# #
# -*- coding: utf-8 -*-
# Copyright 2012-2025 Ghent University
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
Unit tests for run.py

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""
import contextlib
import glob
import os
import re
import signal
import string
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner, mock
from easybuild.base.fancylogger import setLogLevelDebug

import easybuild.tools.asyncprocess as asyncprocess
import easybuild.tools.utilities
from easybuild.tools.build_log import EasyBuildError, init_logging, stop_logging
from easybuild.tools.config import update_build_option
from easybuild.tools.filetools import adjust_permissions, change_dir, mkdir, read_file, remove_dir, write_file
from easybuild.tools.modules import EnvironmentModules, Lmod
from easybuild.tools.run import RunShellCmdResult, RunShellCmdError, check_async_cmd, check_log_for_errors
from easybuild.tools.run import complete_cmd, fileprefix_from_cmd, get_output_from_process, parse_log_for_error
from easybuild.tools.run import run_cmd, run_cmd_qa, run_shell_cmd, subprocess_terminate
from easybuild.tools.config import ERROR, IGNORE, WARN


class RunTest(EnhancedTestCase):
    """ Testcase for run module """

    def setUp(self):
        """Set up test."""
        super().setUp()
        self.orig_experimental = easybuild.tools.utilities._log.experimental

    def tearDown(self):
        """Test cleanup."""
        super().tearDown()

        # restore log.experimental
        easybuild.tools.utilities._log.experimental = self.orig_experimental

    def test_get_output_from_process(self):
        """Test for get_output_from_process utility function."""

        # use of get_output_from_process is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        @contextlib.contextmanager
        def get_proc(cmd, asynchronous=False):
            if asynchronous:
                proc = asyncprocess.Popen(cmd, shell=True, stdout=asyncprocess.PIPE, stderr=asyncprocess.STDOUT,
                                          stdin=asyncprocess.PIPE, close_fds=True, executable='/bin/bash')
            else:
                proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        stdin=subprocess.PIPE, close_fds=True, executable='/bin/bash')

            try:
                yield proc
            finally:
                # Make sure to close the process and its pipes
                subprocess_terminate(proc, timeout=1)

        # get all output at once
        with self.mocked_stdout_stderr():
            with get_proc("echo hello") as proc:
                out = get_output_from_process(proc)
                self.assertEqual(out, 'hello\n')

        # first get 100 bytes, then get the rest all at once
        with self.mocked_stdout_stderr():
            with get_proc("echo hello") as proc:
                out = get_output_from_process(proc, read_size=100)
                self.assertEqual(out, 'hello\n')
                out = get_output_from_process(proc)
                self.assertEqual(out, '')

        # get output in small bits, keep trying to get output (which shouldn't fail)
        with self.mocked_stdout_stderr():
            with get_proc("echo hello") as proc:
                out = get_output_from_process(proc, read_size=1)
                self.assertEqual(out, 'h')
                out = get_output_from_process(proc, read_size=3)
                self.assertEqual(out, 'ell')
                out = get_output_from_process(proc, read_size=2)
                self.assertEqual(out, 'o\n')
                out = get_output_from_process(proc, read_size=1)
                self.assertEqual(out, '')
                out = get_output_from_process(proc, read_size=10)
                self.assertEqual(out, '')
                out = get_output_from_process(proc)
                self.assertEqual(out, '')

        # can also get output asynchronously (read_size is *ignored* in that case)
        async_cmd = "echo hello; read reply; echo $reply"

        with self.mocked_stdout_stderr():
            with get_proc(async_cmd, asynchronous=True) as proc:
                out = get_output_from_process(proc, asynchronous=True)
                self.assertEqual(out, 'hello\n')
                asyncprocess.send_all(proc, 'test123\n')
                out = get_output_from_process(proc)
                self.assertEqual(out, 'test123\n')

        with self.mocked_stdout_stderr():
            with get_proc(async_cmd, asynchronous=True) as proc:
                out = get_output_from_process(proc, asynchronous=True, read_size=1)
                # read_size is ignored when getting output asynchronously, we're getting more than 1 byte!
                self.assertEqual(out, 'hello\n')
                asyncprocess.send_all(proc, 'test123\n')
                out = get_output_from_process(proc, read_size=3)
                self.assertEqual(out, 'tes')
                out = get_output_from_process(proc, read_size=2)
                self.assertEqual(out, 't1')
                out = get_output_from_process(proc)
                self.assertEqual(out, '23\n')

    def test_run_cmd(self):
        """Basic test for run_cmd function."""

        # use of run_cmd is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd("echo hello")
        self.assertEqual(out, "hello\n")
        # no reason echo hello could fail
        self.assertEqual(ec, 0)
        self.assertEqual(type(out), str)

        # test running command that emits non-UTF-8 characters
        # this is constructed to reproduce errors like:
        # UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe2
        # UnicodeEncodeError: 'ascii' codec can't encode character u'\u2018'
        for text in [b"foo \xe2 bar", "foo \u2018 bar"]:
            test_file = os.path.join(self.test_prefix, 'foo.txt')
            write_file(test_file, text)
            cmd = "cat %s" % test_file

            with self.mocked_stdout_stderr():
                (out, ec) = run_cmd(cmd)
            self.assertEqual(ec, 0)
            self.assertTrue(out.startswith('foo ') and out.endswith(' bar'))
            self.assertEqual(type(out), str)

    def test_run_shell_cmd_basic(self):
        """Basic test for run_shell_cmd function."""

        os.environ['FOOBAR'] = 'foobar'

        cwd = change_dir(self.test_prefix)

        with self.mocked_stdout_stderr():
            res = run_shell_cmd("echo hello")
        self.assertEqual(res.output, "hello\n")
        # no reason echo hello could fail
        self.assertEqual(res.cmd, "echo hello")
        self.assertEqual(res.exit_code, 0)
        self.assertTrue(isinstance(res.output, str))
        self.assertEqual(res.stderr, None)
        self.assertTrue(res.work_dir and isinstance(res.work_dir, str))

        change_dir(cwd)
        del os.environ['FOOBAR']

        # check on helper scripts that were generated for this command
        paths = glob.glob(os.path.join(self.test_prefix, 'eb-*', 'run-shell-cmd-output', 'echo-*'))
        self.assertEqual(len(paths), 1)
        cmd_tmpdir = paths[0]

        # check on env.sh script that can be used to set up environment in which command was run
        env_script = os.path.join(cmd_tmpdir, 'env.sh')
        self.assertExists(env_script)
        env_script_txt = read_file(env_script)
        self.assertIn("export FOOBAR=foobar", env_script_txt)
        self.assertIn("history -s 'echo hello'", env_script_txt)

        with self.mocked_stdout_stderr():
            res = run_shell_cmd(f"source {env_script}; echo $USER; echo $FOOBAR; history")
        self.assertEqual(res.exit_code, 0)
        user = os.getenv('USER')
        self.assertTrue(res.output.startswith(f'{user}\nfoobar\n'))
        self.assertTrue(res.output.endswith("echo hello\n"))

        # check on cmd.sh script that can be used to create interactive shell environment for command
        cmd_script = os.path.join(cmd_tmpdir, 'cmd.sh')
        self.assertExists(cmd_script)

        cmd = f"{cmd_script} -c 'echo pwd: $PWD; echo $FOOBAR; echo $EB_CMD_OUT_FILE; cat $EB_CMD_OUT_FILE'"
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, fail_on_error=False)
        self.assertEqual(res.exit_code, 0)
        regex = re.compile("pwd: .*\nfoobar\n.*/echo-.*/out.txt\nhello$")
        self.assertTrue(regex.search(res.output), f"Pattern '{regex.pattern}' should be found in {res.output}")

        # check whether working directory is what's expected
        regex = re.compile('^pwd: .*', re.M)
        res = regex.findall(res.output)
        self.assertEqual(len(res), 1)
        pwd = res[0].strip()[5:]
        self.assertTrue(os.path.samefile(pwd, self.test_prefix))

        cmd = f"{cmd_script} -c 'module --version'"
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, fail_on_error=False)
        self.assertEqual(res.exit_code, 0)

        if isinstance(self.modtool, Lmod):
            regex = re.compile("^Modules based on Lua: Version [0-9]", re.M)
        elif isinstance(self.modtool, EnvironmentModules):
            regex = re.compile("^Modules Release [0-9]", re.M)
        else:
            self.fail("Unknown modules tool used!")

        self.assertTrue(regex.search(res.output), f"Pattern '{regex.pattern}' should be found in {res.output}")

        # test running command that emits non-UTF-8 characters
        # this is constructed to reproduce errors like:
        # UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe2
        # UnicodeEncodeError: 'ascii' codec can't encode character u'\u2018'
        # (such errors are ignored by the 'run' implementation)
        for text in [b"foo \xe2 bar", "foo \u2018 bar"]:
            test_file = os.path.join(self.test_prefix, 'foo.txt')
            write_file(test_file, text)
            cmd = "cat %s" % test_file

            with self.mocked_stdout_stderr():
                res = run_shell_cmd(cmd)
            self.assertEqual(res.cmd, cmd)
            self.assertEqual(res.exit_code, 0)
            self.assertTrue(res.output.startswith('foo ') and res.output.endswith(' bar'))
            self.assertTrue(isinstance(res.output, str))
            self.assertTrue(res.work_dir and isinstance(res.work_dir, str))

    def test_run_shell_cmd_perl(self):
        """
        Test running of Perl script via run_shell_cmd that detects type of shell
        """
        perl_script = os.path.join(self.test_prefix, 'test.pl')
        perl_script_txt = """#!/usr/bin/perl

        # wait for input, see what happens (should not hang)
        print STDOUT "foo:\n";
        STDOUT->autoflush(1);
        my $stdin = <STDIN>;
        print "stdin: $stdin\n";

        # conditional print statements below should *not* be triggered
        print "stdin+stdout are terminals\n" if -t STDIN && -t STDOUT;
        print "stdin is terminal\n" if -t STDIN;
        print "stdout is terminal\n" if -t STDOUT;
        my $ISA_TTY = -t STDIN && (-t STDOUT || !(-f STDOUT || -c STDOUT)) ;
        print "ISA_TTY" if $ISA_TTY;

        print "PS1 is set\n" if $ENV{PS1};

        print "tty -s returns 0\n" if system("tty -s") == 0;

        # check if parent process is a shell
        my $ppid = getppid();
        my $parent_cmd = `ps -p $ppid -o comm=`;
        print "parent process is bash\n" if ($parent_cmd =~ '/bash$');
        """
        write_file(perl_script, perl_script_txt)
        adjust_permissions(perl_script, stat.S_IXUSR)

        def handler(signum, _):
            raise RuntimeError(f"Test for running Perl script via run_shell_cmd took too long, signal {signum}")

        orig_sigalrm_handler = signal.getsignal(signal.SIGALRM)

        try:
            # set the signal handler and a 3-second alarm
            signal.signal(signal.SIGALRM, handler)
            signal.alarm(3)

            res = run_shell_cmd(perl_script, hidden=True)
            self.assertEqual(res.exit_code, 0)
            self.assertEqual(res.output, 'foo:\nstdin: \n')

            res = run_shell_cmd(perl_script, hidden=True, stdin="test")
            self.assertEqual(res.exit_code, 0)
            self.assertEqual(res.output, 'foo:\nstdin: test\n')

            res = run_shell_cmd(perl_script, hidden=True, qa_patterns=[('foo:', 'bar')], qa_timeout=1)
            self.assertEqual(res.exit_code, 0)
            self.assertEqual(res.output, 'foo:\nstdin: bar\n\n')

            error_pattern = "No matching questions found for current command output"
            self.assertErrorRegex(EasyBuildError, error_pattern, run_shell_cmd, perl_script,
                                  hidden=True, qa_patterns=[('bleh', 'blah')], qa_timeout=1)
        finally:
            # cleanup: disable the alarm + reset signal handler for SIGALRM
            signal.signal(signal.SIGALRM, orig_sigalrm_handler)
            signal.alarm(0)

    def test_run_shell_cmd_env(self):
        """Test env option in run_shell_cmd."""

        # use 'env' to define environment in which command should be run;
        # with a few exceptions (like $_, $PWD) no other environment variables will be defined,
        # so $HOME and $USER will not be set
        cmd = "env | sort"
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, env={'FOOBAR': 'foobar', 'PATH': os.getenv('PATH')})
        self.assertEqual(res.cmd, cmd)
        self.assertEqual(res.exit_code, 0)
        self.assertIn("FOOBAR=foobar\n", res.output)
        self.assertTrue(re.search("^_=.*/env$", res.output, re.M))
        for var in ('HOME', 'USER'):
            self.assertFalse(re.search('^' + var + '=.*', res.output, re.M))

        # check on helper scripts that were generated for this command
        paths = glob.glob(os.path.join(self.test_prefix, 'eb-*', 'run-shell-cmd-output', 'env-*'))
        self.assertEqual(len(paths), 1)
        cmd_tmpdir = paths[0]

        # set environment variable in current environment,
        # this should not be set in shell environment produced by scripts
        os.environ['TEST123'] = 'test123'

        env_script = os.path.join(cmd_tmpdir, 'env.sh')
        self.assertExists(env_script)
        env_script_txt = read_file(env_script)
        self.assertIn('unset "$var"', env_script_txt)
        self.assertIn('unset -f "$func"', env_script_txt)
        self.assertIn('\nexport FOOBAR=foobar\nexport PATH', env_script_txt)

        cmd_script = os.path.join(cmd_tmpdir, 'cmd.sh')
        self.assertExists(cmd_script)

        with self.mocked_stdout_stderr():
            res = run_shell_cmd(f"{cmd_script} -c 'echo $FOOBAR; echo TEST123:$TEST123'", fail_on_error=False)
        self.assertEqual(res.exit_code, 0)
        self.assertTrue(res.output.endswith('\nfoobar\nTEST123:\n'))

    def test_fileprefix_from_cmd(self):
        """test simplifications from fileprefix_from_cmd."""
        cmds = {
            'abd123': 'abd123',
            'ab"a': 'aba',
            'a{:$:S@"a': 'aSa',
            'cmd-with-dash': 'cmd-with-dash',
            'cmd_with_underscore': 'cmd_with_underscore',
        }
        for cmd, expected_simplification in cmds.items():
            self.assertEqual(fileprefix_from_cmd(cmd), expected_simplification)

        cmds = {
            'abd123': 'abd',
            'ab"a': 'aba',
            '0a{:$:2@"a': 'aa',
        }
        for cmd, expected_simplification in cmds.items():
            self.assertEqual(fileprefix_from_cmd(cmd, allowed_chars=string.ascii_letters), expected_simplification)

    def test_run_cmd_log(self):
        """Test logging of executed commands."""

        # use of run_cmd is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        fd, logfile = tempfile.mkstemp(suffix='.log', prefix='eb-test-')
        os.close(fd)

        regex = re.compile('cmd "echo hello" exited with exit code [0-9]* and output:')

        # command output is not logged by default without debug logging
        init_logging(logfile, silent=True)
        with self.mocked_stdout_stderr():
            self.assertTrue(run_cmd("echo hello"))
        stop_logging(logfile)
        self.assertEqual(len(regex.findall(read_file(logfile))), 0)
        write_file(logfile, '')

        init_logging(logfile, silent=True)
        with self.mocked_stdout_stderr():
            self.assertTrue(run_cmd("echo hello", log_all=True))
        stop_logging(logfile)
        self.assertEqual(len(regex.findall(read_file(logfile))), 1)
        write_file(logfile, '')

        # with debugging enabled, exit code and output of command should only get logged once
        setLogLevelDebug()

        init_logging(logfile, silent=True)
        with self.mocked_stdout_stderr():
            self.assertTrue(run_cmd("echo hello"))
        stop_logging(logfile)
        self.assertEqual(len(regex.findall(read_file(logfile))), 1)
        write_file(logfile, '')

        init_logging(logfile, silent=True)
        with self.mocked_stdout_stderr():
            self.assertTrue(run_cmd("echo hello", log_all=True))
        stop_logging(logfile)
        self.assertEqual(len(regex.findall(read_file(logfile))), 1)
        write_file(logfile, '')

        # Test that we can set the directory for the logfile
        log_path = os.path.join(self.test_prefix, 'chicken')
        mkdir(log_path)
        logfile = None
        init_logging(logfile, silent=True, tmp_logdir=log_path)
        logfiles = os.listdir(log_path)
        self.assertEqual(len(logfiles), 1)
        self.assertTrue(logfiles[0].startswith("easybuild"))
        self.assertTrue(logfiles[0].endswith("log"))

    def test_run_shell_cmd_log(self):
        """Test logging of executed commands with run_shell_cmd function."""

        fd, logfile = tempfile.mkstemp(suffix='.log', prefix='eb-test-')
        os.close(fd)

        regex_start_cmd = re.compile("Running shell command 'echo hello' in /")
        regex_cmd_exit = re.compile(r"Shell command completed successfully \(see output above\): echo hello")

        # command output is always logged
        init_logging(logfile, silent=True)
        with self.mocked_stdout_stderr():
            res = run_shell_cmd("echo hello")
        stop_logging(logfile)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, 'hello\n')
        logtxt = read_file(logfile)
        self.assertEqual(len(regex_start_cmd.findall(logtxt)), 1)
        self.assertEqual(len(regex_cmd_exit.findall(logtxt)), 1)
        write_file(logfile, '')

        # with debugging enabled, exit code and output of command should only get logged once
        setLogLevelDebug()

        init_logging(logfile, silent=True)
        with self.mocked_stdout_stderr():
            res = run_shell_cmd("echo hello")
        stop_logging(logfile)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, 'hello\n')
        self.assertEqual(len(regex_start_cmd.findall(read_file(logfile))), 1)
        self.assertEqual(len(regex_cmd_exit.findall(read_file(logfile))), 1)
        write_file(logfile, '')

    def test_run_cmd_negative_exit_code(self):
        """Test run_cmd function with command that has negative exit code."""

        # use of run_cmd/run_cmd_qa is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        # define signal handler to call in case run_cmd takes too long
        def handler(signum, _):
            raise RuntimeError("Signal handler called with signal %s" % signum)

        orig_sigalrm_handler = signal.getsignal(signal.SIGALRM)

        try:
            # set the signal handler and a 3-second alarm
            signal.signal(signal.SIGALRM, handler)
            signal.alarm(3)

            with self.mocked_stdout_stderr():
                (_, ec) = run_cmd("kill -9 $$", log_ok=False)
            self.assertEqual(ec, -9)

            # reset the alarm
            signal.alarm(0)
            signal.alarm(3)

            with self.mocked_stdout_stderr():
                (_, ec) = run_cmd_qa("kill -9 $$", {}, log_ok=False)
            self.assertEqual(ec, -9)

        finally:
            # cleanup: disable the alarm + reset signal handler for SIGALRM
            signal.signal(signal.SIGALRM, orig_sigalrm_handler)
            signal.alarm(0)

    def test_run_shell_cmd_fail(self):
        """Test run_shell_cmd function with command that has negative exit code."""
        # define signal handler to call in case run takes too long
        def handler(signum, _):
            raise RuntimeError("Signal handler called with signal %s" % signum)

        # disable trace output for this test (so stdout remains empty)
        update_build_option('trace', False)

        orig_sigalrm_handler = signal.getsignal(signal.SIGALRM)

        try:
            # set the signal handler and a 3-second alarm
            signal.signal(signal.SIGALRM, handler)
            signal.alarm(3)

            # command to kill parent shell
            cmd = "kill -9 $$"

            work_dir = os.path.realpath(self.test_prefix)
            change_dir(work_dir)

            try:
                run_shell_cmd(cmd)
                self.assertFalse("This should never be reached, RunShellCmdError should occur!")
            except RunShellCmdError as err:
                self.assertEqual(str(err), "Shell command 'kill' failed!")
                self.assertEqual(err.cmd, "kill -9 $$")
                self.assertEqual(err.cmd_name, 'kill')
                self.assertEqual(err.exit_code, -9)
                self.assertEqual(err.work_dir, work_dir)
                self.assertEqual(err.output, '')
                self.assertEqual(err.stderr, None)
                self.assertTrue(isinstance(err.caller_info, tuple))
                self.assertEqual(len(err.caller_info), 3)
                self.assertEqual(err.caller_info[0], __file__)
                self.assertTrue(isinstance(err.caller_info[1], int))  # line number of calling site
                self.assertEqual(err.caller_info[2], 'test_run_shell_cmd_fail')

                with self.mocked_stdout_stderr() as (_, stderr):
                    err.print()

                # check error reporting output
                stderr = stderr.getvalue()
                patterns = [
                    r"ERROR: Shell command failed!",
                    r"\s+full command\s* ->  kill -9 \$\$",
                    r"\s+exit code\s* ->  -9",
                    r"\s+working directory\s* ->  " + work_dir,
                    r"\s+called from\s* ->  'test_run_shell_cmd_fail' function in "
                    r"(.|\n)*/test/(.|\n)*/run.py \(line [0-9]+\)",
                    r"\s+output \(stdout \+ stderr\)\s* ->  (.|\n)*/run-shell-cmd-output/kill-(.|\n)*/out.txt",
                    r"\s+interactive shell script\s* ->  (.|\n)*/run-shell-cmd-output/kill-(.|\n)*/cmd.sh",
                ]
                for pattern in patterns:
                    regex = re.compile(pattern, re.M)
                    self.assertTrue(regex.search(stderr), "Pattern '%s' should be found in: %s" % (pattern, stderr))

            # check error reporting output when stdout/stderr are collected separately
            try:
                run_shell_cmd(cmd, split_stderr=True)
                self.assertFalse("This should never be reached, RunShellCmdError should occur!")
            except RunShellCmdError as err:
                self.assertEqual(str(err), "Shell command 'kill' failed!")
                self.assertEqual(err.cmd, "kill -9 $$")
                self.assertEqual(err.cmd_name, 'kill')
                self.assertEqual(err.exit_code, -9)
                self.assertEqual(err.work_dir, work_dir)
                self.assertEqual(err.output, '')
                self.assertEqual(err.stderr, '')
                self.assertTrue(isinstance(err.caller_info, tuple))
                self.assertEqual(len(err.caller_info), 3)
                self.assertEqual(err.caller_info[0], __file__)
                self.assertTrue(isinstance(err.caller_info[1], int))  # line number of calling site
                self.assertEqual(err.caller_info[2], 'test_run_shell_cmd_fail')

                with self.mocked_stdout_stderr() as (_, stderr):
                    err.print()

                # check error reporting output
                stderr = stderr.getvalue()
                patterns = [
                    r"ERROR: Shell command failed!",
                    r"\s+full command\s+ ->  kill -9 \$\$",
                    r"\s+exit code\s+ ->  -9",
                    r"\s+working directory\s+ ->  " + work_dir,
                    r"\s+called from\s+ ->  'test_run_shell_cmd_fail' function in "
                    r"(.|\n)*/test/(.|\n)*/run.py \(line [0-9]+\)",
                    r"\s+output \(stdout\)\s+ -> (.|\n)*/run-shell-cmd-output/kill-(.|\n)*/out.txt",
                    r"\s+error/warnings \(stderr\)\s+ -> (.|\n)*/run-shell-cmd-output/kill-(.|\n)*/err.txt",
                    r"\s+interactive shell script\s* ->  (.|\n)*/run-shell-cmd-output/kill-(.|\n)*/cmd.sh",
                ]
                for pattern in patterns:
                    regex = re.compile(pattern, re.M)
                    self.assertTrue(regex.search(stderr), "Pattern '%s' should be found in: %s" % (pattern, stderr))

            # no error reporting when fail_on_error is disabled
            with self.mocked_stdout_stderr() as (_, stderr):
                res = run_shell_cmd(cmd, fail_on_error=False)
            self.assertEqual(res.exit_code, -9)
            self.assertEqual(stderr.getvalue(), '')

        finally:
            # cleanup: disable the alarm + reset signal handler for SIGALRM
            signal.signal(signal.SIGALRM, orig_sigalrm_handler)
            signal.alarm(0)

    def test_run_cmd_bis(self):
        """More 'complex' test for run_cmd function."""

        # use of run_cmd is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        # a more 'complex' command to run, make sure all required output is there
        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd("for j in `seq 1 3`; do for i in `seq 1 100`; do echo hello; done; sleep 1.4; done")
        self.assertTrue(out.startswith('hello\nhello\n'))
        self.assertEqual(len(out), len("hello\n" * 300))
        self.assertEqual(ec, 0)

    def test_run_shell_cmd_bis(self):
        """More 'complex' test for run_shell_cmd function."""
        # a more 'complex' command to run, make sure all required output is there
        with self.mocked_stdout_stderr():
            res = run_shell_cmd("for j in `seq 1 3`; do for i in `seq 1 100`; do echo hello; done; sleep 1.4; done")
        self.assertTrue(res.output.startswith('hello\nhello\n'))
        self.assertEqual(len(res.output), len("hello\n" * 300))
        self.assertEqual(res.exit_code, 0)

    def test_run_cmd_work_dir(self):
        """
        Test running command in specific directory with run_cmd function.
        """

        # use of run_cmd is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        orig_wd = os.getcwd()
        self.assertFalse(os.path.samefile(orig_wd, self.test_prefix))

        test_dir = os.path.join(self.test_prefix, 'test')
        for fn in ('foo.txt', 'bar.txt'):
            write_file(os.path.join(test_dir, fn), 'test')

        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd("ls | sort", path=test_dir)

        self.assertEqual(ec, 0)
        self.assertEqual(out, 'bar.txt\nfoo.txt\n')

        self.assertTrue(os.path.samefile(orig_wd, os.getcwd()))

    def test_run_shell_cmd_work_dir(self):
        """
        Test running shell command in specific directory with run_shell_cmd function.
        """
        test_dir = os.path.join(self.test_prefix, 'test')
        test_workdir = os.path.join(self.test_prefix, 'test', 'workdir')
        for fn in ('foo.txt', 'bar.txt'):
            write_file(os.path.join(test_workdir, fn), 'test')

        os.chdir(test_dir)
        orig_wd = os.getcwd()
        self.assertFalse(os.path.samefile(orig_wd, self.test_prefix))

        cmd = "ls | sort"

        # working directory is not explicitly defined
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd)

        self.assertEqual(res.cmd, cmd)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, 'workdir\n')
        self.assertEqual(res.stderr, None)
        self.assertEqual(res.work_dir, orig_wd)

        self.assertTrue(os.path.samefile(orig_wd, os.getcwd()))

        # working directory is explicitly defined
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, work_dir=test_workdir)

        self.assertEqual(res.cmd, cmd)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, 'bar.txt\nfoo.txt\n')
        self.assertEqual(res.stderr, None)
        self.assertEqual(res.work_dir, test_workdir)

        self.assertTrue(os.path.samefile(orig_wd, os.getcwd()))

    def test_run_cmd_log_output(self):
        """Test run_cmd with log_output enabled"""

        # use of run_cmd is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd("seq 1 100", log_output=True)
        self.assertEqual(ec, 0)
        self.assertEqual(type(out), str)
        self.assertTrue(out.startswith("1\n2\n"))
        self.assertTrue(out.endswith("99\n100\n"))

        run_cmd_logs = glob.glob(os.path.join(self.test_prefix, '*', 'easybuild-run_cmd*.log'))
        self.assertEqual(len(run_cmd_logs), 1)
        run_cmd_log_txt = read_file(run_cmd_logs[0])
        self.assertTrue(run_cmd_log_txt.startswith("# output for command: seq 1 100\n\n"))
        run_cmd_log_lines = run_cmd_log_txt.split('\n')
        self.assertEqual(run_cmd_log_lines[2:5], ['1', '2', '3'])
        self.assertEqual(run_cmd_log_lines[-4:-1], ['98', '99', '100'])

        # test running command that emits non-UTF-8 characters
        # this is constructed to reproduce errors like:
        # UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe2
        # UnicodeEncodeError: 'ascii' codec can't encode character u'\u2018' (‘)
        for text in [b"foo \xe2 bar", "foo ‘ bar"]:
            test_file = os.path.join(self.test_prefix, 'foo.txt')
            write_file(test_file, text)
            cmd = "cat %s" % test_file

            with self.mocked_stdout_stderr():
                (out, ec) = run_cmd(cmd, log_output=True)
            self.assertEqual(ec, 0)
            self.assertTrue(out.startswith('foo ') and out.endswith(' bar'))
            self.assertEqual(type(out), str)

    def test_run_shell_cmd_split_stderr(self):
        """Test getting split stdout/stderr output from run_shell_cmd function."""
        cmd = ';'.join([
            "echo ok",
            "echo warning >&2",
        ])

        # by default, output contains both stdout + stderr
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd)
        self.assertEqual(res.exit_code, 0)
        output_lines = res.output.split('\n')
        self.assertTrue("ok" in output_lines)
        self.assertTrue("warning" in output_lines)
        self.assertEqual(res.stderr, None)

        # cleanup of artifacts in between calls to run_shell_cmd
        remove_dir(self.test_prefix)

        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, split_stderr=True)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.stderr, "warning\n")
        self.assertEqual(res.output, "ok\n")

        # check whether environment variables that point to stdout/stderr output files
        # are set in environment defined by cmd.sh script
        paths = glob.glob(os.path.join(self.test_prefix, 'eb-*', 'run-shell-cmd-output', 'echo-*'))
        self.assertEqual(len(paths), 1)
        cmd_tmpdir = paths[0]
        cmd_script = os.path.join(cmd_tmpdir, 'cmd.sh')
        self.assertExists(cmd_script)

        cmd_cmd = '; '.join([
            "echo $EB_CMD_OUT_FILE",
            "cat $EB_CMD_OUT_FILE",
            "echo $EB_CMD_ERR_FILE",
            "cat $EB_CMD_ERR_FILE",
        ])
        cmd = f"{cmd_script} -c '{cmd_cmd}'"
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, fail_on_error=False)

        regex = re.compile(".*/echo-.*/out.txt\nok\n.*/echo-.*/err.txt\nwarning$")
        self.assertTrue(regex.search(res.output), f"Pattern '{regex.pattern}' should be found in {res.output}")

    def test_run_cmd_trace(self):
        """Test run_cmd in trace mode, and with tracing disabled."""

        # use of run_cmd is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        pattern = [
            r"^  >> running command:",
            r"\t\[started at: .*\]",
            r"\t\[working dir: .*\]",
            r"\t\[output logged in .*\]",
            r"\techo hello",
            r"  >> command completed: exit 0, ran in .*",
        ]

        # trace output is enabled by default (since EasyBuild v5.0)
        self.mock_stdout(True)
        self.mock_stderr(True)
        (out, ec) = run_cmd("echo hello")
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(out, 'hello\n')
        self.assertEqual(ec, 0)
        self.assertTrue(stderr.strip().startswith("WARNING: Deprecated functionality"))
        regex = re.compile('\n'.join(pattern))
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        init_config(build_options={'trace': False})

        self.mock_stdout(True)
        self.mock_stderr(True)
        (out, ec) = run_cmd("echo hello")
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(out, 'hello\n')
        self.assertEqual(ec, 0)
        self.assertTrue(stderr.strip().startswith("WARNING: Deprecated functionality"))
        self.assertEqual(stdout, '')

        init_config(build_options={'trace': True})

        # also test with command that is fed input via stdin
        self.mock_stdout(True)
        self.mock_stderr(True)
        (out, ec) = run_cmd('cat', inp='hello')
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(out, 'hello')
        self.assertEqual(ec, 0)
        self.assertTrue(stderr.strip().startswith("WARNING: Deprecated functionality"))
        pattern.insert(3, r"\t\[input: hello\]")
        pattern[-2] = "\tcat"
        regex = re.compile('\n'.join(pattern))
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        init_config(build_options={'trace': False})

        self.mock_stdout(True)
        self.mock_stderr(True)
        (out, ec) = run_cmd('cat', inp='hello')
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(out, 'hello')
        self.assertEqual(ec, 0)
        self.assertTrue(stderr.strip().startswith("WARNING: Deprecated functionality"))
        self.assertEqual(stdout, '')

        # trace output can be disabled on a per-command basis
        for trace in (True, False):
            init_config(build_options={'trace': trace})

            self.mock_stdout(True)
            self.mock_stderr(True)
            (out, ec) = run_cmd("echo hello", trace=False)
            stdout = self.get_stdout()
            stderr = self.get_stderr()
            self.mock_stdout(False)
            self.mock_stderr(False)
            self.assertEqual(out, 'hello\n')
            self.assertEqual(ec, 0)
            self.assertEqual(stdout, '')
            self.assertTrue(stderr.strip().startswith("WARNING: Deprecated functionality"))

    def test_run_shell_cmd_trace(self):
        """Test run_shell_cmd function in trace mode, and with tracing disabled."""

        pattern = [
            r"^  >> running shell command:",
            r"\techo hello",
            r"\t\[started at: .*\]",
            r"\t\[working dir: .*\]",
            r"\t\[output and state saved to .*\]",
            r"  >> command completed: exit 0, ran in .*",
        ]

        # trace output is enabled by default (since EasyBuild v5.0)
        self.mock_stdout(True)
        self.mock_stderr(True)
        res = run_shell_cmd("echo hello")
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(res.output, 'hello\n')
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(stderr, '')
        regex = re.compile('\n'.join(pattern))
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        init_config(build_options={'trace': False})

        self.mock_stdout(True)
        self.mock_stderr(True)
        res = run_shell_cmd("echo hello")
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(res.output, 'hello\n')
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(stderr, '')
        self.assertEqual(stdout, '')

        init_config(build_options={'trace': True})

        # trace output can be disabled on a per-command basis via 'hidden' option
        for trace in (True, False):
            init_config(build_options={'trace': trace})

            self.mock_stdout(True)
            self.mock_stderr(True)
            res = run_shell_cmd("echo hello", hidden=True)
            stdout = self.get_stdout()
            stderr = self.get_stderr()
            self.mock_stdout(False)
            self.mock_stderr(False)
            self.assertEqual(res.output, 'hello\n')
            self.assertEqual(res.exit_code, 0)
            self.assertEqual(stdout, '')
            self.assertEqual(stderr, '')

    def test_run_shell_cmd_trace_stdin(self):
        """Test run_shell_cmd function under --trace + passing stdin input."""

        init_config(build_options={'trace': True})

        pattern = [
            r"^  >> running shell command:",
            r"\techo hello",
            r"\t\[started at: [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]\]",
            r"\t\[working dir: .*\]",
            r"\t\[output and state saved to .*\]",
            r"  >> command completed: exit 0, ran in .*",
        ]

        self.mock_stdout(True)
        self.mock_stderr(True)
        res = run_shell_cmd("echo hello")
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(res.output, 'hello\n')
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(stderr, '')
        regex = re.compile('\n'.join(pattern))
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        # also test with command that is fed input via stdin
        self.mock_stdout(True)
        self.mock_stderr(True)
        res = run_shell_cmd('cat', stdin='hello')
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(res.output, 'hello')
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(stderr, '')
        pattern.insert(4, r"\t\[input: hello\]")
        pattern[1] = "\tcat"
        regex = re.compile('\n'.join(pattern))
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        # trace output can be disabled on a per-command basis by enabling 'hidden'
        self.mock_stdout(True)
        self.mock_stderr(True)
        res = run_shell_cmd("echo hello", hidden=True)
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(res.output, 'hello\n')
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(stdout, '')
        self.assertEqual(stderr, '')

    def test_run_cmd_qa(self):
        """Basic test for run_cmd_qa function."""

        # use of run_cmd_qa is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        cmd = "echo question; read x; echo $x"
        qa = {'question': 'answer'}
        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd_qa(cmd, qa)
        self.assertEqual(out, "question\nanswer\n")
        # no reason echo hello could fail
        self.assertEqual(ec, 0)

        # test running command that emits non-UTF8 characters
        # this is constructed to reproduce errors like:
        # UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe2
        test_file = os.path.join(self.test_prefix, 'foo.txt')
        write_file(test_file, b"foo \xe2 bar")
        cmd += "; cat %s" % test_file

        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd_qa(cmd, qa)
        self.assertEqual(ec, 0)
        self.assertTrue(out.startswith("question\nanswer\nfoo "))
        self.assertTrue(out.endswith('bar'))

        # test handling of output that is not actually a question
        cmd = ';'.join([
            "echo not-a-question-but-a-statement",
            "sleep 3",
            "echo question",
            "read x",
            "echo $x",
        ])
        qa = {'question': 'answer'}

        # fails because non-question is encountered
        error_pattern = "Max nohits 1 reached: end of output not-a-question-but-a-statement"
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, run_cmd_qa, cmd, qa, maxhits=1, trace=False)

        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd_qa(cmd, qa, no_qa=["not-a-question-but-a-statement"], maxhits=1, trace=False)
        self.assertEqual(out, "not-a-question-but-a-statement\nquestion\nanswer\n")
        self.assertEqual(ec, 0)

    def test_run_shell_cmd_qa(self):
        """Basic test for Q&A support in run_shell_cmd function."""

        cmd = '; '.join([
            "echo question1",
            "read x",
            "echo $x",
            "echo question2",
            "read y",
            "echo $y",
        ])
        qa = [
            ('question1', 'answer1'),
            ('question2', 'answer2'),
        ]
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, qa_patterns=qa)
        self.assertEqual(res.output, "question1\nanswer1\nquestion2\nanswer2\n")
        # no reason echo hello could fail
        self.assertEqual(res.exit_code, 0)

        # test running command that emits non-UTF8 characters
        # this is constructed to reproduce errors like:
        # UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe2
        test_file = os.path.join(self.test_prefix, 'foo.txt')
        write_file(test_file, b"foo \xe2 bar")
        cmd += "; cat %s" % test_file

        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, qa_patterns=qa)
        self.assertEqual(res.exit_code, 0)
        self.assertTrue(res.output.startswith("question1\nanswer1\nquestion2\nanswer2\nfoo "))
        self.assertTrue(res.output.endswith('bar'))

        # check type check on qa_patterns
        error_pattern = "qa_patterns passed to run_shell_cmd should be a list of 2-tuples!"
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, run_shell_cmd, cmd, qa_patterns={'foo': 'bar'})
            self.assertErrorRegex(EasyBuildError, error_pattern, run_shell_cmd, cmd, qa_patterns=('foo', 'bar'))
            self.assertErrorRegex(EasyBuildError, error_pattern, run_shell_cmd, cmd, qa_patterns=(('foo', 'bar'),))
            self.assertErrorRegex(EasyBuildError, error_pattern, run_shell_cmd, cmd, qa_patterns='foo:bar')
            self.assertErrorRegex(EasyBuildError, error_pattern, run_shell_cmd, cmd, qa_patterns=['foo:bar'])

        # validate use of qa_timeout to give up if there's no matching question for too long
        cmd = "sleep 3; echo 'question'; read a; echo $a"
        error_pattern = "No matching questions found for current command output, giving up after 1 seconds!"
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, run_shell_cmd, cmd, qa_patterns=qa, qa_timeout=1)

        # check using answer that is completed via pattern extracted from question
        cmd = ';'.join([
            "echo 'and the magic number is: 42'",
            "read magic_number",
            "echo $magic_number",
        ])
        qa = [("and the magic number is: (?P<nr>[0-9]+)", "%(nr)s")]
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, qa_patterns=qa)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, "and the magic number is: 42\n42\n")

        # test handling of output that is not actually a question
        cmd = ';'.join([
            "echo not-a-question-but-a-statement",
            "sleep 3",
            "echo question",
            "read x",
            "echo $x",
        ])
        qa = [('question', 'answer')]

        # fails because non-question is encountered
        error_pattern = "No matching questions found for current command output, giving up after 1 seconds!"
        self.assertErrorRegex(EasyBuildError, error_pattern, run_shell_cmd, cmd, qa_patterns=qa, qa_timeout=1,
                              hidden=True)

        qa_wait_patterns = ["not-a-question-but-a-statement"]
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, qa_patterns=qa, qa_wait_patterns=qa_wait_patterns, qa_timeout=1)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, "not-a-question-but-a-statement\nquestion\nanswer\n")

        # test multi-line question
        cmd = ';'.join([
            "echo please",
            "echo answer",
            "read x",
            "echo $x",
        ])
        qa = [("please answer", "42")]
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, qa_patterns=qa)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, "please\nanswer\n42\n")

        # also test multi-line wait pattern
        cmd = "echo just; echo wait; sleep 3; " + cmd
        qa_wait_patterns = ["just wait"]
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, qa_patterns=qa, qa_wait_patterns=qa_wait_patterns, qa_timeout=1)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, "just\nwait\nplease\nanswer\n42\n")

        # test multi-line question pattern with hard space
        cmd = ';'.join([
            "echo please",
            "echo answer",
            "read x",
            "echo $x",
        ])
        # question pattern uses hard space, should get replaced internally by more liberal whitespace regex pattern
        qa = [(r"please\ answer", "42")]
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, qa_patterns=qa, qa_timeout=3)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, "please\nanswer\n42\n")

        # test interactive command that takes a while before producing more output that includes second question
        cmd = ';'.join([
            "echo question1",
            "read answer1",
            "sleep 2",
            "echo question2",
            "read answer2",
            # note: delaying additional output (except the actual questions) is important
            # to verify that this is working as intended
            "echo $answer1",
            "echo $answer2",
        ])
        qa = [
            (r'question1', 'answer1'),
            (r'question2', 'answer2'),
        ]
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, qa_patterns=qa)

        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, "question1\nquestion2\nanswer1\nanswer2\n")

    def test_run_cmd_qa_buffering(self):
        """Test whether run_cmd_qa uses unbuffered output."""

        # use of run_cmd_qa is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        # command that generates a lot of output before waiting for input
        # note: bug being fixed can be reproduced reliably using 1000, but not with too high values like 100000!
        cmd = 'for x in $(seq 1000); do echo "This is a number you can pick: $x"; done; '
        cmd += 'echo "Pick a number: "; read number; echo "Picked number: $number"'
        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd_qa(cmd, {'Pick a number: ': '42'}, log_all=True, maxhits=5)

        self.assertEqual(ec, 0)
        regex = re.compile("Picked number: 42$")
        self.assertTrue(regex.search(out), "Pattern '%s' found in: %s" % (regex.pattern, out))

        # also test with script run as interactive command that quickly exits with non-zero exit code;
        # see https://github.com/easybuilders/easybuild-framework/issues/3593
        script_txt = '\n'.join([
            "#/bin/bash",
            "echo 'Hello, I am about to exit'",
            "echo 'ERROR: I failed' >&2",
            "exit 1",
        ])
        script = os.path.join(self.test_prefix, 'test.sh')
        write_file(script, script_txt)
        adjust_permissions(script, stat.S_IXUSR)

        with self.mocked_stdout_stderr():
            out, ec = run_cmd_qa(script, {}, log_ok=False)

        self.assertEqual(ec, 1)
        self.assertEqual(out, "Hello, I am about to exit\nERROR: I failed\n")

    def test_run_shell_cmd_qa_buffering(self):
        """Test whether run_shell_cmd uses unbuffered output when running interactive commands."""

        # command that generates a lot of output before waiting for input
        # note: bug being fixed can be reproduced reliably using 1000, but not with too high values like 100000!
        cmd = 'for x in $(seq 1000); do echo "This is a number you can pick: $x"; done; '
        cmd += 'echo "Pick a number: "; read number; echo "Picked number: $number"'
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, qa_patterns=[('Pick a number: ', '42')], qa_timeout=10)

        self.assertEqual(res.exit_code, 0)
        regex = re.compile("Picked number: 42$")
        self.assertTrue(regex.search(res.output), f"Pattern '{regex.pattern}' found in: {res.output}")

        # also test with script run as interactive command that quickly exits with non-zero exit code;
        # see https://github.com/easybuilders/easybuild-framework/issues/3593
        script_txt = '\n'.join([
            "#/bin/bash",
            "echo 'Hello, I am about to exit'",
            "echo 'ERROR: I failed' >&2",
            "exit 1",
        ])
        script = os.path.join(self.test_prefix, 'test.sh')
        write_file(script, script_txt)
        adjust_permissions(script, stat.S_IXUSR)

        with self.mocked_stdout_stderr():
            res = run_shell_cmd(script, qa_patterns=[], fail_on_error=False)

        self.assertEqual(res.exit_code, 1)
        self.assertEqual(res.output, "Hello, I am about to exit\nERROR: I failed\n")

    def test_run_cmd_qa_log_all(self):
        """Test run_cmd_qa with log_output enabled"""

        # use of run_cmd_qa is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd_qa("echo 'n: '; read n; seq 1 $n", {'n: ': '5'}, log_all=True)
        self.assertEqual(ec, 0)
        self.assertEqual(out, "n: \n1\n2\n3\n4\n5\n")

        run_cmd_logs = glob.glob(os.path.join(self.test_prefix, '*', 'easybuild-run_cmd_qa*.log'))
        self.assertEqual(len(run_cmd_logs), 1)
        run_cmd_log_txt = read_file(run_cmd_logs[0])
        extra_pref = "# output for interactive command: echo 'n: '; read n; seq 1 $n\n\n"
        self.assertEqual(run_cmd_log_txt, extra_pref + "n: \n1\n2\n3\n4\n5\n")

    def test_run_shell_cmd_qa_log(self):
        """Test temporary log file for run_shell_cmd with qa_patterns"""
        with self.mocked_stdout_stderr():
            res = run_shell_cmd("echo 'n: '; read n; seq 1 $n", qa_patterns=[('n:', '5')])
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, "n: \n1\n2\n3\n4\n5\n")

        run_cmd_logs = glob.glob(os.path.join(tempfile.gettempdir(), 'run-shell-cmd-output', 'echo-*', 'out.txt'))
        self.assertEqual(len(run_cmd_logs), 1)
        run_cmd_log_txt = read_file(run_cmd_logs[0])
        self.assertEqual(run_cmd_log_txt, "n: \n1\n2\n3\n4\n5\n")

    def test_run_cmd_qa_trace(self):
        """Test run_cmd under --trace"""

        # use of run_cmd/run_cmd_qa is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        # --trace is enabled by default
        self.mock_stdout(True)
        self.mock_stderr(True)
        (out, ec) = run_cmd_qa("echo 'n: '; read n; seq 1 $n", {'n: ': '5'})
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertTrue(stderr.strip().startswith("WARNING: Deprecated functionality"))
        pattern = r"^  >> running interactive command:\n"
        pattern += r"\t\[started at: .*\]\n"
        pattern += r"\t\[working dir: .*\]\n"
        pattern += r"\t\[output logged in .*\]\n"
        pattern += r"\techo \'n: \'; read n; seq 1 \$n\n"
        pattern += r'  >> interactive command completed: exit 0, ran in .*'
        self.assertTrue(re.search(pattern, stdout), "Pattern '%s' found in: %s" % (pattern, stdout))

        # trace output can be disabled on a per-command basis
        self.mock_stdout(True)
        self.mock_stderr(True)
        (out, ec) = run_cmd("echo hello", trace=False)
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(stdout, '')
        self.assertTrue(stderr.strip().startswith("WARNING: Deprecated functionality"))

    def test_run_shell_cmd_qa_trace(self):
        """Test run_shell_cmd with qa_patterns under --trace"""

        # --trace is enabled by default
        self.mock_stdout(True)
        self.mock_stderr(True)
        run_shell_cmd("echo 'n: '; read n; seq 1 $n", qa_patterns=[('n: ', '5')])
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(stderr, '')
        pattern = r"^  >> running interactive shell command:\n"
        pattern += r"\techo \'n: \'; read n; seq 1 \$n\n"
        pattern += r"\t\[started at: .*\]\n"
        pattern += r"\t\[working dir: .*\]\n"
        pattern += r"\t\[output and state saved to .*\]\n"
        pattern += r'  >> command completed: exit 0, ran in .*'
        self.assertTrue(re.search(pattern, stdout), "Pattern '%s' found in: %s" % (pattern, stdout))

        # trace output can be disabled on a per-command basis
        self.mock_stdout(True)
        self.mock_stderr(True)
        run_shell_cmd("echo 'n: '; read n; seq 1 $n", qa_patterns=[('n: ', '5')], hidden=True)
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(stdout, '')
        self.assertEqual(stderr, '')

    def test_run_cmd_qa_answers(self):
        """Test providing list of answers in run_cmd_qa."""

        # use of run_cmd_qa is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        cmd = "echo question; read x; echo $x; " * 2
        qa = {"question": ["answer1", "answer2"]}

        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd_qa(cmd, qa)
        self.assertEqual(out, "question\nanswer1\nquestion\nanswer2\n")
        self.assertEqual(ec, 0)

        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd_qa(cmd, {}, std_qa=qa)
        self.assertEqual(out, "question\nanswer1\nquestion\nanswer2\n")
        self.assertEqual(ec, 0)

        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, "Invalid type for answer", run_cmd_qa, cmd, {'q': 1})

        # test cycling of answers
        cmd = cmd * 2
        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd_qa(cmd, {}, std_qa=qa)
        self.assertEqual(out, "question\nanswer1\nquestion\nanswer2\n" * 2)
        self.assertEqual(ec, 0)

    def test_run_shell_cmd_qa_answers(self):
        """Test providing list of answers for a question in run_shell_cmd."""

        cmd = "echo question; read x; echo $x; " * 2
        qa = [("question", ["answer1", "answer2"])]

        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, qa_patterns=qa)
        self.assertEqual(res.output, "question\nanswer1\nquestion\nanswer2\n")
        self.assertEqual(res.exit_code, 0)

        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, "Unknown type of answers encountered", run_shell_cmd, cmd,
                                  qa_patterns=[('question', 1)])

        # test cycling of answers
        cmd = cmd * 2
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, qa_patterns=qa)
        self.assertEqual(res.output, "question\nanswer1\nquestion\nanswer2\n" * 2)
        self.assertEqual(res.exit_code, 0)

    def test_run_cmd_simple(self):
        """Test return value for run_cmd in 'simple' mode."""

        # use of run_cmd is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        with self.mocked_stdout_stderr():
            self.assertEqual(True, run_cmd("echo hello", simple=True))
            self.assertEqual(False, run_cmd("exit 1", simple=True, log_all=False, log_ok=False))

    def test_run_cmd_cache(self):
        """Test caching for run_cmd"""

        # use of run_cmd is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        with self.mocked_stdout_stderr():
            (first_out, ec) = run_cmd("ulimit -u")
        self.assertEqual(ec, 0)
        with self.mocked_stdout_stderr():
            (cached_out, ec) = run_cmd("ulimit -u")
        self.assertEqual(ec, 0)
        self.assertEqual(first_out, cached_out)

        # inject value into cache to check whether executing command again really returns cached value
        with self.mocked_stdout_stderr():
            run_cmd.update_cache({("ulimit -u", None): ("123456", 123)})
            (cached_out, ec) = run_cmd("ulimit -u")
        self.assertEqual(ec, 123)
        self.assertEqual(cached_out, "123456")

        # also test with command that uses stdin
        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd("cat", inp='foo')
        self.assertEqual(ec, 0)
        self.assertEqual(out, 'foo')

        # inject different output for cat with 'foo' as stdin to check whether cached value is used
        with self.mocked_stdout_stderr():
            run_cmd.update_cache({('cat', 'foo'): ('bar', 123)})
            (cached_out, ec) = run_cmd("cat", inp='foo')
        self.assertEqual(ec, 123)
        self.assertEqual(cached_out, 'bar')

        run_cmd.clear_cache()

    def test_run_shell_cmd_cache(self):
        """Test caching for run_shell_cmd function"""

        cmd = "ulimit -u"
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd)
            first_out = res.output
        self.assertEqual(res.exit_code, 0)

        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd)
            cached_out = res.output
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(first_out, cached_out)

        # inject value into cache to check whether executing command again really returns cached value
        with self.mocked_stdout_stderr():
            cached_res = RunShellCmdResult(cmd=cmd, output="123456", exit_code=123, stderr=None,
                                           work_dir='/test_ulimit', out_file='/tmp/foo.out', err_file=None,
                                           cmd_sh='/tmp/cmd.sh', thread_id=None, task_id=None)
            run_shell_cmd.update_cache({(cmd, None): cached_res})
            res = run_shell_cmd(cmd)
        self.assertEqual(res.cmd, cmd)
        self.assertEqual(res.exit_code, 123)
        self.assertEqual(res.output, "123456")
        self.assertEqual(res.stderr, None)
        self.assertEqual(res.work_dir, '/test_ulimit')

        # also test with command that uses stdin
        cmd = "cat"
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, stdin='foo')
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, 'foo')

        # inject different output for cat with 'foo' as stdin to check whether cached value is used
        with self.mocked_stdout_stderr():
            cached_res = RunShellCmdResult(cmd=cmd, output="bar", exit_code=123, stderr=None,
                                           work_dir='/test_cat', out_file='/tmp/cat.out', err_file=None,
                                           cmd_sh='/tmp/cmd.sh', thread_id=None, task_id=None)
            run_shell_cmd.update_cache({(cmd, 'foo'): cached_res})
            res = run_shell_cmd(cmd, stdin='foo')
        self.assertEqual(res.cmd, cmd)
        self.assertEqual(res.exit_code, 123)
        self.assertEqual(res.output, 'bar')
        self.assertEqual(res.stderr, None)
        self.assertEqual(res.work_dir, '/test_cat')

        run_shell_cmd.clear_cache()

    def test_parse_log_error(self):
        """Test basic parse_log_for_error functionality."""

        # use of parse_log_for_error is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        with self.mocked_stdout_stderr():
            errors = parse_log_for_error("error failed", True)
        self.assertEqual(len(errors), 1)

    def test_run_cmd_dry_run(self):
        """Test use of run_cmd function under (extended) dry run."""

        # use of run_cmd is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        build_options = {
            'extended_dry_run': True,
            'silent': False,
        }
        init_config(build_options=build_options)

        cmd = "somecommand foo 123 bar"

        with self.mocked_stdout_stderr():
            run_cmd(cmd)
            stdout = self.get_stdout()

        expected = """  running command "somecommand foo 123 bar"\n"""
        self.assertIn(expected, stdout)

        # check disabling 'verbose'
        with self.mocked_stdout_stderr():
            run_cmd("somecommand foo 123 bar", verbose=False)
            stdout = self.get_stdout()
        self.assertNotIn(expected, stdout)

        # check forced run_cmd
        outfile = os.path.join(self.test_prefix, 'cmd.out')
        self.assertNotExists(outfile)
        with self.mocked_stdout_stderr():
            run_cmd("echo 'This is always echoed' > %s" % outfile, force_in_dry_run=True)
        self.assertExists(outfile)
        self.assertEqual(read_file(outfile), "This is always echoed\n")

        # Q&A commands
        with self.mocked_stdout_stderr():
            run_shell_cmd("some_qa_cmd", qa_patterns=[('question1', 'answer1')])
            stdout = self.get_stdout()

        expected = """  running interactive shell command "some_qa_cmd"\n"""
        self.assertIn(expected, stdout)

        with self.mocked_stdout_stderr():
            run_cmd_qa("some_qa_cmd", {'question1': 'answer1'})
            stdout = self.get_stdout()

        expected = """  running interactive command "some_qa_cmd"\n"""
        self.assertIn(expected, stdout)

    def test_run_shell_cmd_dry_run(self):
        """Test use of run_shell_cmd function under (extended) dry run."""
        build_options = {
            'extended_dry_run': True,
            'silent': False,
        }
        init_config(build_options=build_options)

        cmd = "somecommand foo 123 bar"

        self.mock_stdout(True)
        res = run_shell_cmd(cmd)
        stdout = self.get_stdout()
        self.mock_stdout(False)
        # fake output/exit code is returned for commands not actually run in dry run mode
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, '')
        self.assertEqual(res.stderr, None)
        # check dry run output
        expected = """  running shell command "somecommand foo 123 bar"\n"""
        self.assertIn(expected, stdout)

        # check enabling 'hidden'
        self.mock_stdout(True)
        res = run_shell_cmd(cmd, hidden=True)
        stdout = self.get_stdout()
        self.mock_stdout(False)
        # fake output/exit code is returned for commands not actually run in dry run mode
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, '')
        self.assertEqual(res.stderr, None)
        # dry run output should be missing
        self.assertNotIn(expected, stdout)

        # check forced run_cmd
        outfile = os.path.join(self.test_prefix, 'cmd.out')
        self.assertNotExists(outfile)
        self.mock_stdout(True)
        res = run_shell_cmd("echo 'This is always echoed' > %s; echo done; false" % outfile,
                            fail_on_error=False, in_dry_run=True)
        stdout = self.get_stdout()
        self.mock_stdout(False)
        self.assertNotIn('running shell command "', stdout)
        self.assertNotEqual(res.exit_code, 0)
        self.assertEqual(res.output, 'done\n')
        self.assertEqual(res.stderr, None)
        self.assertExists(outfile)
        self.assertEqual(read_file(outfile), "This is always echoed\n")

    def test_run_cmd_list(self):
        """Test run_cmd with command specified as a list rather than a string"""

        # use of run_cmd is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        cmd = ['/bin/sh', '-c', "echo hello"]
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, "When passing cmd as a list then `shell` must be set explictely!",
                                  run_cmd, cmd)
            (out, ec) = run_cmd(cmd, shell=False)
        self.assertEqual(out, "hello\n")
        # no reason echo hello could fail
        self.assertEqual(ec, 0)

    def test_run_cmd_script(self):
        """Testing use of run_cmd with shell=False to call external scripts"""

        # use of run_cmd is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        py_test_script = os.path.join(self.test_prefix, 'test.py')
        write_file(py_test_script, '\n'.join([
            '#!%s' % sys.executable,
            'print("hello")',
        ]))
        adjust_permissions(py_test_script, stat.S_IXUSR)

        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd(py_test_script)
        self.assertEqual(ec, 0)
        self.assertEqual(out, "hello\n")

        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd([py_test_script], shell=False)
        self.assertEqual(ec, 0)
        self.assertEqual(out, "hello\n")

    def test_run_shell_cmd_no_bash(self):
        """Testing use of run_shell_cmd with use_bash=False to call external scripts"""
        py_test_script = os.path.join(self.test_prefix, 'test.py')
        write_file(py_test_script, '\n'.join([
            '#!%s' % sys.executable,
            'print("hello")',
        ]))
        adjust_permissions(py_test_script, stat.S_IXUSR)

        with self.mocked_stdout_stderr():
            res = run_shell_cmd(py_test_script)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, "hello\n")

        with self.mocked_stdout_stderr():
            res = run_shell_cmd([py_test_script], use_bash=False)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, "hello\n")

    def test_run_cmd_stream(self):
        """Test use of run_cmd with streaming output."""

        # use of run_cmd is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        self.mock_stdout(True)
        self.mock_stderr(True)
        (out, ec) = run_cmd("echo hello", stream_output=True)
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)

        self.assertEqual(ec, 0)
        self.assertEqual(out, "hello\n")

        self.assertTrue(stderr.strip().startswith("WARNING: Deprecated functionality"))
        expected = [
            "== (streaming) output for command 'echo hello':",
            "hello",
            '',
        ]
        for line in expected:
            self.assertIn(line, stdout)

    def test_run_shell_cmd_stream(self):
        """Test use of run_shell_cmd with streaming output."""
        self.mock_stdout(True)
        self.mock_stderr(True)
        cmd = '; '.join([
            "echo hello there",
            "sleep 1",
            "echo testing command that produces a fair amount of output",
            "sleep 1",
            "echo more than 128 bytes which means a whole bunch of characters...",
            "sleep 1",
            "echo more than 128 characters in fact, which is quite a bit when you think of it",
        ])
        res = run_shell_cmd(cmd, stream_output=True)
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)

        expected_output = '\n'.join([
            "hello there",
            "testing command that produces a fair amount of output",
            "more than 128 bytes which means a whole bunch of characters...",
            "more than 128 characters in fact, which is quite a bit when you think of it",
            '',
        ])
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, expected_output)

        self.assertEqual(stderr, '')
        expected = ("running shell command:\n\techo hello" + '\n' + expected_output).split('\n')
        for line in expected:
            self.assertIn(line, stdout)

    def test_run_shell_cmd_eof_stdin(self):
        """Test use of run_shell_cmd with streaming output and blocking stdin read."""
        cmd = 'timeout 1 cat -'

        inp = 'hello\nworld\n'
        # test with streaming output
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, stream_output=True, stdin=inp, fail_on_error=False)

        self.assertEqual(res.exit_code, 0, "Streaming output: Command timed out")
        self.assertEqual(res.output, inp)

        # test with non-streaming output (proc.communicate() is used)
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd, stdin=inp, fail_on_error=False)

        self.assertEqual(res.exit_code, 0, "Non-streaming output: Command timed out")
        self.assertEqual(res.output, inp)

    def test_run_cmd_async(self):
        """Test asynchronously running of a shell command via run_cmd + complete_cmd."""

        # use of run_cmd/check_async_cmd/get_output_from_process is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        os.environ['TEST'] = 'test123'

        test_cmd = "echo 'sleeping...'; sleep 2; echo $TEST"
        with self.mocked_stdout_stderr():
            cmd_info = run_cmd(test_cmd, asynchronous=True)
        proc = cmd_info[0]

        # change value of $TEST to check that command is completed with correct environment
        os.environ['TEST'] = 'some_other_value'

        # initial poll should result in None, since it takes a while for the command to complete
        ec = proc.poll()
        self.assertEqual(ec, None)

        # wait until command is done
        while ec is None:
            time.sleep(1)
            ec = proc.poll()

        with self.mocked_stdout_stderr():
            out, ec = complete_cmd(*cmd_info, simple=False)
        self.assertEqual(ec, 0)
        self.assertEqual(out, 'sleeping...\ntest123\n')

        # also test use of check_async_cmd function
        os.environ['TEST'] = 'test123'
        with self.mocked_stdout_stderr():
            cmd_info = run_cmd(test_cmd, asynchronous=True)

        # first check, only read first 12 output characters
        # (otherwise we'll be waiting until command is completed)
        with self.mocked_stdout_stderr():
            res = check_async_cmd(*cmd_info, output_read_size=12)
        self.assertEqual(res, {'done': False, 'exit_code': None, 'output': 'sleeping...\n'})

        # 2nd check with default output size (1024) gets full output
        # (keep checking until command is fully done)
        with self.mocked_stdout_stderr():
            while not res['done']:
                res = check_async_cmd(*cmd_info, output=res['output'])
        self.assertEqual(res, {'done': True, 'exit_code': 0, 'output': 'sleeping...\ntest123\n'})

        # check asynchronous running of failing command
        error_test_cmd = "echo 'FAIL!' >&2; exit 123"
        with self.mocked_stdout_stderr():
            cmd_info = run_cmd(error_test_cmd, asynchronous=True)
        time.sleep(1)
        error_pattern = 'cmd ".*" exited with exit code 123'
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, check_async_cmd, *cmd_info)

        with self.mocked_stdout_stderr():
            cmd_info = run_cmd(error_test_cmd, asynchronous=True)
            res = check_async_cmd(*cmd_info, fail_on_error=False)
        # keep checking until command is fully done
        with self.mocked_stdout_stderr():
            while not res['done']:
                res = check_async_cmd(*cmd_info, fail_on_error=False, output=res['output'])
        self.assertEqual(res, {'done': True, 'exit_code': 123, 'output': "FAIL!\n"})

        # also test with a command that produces a lot of output,
        # since that tends to lock up things unless we frequently grab some output...
        verbose_test_cmd = ';'.join([
            "echo start",
            "for i in $(seq 1 50)",
            "do sleep 0.1",
            "for j in $(seq 1000)",
            "do echo foo${i}${j}",
            "done",
            "done",
            "echo done",
        ])
        with self.mocked_stdout_stderr():
            cmd_info = run_cmd(verbose_test_cmd, asynchronous=True)
        proc = cmd_info[0]

        output = ''
        ec = proc.poll()
        self.assertEqual(ec, None)

        with self.mocked_stdout_stderr():
            while ec is None:
                time.sleep(1)
                output += get_output_from_process(proc)
                ec = proc.poll()

        with self.mocked_stdout_stderr():
            out, ec = complete_cmd(*cmd_info, simple=False, output=output)
        self.assertEqual(ec, 0)
        self.assertTrue(out.startswith('start\n'))
        self.assertTrue(out.endswith('\ndone\n'))

        # also test use of check_async_cmd on verbose test command
        with self.mocked_stdout_stderr():
            cmd_info = run_cmd(verbose_test_cmd, asynchronous=True)

        error_pattern = r"Number of output bytes to read should be a positive integer value \(or zero\)"
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, check_async_cmd, *cmd_info, output_read_size=-1)
            self.assertErrorRegex(EasyBuildError, error_pattern, check_async_cmd, *cmd_info, output_read_size='foo')

        # with output_read_size set to 0, no output is read yet, only status of command is checked
        with self.mocked_stdout_stderr():
            res = check_async_cmd(*cmd_info, output_read_size=0)
        self.assertEqual(res['done'], False)
        self.assertEqual(res['exit_code'], None)
        self.assertEqual(res['output'], '')

        with self.mocked_stdout_stderr():
            res = check_async_cmd(*cmd_info)
        self.assertEqual(res['done'], False)
        self.assertEqual(res['exit_code'], None)
        self.assertTrue(res['output'].startswith('start\n'))
        self.assertFalse(res['output'].endswith('\ndone\n'))
        # keep checking until command is complete
        with self.mocked_stdout_stderr():
            while not res['done']:
                res = check_async_cmd(*cmd_info, output=res['output'])
        self.assertEqual(res['done'], True)
        self.assertEqual(res['exit_code'], 0)
        self.assertEqual(len(res['output']), 435661)
        self.assertTrue(res['output'].startswith('start\nfoo11\nfoo12\n'))
        self.assertTrue('\nfoo49999\nfoo491000\nfoo501\n' in res['output'])
        self.assertTrue(res['output'].endswith('\nfoo501000\ndone\n'))

    def test_run_shell_cmd_async(self):
        """Test asynchronously running of a shell command via run_shell_cmd """

        thread_pool = ThreadPoolExecutor()

        os.environ['TEST'] = 'test123'
        env = os.environ.copy()

        test_cmd = "echo 'sleeping...'; sleep 2; echo $TEST"
        task = thread_pool.submit(run_shell_cmd, test_cmd, hidden=True, asynchronous=True, env=env)

        # change value of $TEST to check that command is completed with correct environment
        os.environ['TEST'] = 'some_other_value'

        # initial poll should result in None, since it takes a while for the command to complete
        self.assertEqual(task.done(), False)

        # wait until command is done
        while not task.done():
            time.sleep(1)
            res = task.result()

        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, 'sleeping...\ntest123\n')

        # check asynchronous running of failing command
        error_test_cmd = "echo 'FAIL!' >&2; exit 123"
        task = thread_pool.submit(run_shell_cmd, error_test_cmd, hidden=True, fail_on_error=False, asynchronous=True)
        time.sleep(1)
        res = task.result()
        self.assertEqual(res.exit_code, 123)
        self.assertEqual(res.output, "FAIL!\n")
        self.assertTrue(res.thread_id)

        # also test with a command that produces a lot of output,
        # since that tends to lock up things unless we frequently grab some output...
        verbose_test_cmd = ';'.join([
            "echo start",
            "for i in $(seq 1 50)",
            "do sleep 0.1",
            "for j in $(seq 1000)",
            "do echo foo${i}${j}",
            "done",
            "done",
            "echo done",
        ])
        task = thread_pool.submit(run_shell_cmd, verbose_test_cmd, hidden=True, asynchronous=True)

        while not task.done():
            time.sleep(1)
        res = task.result()

        self.assertEqual(res.exit_code, 0)
        self.assertEqual(len(res.output), 435661)
        self.assertTrue(res.output.startswith('start\nfoo11\nfoo12\n'))
        self.assertTrue('\nfoo49999\nfoo491000\nfoo501\n' in res.output)
        self.assertTrue(res.output.endswith('\nfoo501000\ndone\n'))

    def test_check_log_for_errors(self):
        """Test for check_log_for_errors"""

        # use of check_log_for_errors is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        fd, logfile = tempfile.mkstemp(suffix='.log', prefix='eb-test-')
        os.close(fd)

        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, "Invalid input:", check_log_for_errors, "", [42])
            self.assertErrorRegex(EasyBuildError, "Invalid input:", check_log_for_errors, "", [(42, IGNORE)])
            self.assertErrorRegex(EasyBuildError, "Invalid input:", check_log_for_errors, "", [("42", "invalid-mode")])
            self.assertErrorRegex(EasyBuildError, "Invalid input:", check_log_for_errors, "", [("42", IGNORE, "")])

        input_text = "\n".join([
            "OK",
            "error found",
            "test failed",
            "msg: allowed-test failed",
            "enabling -Werror",
            "the process crashed with 0"
        ])
        expected_msg = r"Found 2 error\(s\) in command output:\n"\
                       r"\terror found\n"\
                       r"\tthe process crashed with 0"

        # String promoted to list
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, expected_msg, check_log_for_errors, input_text,
                                  r"\b(error|crashed)\b")
        # List of string(s)
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, expected_msg, check_log_for_errors, input_text,
                                  [r"\b(error|crashed)\b"])
        # List of tuple(s)
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, expected_msg, check_log_for_errors, input_text,
                                  [(r"\b(error|crashed)\b", ERROR)])

        expected_msg = "Found 2 potential error(s) in command output:\n"\
                       "\terror found\n"\
                       "\tthe process crashed with 0"
        init_logging(logfile, silent=True)
        with self.mocked_stdout_stderr():
            check_log_for_errors(input_text, [(r"\b(error|crashed)\b", WARN)])
        stop_logging(logfile)
        self.assertIn(expected_msg, read_file(logfile))

        expected_msg = r"Found 2 error\(s\) in command output:\n"\
                       r"\terror found\n"\
                       r"\ttest failed"
        write_file(logfile, '')
        init_logging(logfile, silent=True)
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, expected_msg, check_log_for_errors, input_text, [
                r"\berror\b",
                (r"\ballowed-test failed\b", IGNORE),
                (r"(?i)\bCRASHED\b", WARN),
                "fail"
            ])
        stop_logging(logfile)
        expected_msg = "Found 1 potential error(s) in command output:\n\tthe process crashed with 0"
        self.assertIn(expected_msg, read_file(logfile))

    def test_run_cmd_with_hooks(self):
        """
        Test running command with run_cmd with pre/post run_shell_cmd hooks in place.
        """

        # use of run_cmd/run_cmd_qa is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        cwd = os.getcwd()

        hooks_file = os.path.join(self.test_prefix, 'my_hooks.py')
        hooks_file_txt = textwrap.dedent("""
            def pre_run_shell_cmd_hook(cmd, *args, **kwargs):
                work_dir = kwargs['work_dir']
                if kwargs.get('interactive'):
                    print("pre-run hook interactive '%s' in %s" % (cmd, work_dir))
                else:
                    print("pre-run hook '%s' in %s" % (cmd, work_dir))
                if not cmd.startswith('echo'):
                    cmds = cmd.split(';')
                    return '; '.join(cmds[:-1] + ["echo " + cmds[-1].lstrip()])

            def post_run_shell_cmd_hook(cmd, *args, **kwargs):
                exit_code = kwargs.get('exit_code')
                output = kwargs.get('output')
                work_dir = kwargs['work_dir']
                if kwargs.get('interactive'):
                    msg = "post-run hook interactive '%s'" % cmd
                else:
                    msg = "post-run hook '%s'" % cmd
                msg += " (exit code: %s, output: '%s')" % (exit_code, output)
                print(msg)
        """)
        write_file(hooks_file, hooks_file_txt)
        update_build_option('hooks', hooks_file)

        # disable trace output to make checking of generated output produced by hooks easier
        update_build_option('trace', False)

        with self.mocked_stdout_stderr():
            run_cmd("make")
            stdout = self.get_stdout()

        expected_stdout = '\n'.join([
            "pre-run hook 'make' in %s" % cwd,
            "post-run hook 'echo make' (exit code: 0, output: 'make\n')",
            '',
        ])
        self.assertEqual(stdout, expected_stdout)

        with self.mocked_stdout_stderr():
            run_shell_cmd("sleep 2; make", qa_patterns=[('q', 'a')])
            stdout = self.get_stdout()

        expected_stdout = '\n'.join([
            "pre-run hook interactive 'sleep 2; make' in %s" % cwd,
            "post-run hook interactive 'sleep 2; echo make' (exit code: 0, output: 'make\n')",
            '',
        ])
        self.assertEqual(stdout, expected_stdout)

        with self.mocked_stdout_stderr():
            run_cmd_qa("sleep 2; make", qa={})
            stdout = self.get_stdout()

        expected_stdout = '\n'.join([
            "pre-run hook interactive 'sleep 2; make' in %s" % cwd,
            "post-run hook interactive 'sleep 2; echo make' (exit code: 0, output: 'make\n')",
            '',
        ])
        self.assertEqual(stdout, expected_stdout)

    def test_run_shell_cmd_with_hooks(self):
        """
        Test running shell command with run_shell_cmd function with pre/post run_shell_cmd hooks in place.
        """
        cwd = os.getcwd()

        hooks_file = os.path.join(self.test_prefix, 'my_hooks.py')
        hooks_file_txt = textwrap.dedent("""
            def pre_run_shell_cmd_hook(cmd, *args, **kwargs):
                work_dir = kwargs['work_dir']
                if kwargs.get('interactive'):
                    print("pre-run hook interactive '||%s||' in %s" % (cmd, work_dir))
                else:
                    print("pre-run hook '%s' in %s" % (cmd, work_dir))
                    import sys
                    sys.stderr.write('pre-run hook done\\n')
                print("command is allowed to fail: %s" % kwargs.get('fail_on_error', 'NOT AVAILABLE'))
                print("command is hidden: %s" % kwargs.get('hidden', 'NOT AVAILABLE'))
                if cmd != 'false' and not cmd.startswith('echo'):
                    cmds = cmd.split(';')
                    return '; '.join(cmds[:-1] + ["echo " + cmds[-1].lstrip()])

            def post_run_shell_cmd_hook(cmd, *args, **kwargs):
                exit_code = kwargs.get('exit_code')
                output = kwargs.get('output')
                work_dir = kwargs['work_dir']
                if kwargs.get('interactive'):
                    msg = "post-run hook interactive '%s'" % cmd
                else:
                    msg = "post-run hook '%s'" % cmd
                msg += " (exit code: %s, output: '%s')" % (exit_code, output)
                msg += "\\ncommand was allowed to fail: %s" % kwargs.get('fail_on_error', 'NOT AVAILABLE')
                msg += "\\ncommand was hidden: %s" % kwargs.get('hidden', 'NOT AVAILABLE')
                print(msg)
        """)
        write_file(hooks_file, hooks_file_txt)
        update_build_option('hooks', hooks_file)

        # disable trace output to make checking of generated output produced by hooks easier
        update_build_option('trace', False)

        with self.mocked_stdout_stderr():
            run_shell_cmd("make")
            stdout = self.get_stdout()

        expected_stdout = '\n'.join([
            f"pre-run hook 'make' in {cwd}",
            "command is allowed to fail: True",
            "command is hidden: False",
            "post-run hook 'echo make' (exit code: 0, output: 'make\n')",
            "command was allowed to fail: True",
            "command was hidden: False",
            '',
        ])
        self.assertEqual(stdout, expected_stdout)

        # also check in dry run mode, to verify that pre-run_shell_cmd hook is triggered sufficiently early
        update_build_option('extended_dry_run', True)

        with self.mocked_stdout_stderr():
            run_shell_cmd("make")
            stdout = self.get_stdout()

        expected_stdout = '\n'.join([
            "pre-run hook 'make' in %s" % cwd,
            "command is allowed to fail: True",
            "command is hidden: False",
            '  running shell command "echo make"',
            '  (in %s)' % cwd,
            '',
        ])
        self.assertEqual(stdout, expected_stdout)

        # also check with trace output enabled
        update_build_option('extended_dry_run', False)
        update_build_option('trace', True)

        with self.mocked_stdout_stderr():
            run_shell_cmd("make")
            stdout = self.get_stdout()

        regex = re.compile('>> running shell command:\n\techo make', re.M)
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        with self.mocked_stdout_stderr():
            # run_shell_cmd will raise RunShellCmdError which we don't care about here,
            # we just want to verify that the post_run_shell_cmd_hook has run
            try:
                run_shell_cmd("false")
            except RunShellCmdError:
                pass
            stdout = self.get_stdout()

        expected_end = '\n'.join([
            '',
            "post-run hook 'false' (exit code: 1, output: '')",
            "command was allowed to fail: True",
            "command was hidden: False",
            '',
        ])
        self.assertTrue(stdout.endswith(expected_end), f"Stdout should end with '{expected_end}': {stdout}")

    def test_run_shell_cmd_delete_cwd(self):
        """
        Test commands that destroy directories inside initial working directory
        """
        workdir = os.path.join(self.test_prefix, 'workdir')
        sub_workdir = os.path.join(workdir, 'subworkdir')

        # 1. test destruction of CWD which is a subdirectory inside original working directory
        cmd_subworkdir_rm = (
            "echo 'Command that jumps to subdir and removes it' && "
            f"cd {sub_workdir} && pwd && rm -rf {sub_workdir} && "
            "echo 'Working sub-directory removed.'"
        )

        # 1.a. in a robust system
        expected_output = (
            "Command that jumps to subdir and removes it\n"
            f"{sub_workdir}\n"
            "Working sub-directory removed.\n"
        )

        mkdir(sub_workdir, parents=True)
        with self.mocked_stdout_stderr():
            res = run_shell_cmd(cmd_subworkdir_rm, work_dir=workdir)

        self.assertEqual(res.cmd, cmd_subworkdir_rm)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, expected_output)
        self.assertEqual(res.stderr, None)
        self.assertEqual(res.work_dir, workdir)

        # 1.b. in a flaky system that ends up in an unknown CWD after execution
        mkdir(sub_workdir, parents=True)
        fd, logfile = tempfile.mkstemp(suffix='.log', prefix='eb-test-')
        os.close(fd)

        with self.mocked_stdout_stderr():
            with mock.patch('os.getcwd') as mock_getcwd:
                mock_getcwd.side_effect = [
                    workdir,
                    FileNotFoundError(),
                ]
                init_logging(logfile, silent=True)
                res = run_shell_cmd(cmd_subworkdir_rm, work_dir=workdir)
                stop_logging(logfile)

        self.assertEqual(res.cmd, cmd_subworkdir_rm)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.output, expected_output)
        self.assertEqual(res.stderr, None)
        self.assertEqual(res.work_dir, workdir)

        expected_warning = f"Changing back to initial working directory: {workdir}\n"
        logtxt = read_file(logfile)
        self.assertTrue(logtxt.endswith(expected_warning))

        # 2. test destruction of CWD which is main working directory passed to run_shell_cmd
        cmd_workdir_rm = (
            "echo 'Command that removes working directory' && pwd && "
            f"rm -rf {workdir} && echo 'Working directory removed.'"
        )

        error_pattern = rf"Failed to return to .*/{os.path.basename(self.test_prefix)}/workdir after executing command"

        mkdir(workdir, parents=True)
        with self.mocked_stdout_stderr():
            self.assertErrorRegex(EasyBuildError, error_pattern, run_shell_cmd, cmd_workdir_rm, work_dir=workdir)

    def test_run_cmd_sysroot(self):
        """Test with_sysroot option of run_cmd function."""

        # use of run_cmd/run_cmd_qa is deprecated, so we need to allow it here
        self.allow_deprecated_behaviour()

        # put fake /bin/bash in place that will be picked up when using run_cmd with with_sysroot=True
        bin_bash = os.path.join(self.test_prefix, 'bin', 'bash')
        bin_bash_txt = '\n'.join([
            "#!/bin/bash",
            "echo 'Hi there I am a fake /bin/bash in %s'" % self.test_prefix,
            '/bin/bash "$@"',
        ])
        write_file(bin_bash, bin_bash_txt)
        adjust_permissions(bin_bash, stat.S_IXUSR)

        update_build_option('sysroot', self.test_prefix)

        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd("echo hello")
        self.assertEqual(ec, 0)
        self.assertTrue(out.startswith("Hi there I am a fake /bin/bash in"))
        self.assertTrue(out.endswith("\nhello\n"))

        # picking up on alternate sysroot is enabled by default, but can be disabled via with_sysroot=False
        with self.mocked_stdout_stderr():
            (out, ec) = run_cmd("echo hello", with_sysroot=False)
        self.assertEqual(ec, 0)
        self.assertEqual(out, "hello\n")


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(RunTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
