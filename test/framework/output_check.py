##
# Copyright 2026-2026 Ghent University
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
Check that tests don't print unexpected output to stdout/stderr.

Output is captured at the file descriptor level (fd 1 and 2), so output produced by subprocesses
or written directly to the original streams is caught too, not only output going through sys.stdout/sys.stderr.
Output that a test captures itself via mock_stdout/mock_stderr never reaches the file descriptors, so it is not
affected.

Set $EB_TEST_ALLOW_OUTPUT to 1 to disable the check (and the capturing), for example when debugging a test.
"""
import os
import re
import sys
import tempfile

ALLOW_OUTPUT_ENV_VAR = 'EB_TEST_ALLOW_OUTPUT'

# lines of output that are tolerated (for example, messages printed when a test is skipped)
ALLOWED_OUTPUT_PATTERNS = [
    r"no GitHub token available",
    r"skipping SvnRepository test",
    r"requires Lmod as modules tool",
    r"stty: 'standard input': Inappropriate ioctl for device",
    r"CryptographyDeprecationWarning: Python 3\.[78]",
    r"from cryptography.* import ",
    r"Blowfish",
    r"GC3Pie not available, skipping test",
    r"CryptographyDeprecationWarning: TripleDES has been moved",
    r"algorithms\.TripleDES",
    # status characters of the unittest runner (successful, skipped, failed, ... tests)
    r"^[.sEFxu]+$",
]
ALLOWED_OUTPUT_REGEX = re.compile('|'.join(ALLOWED_OUTPUT_PATTERNS))


def _flush_std_streams():
    """Flush the (original and current) Python stdout/stderr streams."""
    for stream in (sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__):
        try:
            stream.flush()
        except (AttributeError, ValueError):
            # stream may be missing or closed
            pass


class OutputCheckMixin:
    """
    Mixin for test cases that makes a test fail if it prints unexpected output to stdout/stderr.

    Call start_output_check() at the very start of setUp().
    """

    def start_output_check(self):
        """Start capturing output written to stdout/stderr (at the file descriptor level)."""
        if os.getenv(ALLOW_OUTPUT_ENV_VAR) == '1':
            return

        _flush_std_streams()
        capture = tempfile.TemporaryFile(mode='w+b')
        saved_fds = {}
        for fd in (1, 2):
            saved_fds[fd] = os.dup(fd)
            os.dup2(capture.fileno(), fd)

        # registered as the first cleanup, so it runs last:
        # after tearDown and all other cleanups, which may also produce output
        self.addCleanup(self._stop_output_check, capture, saved_fds)

    def _test_already_failed(self):
        """Determine whether the current test already failed (or errored), based on unittest internals."""
        outcome = getattr(self, '_outcome', None)
        # Python < 3.11: errors are collected in the outcome, and only passed to the result at the end
        if any(exc_info is not None for _, exc_info in getattr(outcome, 'errors', [])):
            return True
        # Python >= 3.11: errors are passed to the result immediately
        result = getattr(outcome, 'result', None)
        for failed_tests in (getattr(result, 'failures', []), getattr(result, 'errors', [])):
            if any(test is self for test, _ in failed_tests):
                return True
        return False

    def _stop_output_check(self, capture, saved_fds):
        """Stop capturing output, restore stdout/stderr, and fail if unexpected output was produced."""
        _flush_std_streams()
        for fd, saved_fd in saved_fds.items():
            os.dup2(saved_fd, fd)
            os.close(saved_fd)

        capture.seek(0)
        output = capture.read().decode('utf-8', 'replace')
        capture.close()

        # if the test already failed, don't report its output as another failure:
        # it's likely related (and the unittest runner may already have written its 'F'/'E' status character)
        test_failed = self._test_already_failed()

        unexpected = [line for line in output.splitlines() if line.strip() and not ALLOWED_OUTPUT_REGEX.search(line)]
        if unexpected and not test_failed:
            self.fail("Test %s printed unexpected output to stdout/stderr "
                      "(capture it via self.mocked_stdout_stderr(), or set $%s=1 to disable this check):\n%s"
                      % (self.id(), ALLOW_OUTPUT_ENV_VAR, output))

        # pass through output as is, so it's not hidden from the test log
        if output:
            sys.stderr.write(output)
            sys.stderr.flush()
