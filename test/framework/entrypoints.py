# #
# Copyright 2013-2025 Ghent University
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
Unit tests for EasyBuild configuration.

@author: Davide Grassano (CECAM - EPFL)
"""

import os
import shutil
import sys
import tempfile
from importlib import reload
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner

import easybuild.tools.options as eboptions
from easybuild.tools.filetools import write_file
from easybuild.tools.docs import list_easyblocks, list_toolchains
from easybuild.tools.entrypoints import (
    get_group_entrypoints, HOOKS_ENTRYPOINT, EASYBLOCK_ENTRYPOINT, TOOLCHAIN_ENTRYPOINT,
    HAVE_ENTRY_POINTS
)
from easybuild.framework.easyconfig.easyconfig import get_module_path


if HAVE_ENTRY_POINTS:
    from importlib.metadata import DistributionFinder, Distribution
else:
    DistributionFinder = object
    Distribution = object


MOCK_HOOK_EP_NAME = "mock_hook"
MOCK_EASYBLOCK_EP_NAME = "mock_easyblock"
MOCK_TOOLCHAIN_EP_NAME = "mock_toolchain"

MOCK_HOOK = "hello_world"
MOCK_EASYBLOCK = "TestEasyBlock"
MOCK_TOOLCHAIN = "MockTc"


MOCK_EP_FILE = f"""
from easybuild.tools.entrypoints import register_entrypoint_hooks
from easybuild.tools.hooks import CONFIGURE_STEP, START


@register_entrypoint_hooks(START)
def {MOCK_HOOK}():
    print("Hello, World! ----------------------------------------")

##########################################################################
from easybuild.framework.easyblock import EasyBlock
from easybuild.tools.entrypoints import register_easyblock_entrypoint

@register_easyblock_entrypoint()
class {MOCK_EASYBLOCK}(EasyBlock):
    def configure_step(self):
        print("{MOCK_EASYBLOCK}: configure_step called.")

    def build_step(self):
        print("{MOCK_EASYBLOCK}: build_step called.")

    def install_step(self):
        print("{MOCK_EASYBLOCK}: install_step called.")

    def sanity_check_step(self):
        print("{MOCK_EASYBLOCK}: sanity_check_step called.")

##########################################################################
from easybuild.tools.entrypoints import register_toolchain_entrypoint
from easybuild.tools.toolchain.compiler import DEFAULT_OPT_LEVEL, Compiler
from easybuild.tools.toolchain.toolchain import SYSTEM_TOOLCHAIN_NAME

TC_CONSTANT_MOCK = "Mock"

class MockCompiler(Compiler):
    COMPILER_FAMILY = TC_CONSTANT_MOCK
    SUBTOOLCHAIN = SYSTEM_TOOLCHAIN_NAME

@register_toolchain_entrypoint()
class {MOCK_TOOLCHAIN}(MockCompiler):
    NAME = '{MOCK_TOOLCHAIN}'  # Using `...tc` to distinguish toolchain from package
    COMPILER_MODULE_NAME = [NAME]
    SUBTOOLCHAIN = [SYSTEM_TOOLCHAIN_NAME]
"""


MOCK_EP_META_FILE = f"""
[{HOOKS_ENTRYPOINT}]
{MOCK_HOOK_EP_NAME} = {{module}}:hello_world

[{EASYBLOCK_ENTRYPOINT}]
{MOCK_EASYBLOCK_EP_NAME} = {{module}}:TestEasyBlock

