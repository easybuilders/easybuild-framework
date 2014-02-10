# #
# Copyright 2013-2014 Ghent University
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
Toy build unit test

@author: Kenneth Hoste (Ghent University)
"""

import copy
import glob
import os
import re
import shutil
import sys
import tempfile
from unittest import TestCase, TestLoader
from unittest import main as unittestmain

from easybuild.main import main
from easybuild.tools import config
from easybuild.tools.environment import modify_env
from easybuild.tools.filetools import read_file, write_file


class ToyBuildTest(TestCase):
    """Toy build unit test."""

    def setUp(self):
        """Test setup."""
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

        # keep track of original environment to restore
        self.orig_environ = copy.deepcopy(os.environ)

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

        modify_env(os.environ, self.orig_environ)
        tempfile.tempdir = None

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

    def check_toy(self, installpath, outtxt, version='0.0', versionprefix='', versionsuffix=''):
        """Check whether toy build succeeded."""

        full_version = ''.join([versionprefix, version, versionsuffix])

        # if the module exists, it should be fine
        toy_module = os.path.join(installpath, 'modules', 'all', 'toy', full_version)
        self.assertTrue(os.path.exists(toy_module), "module for toy build toy/%s found" % full_version)

        # check for success
        success = re.compile("COMPLETED: Installation ended successfully")
        self.assertTrue(success.search(outtxt))

        # make sure installation log file and easyconfig file are copied to install dir
        software_path = os.path.join(installpath, 'software', 'toy', full_version)
        install_log_path_pattern = os.path.join(software_path, 'easybuild', 'easybuild-toy-%s*.log' % version)
        self.assertTrue(len(glob.glob(install_log_path_pattern)) == 1, "Found 1 file at %s" % install_log_path_pattern)

        ec_file_path = os.path.join(software_path, 'easybuild', 'toy-%s.eb' % full_version)
        self.assertTrue(os.path.exists(ec_file_path))

        devel_module_path = os.path.join(software_path, 'easybuild', 'toy-%s-easybuild-devel' % full_version)
        self.assertTrue(os.path.exists(devel_module_path))

    def test_toy_build(self):
        """Perform a toy build."""
        args = [
                os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb'),
                '--sourcepath=%s' % self.sourcepath,
                '--buildpath=%s' % self.buildpath,
                '--installpath=%s' % self.installpath,
                '--debug',
                '--unittest-file=%s' % self.logfile,
                '--force',
                '--robot=%s' % os.pathsep.join([self.buildpath, os.path.dirname(__file__)]),
               ]
        try:
            main((args, self.dummylogfn, True))
        except SystemExit:
            pass
        except Exception, err:
            print "err: %s" % err
        outtxt = read_file(self.logfile)

        self.check_toy(self.installpath, outtxt)

    def test_toy_build_formatv2(self):
        """Perform a toy build (format v2)."""
        # set $MODULEPATH such that modules for specified dependencies are found
        modulepath = os.environ.get('MODULEPATH')
        os.environ['MODULEPATH'] = os.path.abspath(os.path.join(os.path.dirname(__file__), 'modules'))

        args = [
            os.path.join(os.path.dirname(__file__), 'easyconfigs', 'v2.0', 'toy.eb'),
            '--sourcepath=%s' % self.sourcepath,
            '--buildpath=%s' % self.buildpath,
            '--installpath=%s' % self.installpath,
            '--debug',
            '--unittest-file=%s' % self.logfile,
            '--force',
            '--robot=%s' % os.pathsep.join([self.buildpath, os.path.dirname(__file__)]),
            '--software-version=0.0',
            '--toolchain=dummy,dummy',
            '--experimental',
        ]
        try:
            main((args, self.dummylogfn, True))
        except SystemExit:
            pass
        outtxt = read_file(self.logfile)

        self.check_toy(self.installpath, outtxt)

        # restore
        if modulepath is not None:
            os.environ['MODULEPATH'] = modulepath
        else:
            del os.environ['MODULEPATH']

    def test_toy_build_with_blocks(self):
        """Test a toy build with multiple blocks."""
        orig_sys_path = sys.path[:]
        # add directory in which easyconfig file can be found to Python search path, since we're not specifying it full path below
        tmpdir = tempfile.mkdtemp()
        # note get_paths_for expects easybuild/easyconfigs subdir
        ecs_path = os.path.join(tmpdir, "easybuild", "easyconfigs")
        os.makedirs(ecs_path)
        shutil.copy2(os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0-multiple.eb'), ecs_path)
        sys.path.append(tmpdir)

        args = [
                'toy-0.0-multiple.eb',
                '--sourcepath=%s' % self.sourcepath,
                '--buildpath=%s' % self.buildpath,
                '--installpath=%s' % self.installpath,
                '--debug',
                '--unittest-file=%s' % self.logfile,
                '--force',
               ]
        try:
            main((args, self.dummylogfn, True))
        except SystemExit:
            pass
        except Exception, err:
            print "err: %s" % err
        outtxt = read_file(self.logfile)

        for toy_prefix, toy_version, toy_suffix in [
            ('', '0.0', '-somesuffix'),
            ('someprefix-', '0.0', '-somesuffix')
        ]:
            self.check_toy(self.installpath, outtxt, version=toy_version,
                           versionprefix=toy_prefix, versionsuffix=toy_suffix)

        # cleanup
        shutil.rmtree(tmpdir)
        sys.path = orig_sys_path

def suite():
    """ return all the tests in this file """
    return TestLoader().loadTestsFromTestCase(ToyBuildTest)

if __name__ == '__main__':
    unittestmain()
