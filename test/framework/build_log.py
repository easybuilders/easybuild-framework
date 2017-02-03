# #
# Copyright 2015-2017 Ghent University
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
Unit tests for EasyBuild log infrastructure

@author: Kenneth Hoste (Ghent University)
"""
import os
import re
import sys
import tempfile
from distutils.version import LooseVersion
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner
from vsc.utils.fancylogger import getLogger, getRootLoggerName, logToFile, setLogFormat

from easybuild.tools.build_log import LOGGING_FORMAT, EasyBuildError
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

        log_re = re.compile("^%s ::.* BOOM \(at .*:[0-9]+ in [a-z_]+\)$" % getRootLoggerName(), re.M)
        logtxt = open(tmplog, 'r').read()
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
        log.warn("justawarning")
        log.deprecated("anotherwarning", newer_ver)
        log.deprecated("onemorewarning", '1.0', '2.0')
        log.deprecated("lastwarning", '1.0', max_ver='2.0')
        log.error("kaput")
        log.error("err: %s", 'msg: %s')
        stderr = self.get_stderr()
        self.mock_stderr(False)
        # no output to stderr (should all go to log file)
        self.assertEqual(stderr, '')
        try:
            log.exception("oops")
        except EasyBuildError:
            pass
        logToFile(tmplog, enable=False)
        logtxt = read_file(tmplog)

        root = getRootLoggerName()

        expected_logtxt = '\n'.join([
            r"%s.test_easybuildlog \[DEBUG\] :: 123 debug" % root,
            r"%s.test_easybuildlog \[INFO\] :: foobar info" % root,
            r"%s.test_easybuildlog \[WARNING\] :: justawarning" % root,
            r"%s.test_easybuildlog \[WARNING\] :: Deprecated functionality.*anotherwarning.*" % root,
            r"%s.test_easybuildlog \[WARNING\] :: Deprecated functionality.*onemorewarning.*" % root,
            r"%s.test_easybuildlog \[WARNING\] :: Deprecated functionality.*lastwarning.*" % root,
            r"%s.test_easybuildlog \[ERROR\] :: EasyBuild crashed with an error \(at .* in .*\): kaput" % root,
            root + r".test_easybuildlog \[ERROR\] :: EasyBuild crashed with an error \(at .* in .*\): err: msg: %s",
            r"%s.test_easybuildlog \[ERROR\] :: .*EasyBuild encountered an exception \(at .* in .*\): oops" % root,
            '',
        ])
        logtxt_regex = re.compile(r'^%s' % expected_logtxt, re.M)
        self.assertTrue(logtxt_regex.search(logtxt), "Pattern '%s' found in %s" % (logtxt_regex.pattern, logtxt))

        self.assertErrorRegex(EasyBuildError, "DEPRECATED \(since .*: kaput", log.deprecated, "kaput", older_ver)
        self.assertErrorRegex(EasyBuildError, "DEPRECATED \(since .*: 2>1", log.deprecated, "2>1", '2.0', '1.0')
        self.assertErrorRegex(EasyBuildError, "DEPRECATED \(since .*: 2>1", log.deprecated, "2>1", '2.0', max_ver='1.0')

        # wipe log so we can reuse it
        write_file(tmplog, '')

        # test formatting log messages by providing extra arguments
        logToFile(tmplog, enable=True)
        log.warn("%s", "bleh"),
        log.info("%s+%s = %d", '4', '2', 42)
        args = ['this', 'is', 'just', 'a', 'test']
        log.debug("%s %s %s %s %s", *args)
        log.error("foo %s baz", 'baz')
        logToFile(tmplog, enable=False)
        logtxt = read_file(tmplog)
        expected_logtxt = '\n'.join([
            r"%s.test_easybuildlog \[WARNING\] :: bleh" % root,
            r"%s.test_easybuildlog \[INFO\] :: 4\+2 = 42" % root,
            r"%s.test_easybuildlog \[DEBUG\] :: this is just a test" % root,
            r"%s.test_easybuildlog \[ERROR\] :: EasyBuild crashed with an error \(at .* in .*\): foo baz baz" % root,
            '',
        ])
        logtxt_regex = re.compile(r'^%s' % expected_logtxt, re.M)
        self.assertTrue(logtxt_regex.search(logtxt), "Pattern '%s' found in %s" % (logtxt_regex.pattern, logtxt))

    def test_log_levels(self):
        """Test whether log levels are respected"""
        fd, tmplog = tempfile.mkstemp()
        os.close(fd)

        # set log format, for each regex searching
        setLogFormat("%(name)s [%(levelname)s] :: %(message)s")

        # test basic log methods
        logToFile(tmplog, enable=True)
        log = getLogger('test_easybuildlog')

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

        logToFile(tmplog, enable=False)
        logtxt = read_file(tmplog)

        root = getRootLoggerName()

        devel_msg = r"%s.test_easybuildlog \[DEVEL\] :: tmi" % root
        debug_msg = r"%s.test_easybuildlog \[DEBUG\] :: gdb" % root
        info_msg = r"%s.test_easybuildlog \[INFO\] :: fyi" % root
        warning_msg = r"%s.test_easybuildlog \[WARNING\] :: this is a warning" % root
        deprecated_msg = r"%s.test_easybuildlog \[WARNING\] :: Deprecated functionality, .*: almost kaput; see .*" % root
        error_msg = r"%s.test_easybuildlog \[ERROR\] :: EasyBuild crashed with an error \(at .* in .*\): kaput" % root

        expected_logtxt = '\n'.join([
            error_msg,
            error_msg, deprecated_msg, warning_msg,
            error_msg, deprecated_msg, warning_msg, info_msg,
            error_msg, deprecated_msg, warning_msg, info_msg, debug_msg,
            error_msg, deprecated_msg, warning_msg, info_msg, debug_msg, devel_msg,
        ])
        logtxt_regex = re.compile(r'^%s' % expected_logtxt, re.M)
        self.assertTrue(logtxt_regex.search(logtxt), "Pattern '%s' found in %s" % (logtxt_regex.pattern, logtxt))


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(BuildLogTest, sys.argv[1:])

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
