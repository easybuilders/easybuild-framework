##
# Copyright 2012 Ghent University
# Copyright 2012 Toon Willems
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
import os
import random

import easybuild.tools.modules as modules
from unittest import TestCase, TestLoader 


class ModulesTest(TestCase):
    """ small test for Modules """

    def setUp(self):
        """setup"""
        self.cwd = os.getcwd()

    def test_load(self):
        """ test if we load one module it is in the loaded_modules """
        testmods = modules.Modules([os.path.join('easybuild', 'test', 'modules')])
        ms = testmods.available('', None)

        m = random.choice(ms)
        testmods.add_module([m])
        testmods.load()

        tmp = {"name": m[0], "version": m[1]}
        assert(tmp in testmods.loaded_modules())

    def test_purge(self):
        """Test if purging of modules works."""
        m = modules.Modules([os.path.join('easybuild', 'test', 'modules')])

        ms = m.available('', None)
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

