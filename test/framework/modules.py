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
import tempfile
import shutil

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
        self.orig_modulepath = os.environ.get('MODULEPATH', '').split(os.pathsep)

        test_modules_path = os.path.join(os.path.dirname(__file__), 'modules')
        self.testmods = modules_tool([test_modules_path])

    def test_avail(self):
        """Test if getting a (restricted) list of available modules works."""

        # test modules include 3 GCC modules
        ms = self.testmods.available('GCC')
        self.assertEqual(ms, ['GCC/4.6.3', 'GCC/4.6.4', 'GCC/4.7.2'])

        # test modules include one GCC/4.6.3 module
        ms = self.testmods.available(mod_name='GCC/4.6.3')
        self.assertEqual(ms, ['GCC/4.6.3'])

        # all test modules are accounted for
        ms = self.testmods.available()
        self.assertEqual(len(ms), TEST_MODULES_COUNT)

    def test_exists(self):
        """Test if testing for module existence works."""
        self.assertTrue(self.testmods.exists('OpenMPI/1.6.4-GCC-4.6.4'))
        self.assertTrue(not self.testmods.exists(mod_name='foo/1.2.3'))

    def test_load(self):
        """ test if we load one module it is in the loaded_modules """
        ms = self.testmods.available()

        for m in ms:
            self.testmods.load([m])
            self.assertTrue(m in self.testmods.loaded_modules())
            self.testmods.purge()

        # deprecated version
        for m in ms:
            self.testmods.add_module([m])
            self.testmods.load()

            self.assertTrue(m in self.testmods.loaded_modules())

            # remove module again and purge to avoid conflicts when loading modules
            self.testmods.remove_module([m])
            self.testmods.purge()

    def test_LD_LIBRARY_PATH(self):
        """Make sure LD_LIBRARY_PATH is what it should be when loaded multiple modules."""

        testpath = '/this/is/just/a/test'

        os.environ['LD_LIBRARY_PATH'] = testpath

        # load module and check that previous LD_LIBRARY_PATH is still there, at the end
        self.testmods.load(['GCC/4.6.3'])
        self.assertTrue(re.search("%s$" % testpath, os.environ['LD_LIBRARY_PATH']))
        self.testmods.purge()

        # deprecated version
        self.testmods.add_module([('GCC', '4.6.3')])
        self.testmods.load()

        # check that previous LD_LIBRARY_PATH is still there, at the end
        self.assertTrue(re.search("%s$" % testpath, os.environ['LD_LIBRARY_PATH']))
        self.testmods.purge()

    def test_purge(self):
        """Test if purging of modules works."""
        ms = self.testmods.available()

        self.testmods.load([ms[0]])
        self.assertTrue(len(self.testmods.loaded_modules()) > 0)

        self.testmods.purge()
        self.assertTrue(len(self.testmods.loaded_modules()) == 0)

        # deprecated version
        self.testmods.add_module([ms[0]])
        self.testmods.load()
        self.assertTrue(len(self.testmods.loaded_modules()) > 0)

        self.testmods.purge()
        self.assertTrue(len(self.testmods.loaded_modules()) == 0)

    def test_long_module_path(self):
        """Test dealing with a (very) long module path."""

        # create a really long modules install path
        tmpdir = tempfile.mkdtemp()
        long_mod_path = tmpdir
        for x in range(100):
            long_mod_path = os.path.join(long_mod_path, 'foo')
        long_mod_path = os.path.join(long_mod_path, 'modules')

        # copy one of the test modules there
        gcc_mod_dir = os.path.join(long_mod_path, 'GCC')
        os.makedirs(gcc_mod_dir)
        gcc_mod_path = os.path.join(os.path.dirname(__file__), 'modules', 'GCC', '4.6.3')
        shutil.copy2(gcc_mod_path, gcc_mod_dir)

        # try and use long modules path
        m = modules_tool([long_mod_path])
        ms = m.available()

        self.assertEqual(ms, ['GCC/4.6.3'])

        shutil.rmtree(tmpdir)

    def tearDown(self):
        """cleanup"""
        os.chdir(self.cwd)
        os.environ['MODULEPATH'] = os.pathsep.join(self.orig_modulepath)

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(ModulesTest)

if __name__ == '__main__':
    main()
