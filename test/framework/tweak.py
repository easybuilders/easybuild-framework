##
# Copyright 2014-2021 Ghent University
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
##
"""
Unit tests for framework/easyconfig/tweak.py

@author: Kenneth Hoste (Ghent University)
"""
import os
import sys
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner

from easybuild.framework.easyconfig.easyconfig import get_toolchain_hierarchy, process_easyconfig
from easybuild.framework.easyconfig.parser import EasyConfigParser
from easybuild.framework.easyconfig.tweak import find_matching_easyconfigs, obtain_ec_for, pick_version, tweak_one
from easybuild.framework.easyconfig.tweak import check_capability_mapping, match_minimum_tc_specs
from easybuild.framework.easyconfig.tweak import get_dep_tree_of_toolchain, map_common_versionsuffixes
from easybuild.framework.easyconfig.tweak import get_matching_easyconfig_candidates, map_toolchain_hierarchies
from easybuild.framework.easyconfig.tweak import find_potential_version_mappings
from easybuild.framework.easyconfig.tweak import map_easyconfig_to_target_tc_hierarchy
from easybuild.framework.easyconfig.tweak import list_deps_versionsuffixes
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import module_classes
from easybuild.tools.filetools import change_dir, write_file


class TweakTest(EnhancedTestCase):
    """Tests for tweak functionality."""

    def test_pick_version(self):
        """Test pick_version function."""
        # if required version is not available, the most recent version less than or equal should be returned
        self.assertEqual(('1.4', '1.0'), pick_version('1.4', ['0.5', '1.0', '1.5']))

        # if required version is available, that should be what's returned
        self.assertEqual(('0.5', '0.5'), pick_version('0.5', ['0.5', '1.0', '1.5']))
        self.assertEqual(('1.0', '1.0'), pick_version('1.0', ['0.5', '1.0', '1.5']))
        self.assertEqual(('1.5', '1.5'), pick_version('1.5', ['0.5', '1.0', '1.5']))

        # if no required version is specified, most recent version is picked
        self.assertEqual(('1.5', '1.5'), pick_version(None, ['0.5', '1.0', '1.5']))

        # if only a single version is available, there's nothing much to choose from
        self.assertEqual(('1.4', '0.5'), pick_version('1.4', ['0.5']))
        self.assertEqual(('0.5', '0.5'), pick_version(None, ['0.5']))

        # check correct ordering of versions (not alphabetical ordering!)
        self.assertEqual(('1.12', '1.10'), pick_version('1.12', ['1.5', '1.20', '1.1', '1.50', '1.10', '1.9', '1.8']))

        # if no older versions are available, oldest available version is returned
        self.assertEqual(('0.8', '1.1'), pick_version('0.8', ['1.5', '1.1', '1.10', '1.8']))

    def test_find_matching_easyconfigs(self):
        """Test find_matching_easyconfigs function."""
        test_easyconfigs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        for (name, installver) in [('GCC', '4.8.2'), ('gzip', '1.5-foss-2018a')]:
            ecs = find_matching_easyconfigs(name, installver, [test_easyconfigs_path])
            self.assertTrue(len(ecs) == 1 and ecs[0].endswith('/%s-%s.eb' % (name, installver)))

        ecs = find_matching_easyconfigs('GCC', '*', [test_easyconfigs_path])
        gccvers = ['4.6.3', '4.6.4', '4.8.2', '4.8.3', '4.9.2', '4.9.3-2.25', '4.9.3-2.26', '6.4.0-2.28', '7.3.0-2.30']
        self.assertEqual(len(ecs), len(gccvers))
        ecs_basename = [os.path.basename(ec) for ec in ecs]
        for gccver in gccvers:
            gcc_ec = 'GCC-%s.eb' % gccver
            self.assertTrue(gcc_ec in ecs_basename, "%s is included in %s" % (gcc_ec, ecs_basename))

    def test_obtain_ec_for(self):
        """Test obtain_ec_for function."""
        init_config(build_options={'silent': True})

        test_easyconfigs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        # find existing easyconfigs
        specs = {
            'name': 'GCC',
            'version': '6.4.0',
            'versionsuffix': '-2.28',
        }
        (generated, ec_file) = obtain_ec_for(specs, [test_easyconfigs_path])
        self.assertFalse(generated)
        self.assertEqual(os.path.basename(ec_file), 'GCC-6.4.0-2.28.eb')

        specs = {
            'name': 'ScaLAPACK',
            'version': '2.0.2',
            'toolchain_name': 'gompi',
            'toolchain_version': '2018a',
            'versionsuffix': '-OpenBLAS-0.2.20',
        }
        (generated, ec_file) = obtain_ec_for(specs, [test_easyconfigs_path])
        self.assertFalse(generated)
        self.assertEqual(os.path.basename(ec_file), 'ScaLAPACK-2.0.2-gompi-2018a-OpenBLAS-0.2.20.eb')

        specs = {
            'name': 'ifort',
            'versionsuffix': '-GCC-4.9.3-2.25',
        }
        (generated, ec_file) = obtain_ec_for(specs, [test_easyconfigs_path])
        self.assertFalse(generated)
        self.assertEqual(os.path.basename(ec_file), 'ifort-2016.1.150-GCC-4.9.3-2.25.eb')

        # latest version if not specified
        specs = {
            'name': 'GCC',
        }
        (generated, ec_file) = obtain_ec_for(specs, [test_easyconfigs_path])
        self.assertFalse(generated)
        self.assertEqual(os.path.basename(ec_file), 'GCC-7.3.0-2.30.eb')

        # generate non-existing easyconfig
        change_dir(self.test_prefix)
        specs = {
            'name': 'GCC',
            'version': '4.9.0',
        }
        (generated, ec_file) = obtain_ec_for(specs, [test_easyconfigs_path])
        self.assertTrue(generated)
        self.assertEqual(os.path.basename(ec_file), 'GCC-4.9.0.eb')

    def test_tweak_one_version(self):
        """Test tweak_one function"""
        test_easyconfigs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_easyconfigs_path, 't', 'toy', 'toy-0.0.eb')

        # test tweaking of software version (--try-software-version)
        tweaked_toy_ec = os.path.join(self.test_prefix, 'toy-tweaked.eb')
        tweak_one(toy_ec, tweaked_toy_ec, {'version': '1.2.3'})

        toy_ec_parsed = EasyConfigParser(toy_ec).get_config_dict()
        tweaked_toy_ec_parsed = EasyConfigParser(tweaked_toy_ec).get_config_dict()

        # checksums should be reset to empty list, only version should be changed, nothing else
        self.assertEqual(tweaked_toy_ec_parsed['checksums'], [])
        self.assertEqual(tweaked_toy_ec_parsed['version'], '1.2.3')
        for key in [k for k in toy_ec_parsed.keys() if k not in ['checksums', 'version']]:
            val = toy_ec_parsed[key]
            self.assertTrue(key in tweaked_toy_ec_parsed, "Parameter '%s' not defined in tweaked easyconfig file" % key)
            tweaked_val = tweaked_toy_ec_parsed.get(key)
            self.assertEqual(val, tweaked_val, "Different value for %s parameter: %s vs %s" % (key, val, tweaked_val))

        # check behaviour if target file already exists
        error_pattern = "File exists, not overwriting it without --force"
        self.assertErrorRegex(EasyBuildError, error_pattern, tweak_one, toy_ec, tweaked_toy_ec, {'version': '1.2.3'})

        # existing file does get overwritten when --force is used
        init_config(build_options={'force': True, 'silent': True})
        write_file(tweaked_toy_ec, '')
        tweak_one(toy_ec, tweaked_toy_ec, {'version': '1.2.3'})
        tweaked_toy_ec_parsed = EasyConfigParser(tweaked_toy_ec).get_config_dict()
        self.assertEqual(tweaked_toy_ec_parsed['version'], '1.2.3')

    def test_check_capability_mapping(self):
        """Test comparing the functionality of two toolchains"""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        init_config(build_options={
            'valid_module_classes': module_classes(),
            'robot_path': test_easyconfigs,
        })
        get_toolchain_hierarchy.clear()
        foss_hierarchy = get_toolchain_hierarchy({'name': 'foss', 'version': '2018a'}, incl_capabilities=True)
        iimpi_hierarchy = get_toolchain_hierarchy({'name': 'iimpi', 'version': '2016.01'},
                                                  incl_capabilities=True)

        # Hierarchies are returned with top-level toolchain last, foss has 4 elements here, intel has 2
        self.assertEqual(foss_hierarchy[0]['name'], 'GCC')
        self.assertEqual(foss_hierarchy[1]['name'], 'golf')
        self.assertEqual(foss_hierarchy[2]['name'], 'gompi')
        self.assertEqual(foss_hierarchy[3]['name'], 'foss')
        self.assertEqual(iimpi_hierarchy[0]['name'], 'GCCcore')
        self.assertEqual(iimpi_hierarchy[1]['name'], 'iccifort')
        self.assertEqual(iimpi_hierarchy[2]['name'], 'iimpi')

        # golf <-> iimpi (should return False)
        self.assertFalse(check_capability_mapping(foss_hierarchy[1], iimpi_hierarchy[1]), "golf requires math libs")
        # gompi <-> iimpi
        self.assertTrue(check_capability_mapping(foss_hierarchy[2], iimpi_hierarchy[2]))
        # GCC <-> iimpi
        self.assertTrue(check_capability_mapping(foss_hierarchy[0], iimpi_hierarchy[2]))
        # GCC <-> iccifort
        self.assertTrue(check_capability_mapping(foss_hierarchy[0], iimpi_hierarchy[1]))
        # GCC <-> GCCcore
        self.assertTrue(check_capability_mapping(foss_hierarchy[0], iimpi_hierarchy[0]))

    def test_match_minimum_tc_specs(self):
        """Test matching a toolchain to lowest possible in a hierarchy"""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        init_config(build_options={
            'robot_path': test_easyconfigs,
            'silent': True,
            'valid_module_classes': module_classes(),
        })
        get_toolchain_hierarchy.clear()
        foss_hierarchy = get_toolchain_hierarchy({'name': 'foss', 'version': '2018a'}, incl_capabilities=True)
        iimpi_hierarchy = get_toolchain_hierarchy({'name': 'iimpi', 'version': '2016.01'},
                                                  incl_capabilities=True)
        # Hierarchies are returned with top-level toolchain last, foss has 4 elements here, intel has 2
        self.assertEqual(foss_hierarchy[0]['name'], 'GCC')
        self.assertEqual(foss_hierarchy[1]['name'], 'golf')
        self.assertEqual(foss_hierarchy[2]['name'], 'gompi')
        self.assertEqual(foss_hierarchy[3]['name'], 'foss')
        self.assertEqual(iimpi_hierarchy[0]['name'], 'GCCcore')
        self.assertEqual(iimpi_hierarchy[1]['name'], 'iccifort')
        self.assertEqual(iimpi_hierarchy[2]['name'], 'iimpi')

        # base compiler first (GCCcore which maps to GCC/6.4.0-2.28)
        self.assertEqual(match_minimum_tc_specs(iimpi_hierarchy[0], foss_hierarchy),
                         {'name': 'GCC', 'version': '6.4.0-2.28'})
        # then iccifort (which also maps to GCC/6.4.0-2.28)
        self.assertEqual(match_minimum_tc_specs(iimpi_hierarchy[1], foss_hierarchy),
                         {'name': 'GCC', 'version': '6.4.0-2.28'})
        # Then MPI
        self.assertEqual(match_minimum_tc_specs(iimpi_hierarchy[2], foss_hierarchy),
                         {'name': 'gompi', 'version': '2018a'})
        # Check against own math only subtoolchain for math
        self.assertEqual(match_minimum_tc_specs(foss_hierarchy[1], foss_hierarchy),
                         {'name': 'golf', 'version': '2018a'})
        # Make sure there's an error when we can't do the mapping
        error_msg = "No possible mapping from source toolchain spec .*"
        self.assertErrorRegex(EasyBuildError, error_msg, match_minimum_tc_specs,
                              foss_hierarchy[3], iimpi_hierarchy)

    def test_dep_tree_of_toolchain(self):
        """Test getting list of dependencies of a toolchain (as EasyConfig objects)"""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        init_config(build_options={
            'valid_module_classes': module_classes(),
            'robot_path': test_easyconfigs,
            'check_osdeps': False,
        })
        toolchain_spec = {'name': 'foss', 'version': '2018a'}
        list_of_deps = get_dep_tree_of_toolchain(toolchain_spec, self.modtool)
        expected_deps = [
            ['GCC', '6.4.0'],
            ['OpenBLAS', '0.2.20'],
            ['hwloc', '1.11.8'],
            ['OpenMPI', '2.1.2'],
            ['gompi', '2018a'],
            ['FFTW', '3.3.7'],
            ['ScaLAPACK', '2.0.2'],
            ['foss', '2018a']
        ]
        actual_deps = [[dep['name'], dep['version']] for dep in list_of_deps]
        self.assertEqual(expected_deps, actual_deps)

    def test_map_toolchain_hierarchies(self):
        """Test mapping between two toolchain hierarchies"""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        init_config(build_options={
            'robot_path': test_easyconfigs,
            'silent': True,
            'valid_module_classes': module_classes(),
        })
        get_toolchain_hierarchy.clear()
        foss_tc = {'name': 'foss', 'version': '2018a'}
        gompi_tc = {'name': 'gompi', 'version': '2018a'}
        iimpi_tc = {'name': 'iimpi', 'version': '2016.01'}

        # GCCcore is mapped to GCC, iccifort is mapped to GCC, iimpi is mapped to gompi
        expected = {
            'GCCcore': {'name': 'GCC', 'version': '6.4.0-2.28'},
            'iccifort': {'name': 'GCC', 'version': '6.4.0-2.28'},
            'iimpi': {'name': 'gompi', 'version': '2018a'},
        }
        self.assertEqual(map_toolchain_hierarchies(iimpi_tc, foss_tc, self.modtool), expected)

        # GCC is mapped to iccifort, gompi is mapped to iimpi
        expected = {
            'GCC': {'name': 'iccifort', 'version': '2016.1.150-GCC-4.9.3-2.25'},
            'gompi': {'name': 'iimpi', 'version': '2016.01'}
        }
        self.assertEqual(map_toolchain_hierarchies(gompi_tc, iimpi_tc, self.modtool), expected)

        # Expect an error when there is no possible mapping
        error_msg = "No possible mapping from source toolchain spec .*"
        self.assertErrorRegex(EasyBuildError, error_msg, map_toolchain_hierarchies,
                              foss_tc, iimpi_tc, self.modtool)

        # Test that we correctly include GCCcore binutils when it is there
        gcc_binutils_tc = {'name': 'GCC', 'version': '4.9.3-2.26'}
        iccifort_binutils_tc = {'name': 'iccifort', 'version': '2016.1.150-GCC-4.9.3-2.25'}
        # Should see a binutils in the mapping (2.26 will get mapped to 2.25)
        expected = {
            'GCC': {'name': 'iccifort', 'version': '2016.1.150-GCC-4.9.3-2.25'},
            'GCCcore': {'name': 'GCCcore', 'version': '4.9.3'},
            'binutils': {'version': '2.25', 'versionsuffix': ''}
        }
        self.assertEqual(map_toolchain_hierarchies(gcc_binutils_tc, iccifort_binutils_tc, self.modtool), expected)

    def test_get_matching_easyconfig_candidates(self):
        """Test searching for easyconfig candidates based on a stub and toolchain"""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        init_config(build_options={
            'valid_module_classes': module_classes(),
            'robot_path': [test_easyconfigs],
        })
        toolchain = {'name': 'GCC', 'version': '4.9.3-2.26'}
        paths, toolchain_suff = get_matching_easyconfig_candidates('gzip-', toolchain)
        expected_toolchain_suff = '-GCC-4.9.3-2.26'
        self.assertEqual(toolchain_suff, expected_toolchain_suff)
        expected_paths = [os.path.join(test_easyconfigs, 'g', 'gzip', 'gzip-1.4' + expected_toolchain_suff + '.eb')]
        self.assertEqual(paths, expected_paths)

        paths, toolchain_stub = get_matching_easyconfig_candidates('nosuchmatch', toolchain)
        self.assertEqual(paths, [])
        self.assertEqual(toolchain_stub, expected_toolchain_suff)

    def test_map_common_versionsuffixes(self):
        """Test mapping between two toolchain hierarchies"""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        init_config(build_options={
            'robot_path': [test_easyconfigs],
            'silent': True,
            'valid_module_classes': module_classes(),
        })
        get_toolchain_hierarchy.clear()

        gcc_binutils_tc = {'name': 'GCC', 'version': '4.9.3-2.26'}
        iccifort_binutils_tc = {'name': 'iccifort', 'version': '2016.1.150-GCC-4.9.3-2.25'}

        toolchain_mapping = map_toolchain_hierarchies(iccifort_binutils_tc, gcc_binutils_tc, self.modtool)
        possible_mappings = map_common_versionsuffixes('binutils', iccifort_binutils_tc, toolchain_mapping)
        self.assertEqual(possible_mappings, {'-binutils-2.25': '-binutils-2.26'})

        # Make sure we only map upwards, here it's gzip 1.4 in gcc and 1.6 in iccifort
        possible_mappings = map_common_versionsuffixes('gzip', iccifort_binutils_tc, toolchain_mapping)
        self.assertEqual(possible_mappings, {})

        # newer gzip is picked up other way around (GCC -> iccifort)
        toolchain_mapping = map_toolchain_hierarchies(gcc_binutils_tc, iccifort_binutils_tc, self.modtool)
        possible_mappings = map_common_versionsuffixes('gzip', gcc_binutils_tc, toolchain_mapping)
        self.assertEqual(possible_mappings, {'-gzip-1.4': '-gzip-1.6'})

    def test_find_potential_version_mappings(self):
        """Test ability to find potential version mappings of a dependency for a given toolchain mapping"""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        init_config(build_options={
            'robot_path': [test_easyconfigs],
            'silent': True,
            'valid_module_classes': module_classes(),
        })
        get_toolchain_hierarchy.clear()

        gcc_binutils_tc = {'name': 'GCC', 'version': '4.9.3-2.26'}
        iccifort_binutils_tc = {'name': 'iccifort', 'version': '2016.1.150-GCC-4.9.3-2.25'}
        # The below mapping includes a binutils mapping (2.26 to 2.25)
        tc_mapping = map_toolchain_hierarchies(gcc_binutils_tc, iccifort_binutils_tc, self.modtool)
        ec_spec = os.path.join(test_easyconfigs, 'h', 'hwloc', 'hwloc-1.6.2-GCC-4.9.3-2.26.eb')
        parsed_ec = process_easyconfig(ec_spec)[0]
        gzip_dep = [dep for dep in parsed_ec['ec']['dependencies'] if dep['name'] == 'gzip'][0]
        self.assertEqual(gzip_dep['full_mod_name'], 'gzip/1.4-GCC-4.9.3-2.26')

        potential_versions = find_potential_version_mappings(gzip_dep, tc_mapping)
        self.assertEqual(len(potential_versions), 1)
        # Should see version 1.6 of gzip with iccifort toolchain
        expected = {
            'path': os.path.join(test_easyconfigs, 'g', 'gzip', 'gzip-1.6-iccifort-2016.1.150-GCC-4.9.3-2.25.eb'),
            'toolchain': {'name': 'iccifort', 'version': '2016.1.150-GCC-4.9.3-2.25'},
            'version': '1.6',
            'versionsuffix': '',
        }
        self.assertEqual(potential_versions[0], expected)

        # Test that we can override respecting the versionsuffix

        # Create toolchain mapping for OpenBLAS
        gcc_4_tc = {'name': 'GCC', 'version': '4.8.2'}
        gcc_6_tc = {'name': 'GCC', 'version': '6.4.0-2.28'}
        tc_mapping = map_toolchain_hierarchies(gcc_4_tc, gcc_6_tc, self.modtool)
        # Create a dep with the necessary params (including versionsuffix)
        openblas_dep = {
            'toolchain': {'version': '4.8.2', 'name': 'GCC'},
            'name': 'OpenBLAS',
            'system': False,
            'versionsuffix': '-LAPACK-3.4.2',
            'version': '0.2.8'
        }

        self.mock_stderr(True)
        potential_versions = find_potential_version_mappings(openblas_dep, tc_mapping)
        errtxt = self.get_stderr()
        warning_stub = "\nWARNING: There may be newer version(s) of dep 'OpenBLAS' available with a different " \
                       "versionsuffix to '-LAPACK-3.4.2'"
        self.mock_stderr(False)
        self.assertTrue(errtxt.startswith(warning_stub))
        self.assertEqual(len(potential_versions), 0)
        potential_versions = find_potential_version_mappings(openblas_dep, tc_mapping, ignore_versionsuffixes=True)
        self.assertEqual(len(potential_versions), 1)
        expected = {
            'path': os.path.join(test_easyconfigs, 'o', 'OpenBLAS', 'OpenBLAS-0.2.20-GCC-6.4.0-2.28.eb'),
            'toolchain': {'version': '6.4.0-2.28', 'name': 'GCC'},
            'version': '0.2.20',
            'versionsuffix': '',
        }
        self.assertEqual(potential_versions[0], expected)

    def test_map_easyconfig_to_target_tc_hierarchy(self):
        """Test mapping of easyconfig to target hierarchy"""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        build_options = {
            'robot_path': [test_easyconfigs],
            'silent': True,
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)
        get_toolchain_hierarchy.clear()

        gcc_binutils_tc = {'name': 'GCC', 'version': '4.9.3-2.26'}
        iccifort_binutils_tc = {'name': 'iccifort', 'version': '2016.1.150-GCC-4.9.3-2.25'}
        # The below mapping includes a binutils mapping (2.26 to 2.25)
        tc_mapping = map_toolchain_hierarchies(gcc_binutils_tc, iccifort_binutils_tc, self.modtool)
        ec_spec = os.path.join(test_easyconfigs, 'h', 'hwloc', 'hwloc-1.6.2-GCC-4.9.3-2.26.eb')
        tweaked_spec = map_easyconfig_to_target_tc_hierarchy(ec_spec, tc_mapping)
        tweaked_ec = process_easyconfig(tweaked_spec)[0]
        tweaked_dict = tweaked_ec['ec'].asdict()
        # First check the mapped toolchain
        key, value = 'toolchain', iccifort_binutils_tc
        self.assertTrue(key in tweaked_dict and value == tweaked_dict[key])
        # Also check that binutils has been mapped
        for key, value in {'name': 'binutils', 'version': '2.25', 'versionsuffix': ''}.items():
            self.assertTrue(key in tweaked_dict['builddependencies'][0] and
                            value == tweaked_dict['builddependencies'][0][key])

        # Now test the case where we try to update the dependencies
        init_config(build_options=build_options)
        get_toolchain_hierarchy.clear()
        tweaked_spec = map_easyconfig_to_target_tc_hierarchy(ec_spec, tc_mapping, update_dep_versions=True)
        tweaked_ec = process_easyconfig(tweaked_spec)[0]
        tweaked_dict = tweaked_ec['ec'].asdict()
        # First check the mapped toolchain
        key, value = 'toolchain', iccifort_binutils_tc
        self.assertTrue(key in tweaked_dict and value == tweaked_dict[key])
        # Also check that binutils has been mapped
        for key, value in {'name': 'binutils', 'version': '2.25', 'versionsuffix': ''}.items():
            self.assertTrue(
                key in tweaked_dict['builddependencies'][0] and value == tweaked_dict['builddependencies'][0][key]
            )
        # Also check that the gzip dependency was upgraded
        for key, value in {'name': 'gzip', 'version': '1.6', 'versionsuffix': ''}.items():
            self.assertTrue(key in tweaked_dict['dependencies'][0] and value == tweaked_dict['dependencies'][0][key])

        # Make sure there are checksums for our next test
        self.assertTrue(tweaked_dict['checksums'])

        # Test the case where we also update the software version at the same time
        init_config(build_options=build_options)
        get_toolchain_hierarchy.clear()
        new_version = '1.x.3'
        tweaked_spec = map_easyconfig_to_target_tc_hierarchy(ec_spec,
                                                             tc_mapping,
                                                             update_build_specs={'version': new_version},
                                                             update_dep_versions=True)
        tweaked_ec = process_easyconfig(tweaked_spec)[0]
        tweaked_dict = tweaked_ec['ec'].asdict()
        # First check the mapped toolchain
        key, value = 'toolchain', iccifort_binutils_tc
        self.assertTrue(key in tweaked_dict and value == tweaked_dict[key])
        # Also check that binutils has been mapped
        for key, value in {'name': 'binutils', 'version': '2.25', 'versionsuffix': ''}.items():
            self.assertTrue(
                key in tweaked_dict['builddependencies'][0] and value == tweaked_dict['builddependencies'][0][key]
            )
        # Also check that the gzip dependency was upgraded
        for key, value in {'name': 'gzip', 'version': '1.6', 'versionsuffix': ''}.items():
            self.assertTrue(key in tweaked_dict['dependencies'][0] and value == tweaked_dict['dependencies'][0][key])

        # Finally check that the version was upgraded
        key, value = 'version', new_version
        self.assertTrue(key in tweaked_dict and value == tweaked_dict[key])
        # and that the checksum was removed
        self.assertFalse(tweaked_dict['checksums'])

        # Check that if we update a software version, it also updates the version if the software appears in an
        # extension list (like for a PythonBundle)
        ec_spec = os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0-gompi-2018a-test.eb')
        # Create the trivial toolchain mapping
        toolchain = {'name': 'gompi', 'version': '2018a'}
        tc_mapping = map_toolchain_hierarchies(toolchain, toolchain, self.modtool)
        # Update the software version
        init_config(build_options=build_options)
        get_toolchain_hierarchy.clear()
        new_version = '1.x.3'
        tweaked_spec = map_easyconfig_to_target_tc_hierarchy(ec_spec,
                                                             tc_mapping,
                                                             update_build_specs={'version': new_version},
                                                             update_dep_versions=False)
        tweaked_ec = process_easyconfig(tweaked_spec)[0]
        extensions = tweaked_ec['ec']['exts_list']
        # check one extension with the same name exists and that the version has been updated
        hit_extension = 0
        for extension in extensions:
            if isinstance(extension, tuple) and extension[0] == 'toy':
                self.assertEqual(extension[1], new_version)
                # Make sure checksum has been purged
                self.assertFalse('checksums' in extension[2])
                hit_extension += 1
        self.assertEqual(hit_extension, 1, "Should only have updated one extension")

    def test_list_deps_versionsuffixes(self):
        """Test listing of dependencies' version suffixes"""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        build_options = {
            'robot_path': [test_easyconfigs],
            'silent': True,
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)
        get_toolchain_hierarchy.clear()

        ec_spec = os.path.join(test_easyconfigs, 'g', 'golf', 'golf-2018a.eb')
        self.assertEqual(list_deps_versionsuffixes(ec_spec), ['-serial'])
        ec_spec = os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0-deps.eb')
        self.assertEqual(list_deps_versionsuffixes(ec_spec), [])
        ec_spec = os.path.join(test_easyconfigs, 'g', 'gzip', 'gzip-1.4-GCC-4.6.3.eb')
        self.assertEqual(list_deps_versionsuffixes(ec_spec), ['-deps'])


def suite():
    """ return all the tests in this file """
    return TestLoaderFiltered().loadTestsFromTestCase(TweakTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
