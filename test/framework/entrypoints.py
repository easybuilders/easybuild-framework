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
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import write_file
from easybuild.tools.docs import list_easyblocks, list_toolchains
from easybuild.tools.entrypoints import (
    get_group_entrypoints, HOOKS_ENTRYPOINT, EASYBLOCK_ENTRYPOINT, TOOLCHAIN_ENTRYPOINT,
    HAVE_ENTRY_POINTS, EntrypointHook, EntrypointEasyblock, EntrypointToolchain,
)
from easybuild.framework.easyconfig.easyconfig import get_easyblock_class
from easybuild.tools.hooks import START


if HAVE_ENTRY_POINTS:
    from importlib.metadata import DistributionFinder, Distribution
else:
    DistributionFinder = object
    Distribution = object


MOCK_HOOK_EP_NAME = "mock_hook"
MOCK_EASYBLOCK_EP_NAME = "mock_easyblock"
MOCK_TOOLCHAIN_EP_NAME = "mock_toolchain"

MOCK_HOOK = "hello_world_12412412"
MOCK_EASYBLOCK = "TestEasyBlock_1212461"
MOCK_TOOLCHAIN = "MockTc_352124671346"


MOCK_EP_FILE = f"""
from easybuild.tools.entrypoints import EntrypointHook
from easybuild.tools.hooks import CONFIGURE_STEP, START


@EntrypointHook(START)
def {MOCK_HOOK}():
    print("Hello, World! ----------------------------------------")

def {MOCK_HOOK}_invalid():
    print("This hook should not be registered, as it is invalid.")

##########################################################################
from easybuild.framework.easyblock import EasyBlock
from easybuild.tools.entrypoints import EntrypointEasyblock

@EntrypointEasyblock()
class {MOCK_EASYBLOCK}(EasyBlock):
    def configure_step(self):
        print("{MOCK_EASYBLOCK}: configure_step called.")

    def build_step(self):
        print("{MOCK_EASYBLOCK}: build_step called.")

    def install_step(self):
        print("{MOCK_EASYBLOCK}: install_step called.")

    def sanity_check_step(self):
        print("{MOCK_EASYBLOCK}: sanity_check_step called.")

class {MOCK_EASYBLOCK}_invalid(EasyBlock):
    pass

##########################################################################
from easybuild.tools.entrypoints import EntrypointToolchain
from easybuild.tools.toolchain.compiler import DEFAULT_OPT_LEVEL, Compiler
from easybuild.tools.toolchain.toolchain import SYSTEM_TOOLCHAIN_NAME

TC_CONSTANT_MOCK = "Mock"

class MockCompiler(Compiler):
    COMPILER_FAMILY = TC_CONSTANT_MOCK
    SUBTOOLCHAIN = SYSTEM_TOOLCHAIN_NAME

@EntrypointToolchain()
class {MOCK_TOOLCHAIN}(MockCompiler):
    NAME = '{MOCK_TOOLCHAIN}'  # Using `...tc` to distinguish toolchain from package
    COMPILER_MODULE_NAME = [NAME]
    SUBTOOLCHAIN = [SYSTEM_TOOLCHAIN_NAME]

class {MOCK_TOOLCHAIN}_invalid(MockCompiler):
    pass
"""


MOCK_EP_META_FILE = f"""
[{HOOKS_ENTRYPOINT}]
{MOCK_HOOK_EP_NAME} = {{module}}:{MOCK_HOOK}
{{invalid_hook}}

[{EASYBLOCK_ENTRYPOINT}]
{MOCK_EASYBLOCK_EP_NAME} = {{module}}:{MOCK_EASYBLOCK}
{{invalid_easyblock}}

[{TOOLCHAIN_ENTRYPOINT}]
{MOCK_TOOLCHAIN_EP_NAME} = {{module}}:{MOCK_TOOLCHAIN}
{{invalid_toolchain}}
"""

FORMAT_DCT = {
    'invalid_hook': '',
    'invalid_easyblock': '',
    'invalid_toolchain': '',
}


