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
Unit tests for .yeb easyconfig format

@author: Caroline De Brouwer (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import os
from test.framework.utilities import EnhancedTestCase
from unittest import TestLoader, main

from easybuild.framework.easyconfig.easyconfig import ActiveMNS, EasyConfig


class YebTest(EnhancedTestCase):
    """ Testcase for run module """

    def test_parse_yeb(self):
        """Test parsing of .yeb easyconfigs."""
        testdir = os.path.dirname(os.path.abspath(__file__))
        test_easyconfigs = os.path.join(testdir, 'easyconfigs')
        test_yeb_easyconfigs = os.path.join(testdir, 'easyconfigs', 'yeb')

        # test parsing
        ec_yeb = EasyConfig(os.path.join(test_yeb_easyconfigs, 'bzip2.yeb'))

        # compare with parsed result of .eb easyconfig
        ec_eb = EasyConfig(os.path.join(test_easyconfigs, 'bzip2-1.0.6-GCC-4.9.2.eb'))

        no_match = False
        for key in sorted(ec_yeb.asdict()):
            #self.assertEqual(ec_yeb[key], ec_eb[key])
            if ec_yeb[key] != ec_eb[key]:
                print '>>> ', key, ec_yeb[key], type(ec_yeb[key]), ec_eb[key], type(ec_eb[key]), ec_yeb[key] == ec_eb[key]
                no_match = True
        self.assertFalse(no_match)


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(YebTest)

if __name__ == '__main__':
    main()
