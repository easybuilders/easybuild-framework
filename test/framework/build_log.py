# #
# Copyright 2015-2016 Ghent University
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
import tempfile
from test.framework.utilities import EnhancedTestCase, init_config
from unittest import TestLoader
from unittest import main as unittestmain
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

        log_re = re.compile("^%s :: BOOM \(at .*:[0-9]+ in [a-z_]+\)$" % getRootLoggerName(), re.M)
        logtxt = open(tmplog, 'r').read()
        self.assertTrue(log_re.match(logtxt), "%s matches %s" % (log_re.pattern, logtxt))

        # test formatting of message
        self.assertErrorRegex(EasyBuildError, 'BOOMBAF', raise_easybuilderror, 'BOOM%s', 'BAF')

        os.remove(tmplog)

    def test_easybuildlog(self):
        """Tests for EasyBuildLog."""
        fd, tmplog = tempfile.mkstemp()
        os.close(fd)

        # set log format, for each regex searching
        setLogFormat("%(name)s [%(levelname)s] :: %(message)s")

        # test basic log methods
        logToFile(tmplog, enable=True)
        log = getLogger('test_easybuildlog')
        log.setLevelName('DEBUG')
        log.debug("123 debug")
        log.info("foobar info")
        log.warn("justawarning")
        log.raiseError = False
        log.error("kaput")
        log.raiseError = True
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
            r"%s.test_easybuildlog \[ERROR\] :: EasyBuild crashed with an error \(at .* in .*\): kaput" % root,
            r"%s.test_easybuildlog \[ERROR\] :: .*EasyBuild encountered an exception \(at .* in .*\): oops" % root,
            '',
        ])
        logtxt_regex = re.compile(r'^%s' % expected_logtxt, re.M)
        self.assertTrue(logtxt_regex.search(logtxt), "Pattern '%s' found in %s" % (logtxt_regex.pattern, logtxt))

        # wipe log so we can reuse it
        write_file(tmplog, '')

        # test formatting log messages by providing extra arguments
        logToFile(tmplog, enable=True)
        log.warn("%s", "bleh"),
        log.info("%s+%s = %d", '4', '2', 42)
        args = ['this', 'is', 'just', 'a', 'test']
        log.debug("%s %s %s %s %s", *args)
        log.raiseError = False
        log.error("foo %s baz", 'baz')
        log.raiseError = True
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

        # test deprecated behaviour: raise EasyBuildError on log.error and log.exception
        os.environ['EASYBUILD_DEPRECATED'] = '2.1'
        init_config()

        log.warning("No raise for warnings")
        self.assertErrorRegex(EasyBuildError, 'EasyBuild crashed with an error', log.error, 'foo')
        self.assertErrorRegex(EasyBuildError, 'EasyBuild encountered an exception', log.exception, 'bar')


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(BuildLogTest)

if __name__ == '__main__':
    unittestmain()
