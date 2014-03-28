# #
# Copyright 2014 Ghent University
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
Unit tests for scripts

@author: Kenneth Hoste (Ghent University)
"""
import os
import re
import shutil
import sys
import tempfile
from test.framework.utilities import EnhancedTestCase
from unittest import TestLoader, main

from easybuild.tools.run import run_cmd


class ScriptsTest(EnhancedTestCase):
    """ Testcase for run module """

    def test_generate_software_list(self):
        """Test for generate_software_list.py script."""

        # adjust $PYTHONPATH such that test easyblocks are found by the script
        eb_blocks_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'sandbox'))
        pythonpath = os.environ['PYTHONPATH']
        os.environ['PYTHONPATH'] = "%s:%s" % (pythonpath, eb_blocks_path)

        testdir = os.path.dirname(__file__)
        topdir = os.path.dirname(os.path.dirname(testdir))
        script = os.path.join(topdir, 'easybuild', 'scripts', 'generate_software_list.py')
        easyconfigs_dir = os.path.join(testdir, 'easyconfigs')

        # copy easyconfig files in format v1 to run the script
        tmpdir = tempfile.mkdtemp()
        for root, subfolders, files in os.walk(easyconfigs_dir):
            if 'v2.0' in subfolders:
                subfolders.remove('v2.0')
            for ec_file in files:
                shutil.copy2(os.path.join(root, ec_file), tmpdir)

        cmd = "python %s --local --quiet --path %s" % (script, tmpdir)
        out, ec = run_cmd(cmd, simple=False)

        # make sure output is kind of what we expect it to be
        self.assertTrue(re.search(r"Supported Packages \(10", out))
        per_letter = {
            'F': '1',  # FFTW
            'G': '4',  # GCC, gompi, goolf, gzip
            'H': '1',  # hwloc
            'O': '2',  # OpenMPI, OpenBLAS
            'S': '1',  # ScaLAPACK
            'T': '1',  # toy
        }
        self.assertTrue(' - '.join(["[%(l)s](#%(l)s)" % {'l': l} for l in sorted(per_letter.keys())]))
        for key, val in per_letter.items():
            self.assertTrue(re.search(r"### %(l)s \(%(n)s packages\) <a name='%(l)s'/>" % {'l': key, 'n': val}, out))

        software = ['FFTW', 'GCC', 'gompi', 'goolf', 'gzip', 'hwloc', 'OpenMPI', 'OpenBLAS', 'ScaLAPACK', 'toy']
        for soft in software:
            letter = soft[0].lower()
            pattern = r"^\*.*logo[\s\S]*easyconfigs/%(l)s/%(s)s\)[\s\S]*%(s)s.*\n" % {'l': letter, 's': soft}
            self.assertTrue(re.search(pattern, out, re.M))

        shutil.rmtree(tmpdir)
        os.environ['PYTHONPATH'] = pythonpath

def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(ScriptsTest)

if __name__ == '__main__':
    main()
