# #
# Copyright 2015-2018 Ghent University
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
Unit tests for packaging support.

@author: Kenneth Hoste (Ghent University)
"""
import os
import re
import stat
import sys

from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner

from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.tools.config import log_path
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import adjust_permissions, read_file, write_file
from easybuild.tools.package.utilities import ActivePNS, avail_package_naming_schemes, check_pkg_support, package
from easybuild.tools.version import VERSION as EASYBUILD_VERSION

FPM_OUTPUT_FILE = 'fpm_mocked.out'

# purposely using non-bash script, to detect issues with shebang line being ignored (run_cmd with shell=False)
MOCKED_FPM = """#!/usr/bin/env python
import os, sys

def verbose(msg):
    fp = open('%(fpm_output_file)s', 'a')
    fp.write(msg + '\\n')
    fp.close()

description, iteration, name, source, target, url, version, workdir = '', '', '', '', '', '', '', ''
excludes = []

verbose(' '.join(sys.argv[1:]))

idx = 1
while idx < len(sys.argv):

    if sys.argv[idx] == '--workdir':
        idx += 1
        workdir = sys.argv[idx]
        verbose('workdir'); verbose(workdir)

    elif sys.argv[idx] == '--name':
        idx += 1
        name = sys.argv[idx]

    elif sys.argv[idx] == '--version':
        idx += 1
        version = sys.argv[idx]
        verbose('version'); verbose(version)

    elif sys.argv[idx] == '--description':
        idx += 1
        description = sys.argv[idx]

    elif sys.argv[idx] == '--url':
        idx += 1
        url = sys.argv[idx]

    elif sys.argv[idx] == '--iteration':
        idx += 1
        iteration = sys.argv[idx]

    elif sys.argv[idx] == '-t':
        idx += 1
        target = sys.argv[idx]

    elif sys.argv[idx] == '-s':
        idx += 1
        source = sys.argv[idx]

    elif sys.argv[idx] == '--exclude':
        idx += 1
        excludes.append(sys.argv[idx])

    elif sys.argv[idx].startswith('--'):
        verbose("got an unhandled option: " + sys.argv[idx] + ' ' + sys.argv[idx+1])
        idx += 1

    else:
        installdir = sys.argv[idx]
        modulefile = sys.argv[idx+1]
        break

    idx += 1

pkgfile = os.path.join(workdir, name + '-' + version + '.' + iteration + '.' + target)

fp = open(pkgfile, 'w')

fp.write('thisisan' + target + '\\n')
fp.write(' '.join(sys.argv[1:]) + '\\n')
fp.write("STARTCONTENTS of installdir " + installdir + ':\\n')

find_cmd = 'find ' + installdir + '  ' + ''.join([" -not -path /" + x + ' ' for x in excludes])
verbose("trying: " + find_cmd)
fp.write(find_cmd + '\\n')

fp.write('ENDCONTENTS\\n')

fp.write("Contents of module file " + modulefile + ':')


fp.write('modulefile: ' + modulefile + '\\n')
#modtxt = open(modulefile).read()
#fp.write(modtxt + '\\n')

fp.write("I found excludes " + ' '.join(excludes) + '\\n')
fp.write("DESCRIPTION: " + description + '\\n')

