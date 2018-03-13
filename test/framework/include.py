# #
# Copyright 2013-2018 Ghent University
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
Unit tests for eb command line options.

@author: Kenneth Hoste (Ghent University)
"""
import os
import sys
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from unittest import TextTestRunner

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import mkdir, write_file
from easybuild.tools.include import include_easyblocks, include_module_naming_schemes, include_toolchains
from easybuild.tools.include import is_software_specific_easyblock


def up(path, cnt):
    """Return path N times up."""
    if cnt > 0:
        path = up(os.path.dirname(path), cnt-1)
    return path


class IncludeTest(EnhancedTestCase):
    """Testcases for command line options."""

    logfile = None

    def test_include_easyblocks(self):
        """Test include_easyblocks()."""
        test_easyblocks = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox', 'easybuild', 'easyblocks')

        # put a couple of custom easyblocks in place, to test
        myeasyblocks = os.path.join(self.test_prefix, 'myeasyblocks')
        mkdir(os.path.join(myeasyblocks, 'generic'), parents=True)

        # include __init__.py files that should be ignored, and shouldn't cause trouble (bug #1697)
        write_file(os.path.join(myeasyblocks, '__init__.py'), "# dummy init, should not get included")
        write_file(os.path.join(myeasyblocks, 'generic', '__init__.py'), "# dummy init, should not get included")

        myfoo_easyblock_txt = '\n'.join([
            "from easybuild.easyblocks.generic.configuremake import ConfigureMake",
            "class EB_Foo(ConfigureMake):",
            "   pass",
        ])
        write_file(os.path.join(myeasyblocks, 'myfoo.py'), myfoo_easyblock_txt)

        mybar_easyblock_txt = '\n'.join([
            "from easybuild.framework.easyblock import EasyBlock",
            "class Bar(EasyBlock):",
            "   pass",
        ])
        write_file(os.path.join(myeasyblocks, 'generic', 'mybar.py'), mybar_easyblock_txt)

        # second myfoo easyblock, should get ignored...
        myfoo_bis = os.path.join(self.test_prefix, 'myfoo.py')
        write_file(myfoo_bis, '')

        # hijack $HOME to test expanding ~ in locations passed to include_easyblocks
        os.environ['HOME'] = myeasyblocks

        # expand set of known easyblocks with our custom ones;
        # myfoo easyblock is included twice, first path should have preference
        glob_paths = [os.path.join('~', '*'), os.path.join(myeasyblocks, '*/*.py'), myfoo_bis]
        included_easyblocks_path = include_easyblocks(self.test_prefix, glob_paths)

        expected_paths = ['__init__.py', 'easyblocks/__init__.py', 'easyblocks/myfoo.py',
                          'easyblocks/generic/__init__.py', 'easyblocks/generic/mybar.py']
        for filepath in expected_paths:
            fullpath = os.path.join(included_easyblocks_path, 'easybuild', filepath)
            self.assertTrue(os.path.exists(fullpath), "%s exists" % fullpath)

        # path to included easyblocks should be prepended to Python search path
        self.assertEqual(sys.path[0], included_easyblocks_path)

        # importing custom easyblocks should work
        import easybuild.easyblocks.myfoo
        myfoo_pyc_path = easybuild.easyblocks.myfoo.__file__
        myfoo_real_py_path = os.path.realpath(os.path.join(os.path.dirname(myfoo_pyc_path), 'myfoo.py'))
        self.assertTrue(os.path.samefile(up(myfoo_real_py_path, 1), myeasyblocks))

        import easybuild.easyblocks.generic.mybar
        mybar_pyc_path = easybuild.easyblocks.generic.mybar.__file__
        mybar_real_py_path = os.path.realpath(os.path.join(os.path.dirname(mybar_pyc_path), 'mybar.py'))
        self.assertTrue(os.path.samefile(up(mybar_real_py_path, 2), myeasyblocks))

        # existing (test) easyblocks are unaffected
        import easybuild.easyblocks.foofoo
        foofoo_path = os.path.dirname(os.path.dirname(easybuild.easyblocks.foofoo.__file__))
        self.assertTrue(os.path.samefile(foofoo_path, test_easyblocks))

    def test_include_easyblocks_priority(self):
        """Test whether easyblocks included via include_easyblocks() get prioroity over others."""
        test_easyblocks = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox', 'easybuild', 'easyblocks')

        # make sure that test 'foo' easyblock is there
        import easybuild.easyblocks.foo
        foo_path = os.path.dirname(os.path.dirname(easybuild.easyblocks.foo.__file__))
        self.assertTrue(os.path.samefile(foo_path, test_easyblocks))

        # inject custom 'foo' easyblocks
        myeasyblocks = os.path.join(self.test_prefix, 'myeasyblocks')
        mkdir(myeasyblocks)

        # include __init__.py file that should be ignored, and shouldn't cause trouble (bug #1697)
        write_file(os.path.join(myeasyblocks, '__init__.py'), "# dummy init, should not get included")

        # 'undo' import of foo easyblock
        del sys.modules['easybuild.easyblocks.foo']

        foo_easyblock_txt = '\n'.join([
            "from easybuild.framework.easyblock import EasyBlock",
            "class EB_Foo(EasyBlock):",
            "   pass",
        ])
        write_file(os.path.join(myeasyblocks, 'foo.py'), foo_easyblock_txt)
        include_easyblocks(self.test_prefix, [os.path.join(myeasyblocks, 'foo.py')])

        foo_pyc_path = easybuild.easyblocks.foo.__file__
        foo_real_py_path = os.path.realpath(os.path.join(os.path.dirname(foo_pyc_path), 'foo.py'))
        self.assertFalse(os.path.samefile(os.path.dirname(foo_pyc_path), test_easyblocks))
        self.assertTrue(os.path.samefile(foo_real_py_path, os.path.join(myeasyblocks, 'foo.py')))

        # 'undo' import of foo easyblock
        del sys.modules['easybuild.easyblocks.foo']

    def test_include_mns(self):
        """Test include_module_naming_schemes()."""
        testdir = os.path.dirname(os.path.abspath(__file__))
        test_mns = os.path.join(testdir, 'sandbox', 'easybuild', 'module_naming_scheme')

        my_mns = os.path.join(self.test_prefix, 'my_mns')
        mkdir(my_mns)

        # include __init__.py file that should be ignored, and shouldn't cause trouble (bug #1697)
        write_file(os.path.join(my_mns, '__init__.py'), "# dummy init, should not get included")

        my_mns_txt = '\n'.join([
            "from easybuild.tools.module_naming_scheme import ModuleNamingScheme",
            "class MyMNS(ModuleNamingScheme):",
            "   pass",
        ])
        write_file(os.path.join(my_mns, 'my_mns.py'), my_mns_txt)

        my_mns_bis = os.path.join(self.test_prefix, 'my_mns.py')
        write_file(my_mns_bis, '')

        # include custom MNS
        included_mns_path = include_module_naming_schemes(self.test_prefix, [os.path.join(my_mns, '*.py'), my_mns_bis])

        expected_paths = ['__init__.py', 'tools/__init__.py', 'tools/module_naming_scheme/__init__.py',
                          'tools/module_naming_scheme/my_mns.py']
        for filepath in expected_paths:
            fullpath = os.path.join(included_mns_path, 'easybuild', filepath)
            self.assertTrue(os.path.exists(fullpath), "%s exists" % fullpath)

        # path to included MNSs should be prepended to Python search path
        self.assertEqual(sys.path[0], included_mns_path)

        # importing custom MNS should work
        import easybuild.tools.module_naming_scheme.my_mns
        my_mns_pyc_path = easybuild.tools.module_naming_scheme.my_mns.__file__
        my_mns_real_py_path = os.path.realpath(os.path.join(os.path.dirname(my_mns_pyc_path), 'my_mns.py'))
        self.assertTrue(os.path.samefile(up(my_mns_real_py_path, 1), my_mns))

    def test_include_toolchains(self):
        """Test include_toolchains()."""
        my_toolchains = os.path.join(self.test_prefix, 'my_toolchains')
        mkdir(my_toolchains)

        # include __init__.py file that should be ignored, and shouldn't cause trouble (bug #1697)
        write_file(os.path.join(my_toolchains, '__init__.py'), "# dummy init, should not get included")

        for subdir in ['compiler', 'fft', 'linalg', 'mpi']:
            mkdir(os.path.join(my_toolchains, subdir))

        my_tc_txt = '\n'.join([
            "from easybuild.toolchains.compiler.my_compiler import MyCompiler",
            "class MyTc(MyCompiler):",
            "   pass",
        ])
        write_file(os.path.join(my_toolchains, 'my_tc.py'), my_tc_txt)

        my_compiler_txt = '\n'.join([
            "from easybuild.tools.toolchain.compiler import Compiler",
            "class MyCompiler(Compiler):",
            "   pass",
        ])
        write_file(os.path.join(my_toolchains, 'compiler', 'my_compiler.py'), my_compiler_txt)

        my_tc_bis = os.path.join(self.test_prefix, 'my_tc.py')
        write_file(my_tc_bis, '')

        # include custom toolchains
        glob_paths = [os.path.join(my_toolchains, '*.py'), os.path.join(my_toolchains, '*', '*.py'), my_tc_bis]
        included_tcs_path = include_toolchains(self.test_prefix, glob_paths)

        expected_paths = ['__init__.py', 'toolchains/__init__.py', 'toolchains/compiler/__init__.py',
                          'toolchains/my_tc.py', 'toolchains/compiler/my_compiler.py']
        for filepath in expected_paths:
            fullpath = os.path.join(included_tcs_path, 'easybuild', filepath)
            self.assertTrue(os.path.exists(fullpath), "%s exists" % fullpath)

        # path to included MNSs should be prepended to Python search path
        self.assertEqual(sys.path[0], included_tcs_path)

        # importing custom MNS should work
        import easybuild.toolchains.my_tc
        my_tc_pyc_path = easybuild.toolchains.my_tc.__file__
        my_tc_real_py_path = os.path.realpath(os.path.join(os.path.dirname(my_tc_pyc_path), 'my_tc.py'))
        self.assertTrue(os.path.samefile(up(my_tc_real_py_path, 1), my_toolchains))

    def test_is_software_specific_easyblock(self):
        """Test is_software_specific_easyblock function."""

        self.assertErrorRegex(EasyBuildError, "No such file", is_software_specific_easyblock, '/no/such/easyblock.py')

        testdir = os.path.dirname(os.path.abspath(__file__))
        test_easyblocks = os.path.join(testdir, 'sandbox', 'easybuild', 'easyblocks')

        self.assertTrue(is_software_specific_easyblock(os.path.join(test_easyblocks, 'g', 'gcc.py')))
        self.assertTrue(is_software_specific_easyblock(os.path.join(test_easyblocks, 't', 'toy.py')))

        self.assertFalse(is_software_specific_easyblock(os.path.join(test_easyblocks, 'generic', 'configuremake.py')))
        self.assertFalse(is_software_specific_easyblock(os.path.join(test_easyblocks, 'generic', 'toolchain.py')))


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(IncludeTest, sys.argv[1:])

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
