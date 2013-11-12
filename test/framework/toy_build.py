##
# Copyright 2013 Ghent University
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
Toy build unit test

@author: Kenneth Hoste (Ghent University)
"""

import glob
import os
import re
import shutil
import sys
import tempfile
from unittest import TestCase, TestLoader
from unittest import main as unittestmain
from vsc.utils.fancylogger import setLogLevelDebug, logToScreen

import easybuild.tools.options as eboptions
from easybuild.tools import config
from easybuild.main import main
from easybuild.tools.filetools import read_file, write_file
from easybuild.tools.modules import modules_tool


class ToyBuildTest(TestCase):
    """Toy build unit test."""

    def setUp(self):
        """Test setup."""
        # initialize configuration so config.get_modules_tool function works
        eb_go = eboptions.parse_options()
        config.init(eb_go.options, eb_go.get_options_by_section('config'))

        fd, self.logfile = tempfile.mkstemp(suffix='.log', prefix='eb-options-test-')
        os.close(fd)

        fd, self.dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # adjust PYTHONPATH such that test easyblocks are found
        self.orig_sys_path = sys.path[:]

        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'sandbox')))
        import easybuild.easyblocks
        reload(easybuild.easyblocks)
        reload(easybuild.tools.module_naming_scheme)

        # clear log
        write_file(self.logfile, '')

        self.buildpath = tempfile.mkdtemp()
        self.installpath = tempfile.mkdtemp()
        self.sourcepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox', 'sources')

    def tearDown(self):
        """Cleanup."""
        # remove logs
        os.remove(self.logfile)

        if os.path.exists(self.dummylogfn):
            os.remove(self.dummylogfn)
        shutil.rmtree(self.buildpath)
        shutil.rmtree(self.installpath)

        # restore original Python search path
        sys.path = self.orig_sys_path

    def assertErrorRegex(self, error, regex, call, *args):
        """Convenience method to match regex with the error message."""
        try:
            call(*args)
            self.assertTrue(False)  # this will fail when no exception is thrown at all
        except error, err:
            res = re.search(regex, err.msg)
            if not res:
                print "err: %s" % err
            self.assertTrue(res)

    def test_toy_build(self):
        """Perform a toy build."""

        # the toy easyconfig uses the SOFTWARE_LIBDIR constant function, we need to make sure it works as expected
        # load the toylib module, and tweak $EBROOTTOYLIB to something that works
        orig_modulepaths = os.environ.get('MODULEPATH', '').split(os.pathsep)
        test_modules_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'modules'))
        ms = modules_tool([test_modules_path])
        ms.load(['toylib/0.0'])
        # set up a couple of lib dirs for toylib, as required for SOFTWARE_LIBDIR to work
        tmpdir = tempfile.mkdtemp()
        for libdir in ['lib', 'lib64']:
            os.mkdir(os.path.join(tmpdir, libdir))
        open(os.path.join(tmpdir, 'lib64', 'libfoo.a'), 'w').write('foo')
        # rewrite $root in toylib module to make SOFTWARE_LIBDIR work
        toylib_module_path = os.path.join(test_modules_path, 'toylib', '0.0')
        toylib_module_txt = open(toylib_module_path, 'r').read()
        toylib_module_alt_txt = re.sub('^(set\s*root).*$', '\1\t%s' % tmpdir, toylib_module_txt)
        open(toylib_module_path, 'w').write(toylib_module_alt_txt)

        args = [
                os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb'),
                '--sourcepath=%s' % self.sourcepath,
                '--buildpath=%s' % self.buildpath,
                '--installpath=%s' % self.installpath,
                '--debug',
                '--unittest-file=%s' % self.logfile,
                '--force',
               ]
        try:
            main((args, self.dummylogfn, True))
        except (SystemExit, Exception), err:
            print err
        outtxt = read_file(self.logfile)

        # if the module exists, it should be fine
        toy_module = os.path.join(self.installpath, 'modules', 'all', 'toy', '0.0')
        self.assertTrue(os.path.exists(toy_module), "module for toy build toy/0.0 found")

        # make sure the SOFTWARE_LIBDIR function was correctly replaced
        txt = open(toy_module, 'r').read()
        lib_regex = re.compile("requires toylib library directory lib64")
        self.assertTrue(lib_regex.search(txt), "'%s' found in toy/0.0 module" % lib_regex.pattern)

        # check for success
        success = re.compile("COMPLETED: Installation ended successfully")
        self.assertTrue(success.search(outtxt))

        # make sure installation log file and easyconfig file are copied to install dir
        install_log_path_pattern = os.path.join(self.installpath, 'software', 'toy', '0.0', 'easybuild', 'easybuild-toy-0.0-*.log')
        self.assertTrue(len(glob.glob(install_log_path_pattern)) == 1)

        ec_file_path = os.path.join(self.installpath, 'software', 'toy', '0.0', 'easybuild', 'toy-0.0.eb')
        self.assertTrue(os.path.exists(ec_file_path))

        devel_module_path = os.path.join(self.installpath, 'software', 'toy', '0.0', 'easybuild', 'toy-0.0-easybuild-devel')
        self.assertTrue(os.path.exists(devel_module_path))

        # cleanup
        shutil.rmtree(tmpdir)
        open(toylib_module_path, 'w').write(toylib_module_txt)
        os.environ['MODULEPATH'] = os.pathsep.join(orig_modulepaths)
        modules_tool().purge()

    def test_toy_build_with_blocks(self):
        """Test a toy build with multiple blocks."""
        args = [
                os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0-multiple.eb'),
                '--sourcepath=%s' % self.sourcepath,
                '--buildpath=%s' % self.buildpath,
                '--installpath=%s' % self.installpath,
                '--debug',
                '--unittest-file=%s' % self.logfile,
                '--force',
               ]
        try:
            main((args, self.dummylogfn, True))
        except (SystemExit, Exception), err:
            print err

        for toy_version in ['0.0-somesuffix', 'someprefix-0.0-somesuffix']:
            toy_module = os.path.join(self.installpath, 'modules', 'all', 'toy', toy_version)
            self.assertTrue(os.path.exists(toy_module), "module for toy/%s found" % toy_version)

def suite():
    """ return all the tests in this file """
    return TestLoader().loadTestsFromTestCase(ToyBuildTest)

if __name__ == '__main__':
    #logToScreen(enable=True)
    #setLogLevelDebug()
    unittestmain()