fp.close()
"""


def mock_fpm(tmpdir):
    """Put mocked version of fpm command in place in specified tmpdir."""
    # put mocked 'fpm' command in place, just for testing purposes
    fpm = os.path.join(tmpdir, 'fpm')
    write_file(fpm, MOCKED_FPM % {'fpm_output_file': os.path.join(tmpdir, FPM_OUTPUT_FILE)})
    adjust_permissions(fpm, stat.S_IXUSR, add=True)

    # also put mocked rpmbuild in place
    rpmbuild = os.path.join(tmpdir, 'rpmbuild')
    write_file(rpmbuild, '#!/bin/bash')  # only needs to be there, doesn't need to actually do something...
    adjust_permissions(rpmbuild, stat.S_IXUSR, add=True)

    os.environ['PATH'] = '%s:%s' % (tmpdir, os.environ['PATH'])


class PackageTest(EnhancedTestCase):
    """Tests for packaging support."""

    def test_avail_package_naming_schemes(self):
        """Test avail_package_naming_schemes()"""
        self.assertEqual(sorted(avail_package_naming_schemes().keys()), ['EasyBuildPNS'])

    def test_check_pkg_support(self):
        """Test check_pkg_support()."""

        # clear $PATH to make sure fpm/rpmbuild can not be found
        os.environ['PATH'] = ''

        self.assertErrorRegex(EasyBuildError, "Selected packaging tool 'fpm' not found", check_pkg_support)

        for binary in ['fpm', 'rpmbuild']:
            binpath = os.path.join(self.test_prefix, binary)
            write_file(binpath, '#!/bin/bash')
            adjust_permissions(binpath, stat.S_IXUSR, add=True)
        os.environ['PATH'] = self.test_prefix

        # no errors => support check passes
        check_pkg_support()

    def test_active_pns(self):
        """Test use of ActivePNS."""
        topdir = os.path.dirname(os.path.abspath(__file__))
        test_easyconfigs = os.path.join(topdir, 'easyconfigs', 'test_ecs')
        ec = EasyConfig(os.path.join(test_easyconfigs, 'o', 'OpenMPI', 'OpenMPI-1.6.4-GCC-4.6.4.eb'), validate=False)

        pns = ActivePNS()

        # default: EasyBuild package naming scheme, pkg release 1
        self.assertEqual(pns.name(ec), 'OpenMPI-1.6.4-GCC-4.6.4')
        self.assertEqual(pns.version(ec), 'eb-%s' % EASYBUILD_VERSION)
        self.assertEqual(pns.release(ec), '1')

    def test_package(self):
        """Test package function."""
        build_options = {
            'package_tool_options': '--foo bar',
            'silent': True,
        }
        init_config(build_options=build_options)

        topdir = os.path.dirname(os.path.abspath(__file__))
        test_easyconfigs = os.path.join(topdir, 'easyconfigs', 'test_ecs')
        ec = EasyConfig(os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0-gompi-1.3.12-test.eb'), validate=False)

        mock_fpm(self.test_prefix)

        # import needs to be done here, since test easyblocks are only included later
        from easybuild.easyblocks.toy import EB_toy
        easyblock = EB_toy(ec)

        # build & install first
        easyblock.run_all_steps(False)

        # write a dummy log and report file to make sure they don't get packaged
        logfile = os.path.join(easyblock.installdir, log_path(), "logfile.log")
        write_file(logfile, "I'm a logfile")
        reportfile = os.path.join(easyblock.installdir, log_path(), "report.md")
        write_file(reportfile, "I'm a reportfile")

        # package using default packaging configuration (FPM to build RPM packages)
        pkgdir = package(easyblock)
        pkgfile = os.path.join(pkgdir, 'toy-0.0-gompi-1.3.12-test-eb-%s.1.rpm' % EASYBUILD_VERSION)

        fpm_output = read_file(os.path.join(self.test_prefix, FPM_OUTPUT_FILE))
        pkgtxt = read_file(pkgfile)
        #print "The FPM output"
        #print fpm_output
        #print "The Package File"
        #print pkgtxt

        self.assertTrue(os.path.isfile(pkgfile), "Found %s" % pkgfile)

        # check whether extra packaging options were passed down
        regex = re.compile("^got an unhandled option: --foo bar$", re.M)
        self.assertTrue(regex.search(fpm_output), "Pattern '%s' found in: %s" % (regex.pattern, fpm_output))

        pkgtxt = read_file(pkgfile)
        pkgtxt_regex = re.compile("STARTCONTENTS of installdir %s" % easyblock.installdir)
        self.assertTrue(pkgtxt_regex.search(pkgtxt), "Pattern '%s' found in: %s" % (pkgtxt_regex.pattern, pkgtxt))

        no_logfiles_regex = re.compile(r'STARTCONTENTS.*\.(log|md)$.*ENDCONTENTS', re.DOTALL|re.MULTILINE)
        self.assertFalse(no_logfiles_regex.search(pkgtxt), "Pattern not '%s' found in: %s" % (no_logfiles_regex.pattern, pkgtxt))

        toy_txt = read_file(os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0-gompi-1.3.12-test.eb'))
        replace_str = '''description = """Toy C program, 100% toy. Now with `backticks'\n'''
        replace_str += '''and newlines"""'''
        toy_txt = re.sub('description = .*', replace_str, toy_txt)
        toy_file = os.path.join(self.test_prefix, 'toy-test-description.eb')
        write_file(toy_file, toy_txt)

        regex = re.compile(r"""`backticks'""")
        self.assertTrue(regex.search(toy_txt), "Pattern '%s' found in: %s" % (regex.pattern, toy_txt))
        ec_desc = EasyConfig(toy_file, validate=False)
        easyblock_desc = EB_toy(ec_desc)
        easyblock_desc.run_all_steps(False)
        pkgdir = package(easyblock_desc)
        pkgfile = os.path.join(pkgdir, 'toy-0.0-gompi-1.3.12-test-eb-%s.1.rpm' % EASYBUILD_VERSION)
        self.assertTrue(os.path.isfile(pkgfile))
        pkgtxt = read_file(pkgfile)
        regex_pkg = re.compile(r"""DESCRIPTION:.*`backticks'.*""")
        self.assertTrue(regex_pkg.search(pkgtxt), "Pattern '%s' not found in: %s" % (regex_pkg.pattern, pkgtxt))
        regex_pkg = re.compile(r"""DESCRIPTION:.*\nand newlines""", re.MULTILINE)
        self.assertTrue(regex_pkg.search(pkgtxt), "Pattern '%s' not found in: %s" % (regex_pkg.pattern, pkgtxt))


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(PackageTest, sys.argv[1:])


if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
