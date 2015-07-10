# #
# Copyright 2015-2015 Ghent University
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
Unit tests for packaging support.

@author: Kenneth Hoste (Ghent University)
"""
import os
import stat

from test.framework.utilities import EnhancedTestCase, init_config
from unittest import TestLoader
from unittest import main as unittestmain

import easybuild.tools.build_log
from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import adjust_permissions, write_file
from easybuild.tools.package.utilities import ActivePNS, avail_package_naming_schemes, check_pkg_support, package
from easybuild.tools.version import VERSION as EASYBUILD_VERSION


MOCKED_FPM = """#!/bin/bash
# only parse what we need to spit out the expected package file, ignore the rest
workdir=`echo $@ | sed 's/--workdir \([^ ]*\).*/\\1/g'`
name=`echo $@ | sed 's/.* --name \([^ ]*\).*/\\1/g'`
version=`echo $@ | sed 's/.*--version \([^ ]*\).*/\\1/g'`
iteration=`echo $@ | sed 's/.*--iteration \([^ ]*\).*/\\1/g'`
target=`echo $@ | sed 's/.*-t \([^ ]*\).*/\\1/g'`

echo "thisisan$target" > ${workdir}/${name}-${version}.${iteration}.${target}
"""


def mock_fpm(tmpdir):
    """Put mocked version of fpm command in place in specified tmpdir."""
    # put mocked 'fpm' command in place, just for testing purposes
    fpm = os.path.join(tmpdir, 'fpm')
    write_file(fpm, MOCKED_FPM)
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
        # hard enable experimental
        orig_experimental = easybuild.tools.build_log.EXPERIMENTAL
        easybuild.tools.build_log.EXPERIMENTAL = True

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

        # restore
        easybuild.tools.build_log.EXPERIMENTAL = orig_experimental

    def test_active_pns(self):
        """Test use of ActivePNS."""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        ec = EasyConfig(os.path.join(test_easyconfigs, 'OpenMPI-1.6.4-GCC-4.6.4.eb'), validate=False)

        pns = ActivePNS()

        # default: EasyBuild package naming scheme, pkg release 1
        self.assertEqual(pns.name(ec), 'OpenMPI-1.6.4-GCC-4.6.4')
        self.assertEqual(pns.version(ec), 'eb-%s' % EASYBUILD_VERSION)
        self.assertEqual(pns.release(ec), '1')

    def test_package(self):
        """Test package function."""
        init_config(build_options={'silent': True})

        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        ec = EasyConfig(os.path.join(test_easyconfigs, 'toy-0.0-gompi-1.3.12-test.eb'), validate=False)

        mock_fpm(self.test_prefix)

        # import needs to be done here, since test easyblocks are only included later
        from easybuild.easyblocks.toy import EB_toy
        easyblock = EB_toy(ec)

        # build & install first
        easyblock.run_all_steps(False)

        # package using default packaging configuration (FPM to build RPM packages)
        pkgdir = package(easyblock)

        pkgfile = os.path.join(pkgdir, 'toy-0.0-gompi-1.3.12-test-eb-%s.1.rpm' % EASYBUILD_VERSION)
        self.assertTrue(os.path.isfile(pkgfile), "Found %s" % pkgfile)


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(PackageTest)


if __name__ == '__main__':
    unittestmain()
