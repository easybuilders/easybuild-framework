# #
# Copyright 2014-2014 Ghent University
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
Unit tests for easyconfig/format/format EBConfigObj

@author: Stijn De Weirdt (Ghent University)
"""
import os
import re

from easybuild.framework.easyconfig.format.format import EBConfigObj
from easybuild.framework.easyconfig.format.version import VersionOperator, ToolchainVersionOperator
from easybuild.framework.easyconfig.format.version import OrderedVersionOperators
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.configobj import ConfigObj
from easybuild.tools.toolchain.utilities import search_toolchain
from unittest import TestCase, TestLoader, main

from vsc.utils.fancylogger import setLogLevelDebug, logToScreen


class TestEBConfigObj(TestCase):
    """Unit tests for EBConfigObj from format.format module."""

    def assertErrorRegex(self, error, regex, call, *args, **kwargs):
        """ convenience method to match regex with the error message """
        try:
            call(*args, **kwargs)
            self.assertTrue(False)  # this will fail when no exception is thrown at all
        except error, err:
            res = re.search(regex, err.msg)
            if not res:
                print "err: %s" % err
            self.assertTrue(res)

    def test_configobj(self):
        """Test configobj sort"""
        _, tcs = search_toolchain('')
        tc_names = [x.NAME for x in tcs]
        tcmax = min(len(tc_names), 3)
        if len(tc_names) < tcmax:
            tcmax = len(tc_names)
        tc = tc_names[0]
        configobj_txt = [
            '[SUPPORTED]',
            'toolchains=%s >= 7.8.9' % ','.join(tc_names[:tcmax]),
            'versions=1.2.3,2.3.4,3.4.5',
            '[>= 2.3.4]',
            'foo=bar',
            '[== 3.4.5]',
            'baz=biz',
            '[%s == 5.6.7]' % tc,
            '[%s > 7.8.9]' % tc_names[tcmax - 1],
        ]

        co = ConfigObj(configobj_txt)
        cov = EBConfigObj(co)

        cov.default
        # FIXME: actually check something


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(TestEBConfigObj)


if __name__ == '__main__':
    logToScreen(enable=True)
    setLogLevelDebug()
    main()
