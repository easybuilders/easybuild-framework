##
# Copyright 2012-2013 Ghent University
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
Unit tests for modules.py.

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""

import os
import re

import easybuild.tools.options as eboptions
from easybuild.tools import config
from easybuild.tools.modules import modules_tool
from unittest import TestCase, TestLoader, main


# number of modules included for testing purposes
TEST_MODULES_COUNT = 29


class ModulesTest(TestCase):
    """Test cases for modules."""

    def setUp(self):
        """set up everything for a unit test."""
        # initialize configuration so config.get_modules_tool function works
        eb_go = eboptions.parse_options()
        config.init(eb_go.options, eb_go.get_options_by_section('config'))

        self.cwd = os.getcwd()

    def test_avail(self):
        """Test if getting a (restricted) list of available modules works."""
        testmods = modules_tool([os.path.join(os.path.dirname(__file__), 'modules')])
        ms = testmods.available()
        self.assertEqual(len(ms), TEST_MODULES_COUNT)

        # test modules include 3 GCC modules
        ms = testmods.available('GCC')
        self.assertEqual(ms, ['GCC/4.6.3', 'GCC/4.6.4', 'GCC/4.7.2'])

        # test modules include one GCC/4.6.3 module
        ms = testmods.available(mod_name='GCC/4.6.3')
        self.assertEqual(ms, ['GCC/4.6.3'])

    def test_exists(self):
        """Test if testing for module existence works."""
        testmods = modules_tool([os.path.join(os.path.dirname(__file__), 'modules')])
        self.assertTrue(testmods.exists('OpenMPI/1.6.4-GCC-4.6.4'))
        self.assertTrue(not testmods.exists(mod_name='foo/1.2.3'))

    def test_load(self):
        """ test if we load one module it is in the loaded_modules """
        testmods = modules_tool([os.path.join(os.path.dirname(__file__), 'modules')])
        ms = testmods.available()

        for m in ms:
            testmods.load([m])
            self.assertTrue(m in testmods.loaded_modules())
            testmods.purge()

        # deprecated version
        for m in ms:
            testmods.add_module([m])
            testmods.load()

            self.assertTrue(m in testmods.loaded_modules())

            # remove module again and purge to avoid conflicts when loading modules
            testmods.remove_module([m])
            testmods.purge()

    def test_LD_LIBRARY_PATH(self):
        """Make sure LD_LIBRARY_PATH is what it should be when loaded multiple modules."""

        testpath = '/this/is/just/a/test'

        os.environ['LD_LIBRARY_PATH'] = testpath

        testmods = modules_tool([os.path.join(os.path.dirname(__file__), 'modules')])

        # load module and check that previous LD_LIBRARY_PATH is still there, at the end
        testmods.load(['GCC/4.6.3'])
        self.assertTrue(re.search("%s$" % testpath, os.environ['LD_LIBRARY_PATH']))
        testmods.purge()

        # deprecated version
        testmods.add_module([('GCC', '4.6.3')])
        testmods.load()

        # check that previous LD_LIBRARY_PATH is still there, at the end
        self.assertTrue(re.search("%s$" % testpath, os.environ['LD_LIBRARY_PATH']))
        testmods.purge()

    def test_purge(self):
        """Test if purging of modules works."""
        m = modules_tool([os.path.join(os.path.dirname(__file__), 'modules')])
        ms = m.available()

        m.load([ms[0]])
        self.assertTrue(len(m.loaded_modules()) > 0)

        m.purge()
        self.assertTrue(len(m.loaded_modules()) == 0)

        # deprecated version
        m.add_module([ms[0]])
        m.load()
        self.assertTrue(len(m.loaded_modules()) > 0)

        m.purge()
        self.assertTrue(len(m.loaded_modules()) == 0)

    def tearDown(self):
        """cleanup"""
        os.chdir(self.cwd)

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(ModulesTest)

if __name__ == '__main__':
    main()