[{TOOLCHAIN_ENTRYPOINT}]
{MOCK_TOOLCHAIN_EP_NAME} = {{module}}:MockTc
"""


class MockDistribution(Distribution):
    """Mock distribution for testing entry points."""
    def __init__(self, module):
        self.module = module

    def read_text(self, filename):
        if filename == "entry_points.txt":
            return MOCK_EP_META_FILE.format(module=self.module)

        if filename == "METADATA":
            return "Name: mock_hook\nVersion: 0.1.0\n"


class MockDistributionFinder(DistributionFinder):
    """Mock distribution finder for testing entry points."""
    def __init__(self, *args, module, **kwargs):
        super().__init__(*args, **kwargs)
        self.module = module

    def find_distributions(self, context=None):
        yield MockDistribution(self.module)


class EasyBuildEntrypointsTest(EnhancedTestCase):
    """Test cases for EasyBuild configuration."""

    tmpdir = None

    def setUp(self):
        """Set up the test environment."""
        reload(eboptions)
        super().setUp()
        self.tmpdir = tempfile.mkdtemp(prefix='easybuild_test_')

        if HAVE_ENTRY_POINTS:
            filename_root = "mock"
            dirname, dirpath = os.path.split(self.tmpdir)

            self.module = '.'.join([dirpath, filename_root])
            sys.path.insert(0, dirname)
            sys.meta_path.insert(0, MockDistributionFinder(module=self.module))

            # Create a mock entry point for testing
            mock_hook_file = os.path.join(self.tmpdir, f'{filename_root}.py')
            write_file(mock_hook_file, MOCK_EP_FILE)
        else:
            self.skipTest("Entry points not available in this Python version")

    def tearDown(self):
        """Clean up the test environment."""
        if self.tmpdir and os.path.isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)

        if HAVE_ENTRY_POINTS:
            # Remove the entry point from the working set
            torm = []
            for idx, cls in enumerate(sys.meta_path):
                if isinstance(cls, MockDistributionFinder):
                    torm.append(idx)
            for idx in reversed(torm):
                del sys.meta_path[idx]

    def test_entrypoints_get_group(self):
        """Test retrieving entrypoints for a specific group."""
        expected = {
            HOOKS_ENTRYPOINT: MOCK_HOOK_EP_NAME,
            EASYBLOCK_ENTRYPOINT: MOCK_EASYBLOCK_EP_NAME,
            TOOLCHAIN_ENTRYPOINT: MOCK_TOOLCHAIN_EP_NAME,
        }

        for group in [HOOKS_ENTRYPOINT, EASYBLOCK_ENTRYPOINT, TOOLCHAIN_ENTRYPOINT]:
            epts = get_group_entrypoints(group)
            self.assertIsInstance(epts, set, f"Expected set for group {group}")
            self.assertEqual(len(epts), 0, f"Expected non-empty set for group {group}")

        init_config(build_options={'use_entrypoints': True})
        for group in [HOOKS_ENTRYPOINT, EASYBLOCK_ENTRYPOINT, TOOLCHAIN_ENTRYPOINT]:
            epts = get_group_entrypoints(group)
            self.assertIsInstance(epts, set, f"Expected set for group {group}")
            self.assertGreater(len(epts), 0, f"Expected non-empty set for group {group}")

            loaded_names = [ep.name for ep in epts]
            self.assertIn(expected[group], loaded_names, f"Expected entry point {expected[group]} in group {group}")

    def test_entrypoints_list_easyblocks(self):
        """
        Tests for list_easyblocks function with entry points enabled.
        """
        txt = list_easyblocks()
        self.assertNotIn("TestEasyBlock", txt, "TestEasyBlock should not be listed without entry points enabled")

        init_config(build_options={'use_entrypoints': True})
        txt = list_easyblocks()
        self.assertIn("TestEasyBlock", txt, "TestEasyBlock should be listed with entry points enabled")

    def test_entrypoints_list_toolchains(self):
        """
        Tests for list_toolchains function with entry points enabled.
        """
        txt = list_toolchains()
        self.assertNotIn(MOCK_TOOLCHAIN, txt, f"{MOCK_TOOLCHAIN} should not be listed without entry points enabled")

        init_config(build_options={'use_entrypoints': True})

        txt = list_toolchains()
        self.assertIn(MOCK_TOOLCHAIN, txt, f"{MOCK_TOOLCHAIN} should be listed with entry points enabled")

    def test_entrypoints_get_module_path(self):
        """
        Tests for get_module_path function with entry points enabled.
        """
        module_path = get_module_path(MOCK_EASYBLOCK)
        self.assertIn('.generic.', module_path, "Module path should contain '.generic.'")

        init_config(build_options={'use_entrypoints': True})
        # Reload the EasyBlock module to ensure it is recognized
        module_path = get_module_path(MOCK_EASYBLOCK)
        self.assertEqual(module_path, self.module, "Module path should match the mock module path")


def suite():
    return TestLoaderFiltered().loadTestsFromTestCase(EasyBuildEntrypointsTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
