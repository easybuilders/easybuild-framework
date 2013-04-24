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
Unit tests for module_generator.py.

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

import os
import re
import tempfile
from unittest import TestCase, TestSuite, main

from easybuild.tools.module_generator import ModuleGenerator
from easybuild.framework.easyblock import EasyBlock
from easybuild.tools.build_log import EasyBuildError
from test.framework.utilities import find_full_path


class ModuleGeneratorTest(TestCase):
    """ testcase for ModuleGenerator """

    def assertErrorRegex(self, error, regex, call, *args):
        """ convenience method to match regex with the error message """
        try:
            call(*args)
        except error, err:
            self.assertTrue(re.search(regex, err.msg))

    def setUp(self):
        """ initialize ModuleGenerator with test Application """

        # find .eb file
        eb_path = os.path.join('test', 'framework', 'easyconfigs', 'gzip-1.4.eb')
        eb_full_path = find_full_path(eb_path)
        self.assertTrue(eb_full_path)

        self.eb = EasyBlock(eb_full_path)
        self.modgen = ModuleGenerator(self.eb)
        self.modgen.app.installdir = tempfile.mkdtemp(prefix='easybuild-modgen-test-')
        self.cwd = os.getcwd()

    def runTest(self):
        """ since we set the installdir above, we can predict the output """
        expected = """#%%Module

proc ModulesHelp { } {
    puts stderr {   gzip (GNU zip) is a popular data compression program as a replacement for compress - Homepage: http://www.gzip.org/
}
}

module-whatis {gzip (GNU zip) is a popular data compression program as a replacement for compress - Homepage: http://www.gzip.org/}

set root    %s

conflict    gzip
""" % self.modgen.app.installdir

        desc = self.modgen.get_description()
        self.assertEqual(desc, expected)

        # test load_module
        expected = """
if { ![is-loaded name/version] } {
    module load name/version
}
"""
        self.assertEqual(expected, self.modgen.load_module("name", "version"))

        # test unload_module
        expected = """
if { ![is-loaded name/version] } {
    if { [is-loaded name] } {
        module unload name
    }
}
"""
        self.assertEqual(expected, self.modgen.unload_module("name", "version"))

        # test prepend_paths
        expected = """prepend-path	key		$root/path1
prepend-path	key		$root/path2
"""
        self.assertEqual(expected, self.modgen.prepend_paths("key", ["path1", "path2"]))

        expected = """prepend-path	bar		$root/foo
"""
        self.assertEqual(expected, self.modgen.prepend_paths("bar", "foo"))

        self.assertErrorRegex(EasyBuildError, "Absolute path %s/foo passed to prepend_paths " \
                                              "which only expects relative paths." % self.modgen.app.installdir,
                              self.modgen.prepend_paths, "key2", ["bar", "%s/foo" % self.modgen.app.installdir])


        # test set_environment
        self.assertEqual('setenv\tkey\t\t"value"\n', self.modgen.set_environment("key", "value"))
        self.assertEqual("setenv\tkey\t\t'va\"lue'\n", self.modgen.set_environment("key", 'va"lue'))
        self.assertEqual('setenv\tkey\t\t"va\'lue"\n', self.modgen.set_environment("key", "va'lue"))
        self.assertEqual('setenv\tkey\t\t"""va"l\'ue"""\n', self.modgen.set_environment("key", """va"l'ue"""))

    def tearDown(self):
        """cleanup"""
        os.remove(self.eb.logfile)
        os.chdir(self.cwd)

def suite():
    """ returns all the testcases in this module """
    return TestSuite([ModuleGeneratorTest()])

if __name__ == '__main__':
    main()
