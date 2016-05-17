# #
# Copyright 2012-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
Unit tests for filetools.py

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""
import os
import re
import signal
from test.framework.utilities import EnhancedTestCase, init_config
from unittest import TestLoader, main
from vsc.utils.fancylogger import setLogLevelDebug, logToScreen

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import read_file
from easybuild.tools.run import run_cmd, run_cmd_qa, parse_log_for_error
from easybuild.tools.run import _log as run_log


class RunTest(EnhancedTestCase):
    """ Testcase for run module """

    def test_run_cmd(self):
        """Basic test for run_cmd function."""
        (out, ec) = run_cmd("echo hello")
        self.assertEqual(out, "hello\n")
        # no reason echo hello could fail
        self.assertEqual(ec, 0)

    def test_run_cmd_negative_exit_code(self):
        """Test run_cmd function with command that has negative exit code."""
        # define signal handler to call in case run_cmd takes too long
        def handler(signum, _):
            raise RuntimeError("Signal handler called with signal %s" % signum)

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

        # disable the alarm
        signal.alarm(0)

    def test_run_cmd_bis(self):
        """More 'complex' test for run_cmd function."""
        # a more 'complex' command to run, make sure all required output is there
        (out, ec) = run_cmd("for j in `seq 1 3`; do for i in `seq 1 100`; do echo hello; done; sleep 1.4; done")
        self.assertTrue(out.startswith('hello\nhello\n'))
        self.assertEqual(len(out), len("hello\n"*300))
        self.assertEqual(ec, 0)

    def test_run_cmd_qa(self):
        """Basic test for run_cmd_qa function."""
        (out, ec) = run_cmd_qa("echo question; read x; echo $x", {"question": "answer"})
        self.assertEqual(out, "question\nanswer\n")
        # no reason echo hello could fail
        self.assertEqual(ec, 0)

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


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(RunTest)

if __name__ == '__main__':
    #logToScreen(enable=True)
    #setLogLevelDebug()
    main()
