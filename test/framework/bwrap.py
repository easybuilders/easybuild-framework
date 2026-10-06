# #
# Copyright 2026-2026 Ghent University
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
Unit tests for functionality in easybuild.tools.bwrap

@author: Samuel Moors (Vrije Universiteit Brussel)
"""
import os
import re
import sys
from test.framework import TEST_ECS_DIR, TOY_EC_TXT
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner

from easybuild.framework.easyconfig.tools import parse_easyconfigs
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.bwrap import det_install_subdirs
from easybuild.tools.filetools import write_file
from easybuild.tools.robot import resolve_dependencies


class BwrapTest(EnhancedTestCase):
    """Tests for bwrap support"""

    def test_det_install_subdirs(self):
        """Test det_install_subdirs function."""
        build_options = {
            'check_osdeps': False,
            'robot_path': TEST_ECS_DIR,
            'validate': False,
        }
        gzip_ec = os.path.join(TEST_ECS_DIR, 'g', 'gzip', 'gzip-1.5-foss-2018a.eb')

        # install subdirs must not depend on the module naming scheme (cfr. module subdirs with HMNS)
        expected = [
            'FFTW/3.3.7-gompi-2018a',
            'GCC/6.4.0-2.28',
            'OpenBLAS/0.2.20-GCC-6.4.0-2.28',
            'OpenMPI/2.1.2-GCC-6.4.0-2.28',
            'ScaLAPACK/2.0.2-gompi-2018a-OpenBLAS-0.2.20',
            'foss/2018a',
            'gompi/2018a',
            'gzip/1.5-foss-2018a',
            'hwloc/1.11.8-GCC-6.4.0-2.28',
        ]
        for mns in ['EasyBuildMNS', 'HierarchicalMNS']:
            os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = mns
            init_config(build_options=build_options)
            ecs, _ = parse_easyconfigs([(gzip_ec, False)])
            specs = resolve_dependencies(ecs, self.modtool, retain_all_deps=True)
            self.assertEqual(sorted(det_install_subdirs(specs)), expected)

        # without fixed installdir naming scheme, HMNS install subdirs are full module names
        init_config(build_options=dict(build_options, fixed_installdir_naming_scheme=False))
        ecs, _ = parse_easyconfigs([(gzip_ec, False)])
        specs = resolve_dependencies(ecs, self.modtool, retain_all_deps=True)
        res = det_install_subdirs(specs)
        self.assertEqual(res, [spec['full_mod_name'] for spec in specs])
        self.assertIn('MPI/GCC/6.4.0-2.28/OpenMPI/2.1.2/gzip/1.5', res)

        # dummy entries for dependencies without an easyconfig are skipped
        del os.environ['EASYBUILD_MODULE_NAMING_SCHEME']
        init_config(build_options=build_options)
        self.assertEqual(det_install_subdirs([{'dependencies': [], 'ec': None, 'full_mod_name': 'foo/1.0',
                                               'spec': None}]), [])

        # easyconfigs with data_sources are not supported, all of them are listed in the error
        toy_data_txt = re.sub('^sources = ', 'data_sources = ', TOY_EC_TXT, flags=re.M)
        toy_data_ecs = []
        for version in ['0.0', '0.1']:
            toy_data_ec = os.path.join(self.test_prefix, f'toy-{version}.eb')
            write_file(toy_data_ec, re.sub('^version = .*', f"version = '{version}'", toy_data_txt, flags=re.M))
            toy_data_ecs.append(toy_data_ec)
        gzip_ec = os.path.join(TEST_ECS_DIR, 'g', 'gzip', 'gzip-1.4.eb')
        specs, _ = parse_easyconfigs([(ec, False) for ec in toy_data_ecs + [gzip_ec]])
        error_pattern = r"'data_sources' is not supported \(yet\) with --bwrap:\n\* %s\n\* %s$" % tuple(toy_data_ecs)
        self.assertRaisesRegex(EasyBuildError, error_pattern, det_install_subdirs, specs)


def suite(loader=None):
    """ returns all the testcases in this module """
    if loader:
        return loader.loadTestsFromTestCase(BwrapTest)
    else:
        return TestLoaderFiltered().loadTestsFromTestCase(BwrapTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
