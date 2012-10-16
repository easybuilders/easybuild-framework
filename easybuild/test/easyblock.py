##
# Copyright 2012 Toon Willems
# Copyright 2012 Kenneth Hoste
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
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
this module contains unit tests for easyblock
"""
#TODO: implement testcases for each step method
import os
import re
import shutil
import tempfile

from easybuild.framework.easyblock import EasyBlock
from easybuild.tools import config
from unittest import TestCase, TestSuite
from easybuild.tools.build_log import EasyBuildError, init_logger
import sys

stdoutorig = sys.stdout

log_fn = "/tmp/easybuild_easyconfig_tests.log"
_, log, logh = init_logger(filename=log_fn, debug=True, typ="easybuild_easyconfig_test")

class EasyBlockTest(TestCase):
    """ Baseclass for easyblock testcases """


    def setUp(self):
        """ create temporary easyconfig file """
        self.eb_file = "/tmp/easyconfig_test_file.eb"
        f = open(self.eb_file, "w")
        f.write(self.contents)
        f.close()
        config.variables['installPath'] = tempfile.gettempdir()
        config.variables['buildPath'] = tempfile.gettempdir()
        config.variables['logFormat'] = ("/dev/", "null")
        sys.stdout = open("/dev/null", 'w')

    def tearDown(self):
        """ make sure to remove the temporary file """
        os.remove(self.eb_file)
        sys.stdout.close()
        sys.stdout = stdoutorig

    def assertErrorRegex(self, error, regex, call, *args):
        """ convenience method to match regex with the error message """
        try:
            call(*args)
            self.assertTrue(False)  # this will fail when no exception is thrown at all
        except error, err:
            res = re.search(regex, err.msg)
            if not res:
                print "err: %s" % err
            self.assertTrue(res)


class TestEmpty(EasyBlockTest):
    """ Test empty easyblocks """

    contents = "# empty string"

    def runTest(self):
        """ empty files should not parse! """
        self.assertRaises(EasyBuildError, EasyBlock, self.eb_file)
        self.assertErrorRegex(EasyBuildError, "expected a valid path", EasyBlock, "")

class TestEasyBlock(EasyBlockTest):
    """ Test the creation of an easyblock
    and test all the steps (not all implemented yet)
    but it should not be implemented when using the EeasyBlock class directly
    """
    contents = """
name = "pi"
version = "3.14"
homepage = "http://google.com"
description = "test easyconfig"
toolchain = {"name":"dummy", "version": "dummy"}
exts_list = ['ext1']
"""

    def runTest(self):
        """ make sure easyconfigs defining extensions work"""
        eb = EasyBlock(self.eb_file)
        self.assertRaises(NotImplementedError, eb.run_all_steps, True, False)

class TestExtensionsStep(EasyBlockTest):
    """Test extensions step"""

    contents = """
name = "pi"
version = "3.14"
homepage = "http://google.com"
description = "test easyconfig"
toolchain = {"name":"dummy", "version": "dummy"}
exts_list = ['ext1']
"""

    def runTest(self):
        """Testcase for extensions"""
        # test for proper error message without the exts_defaultclass set
        eb = EasyBlock(self.eb_file)
        eb.installdir = config.variables['installPath']
        self.assertRaises(EasyBuildError, eb.extensions_step)
        self.assertErrorRegex(EasyBuildError, "No default extension class set", eb.extensions_step)

        # test if everything works fine if set
        self.contents += "exts_defaultclass = ['easybuild.framework.extension', 'Extension']"
        self.setUp()
        eb = EasyBlock(self.eb_file)
        eb.installdir = config.variables['installPath']
        eb.extensions_step()

        # test for proper error message when skip is set, but no exts_filter is set
        self.assertRaises(EasyBuildError, eb.skip_extensions)
        self.assertErrorRegex(EasyBuildError, "no exts_filter set", eb.skip_extensions)


def suite():
    """ return all the tests in this file """
    return TestSuite([TestEmpty(), TestEasyBlock(), TestExtensionsStep()])
