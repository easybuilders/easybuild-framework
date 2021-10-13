# #
# -*- coding: utf-8 -*-
# Copyright 2012-2021 Ghent University
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
Unit tests for filetools.py

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""
import glob
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner
from easybuild.base.fancylogger import setLogLevelDebug

import easybuild.tools.asyncprocess as asyncprocess
import easybuild.tools.utilities
from easybuild.tools.build_log import EasyBuildError, init_logging, stop_logging
from easybuild.tools.filetools import adjust_permissions, read_file, write_file
from easybuild.tools.run import check_log_for_errors, complete_cmd, get_output_from_process
from easybuild.tools.run import parse_log_for_error, run_cmd, run_cmd_qa
from easybuild.tools.config import ERROR, IGNORE, WARN


class RunTest(EnhancedTestCase):
    """ Testcase for run module """

    def setUp(self):
        """Set up test."""
        super(RunTest, self).setUp()
        self.orig_experimental = easybuild.tools.utilities._log.experimental

    def tearDown(self):
        """Test cleanup."""
        super(RunTest, self).tearDown()

        # restore log.experimental
        easybuild.tools.utilities._log.experimental = self.orig_experimental

    def test_get_output_from_process(self):
        """Test for get_output_from_process utility function."""

        def get_proc(cmd, asynchronous=False):
            if asynchronous:
                proc = asyncprocess.Popen(cmd, shell=True, stdout=asyncprocess.PIPE, stderr=asyncprocess.STDOUT,
                                          stdin=asyncprocess.PIPE, close_fds=True, executable='/bin/bash')
            else:
                proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        stdin=subprocess.PIPE, close_fds=True, executable='/bin/bash')

            return proc

        # get all output at once
        proc = get_proc("echo hello")
        out = get_output_from_process(proc)
        self.assertEqual(out, 'hello\n')

        # first get 100 bytes, then get the rest all at once
        proc = get_proc("echo hello")
        out = get_output_from_process(proc, read_size=100)
        self.assertEqual(out, 'hello\n')
        out = get_output_from_process(proc)
        self.assertEqual(out, '')

        # get output in small bits, keep trying to get output (which shouldn't fail)
        proc = get_proc("echo hello")
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

        proc = get_proc(async_cmd, asynchronous=True)
        out = get_output_from_process(proc, asynchronous=True)
        self.assertEqual(out, 'hello\n')
        asyncprocess.send_all(proc, 'test123\n')
        out = get_output_from_process(proc)
        self.assertEqual(out, 'test123\n')

        proc = get_proc(async_cmd, asynchronous=True)
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
        (out, ec) = run_cmd("echo hello")
        self.assertEqual(out, "hello\n")
        # no reason echo hello could fail
        self.assertEqual(ec, 0)
        self.assertEqual(type(out), str)

        # test running command that emits non-UTF-8 characters
        # this is constructed to reproduce errors like:
        # UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe2
        # UnicodeEncodeError: 'ascii' codec can't encode character u'\u2018'
        for text in [b"foo \xe2 bar", b"foo \u2018 bar"]:
            test_file = os.path.join(self.test_prefix, 'foo.txt')
            write_file(test_file, text)
            cmd = "cat %s" % test_file

            (out, ec) = run_cmd(cmd)
            self.assertEqual(ec, 0)
            self.assertTrue(out.startswith('foo ') and out.endswith(' bar'))
            self.assertEqual(type(out), str)

    def test_run_cmd_log(self):
        """Test logging of executed commands."""
        fd, logfile = tempfile.mkstemp(suffix='.log', prefix='eb-test-')
        os.close(fd)

        regex = re.compile('cmd "echo hello" exited with exit code [0-9]* and output:')

        # command output is not logged by default without debug logging
        init_logging(logfile, silent=True)
        self.assertTrue(run_cmd("echo hello"))
        stop_logging(logfile)
        self.assertEqual(len(regex.findall(read_file(logfile))), 0)
        write_file(logfile, '')

        init_logging(logfile, silent=True)
        self.assertTrue(run_cmd("echo hello", log_all=True))
        stop_logging(logfile)
        self.assertEqual(len(regex.findall(read_file(logfile))), 1)
        write_file(logfile, '')

        # with debugging enabled, exit code and output of command should only get logged once
        setLogLevelDebug()

        init_logging(logfile, silent=True)
        self.assertTrue(run_cmd("echo hello"))
        stop_logging(logfile)
        self.assertEqual(len(regex.findall(read_file(logfile))), 1)
        write_file(logfile, '')

        init_logging(logfile, silent=True)
        self.assertTrue(run_cmd("echo hello", log_all=True))
        stop_logging(logfile)
        self.assertEqual(len(regex.findall(read_file(logfile))), 1)
        write_file(logfile, '')

        # Test that we can set the directory for the logfile
        log_path = os.path.join(self.test_prefix, 'chicken')
        os.mkdir(log_path)
        logfile = None
        init_logging(logfile, silent=True, tmp_logdir=log_path)
        logfiles = os.listdir(log_path)
        self.assertEqual(len(logfiles), 1)
        self.assertTrue(logfiles[0].startswith("easybuild"))
        self.assertTrue(logfiles[0].endswith("log"))

    def test_run_cmd_negative_exit_code(self):
        """Test run_cmd function with command that has negative exit code."""
        # define signal handler to call in case run_cmd takes too long
        def handler(signum, _):
            raise RuntimeError("Signal handler called with signal %s" % signum)

        orig_sigalrm_handler = signal.getsignal(signal.SIGALRM)

        try:
            # set the signal handler and a 3-second alarm
            signal.signal(signal.SIGALRM, handler)
            signal.alarm(3)

            (_, ec) = run_cmd("kill -9 $$", log_ok=False)
            self.assertEqual(ec, -9)

            # reset the alarm
            signal.alarm(0)
            signal.alarm(3)

            (_, ec) = run_cmd_qa("kill -9 $$", {}, log_ok=False)
            self.assertEqual(ec, -9)

        finally:
            # cleanup: disable the alarm + reset signal handler for SIGALRM
            signal.signal(signal.SIGALRM, orig_sigalrm_handler)
            signal.alarm(0)

    def test_run_cmd_bis(self):
        """More 'complex' test for run_cmd function."""
        # a more 'complex' command to run, make sure all required output is there
        (out, ec) = run_cmd("for j in `seq 1 3`; do for i in `seq 1 100`; do echo hello; done; sleep 1.4; done")
        self.assertTrue(out.startswith('hello\nhello\n'))
        self.assertEqual(len(out), len("hello\n" * 300))
        self.assertEqual(ec, 0)

    def test_run_cmd_log_output(self):
        """Test run_cmd with log_output enabled"""
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

            (out, ec) = run_cmd(cmd, log_output=True)
            self.assertEqual(ec, 0)
            self.assertTrue(out.startswith('foo ') and out.endswith(' bar'))
            self.assertEqual(type(out), str)

    def test_run_cmd_trace(self):
        """Test run_cmd under --trace"""
        # replace log.experimental with log.warning to allow experimental code
        easybuild.tools.utilities._log.experimental = easybuild.tools.utilities._log.warning

        init_config(build_options={'trace': True})

        pattern = [
            r"^  >> running command:",
            r"\t\[started at: .*\]",
            r"\t\[working dir: .*\]",
            r"\t\[output logged in .*\]",
            r"\techo hello",
            r"  >> command completed: exit 0, ran in .*",
        ]

        self.mock_stdout(True)
        self.mock_stderr(True)
        (out, ec) = run_cmd("echo hello")
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(ec, 0)
        self.assertEqual(stderr, '')
        regex = re.compile('\n'.join(pattern))
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        # also test with command that is fed input via stdin
        self.mock_stdout(True)
        self.mock_stderr(True)
        (out, ec) = run_cmd('cat', inp='hello')
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(ec, 0)
        self.assertEqual(stderr, '')
        pattern.insert(3, r"\t\[input: hello\]")
        pattern[-2] = "\tcat"
        regex = re.compile('\n'.join(pattern))
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        # trace output can be disabled on a per-command basis
        self.mock_stdout(True)
        self.mock_stderr(True)
        (out, ec) = run_cmd("echo hello", trace=False)
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(stdout, '')
        self.assertEqual(stderr, '')

    def test_run_cmd_qa(self):
        """Basic test for run_cmd_qa function."""

        cmd = "echo question; read x; echo $x"
        qa = {'question': 'answer'}
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

        (out, ec) = run_cmd_qa(cmd, qa)
        self.assertEqual(ec, 0)
        self.assertTrue(out.startswith("question\nanswer\nfoo "))
        self.assertTrue(out.endswith('bar'))

    def test_run_cmd_qa_buffering(self):
        """Test whether run_cmd_qa uses unbuffered output."""

        # command that generates a lot of output before waiting for input
        # note: bug being fixed can be reproduced reliably using 1000, but not with too high values like 100000!
        cmd = 'for x in $(seq 1000); do echo "This is a number you can pick: $x"; done; '
        cmd += 'echo "Pick a number: "; read number; echo "Picked number: $number"'
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

        out, ec = run_cmd_qa(script, {}, log_ok=False)

        self.assertEqual(ec, 1)
        self.assertEqual(out, "Hello, I am about to exit\nERROR: I failed\n")

    def test_run_cmd_qa_log_all(self):
        """Test run_cmd_qa with log_output enabled"""
        (out, ec) = run_cmd_qa("echo 'n: '; read n; seq 1 $n", {'n: ': '5'}, log_all=True)
        self.assertEqual(ec, 0)
        self.assertEqual(out, "n: \n1\n2\n3\n4\n5\n")

        run_cmd_logs = glob.glob(os.path.join(self.test_prefix, '*', 'easybuild-run_cmd_qa*.log'))
        self.assertEqual(len(run_cmd_logs), 1)
        run_cmd_log_txt = read_file(run_cmd_logs[0])
        extra_pref = "# output for interactive command: echo 'n: '; read n; seq 1 $n\n\n"
        self.assertEqual(run_cmd_log_txt, extra_pref + "n: \n1\n2\n3\n4\n5\n")

    def test_run_cmd_qa_trace(self):
        """Test run_cmd under --trace"""
        # replace log.experimental with log.warning to allow experimental code
        easybuild.tools.utilities._log.experimental = easybuild.tools.utilities._log.warning

        init_config(build_options={'trace': True})

        self.mock_stdout(True)
        self.mock_stderr(True)
        (out, ec) = run_cmd_qa("echo 'n: '; read n; seq 1 $n", {'n: ': '5'})
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)
        self.assertEqual(stderr, '')
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
        self.assertEqual(stderr, '')

    def test_run_cmd_qa_answers(self):
        """Test providing list of answers in run_cmd_qa."""
        cmd = "echo question; read x; echo $x; " * 2
        qa = {"question": ["answer1", "answer2"]}

        (out, ec) = run_cmd_qa(cmd, qa)
        self.assertEqual(out, "question\nanswer1\nquestion\nanswer2\n")
        self.assertEqual(ec, 0)

        (out, ec) = run_cmd_qa(cmd, {}, std_qa=qa)
        self.assertEqual(out, "question\nanswer1\nquestion\nanswer2\n")
        self.assertEqual(ec, 0)

        self.assertErrorRegex(EasyBuildError, "Invalid type for answer", run_cmd_qa, cmd, {'q': 1})

        # test cycling of answers
        cmd = cmd * 2
        (out, ec) = run_cmd_qa(cmd, {}, std_qa=qa)
        self.assertEqual(out, "question\nanswer1\nquestion\nanswer2\n" * 2)
        self.assertEqual(ec, 0)

    def test_run_cmd_simple(self):
        """Test return value for run_cmd in 'simple' mode."""
        self.assertEqual(True, run_cmd("echo hello", simple=True))
        self.assertEqual(False, run_cmd("exit 1", simple=True, log_all=False, log_ok=False))

    def test_run_cmd_cache(self):
        """Test caching for run_cmd"""
        (first_out, ec) = run_cmd("ulimit -u")
        self.assertEqual(ec, 0)
        (cached_out, ec) = run_cmd("ulimit -u")
        self.assertEqual(ec, 0)
        self.assertEqual(first_out, cached_out)

        # inject value into cache to check whether executing command again really returns cached value
        run_cmd.update_cache({("ulimit -u", None): ("123456", 123)})
        (cached_out, ec) = run_cmd("ulimit -u")
        self.assertEqual(ec, 123)
        self.assertEqual(cached_out, "123456")

        # also test with command that uses stdin
        (out, ec) = run_cmd("cat", inp='foo')
        self.assertEqual(ec, 0)
        self.assertEqual(out, 'foo')

        # inject different output for cat with 'foo' as stdin to check whether cached value is used
        run_cmd.update_cache({('cat', 'foo'): ('bar', 123)})
        (cached_out, ec) = run_cmd("cat", inp='foo')
        self.assertEqual(ec, 123)
        self.assertEqual(cached_out, 'bar')

        run_cmd.clear_cache()

    def test_parse_log_error(self):
        """Test basic parse_log_for_error functionality."""
        errors = parse_log_for_error("error failed", True)
        self.assertEqual(len(errors), 1)

    def test_dry_run(self):
        """Test use of functions under (extended) dry run."""
        build_options = {
            'extended_dry_run': True,
            'silent': False,
        }
        init_config(build_options=build_options)

        self.mock_stdout(True)
        run_cmd("somecommand foo 123 bar")
        txt = self.get_stdout()
        self.mock_stdout(False)

        expected_regex = re.compile('\n'.join([
            r"  running command \"somecommand foo 123 bar\"",
            r"  \(in .*\)",
        ]))
        self.assertTrue(expected_regex.match(txt), "Pattern %s matches with: %s" % (expected_regex.pattern, txt))

        # check disabling 'verbose'
        self.mock_stdout(True)
        run_cmd("somecommand foo 123 bar", verbose=False)
        txt = self.get_stdout()
        self.mock_stdout(False)
        self.assertEqual(txt, '')

        # check forced run
        outfile = os.path.join(self.test_prefix, 'cmd.out')
        self.assertFalse(os.path.exists(outfile))
        self.mock_stdout(True)
        run_cmd("echo 'This is always echoed' > %s" % outfile, force_in_dry_run=True)
        txt = self.get_stdout()
        self.mock_stdout(False)
        # nothing printed to stdout, but command was run
        self.assertEqual(txt, '')
        self.assertTrue(os.path.exists(outfile))
        self.assertEqual(read_file(outfile), "This is always echoed\n")

        # Q&A commands
        self.mock_stdout(True)
        run_cmd_qa("some_qa_cmd", {'question1': 'answer1'})
        txt = self.get_stdout()
        self.mock_stdout(False)

        expected_regex = re.compile('\n'.join([
            r"  running interactive command \"some_qa_cmd\"",
            r"  \(in .*\)",
        ]))
        self.assertTrue(expected_regex.match(txt), "Pattern %s matches with: %s" % (expected_regex.pattern, txt))

    def test_run_cmd_list(self):
        """Test run_cmd with command specified as a list rather than a string"""
        cmd = ['/bin/sh', '-c', "echo hello"]
        self.assertErrorRegex(EasyBuildError, "When passing cmd as a list then `shell` must be set explictely!",
                              run_cmd, cmd)
        (out, ec) = run_cmd(cmd, shell=False)
        self.assertEqual(out, "hello\n")
        # no reason echo hello could fail
        self.assertEqual(ec, 0)

    def test_run_cmd_script(self):
        """Testing use of run_cmd with shell=False to call external scripts"""
        py_test_script = os.path.join(self.test_prefix, 'test.py')
        write_file(py_test_script, '\n'.join([
            '#!/usr/bin/python',
            'print("hello")',
        ]))
        adjust_permissions(py_test_script, stat.S_IXUSR)

        (out, ec) = run_cmd(py_test_script)
        self.assertEqual(ec, 0)
        self.assertEqual(out, "hello\n")

        (out, ec) = run_cmd([py_test_script], shell=False)
        self.assertEqual(ec, 0)
        self.assertEqual(out, "hello\n")

    def test_run_cmd_stream(self):
        """Test use of run_cmd with streaming output."""
        self.mock_stdout(True)
        self.mock_stderr(True)
        (out, ec) = run_cmd("echo hello", stream_output=True)
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)

        self.assertEqual(ec, 0)
        self.assertEqual(out, "hello\n")

        self.assertEqual(stderr, '')
        expected = '\n'.join([
            "== (streaming) output for command 'echo hello':",
            "hello",
            '',
        ])
        self.assertEqual(stdout, expected)

    def test_run_cmd_async(self):
        """Test asynchronously running of a shell command via run_cmd + complete_cmd."""

        os.environ['TEST'] = 'test123'

        cmd_info = run_cmd("sleep 2; echo $TEST", asynchronous=True)
        proc = cmd_info[0]

        # change value of $TEST to check that command is completed with correct environment
        os.environ['TEST'] = 'some_other_value'

        # initial poll should result in None, since it takes a while for the command to complete
        ec = proc.poll()
        self.assertEqual(ec, None)

        while ec is None:
            time.sleep(1)
            ec = proc.poll()

        out, ec = complete_cmd(*cmd_info, simple=False)
        self.assertEqual(ec, 0)
        self.assertEqual(out, 'test123\n')

        # also test with a command that produces a lot of output,
        # since that tends to lock up things unless we frequently grab some output...
        cmd = "echo start; for i in $(seq 1 50); do sleep 0.1; for j in $(seq 1000); do echo foo; done; done; echo done"
        cmd_info = run_cmd(cmd, asynchronous=True)
        proc = cmd_info[0]

        output = ''
        ec = proc.poll()
        self.assertEqual(ec, None)

        while ec is None:
            time.sleep(1)
            output += get_output_from_process(proc)
            ec = proc.poll()

        out, ec = complete_cmd(*cmd_info, simple=False, output=output)
        self.assertEqual(ec, 0)
        self.assertTrue(out.startswith('start\n'))
        self.assertTrue(out.endswith('\ndone\n'))

    def test_check_log_for_errors(self):
        fd, logfile = tempfile.mkstemp(suffix='.log', prefix='eb-test-')
        os.close(fd)

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
        expected_msg = r"Found 2 error\(s\) in command output "\
                       r"\(output: error found\n\tthe process crashed with 0\)"

        # String promoted to list
        self.assertErrorRegex(EasyBuildError, expected_msg, check_log_for_errors, input_text,
                              r"\b(error|crashed)\b")
        # List of string(s)
        self.assertErrorRegex(EasyBuildError, expected_msg, check_log_for_errors, input_text,
                              [r"\b(error|crashed)\b"])
        # List of tuple(s)
        self.assertErrorRegex(EasyBuildError, expected_msg, check_log_for_errors, input_text,
                              [(r"\b(error|crashed)\b", ERROR)])

        expected_msg = "Found 2 potential error(s) in command output " \
                       "(output: error found\n\tthe process crashed with 0)"
        init_logging(logfile, silent=True)
        check_log_for_errors(input_text, [(r"\b(error|crashed)\b", WARN)])
        stop_logging(logfile)
        self.assertTrue(expected_msg in read_file(logfile))

        expected_msg = r"Found 2 error\(s\) in command output \(output: error found\n\ttest failed\)"
        write_file(logfile, '')
        init_logging(logfile, silent=True)
        self.assertErrorRegex(EasyBuildError, expected_msg, check_log_for_errors, input_text, [
            r"\berror\b",
            (r"\ballowed-test failed\b", IGNORE),
            (r"(?i)\bCRASHED\b", WARN),
            "fail"
        ])
        stop_logging(logfile)
        expected_msg = "Found 1 potential error(s) in command output (output: the process crashed with 0)"
        self.assertTrue(expected_msg in read_file(logfile))


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(RunTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
