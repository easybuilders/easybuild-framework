# #
# Copyright 2014-2019 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# https://github.com/easybuilders/easybuild
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
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from unittest import TextTestRunner

import easybuild.framework
from easybuild.tools.run import run_cmd


class ScriptsTest(EnhancedTestCase):
    """ Testcase for run module """

    def setUp(self):
        """Test setup."""
        super(ScriptsTest, self).setUp()

        # make sure easybuild-framework is included in $PYTHONPATH (so scripts can pick it up)
        framework_loc = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(easybuild.framework.__file__))))
        pythonpath = os.environ.get('PYTHONPATH', '')
        os.environ['PYTHONPATH'] = os.pathsep.join([framework_loc, pythonpath])

    def test_generate_software_list(self):
        """Test for generate_software_list.py script."""

        # adjust $PYTHONPATH such that test easyblocks are found by the script
        test_dir = os.path.abspath(os.path.dirname(__file__))
        eb_blocks_path = os.path.join(test_dir, 'sandbox')
        pythonpath = os.environ.get('PYTHONPATH', os.path.dirname(test_dir))
        os.environ['PYTHONPATH'] = os.pathsep.join([eb_blocks_path, pythonpath])

        testdir = os.path.dirname(__file__)
        topdir = os.path.dirname(os.path.dirname(testdir))
        script = os.path.join(topdir, 'easybuild', 'scripts', 'generate_software_list.py')
        easyconfigs_dir = os.path.join(testdir, 'easyconfigs')

        # copy easyconfig files in format v1 to run the script
        tmpdir = tempfile.mkdtemp()
        for root, subfolders, files in os.walk(easyconfigs_dir):
            if 'v2.0' in subfolders:
                subfolders.remove('v2.0')
            for ec_file in [f for f in files if 'broken' not in os.path.basename(f)]:
                shutil.copy2(os.path.join(root, ec_file), tmpdir)

        cmd = "%s %s --local --quiet --path %s" % (sys.executable, script, tmpdir)
        out, ec = run_cmd(cmd, simple=False)

        # make sure output is kind of what we expect it to be
        regex = r"Supported Packages \(32 "
        self.assertTrue(re.search(regex, out), "Pattern '%s' found in output: %s" % (regex, out))
        per_letter = {
            'B': '2',  # binutils, bzip2
            'C': '2',  # CrayCCE, CUDA
            'F': '3',  # foss, fosscuda, FFTW
            'G': '9',  # GCC, GCCcore, gcccuda, gmvapich2, golf, golfc, gompic, gompi, gzip
            'H': '1',  # hwloc
            'I': '8',  # icc, iccifort, iccifortcuda, intel, ifort, iimpi, imkl, impi
            'M': '1',  # MVAPICH2
            'O': '2',  # OpenMPI, OpenBLAS
            'P': '1',  # Python
            'S': '2',  # ScaLAPACK, SQLite
            'T': '1',  # toy
        }
        self.assertTrue(' - '.join(["[%(l)s](#%(l)s)" % {'l': l} for l in sorted(per_letter.keys())]))
        for key, val in per_letter.items():
            regex = re.compile(r"### %(l)s \(%(n)s packages\) <a name='%(l)s'/>" % {'l': key, 'n': val})
            self.assertTrue(regex.search(out), "Pattern '%s' found in: %s" % (regex.pattern, out))

        software = ['FFTW', 'foss', 'GCC', 'gompi', 'gzip', 'hwloc', 'OpenMPI', 'OpenBLAS', 'ScaLAPACK', 'toy']
        for soft in software:
            letter = soft[0].lower()
            pattern = r"^\*.*logo[\s\S]*easyconfigs/%(l)s/%(s)s\)[\s\S]*%(s)s.*\n" % {'l': letter, 's': soft}
            self.assertTrue(re.search(pattern, out, re.M), "Pattern '%s' found in: %s" % (pattern, out))

        shutil.rmtree(tmpdir)
        os.environ['PYTHONPATH'] = pythonpath


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(ScriptsTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