class MockDistribution(Distribution):
    """Mock distribution for testing entry points."""
    def __init__(self, module):
        self.module = module

    def read_text(self, filename):
        if filename == "entry_points.txt":
            return MOCK_EP_META_FILE.format(module=self.module, **FORMAT_DCT)

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

    def _run_mock_eb(self, args, strip=False, **kwargs):
        """Helper function to mock easybuild runs

        Return (stdout, stderr) optionally stripped of whitespace at start/end
        """
        with self.mocked_stdout_stderr() as (stdout, stderr):
            self.eb_main(args, **kwargs)
        stdout_txt = stdout.getvalue()
        stderr_txt = stderr.getvalue()
        if strip:
            stdout_txt = stdout_txt.strip()
            stderr_txt = stderr_txt.strip()
        return stdout_txt, stderr_txt

    def setUp(self):
        """Set up the test environment."""
        global FORMAT_DCT

        FORMAT_DCT = {
            'invalid_hook': '',
            'invalid_easyblock': '',
            'invalid_toolchain': '',
        }

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
            self.mock_hook_file = os.path.join(self.tmpdir, f'{filename_root}.py')
            write_file(self.mock_hook_file, MOCK_EP_FILE)
        else:
            self.skipTest("Entry points not available in this Python version")

    def tearDown(self):
        """Clean up the test environment."""
        super().tearDown()

        try:
            shutil.rmtree(self.tmpdir)
        except OSError:
            pass
        tempfile.tempdir = None

        if HAVE_ENTRY_POINTS:
            # Remove the entry point from the working set
            dirname, _ = os.path.split(self.tmpdir)
            if dirname in sys.path:
                sys.path.remove(dirname)
            torm = []
            for idx, cls in enumerate(sys.meta_path):
                if isinstance(cls, MockDistributionFinder):
                    torm.append(idx)
            for idx in reversed(torm):
                del sys.meta_path[idx]

            EntrypointHook.clear()

    def test_entrypoints_register_hook(self):
        """Test registering entry point hooks with both valid and invalid hook names."""
        # Dummy function
        def func():
            return

        decorator = EntrypointHook('123')
        with self.assertRaises(EasyBuildError):
            decorator(func)

        decorator = EntrypointHook(START, pre_step=True)
        with self.assertRaises(EasyBuildError):
            decorator(func)

        decorator = EntrypointHook(START)
        decorator(func)

    def test_entrypoints_register_easyblock(self):
        """Test registering entry point easyblocks with both valid and invalid easyblock names."""
        from easybuild.framework.easyblock import EasyBlock
        decorator = EntrypointEasyblock()

        with self.assertRaises(EasyBuildError):
            decorator(123)

        class MOCK():
            pass
        with self.assertRaises(EasyBuildError):
            decorator(MOCK)

        class MOCK(EasyBlock):
            pass
        decorator(MOCK)

    def test_entrypoints_register_toolchain(self):
        """Test registering entry point toolchains with both valid and invalid toolchain names."""
        from easybuild.tools.toolchain.toolchain import Toolchain
        decorator = EntrypointToolchain()

        with self.assertRaises(EasyBuildError):
            decorator(123)

        class MOCK():
            pass
        with self.assertRaises(EasyBuildError):
            decorator(MOCK)

        class MOCK(Toolchain):
            pass
        decorator(MOCK)

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

    def test_entrypoints_exclude_invalid(self):
        """Check that invalid entry points are excluded from the get_entrypoints function."""
        init_config(build_options={'use_entrypoints': True})

        # Check that the invalid hook is not registered

        FORMAT_DCT['invalid_hook'] = f"{MOCK_HOOK_EP_NAME}_invalid = {self.module}:{MOCK_HOOK}_invalid"
        FORMAT_DCT['invalid_easyblock'] = f"{MOCK_EASYBLOCK_EP_NAME}_invalid = {self.module}:{MOCK_EASYBLOCK}_invalid"
        FORMAT_DCT['invalid_toolchain'] = f"{MOCK_TOOLCHAIN_EP_NAME}_invalid = {self.module}:{MOCK_TOOLCHAIN}_invalid"

        hooks = EntrypointHook.get_entrypoints()
        self.assertNotIn(
            MOCK_HOOK + '_invalid', [ep.name for ep in hooks], "Invalid hook should not be registered"
        )

        # Check that the invalid easyblock is not registered
        easyblocks = EntrypointEasyblock.get_entrypoints()
        self.assertNotIn(
            MOCK_EASYBLOCK + '_invalid', [ep.name for ep in easyblocks], "Invalid easyblock should not be registered"
        )

        # Check that the invalid toolchain is not registered
        toolchains = EntrypointToolchain.get_entrypoints()
        self.assertNotIn(
            MOCK_TOOLCHAIN + '_invalid', [ep.name for ep in toolchains], "Invalid toolchain should not be registered"
        )

    def test_entrypoints_list_easyblocks(self):
        """
        Tests for list_easyblocks function with entry points enabled.
        """
        # Invalid EBs are still picked up as subclasses of EasyBlock, difficult to exclude them from this behavior
        # txt = list_easyblocks()
        # self.assertNotIn("TestEasyBlock", txt, "TestEasyBlock should not be listed without entry points enabled")

        init_config(build_options={'use_entrypoints': True})
        txt = list_easyblocks()
        self.assertIn("TestEasyBlock", txt, "TestEasyBlock should be listed with entry points enabled")

    def test_entrypoints_list_toolchains(self):
        """
        Tests for list_toolchains function with entry points enabled.
        """
        # Invalid TCs are still picked up as subclasses of Toolchain, difficult to exclude them from this behavior
        # txt = list_toolchains()
        # self.assertNotIn(MOCK_TOOLCHAIN, txt, f"{MOCK_TOOLCHAIN} should not be listed without entry points enabled")

        init_config(build_options={'use_entrypoints': True})

        txt = list_toolchains()
        self.assertIn(MOCK_TOOLCHAIN, txt, f"{MOCK_TOOLCHAIN} should be listed with entry points enabled")

    def test_entrypoints_get_easyblock_class(self):
        """
        Tests for get_easyblock_class function with entry points enabled.
        """
        with self.assertRaises(EasyBuildError):
            get_easyblock_class(MOCK_EASYBLOCK)
        # self.assertIn('.generic.', module_path, "Module path should contain '.generic.'")

        init_config(build_options={'use_entrypoints': True})
        # Reload the EasyBlock module to ensure it is recognized
        cls = get_easyblock_class(MOCK_EASYBLOCK)
        self.assertEqual(cls.__module__, self.module, "Module path should match the mock module path")

    def test_entrypoints_show_config(self):
        """Test that showing configuration includes entry points."""
        args = ['--show-config']
        stdout, stderr = self._run_mock_eb(args, strip=True)

        for name in ['Hooks', 'Easyblocks', 'Toolchains']:
            pattern = f"{name} from entrypoints ("
            self.assertIn(pattern, stdout, f"Expected {name} in configuration output")

        args = ['--show-full-config']
        stdout, stderr = self._run_mock_eb(args, strip=True)

        for name in ['Hooks', 'Easyblocks', 'Toolchains']:
            pattern = f"{name} from entrypoints ("
            self.assertIn(pattern, stdout, f"Expected {name} in configuration output")


def suite():
    return TestLoaderFiltered().loadTestsFromTestCase(EasyBuildEntrypointsTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
