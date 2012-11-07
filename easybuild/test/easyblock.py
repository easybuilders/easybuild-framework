##
# Copyright 2012 Ghent University
# Copyright 2012 Jens Timmerman
# Copyright 2012 Kenneth Hoste
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
this module contains unit tests for easyblock
"""
#TODO: implement testcases for each step method
import os
import re
import shutil
import tempfile

from easybuild.framework.easyblock import EasyBlock
from easybuild.tools import config
from unittest import TestCase, TestLoader
from easybuild.tools.build_log import EasyBuildError
import sys

class EasyBlockTest(TestCase):
    """ Baseclass for easyblock testcases """

    def writeEC(self):
        """ create temporary easyconfig file """
        f = open(self.eb_file, "w")
        f.write(self.contents)
        f.close()

    def setUp(self):
        """ setup """
        self.eb_file = "/tmp/easyblock_test_file.eb"
        config.variables['log_dir'] = tempfile.mkdtemp()
        self.cwd = os.getcwd()

    def test_empty(self):
        self.contents = "# empty"
        self.writeEC()
        """ empty files should not parse! """
        self.assertRaises(EasyBuildError, EasyBlock, self.eb_file)
        self.assertErrorRegex(EasyBuildError, "expected a valid path", EasyBlock, "")

    def test_easyblock(self):
        """ make sure easyconfigs defining extensions work"""
        self.contents =  """
name = "pi"
version = "3.14"
homepage = "http://google.com"
description = "test easyconfig"
toolchain = {"name":"dummy", "version": "dummy"}
exts_list = ['ext1']
"""
        self.writeEC()
        stdoutorig = sys.stdout
        sys.stdout = open("/dev/null", 'w')
        eb = EasyBlock(self.eb_file)
        self.assertRaises(NotImplementedError, eb.run_all_steps, True, False)
        sys.stdout.close()
        sys.stdout = stdoutorig

    def test_fake_module_load(self):
        """Testcase for fake module load"""
        self.contents = """
name = "pi"
version = "3.14"
homepage = "http://google.com"
description = "test easyconfig"
toolchain = {"name":"dummy", "version": "dummy"}
"""
        self.writeEC()
        # test for proper error message without the exts_defaultclass set
        eb = EasyBlock(self.eb_file)
        eb.installdir = config.variables['install_path']
        eb.load_fake_module()
        
    def test_extensions_step(self):
        """Test the extensions_step"""
        self.contents = """
name = "pi"
version = "3.14"
homepage = "http://google.com"
description = "test easyconfig"
toolchain = {"name":"dummy", "version": "dummy"}
exts_list = ['ext1']
"""
        self.writeEC()
        """Testcase for extensions"""
        # test for proper error message without the exts_defaultclass set
        eb = EasyBlock(self.eb_file)
        eb.installdir = config.variables['install_path']
        self.assertRaises(EasyBuildError, eb.extensions_step)
        self.assertErrorRegex(EasyBuildError, "No default extension class set", eb.extensions_step)

        # test if everything works fine if set
        self.contents += "exts_defaultclass = ['easybuild.framework.extension', 'Extension']"
        self.writeEC()
        eb = EasyBlock(self.eb_file)
        eb.installdir = config.variables['install_path']
        eb.extensions_step()

        # test for proper error message when skip is set, but no exts_filter is set
        self.assertRaises(EasyBuildError, eb.skip_extensions)
        self.assertErrorRegex(EasyBuildError, "no exts_filter set", eb.skip_extensions)


    
    def tearDown(self):
        """ make sure to remove the temporary file """
        os.remove(self.eb_file)
        shutil.rmtree(config.variables['log_dir'])
        os.chdir(self.cwd)

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

def suite():
    """ return all the tests in this file """
    return TestLoader().loadTestsFromTestCase(EasyBlockTest)

