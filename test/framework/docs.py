# #
# Copyright 2012-2015 Ghent University
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
##
"""
Unit tests for docs.py.
"""

from test.framework.utilities import EnhancedTestCase, init_config
from unittest import TestLoader, main
from easybuild.tools.docs import mk_rst_table

class DocsTest(EnhancedTestCase):

    def test_rst_table(self):
        """ Test mk_rst_table function """
        entries = [['one', 'two', 'three']]
        t = 'This title is longer than the entries in the column'
        titles = [t]

        # small table
        table = '\n'.join(mk_rst_table(titles, entries))
        check = '\n'.join([
            '=' * len(t),
            t,
            '=' * len(t),
            'one' + ' ' * (len(t) - 3),
            'two' + ' ' * (len(t) -3),
            'three' + ' ' * (len(t) - 5),
            '=' * len(t),
            '',
        ])

        self.assertEqual(table, check)


def suite():
    """ returns all test cases in this module """
    return TestLoader().loadTestsFromTestCase(DocsTest)

if __name__ == '__main__':
    # also check the setUp for debug
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
