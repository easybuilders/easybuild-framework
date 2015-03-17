# #
# Copyright 2015-2015 Ghent University
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

from easybuild.tools.build_log import EasyBuildError


def raise_easybuilderror(msg, *args, **kwargs):
    """Utility function: just raise a EasyBuildError."""
    raise EasyBuildError(msg, *args, **kwargs)


class BuildLogTest(EnhancedTestCase):
    """Tests for EasyBuild log infrastructure."""

    def test_easybuilderror(self):
        """Tests for EasyBuildError."""
        fd, tmplog = tempfile.mkstemp()
        os.close(fd)

        # auto-logging on raised EasyBuildError relies on deprecated functionality being used
        # this should be removed for testing EasyBuild v3.x
        os.environ['EASYBUILD_DEPRECATED'] = '2.1'
        init_config()

        # set log format, for each regex searching
        setLogFormat("%(name)s :: %(message)s")

        # if no logger is available, and no logger is specified, use default 'root' fancylogger
        logToFile(tmplog, enable=True)
        self.assertErrorRegex(EasyBuildError, 'BOOM', raise_easybuilderror, 'BOOM')
        logToFile(tmplog, enable=False)

        # replace log_re for EasyBuild v3.x
        #log_re = re.compile("^%s :: EasyBuild crashed .*: BOOM$" % getRootLoggerName(), re.M)
        root = getRootLoggerName()
        log_re = re.compile("^%(root)s :: .*\n%(root)s :: EasyBuild crashed .*: BOOM$" % {'root': root}, re.M)
        logtxt = open(tmplog, 'r').read()
        self.assertTrue(log_re.match(logtxt), "%s matches %s" % (log_re.pattern, logtxt))

        # test formatting of message
        self.assertErrorRegex(EasyBuildError, 'BOOMBAF', raise_easybuilderror, 'BOOM%s', 'BAF')

        os.remove(tmplog)

    def test_easybuildlog(self):
        """Tests for EasyBuildLog."""
        log = getLogger('test_easybuildlog')

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
