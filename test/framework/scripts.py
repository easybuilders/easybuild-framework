# #
# Copyright 2014-2018 Ghent University
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

import setuptools
import vsc.utils.generaloption

import easybuild.framework
from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.tools.filetools import read_file, write_file
from easybuild.tools.run import run_cmd


class ScriptsTest(EnhancedTestCase):
    """ Testcase for run module """

    def setUp(self):
        """Test setup."""
        super(ScriptsTest, self).setUp()

        # make sure setuptools, vsc-base and easybuild-framework are included in $PYTHONPATH (so scripts can pick it up)
        setuptools_loc = os.path.dirname(os.path.dirname(setuptools.__file__))
        generaloption_loc = os.path.abspath(vsc.utils.generaloption.__file__)
        vsc_loc = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(generaloption_loc))))
        framework_loc = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(easybuild.framework.__file__))))
        pythonpath = os.environ.get('PYTHONPATH', '')
        os.environ['PYTHONPATH'] = os.pathsep.join([setuptools_loc, vsc_loc, framework_loc, pythonpath])

    def test_generate_software_list(self):
        """Test for generate_software_list.py script."""

        # adjust $PYTHONPATH such that test easyblocks are found by the script
        test_dir = os.path.abspath(os.path.dirname(__file__))
        eb_blocks_path = os.path.join(test_dir, 'sandbox')
        pythonpath = os.environ.get('PYTHONPATH', os.path.dirname(test_dir))
        os.environ['PYTHONPATH'] = os.pathsep.join([pythonpath, eb_blocks_path])

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
        regex = r"Supported Packages \(26 "
        self.assertTrue(re.search(regex, out), "Pattern '%s' found in output: %s" % (regex, out))
        per_letter = {
            'B': '1',  # bzip2
            'C': '2',  # CrayCCE, CUDA
            'F': '1',  # FFTW
            'G': '6',  # GCC, GCCcore, gmvapich2, gompi, goolf, gzip
            'H': '1',  # hwloc
            'I': '8',  # icc, iccifort, iccifortcuda, ictce, ifort, iimpi, imkl, impi
            'M': '1',  # MVAPICH2
            'O': '2',  # OpenMPI, OpenBLAS
            'P': '1',  # Python
            'S': '2',  # ScaLAPACK, SQLite
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

    def test_fix_broken_easyconfig(self):
        """Test fix_broken_easyconfigs.py script."""
        testdir = os.path.dirname(__file__)
        topdir = os.path.dirname(os.path.dirname(testdir))
        script = os.path.join(topdir, 'easybuild', 'scripts', 'fix_broken_easyconfigs.py')
        test_easyblocks = os.path.join(testdir, 'sandbox')

        broken_ec_txt_tmpl = '\n'.join([
            "# licenseheader",
            "%sname = '%s'",
            "version = '1.2.3'",
            '',
            "description = 'foo'",
            "homepage = 'http://example.com'",
            '',
            "toolchain = {'name': 'GCC', 'version': '4.8.2'}",
            '',
            "premakeopts = 'FOO=libfoo.%%s' %% shared_lib_ext",
            "makeopts = 'CC=gcc'",
            '',
            "license = 'foo.lic'",
        ])
        fixed_ec_txt_tmpl = '\n'.join([
            "# licenseheader",
            "%sname = '%s'",
            "version = '1.2.3'",
            '',
            "description = 'foo'",
            "homepage = 'http://example.com'",
            '',
            "toolchain = {'name': 'GCC', 'version': '4.8.2'}",
            '',
            "prebuildopts = 'FOO=libfoo.%%s' %% SHLIB_EXT",
            "buildopts = 'CC=gcc'",
            '',
            "license_file = 'foo.lic'",
        ])
        broken_ec_tmpl = os.path.join(self.test_prefix, '%s.eb')
        script_cmd_tmpl = "PYTHONPATH=%s:$PYTHONPATH:%s %s %%s" % (topdir, test_easyblocks, script)

        # don't change it if it isn't broken
        broken_ec = broken_ec_tmpl % 'notbroken'
        script_cmd = script_cmd_tmpl % broken_ec
        fixed_ec_txt = fixed_ec_txt_tmpl % ("easyblock = 'ConfigureMake'\n\n", 'foo')

        write_file(broken_ec, fixed_ec_txt)
        # (dummy) ConfigureMake easyblock is available in test sandbox
        script_cmd = script_cmd_tmpl % broken_ec
        new_ec_txt = read_file(broken_ec)
        self.assertEqual(new_ec_txt, fixed_ec_txt)
        self.assertTrue(EasyConfig(None, rawtxt=new_ec_txt))
        self.assertFalse(os.path.exists('%s.bk' % broken_ec))  # no backup created if nothing was fixed

        broken_ec = broken_ec_tmpl % 'nosuchsoftware'
        script_cmd = script_cmd_tmpl % broken_ec
        broken_ec_txt = broken_ec_txt_tmpl % ('', 'nosuchsoftware')
        fixed_ec_txt = fixed_ec_txt_tmpl % ("easyblock = 'ConfigureMake'\n\n", 'nosuchsoftware')

        # broken easyconfig is fixed in place, original file is backed up
        write_file(broken_ec, broken_ec_txt)
        run_cmd(script_cmd)
        new_ec_txt = read_file(broken_ec)
        self.assertEqual(new_ec_txt, fixed_ec_txt)
        self.assertTrue(EasyConfig(None, rawtxt=new_ec_txt))
        self.assertEqual(read_file('%s.bk' % broken_ec), broken_ec_txt)
        self.assertFalse(os.path.exists('%s.bk1' % broken_ec))

        # broken easyconfig is fixed in place, original file is backed up, existing backup is not overwritten
        write_file(broken_ec, broken_ec_txt)
        write_file('%s.bk' % broken_ec, 'thisshouldnot\nbechanged')
        run_cmd(script_cmd)
        new_ec_txt = read_file(broken_ec)
        self.assertEqual(new_ec_txt, fixed_ec_txt)
        self.assertTrue(EasyConfig(None, rawtxt=new_ec_txt))
        self.assertEqual(read_file('%s.bk' % broken_ec), 'thisshouldnot\nbechanged')
        self.assertEqual(read_file('%s.bk1' % broken_ec), broken_ec_txt)

        # if easyblock is specified, that part is left untouched
        broken_ec = broken_ec_tmpl % 'footoy'
        script_cmd = script_cmd_tmpl % broken_ec
        broken_ec_txt = broken_ec_txt_tmpl % ("easyblock = 'EB_toy'\n\n", 'foo')
        fixed_ec_txt = fixed_ec_txt_tmpl % ("easyblock = 'EB_toy'\n\n", 'foo')

        write_file(broken_ec, broken_ec_txt)
        run_cmd(script_cmd)
        new_ec_txt = read_file(broken_ec)
        self.assertEqual(new_ec_txt, fixed_ec_txt)
        self.assertTrue(EasyConfig(None, rawtxt=new_ec_txt))
        self.assertEqual(read_file('%s.bk' % broken_ec), broken_ec_txt)

        # for existing easyblocks, "easyblock = 'ConfigureMake'" should *not* be added
        # EB_toy easyblock is available in test sandbox
        test_easyblocks = os.path.join(testdir, 'sandbox')
        broken_ec = broken_ec_tmpl % 'toy'
        # path to test easyblocks must be *appended* to PYTHONPATH (due to flattening in easybuild-easyblocks repo)
        script_cmd = script_cmd_tmpl % broken_ec
        broken_ec_txt = broken_ec_txt_tmpl % ('', 'toy')
        fixed_ec_txt = fixed_ec_txt_tmpl % ('', 'toy')
        write_file(broken_ec, broken_ec_txt)
        run_cmd(script_cmd)
        new_ec_txt = read_file(broken_ec)
        self.assertEqual(new_ec_txt, fixed_ec_txt)
        self.assertTrue(EasyConfig(None, rawtxt=new_ec_txt))
        self.assertEqual(read_file('%s.bk' % broken_ec), broken_ec_txt)

def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(ScriptsTest, sys.argv[1:])

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
