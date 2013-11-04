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
Unit tests for easyblock.py

@author: Jens Timmerman (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

#TODO: implement testcases for each step method
import os
import re
import shutil
import tempfile
import sys

import easybuild.tools.options as eboptions
from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.extension import Extension
from easybuild.tools import config
from unittest import TestCase, TestLoader, main
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import write_file

class EasyBlockTest(TestCase):
    """ Baseclass for easyblock testcases """

    # initialize configuration so modules_tool() function works
    eb_go = eboptions.parse_options()
    config.init(eb_go.options, eb_go.get_options_by_section('config'))

    def writeEC(self):
        """ create temporary easyconfig file """
        write_file(self.eb_file, self.contents)

    def setUp(self):
        """ setup """
        fd, self.eb_file = tempfile.mkstemp(prefix='easyblock_test_file_', suffix='.eb')
        os.close(fd)
        config.variables['tmp_logdir'] = tempfile.mkdtemp()
        config.variables['installpath'] = tempfile.mkdtemp()
        config.variables['buildpath'] = tempfile.mkdtemp()
        config.variables['logfile_format'] = ("temp","temp")
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

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

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
        eb = EasyBlock(self.eb_file)
        eb.installdir = config.variables['installpath']
        fake_mod_data = eb.load_fake_module()
        eb.clean_up_fake_module(fake_mod_data)

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

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
        eb.installdir = config.variables['installpath']
        self.assertRaises(EasyBuildError, eb.extensions_step)
        self.assertErrorRegex(EasyBuildError, "No default extension class set", eb.extensions_step)

        # test if everything works fine if set
        self.contents += "\nexts_defaultclass = ['easybuild.framework.extension', 'Extension']"
        self.writeEC()
        eb = EasyBlock(self.eb_file)
        eb.builddir = config.variables['buildpath']
        eb.installdir = config.variables['installpath']
        eb.extensions_step()

        # test for proper error message when skip is set, but no exts_filter is set
        self.assertRaises(EasyBuildError, eb.skip_extensions)
        self.assertErrorRegex(EasyBuildError, "no exts_filter set", eb.skip_extensions)

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

    def test_skip_extensions_step(self):
        """Test the skip_extensions_step"""
        self.contents = """
name = "pi"
version = "3.14"
homepage = "http://google.com"
description = "test easyconfig"
toolchain = {"name":"dummy", "version": "dummy"}
exts_list = ['ext1', 'ext2']
exts_filter = ("if [ %(name)s == 'ext2' ]; then exit 0; else exit 1; fi", '')
exts_defaultclass = ['easybuild.framework.extension', 'Extension']
"""
        # check if skip skips correct extensions
        self.writeEC()
        eb = EasyBlock(self.eb_file)
        #self.assertTrue('ext1' in eb.exts.keys() and 'ext2' in eb.exts.keys())
        eb.builddir = config.variables['buildpath']
        eb.installdir = config.variables['installpath']
        eb.skip = True
        eb.extensions_step()
        # 'ext1' should be in eb.exts
        self.assertTrue('ext1' in [y for x in eb.exts for y in x.values()])
        # 'ext2' should not
        self.assertFalse('ext2' in [y for x in eb.exts for y in x.values()])

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

    def test_make_module_step(self):
        """Test the make_module_step"""
        name = "pi"
        version = "3.14"
        modextravars = {'PI': '3.1415', 'FOO': 'bar'}
        modextrapaths = {'PATH': 'pibin', 'CPATH': 'pi/include'}
        self.contents = '\n'.join([
            'name = "%s"' % name,
            'version = "%s"' % version,
            'homepage = "http://google.com"',
            'description = "test easyconfig"',
            "toolchain = {'name': 'dummy', 'version': 'dummy'}",
            "dependencies = [('foo', '1.2.3')]",
            "builddependencies = [('bar', '9.8.7')]",
            "modextravars = %s" % str(modextravars),
            "modextrapaths = %s" % str(modextrapaths),
        ])

        # overwrite installpath config setting
        orig_installpath = config.variables['installpath']
        installpath = tempfile.mkdtemp()
        config.variables['installpath'] = installpath

        # test if module is generated correctly
        self.writeEC()
        eb = EasyBlock(self.eb_file)
        eb.installdir = os.path.join(config.variables['installpath'], config.variables['subdir_software'], 'pi', '3.14')
        modpath = os.path.join(eb.make_module_step(), name, version)
        self.assertTrue(os.path.exists(modpath))

        # verify contents of module
        f = open(modpath, 'r')
        txt = f.read()
        f.close()
        self.assertTrue(re.search("^#%Module", txt.split('\n')[0]))
        self.assertTrue(re.search("^conflict\s+%s$" % name, txt, re.M))
        self.assertTrue(re.search("^set\s+root\s+%s$" % eb.installdir, txt, re.M))
        self.assertTrue(re.search('^setenv\s+EBROOT%s\s+".root"\s*$' % name.upper(), txt, re.M))
        self.assertTrue(re.search('^setenv\s+EBVERSION%s\s+"%s"$' % (name.upper(), version), txt, re.M))
        for (key, val) in modextravars.items():
            self.assertTrue(re.search('^setenv\s+%s\s+"%s"$' % (key, val), txt, re.M))
        for (key, val) in modextrapaths.items():
            self.assertTrue(re.search('^prepend-path\s+%s\s+\$root/%s$' % (key, val), txt, re.M))

        # restore original settings
        config.variables['installpath'] = orig_installpath

    def tearDown(self):
        """ make sure to remove the temporary file """
        os.remove(self.eb_file)
        shutil.rmtree(config.variables['tmp_logdir'])
        shutil.rmtree(config.variables['installpath'])
        shutil.rmtree(config.variables['buildpath'])
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

if __name__ == '__main__':
    main()
