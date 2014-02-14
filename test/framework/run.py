# #
# Copyright 2012-2014 Ghent University
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
Unit tests for filetools.py

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""
import os

from easybuild.tools.run import run_cmd, run_cmd_qa, parse_log_for_error
from easybuild.tools.run import _log as run_log

from unittest import TestCase, TestLoader, main


class RunTest(TestCase):
    """ Testcase for run module """

    def test_run_cmd(self):
        """Basic test for run_cmd function."""
        (out, ec) = run_cmd("echo hello")
        self.assertEqual(out, "hello\n")
        # no reason echo hello could fail
        self.assertEqual(ec, 0)

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

    def test_run_cmd_simple(self):
        """Test return value for run_cmd in 'simple' mode."""
        self.assertEqual(True, run_cmd("echo hello", simple=True))
        self.assertEqual(False, run_cmd("exit 1", simple=True, log_all=False, log_ok=False))

    def test_parse_log_error(self):
        """Test basic parse_log_for_error functionality."""
        errors = parse_log_for_error("error failed", True)
        self.assertEqual(len(errors), 1)

    def test_run_cmd_suse(self):
        """Test run_cmd on SuSE systems, which have $PROFILEREAD set."""
        # avoid warning messages
        run_log_level = run_log.getEffectiveLevel()
        run_log.setLevel('ERROR')

        # run_cmd should also work if $PROFILEREAD is set (very relevant for SuSE systems)
        profileread = os.environ.get('PROFILEREAD', None)
        os.environ['PROFILEREAD'] = 'profilereadxxx'
        try:
            (out, ec) = run_cmd("echo hello")
        except Exception, err:
            out, ec = "ERROR: %s" % err, 1

        # make sure it's restored again before we can fail the test
        if profileread is not None:
            os.environ['PROFILEREAD'] = profileread
        else:
            del os.environ['PROFILEREAD']

        self.assertEqual(out, "hello\n")
        self.assertEqual(ec, 0)
        run_log.setLevel(run_log_level)


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(RunTest)

if __name__ == '__main__':
    main()
