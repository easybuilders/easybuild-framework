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

from easybuild.main import main
from easybuild.tools import config
from easybuild.tools.filetools import read_file, write_file


class ToyBuildTest(TestCase):
    """Toy build unit test."""

    def setUp(self):
        """Test setup."""
        fd, self.logfile = tempfile.mkstemp(suffix='.log', prefix='eb-options-test-')
        os.close(fd)

    def tearDown(self):
        """Cleanup."""
        os.remove(self.logfile)

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
        fd, dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # adjust PYTHONPATH such that test easyblocks are found
        orig_sys_path = sys.path[:]

        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'sandbox')))
        import easybuild.easyblocks
        reload(easybuild.easyblocks)
        reload(easybuild.tools.module_naming_scheme)

        # clear log
        write_file(self.logfile, '')

        buildpath = tempfile.mkdtemp()
        installpath = tempfile.mkdtemp()
        sourcepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox', 'sources')

        args = [
                os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb'),
                '--sourcepath=%s' % sourcepath,
                '--buildpath=%s' % buildpath,
                '--installpath=%s' % installpath,
                '--debug',
                '--unittest-file=%s' % self.logfile,
                '--force',
               ]
        try:
            main((args, dummylogfn, True))
        except (SystemExit, Exception), err:
            print err
        outtxt = read_file(self.logfile)

        # if the module exists, it should be fine
        self.assertTrue(os.path.exists(os.path.join(installpath, 'modules', 'all', 'toy', '0.0')))

        # check for success
        success = re.compile("COMPLETED: Installation ended successfully")
        self.assertTrue(success.search(outtxt))

        # make sure installation log file and easyconfig file are copied to install dir
        install_log_path_pattern = os.path.join(installpath, 'software', 'toy', '0.0', 'easybuild', 'easybuild-toy-0.0-*.log')
        self.assertTrue(len(glob.glob(install_log_path_pattern)) == 1)

        ec_file_path = os.path.join(installpath, 'software', 'toy', '0.0', 'easybuild', 'toy-0.0.eb')
        self.assertTrue(os.path.exists(ec_file_path))

        devel_module_path = os.path.join(installpath, 'software', 'toy', '0.0', 'easybuild', 'toy-0.0-easybuild-devel')
        self.assertTrue(os.path.exists(devel_module_path))

        # clear log
        write_file(self.logfile, '')

        if os.path.exists(dummylogfn):
            os.remove(dummylogfn)
        shutil.rmtree(buildpath)
        shutil.rmtree(installpath)

        # restore original Python search path
        sys.path = orig_sys_path

def suite():
    """ return all the tests in this file """
    return TestLoader().loadTestsFromTestCase(ToyBuildTest)

if __name__ == '__main__':
    unittestmain()
