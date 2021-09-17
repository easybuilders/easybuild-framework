# #
# Copyright 2012-2021 Ghent University
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
Unit tests for easyconfig.py

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""
import copy
import glob
import os
import re
import shutil
import stat
import sys
import tempfile
import textwrap
from distutils.version import LooseVersion
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner

import easybuild.tools.build_log
import easybuild.framework.easyconfig as easyconfig
import easybuild.tools.systemtools as st
from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig.constants import EXTERNAL_MODULE_MARKER
from easybuild.framework.easyconfig.easyconfig import ActiveMNS, EasyConfig, create_paths, copy_easyconfigs
from easybuild.framework.easyconfig.easyconfig import det_subtoolchain_version, fix_deprecated_easyconfigs
from easybuild.framework.easyconfig.easyconfig import is_generic_easyblock, get_easyblock_class, get_module_path
from easybuild.framework.easyconfig.easyconfig import letter_dir_for, process_easyconfig, resolve_template
from easybuild.framework.easyconfig.easyconfig import triage_easyconfig_params, verify_easyconfig_filename
from easybuild.framework.easyconfig.licenses import License, LicenseGPLv3
from easybuild.framework.easyconfig.parser import EasyConfigParser, fetch_parameters_from_easyconfig
from easybuild.framework.easyconfig.templates import template_constant_dict, to_template_str
from easybuild.framework.easyconfig.style import check_easyconfigs_style
from easybuild.framework.easyconfig.tools import categorize_files_by_type, check_sha256_checksums, dep_graph
from easybuild.framework.easyconfig.tools import det_copy_ec_specs, find_related_easyconfigs, get_paths_for
from easybuild.framework.easyconfig.tools import parse_easyconfigs
from easybuild.framework.easyconfig.tweak import obtain_ec_for, tweak_one
from easybuild.framework.extension import resolve_exts_filter_template
from easybuild.toolchains.system import SystemToolchain
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option, get_module_syntax, module_classes, update_build_option
from easybuild.tools.configobj import ConfigObj
from easybuild.tools.docs import avail_easyconfig_constants, avail_easyconfig_templates
from easybuild.tools.filetools import adjust_permissions, change_dir, copy_file, mkdir, read_file
from easybuild.tools.filetools import remove_dir, remove_file, symlink, write_file
from easybuild.tools.module_naming_scheme.toolchain import det_toolchain_compilers, det_toolchain_mpi
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.options import parse_external_modules_metadata
from easybuild.tools.py2vs3 import OrderedDict, reload
from easybuild.tools.robot import resolve_dependencies
from easybuild.tools.systemtools import AARCH64, POWER, X86_64, get_cpu_architecture, get_shared_lib_ext
from easybuild.tools.toolchain.utilities import search_toolchain
from easybuild.tools.utilities import quote_str, quote_py_str
from test.framework.utilities import find_full_path

try:
    import pycodestyle  # noqa
except ImportError:
    try:
        import pep8  # noqa
    except ImportError:
        pass


EXPECTED_DOTTXT_TOY_DEPS = """digraph graphname {
toy;
"GCC/6.4.0-2.28 (EXT)";
intel;
toy -> intel;
toy -> "GCC/6.4.0-2.28 (EXT)";
}
"""


class EasyConfigTest(EnhancedTestCase):
    """ easyconfig tests """
    contents = None
    eb_file = ''

    def setUp(self):
        """Set up everything for running a unit test."""
        super(EasyConfigTest, self).setUp()
        self.orig_get_cpu_architecture = st.get_cpu_architecture

        self.cwd = os.getcwd()
        self.all_stops = [x[0] for x in EasyBlock.get_steps()]
        if os.path.exists(self.eb_file):
            os.remove(self.eb_file)

    def prep(self):
        """Prepare for test."""
        # (re)cleanup last test file
        if os.path.exists(self.eb_file):
            os.remove(self.eb_file)
        if self.contents is not None:
            fd, self.eb_file = tempfile.mkstemp(prefix='easyconfig_test_file_', suffix='.eb')
            os.close(fd)
            write_file(self.eb_file, self.contents)

    def tearDown(self):
        """ make sure to remove the temporary file """
        st.get_cpu_architecture = self.orig_get_cpu_architecture
        super(EasyConfigTest, self).tearDown()
        if os.path.exists(self.eb_file):
            os.remove(self.eb_file)

    def test_empty(self):
        """ empty files should not parse! """
        self.contents = "# empty string"
        self.prep()
        self.assertRaises(EasyBuildError, EasyConfig, self.eb_file)
        self.assertErrorRegex(EasyBuildError, "expected a valid path", EasyConfig, "")

    def test_mandatory(self):
        """ make sure all checking of mandatory parameters works """
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
        ])
        self.prep()
        self.assertErrorRegex(EasyBuildError, "mandatory parameters not provided", EasyConfig, self.eb_file)

        self.contents += '\n' + '\n'.join([
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = SYSTEM',
        ])
        self.prep()

        ec = EasyConfig(self.eb_file)

        self.assertEqual(ec['name'], "pi")
        self.assertEqual(ec['version'], "3.14")
        self.assertEqual(ec['homepage'], "http://example.com")
        self.assertEqual(ec['toolchain'], {"name": "system", "version": "system"})
        self.assertEqual(ec['description'], "test easyconfig")

        for key in ['name', 'version', 'homepage', 'toolchain', 'description']:
            self.assertTrue(ec.is_mandatory_param(key))
        for key in ['buildopts', 'dependencies', 'easyblock', 'sources']:
            self.assertFalse(ec.is_mandatory_param(key))

    def test_validation(self):
        """ test other validations beside mandatory parameters """
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = SYSTEM',
            'stop = "notvalid"',
        ])
        self.prep()
        ec = EasyConfig(self.eb_file, validate=False)
        self.assertErrorRegex(EasyBuildError, r"\w* provided '\w*' is not valid", ec.validate)

        ec['stop'] = 'patch'
        # this should now not crash
        ec.validate()

        ec['osdependencies'] = ['non-existent-dep']
        self.assertErrorRegex(EasyBuildError, "OS dependencies were not found", ec.validate)

        # system toolchain, installversion == version
        self.assertEqual(det_full_ec_version(ec), "3.14")

        os.chmod(self.eb_file, 0o000)
        self.assertErrorRegex(EasyBuildError, "Permission denied", EasyConfig, self.eb_file)
        os.chmod(self.eb_file, 0o755)

        self.contents += "\nsyntax_error'"
        self.prep()
        error_pattern = "Parsing easyconfig file failed: EOL while scanning string literal"
        self.assertErrorRegex(EasyBuildError, error_pattern, EasyConfig, self.eb_file)

        # introduce "TypeError: format requires mapping" issue"
        self.contents = self.contents.replace("syntax_error'", "foo = '%(name)s %s' % version")
        self.prep()
        error_pattern = r"Parsing easyconfig file failed: format requires a mapping \(line 8\)"
        self.assertErrorRegex(EasyBuildError, error_pattern, EasyConfig, self.eb_file)

    def test_system_toolchain_constant(self):
        """Test use of SYSTEM constant to specify toolchain."""
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = SYSTEM',
        ])
        self.prep()
        eb = EasyConfig(self.eb_file)
        self.assertEqual(eb['toolchain'], {'name': 'system', 'version': 'system'})
        self.assertTrue(isinstance(eb.toolchain, SystemToolchain))

    def test_shlib_ext(self):
        """ inside easyconfigs shared_lib_ext should be set """
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = SYSTEM',
            'sanity_check_paths = { "files": ["lib/lib.%s" % SHLIB_EXT] }',
        ])
        self.prep()
        eb = EasyConfig(self.eb_file)
        self.assertEqual(eb['sanity_check_paths']['files'][0], "lib/lib.%s" % get_shared_lib_ext())

    def test_dependency(self):
        """ test all possible ways of specifying dependencies """
        init_config(build_options={'silent': True})

        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'versionsuffix = "-test"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"GCC", "version": "4.6.3"}',
            'dependencies = ['
            '   ("first", "1.1"),'
            '   {"name": "second", "version": "2.2"},',
            # funky way of referring to version(suffix), but should work!
            '   ("foo", "%(version)s", versionsuffix),',
            '   ("bar", "1.2.3", "%(versionsuffix)s-123"),',
            ']',
            'builddependencies = [',
            '   ("first", "1.1"),',
            '   {"name": "second", "version": "2.2"},',
            ']',
        ])
        self.prep()
        eb = EasyConfig(self.eb_file)
        # should include builddependencies
        self.assertEqual(len(eb.dependencies()), 6)
        self.assertEqual(len(eb.builddependencies()), 2)

        first = eb.dependencies()[0]
        second = eb.dependencies()[1]

        self.assertEqual(first['name'], "first")
        self.assertEqual(first['version'], "1.1")
        self.assertEqual(first['versionsuffix'], '')

        self.assertEqual(second['name'], "second")
        self.assertEqual(second['version'], "2.2")
        self.assertEqual(second['versionsuffix'], '')

        self.assertEqual(eb['dependencies'][2]['name'], 'foo')
        self.assertEqual(eb['dependencies'][2]['version'], '3.14')
        self.assertEqual(eb['dependencies'][2]['versionsuffix'], '-test')

        self.assertEqual(eb['dependencies'][3]['name'], 'bar')
        self.assertEqual(eb['dependencies'][3]['version'], '1.2.3')
        self.assertEqual(eb['dependencies'][3]['versionsuffix'], '-test-123')

        self.assertEqual(det_full_ec_version(first), '1.1-GCC-4.6.3')
        self.assertEqual(det_full_ec_version(second), '2.2-GCC-4.6.3')

        # same tests for builddependencies
        first = eb.builddependencies()[0]
        second = eb.builddependencies()[1]

        self.assertEqual(first['name'], "first")
        self.assertEqual(second['name'], "second")

        self.assertEqual(first['version'], "1.1")
        self.assertEqual(second['version'], "2.2")

        self.assertEqual(det_full_ec_version(first), '1.1-GCC-4.6.3')
        self.assertEqual(det_full_ec_version(second), '2.2-GCC-4.6.3')

        self.assertErrorRegex(EasyBuildError, "Dependency foo of unsupported type", eb._parse_dependency, "foo")
        self.assertErrorRegex(EasyBuildError, "without name", eb._parse_dependency, ())
        self.assertErrorRegex(EasyBuildError, "without version", eb._parse_dependency, {'name': 'test'})
        err_msg = "Incorrect external dependency specification"
        self.assertErrorRegex(EasyBuildError, err_msg, eb._parse_dependency, (EXTERNAL_MODULE_MARKER,))
        self.assertErrorRegex(EasyBuildError, err_msg, eb._parse_dependency, ('foo', '1.2.3', EXTERNAL_MODULE_MARKER))

    def test_false_dep_version(self):
        """
        Test use False as dependency version via dict using 'arch=' keys,
        which should result in filtering the dependency.
        """
        # silence warnings about missing easyconfigs for dependencies, we don't care
        init_config(build_options={'silent': True})

        arch = get_cpu_architecture()

        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'versionsuffix = "-test"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"GCC", "version": "4.6.3"}',
            'builddependencies = [',
            '   ("first_build", {"arch=%s": False}),' % arch,
            '   ("second_build", "2.0"),',
            ']',
            'dependencies = ['
            '   ("first", "1.0"),',
            '   ("second", {"arch=%s": False}),' % arch,
            ']',
        ])
        self.prep()
        eb = EasyConfig(self.eb_file)
        deps = eb.dependencies()
        self.assertEqual(len(deps), 2)
        self.assertEqual(deps[0]['name'], 'second_build')
        self.assertEqual(deps[1]['name'], 'first')

        # more realistic example: only filter dep for POWER
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'versionsuffix = "-test"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"GCC", "version": "4.6.3"}',
            'dependencies = ['
            '   ("not_on_power", {"arch=*": "1.2.3", "arch=POWER": False}),',
            ']',
        ])
        self.prep()

        # only non-POWER arch, dependency is retained
        for arch in (AARCH64, X86_64):
            st.get_cpu_architecture = lambda: arch
            eb = EasyConfig(self.eb_file)
            deps = eb.dependencies()
            self.assertEqual(len(deps), 1)
            self.assertEqual(deps[0]['name'], 'not_on_power')

        # only power, dependency gets filtered
        st.get_cpu_architecture = lambda: POWER
        eb = EasyConfig(self.eb_file)
        deps = eb.dependencies()
        self.assertEqual(deps, [])

    def test_extra_options(self):
        """ extra_options should allow other variables to be stored """
        init_config(build_options={'silent': True})

        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"GCC", "version": "4.6.3"}',
            'toolchainopts = { "static": True}',
            'dependencies = [("first", "1.1"), {"name": "second", "version": "2.2"}]',
        ])
        self.prep()
        eb = EasyConfig(self.eb_file)
        self.assertErrorRegex(EasyBuildError, "unknown easyconfig parameter", lambda: eb['custom_key'])

        extra_vars = {'custom_key': ['default', "This is a default key", easyconfig.CUSTOM]}

        ec = EasyConfig(self.eb_file, extra_options=extra_vars)
        self.assertEqual(ec['custom_key'], 'default')

        self.assertFalse(ec.is_mandatory_param('custom_key'))

        ec['custom_key'] = "not so default"
        self.assertEqual(ec['custom_key'], 'not so default')

        self.contents += "\ncustom_key = 'test'"

        self.prep()

        ec = EasyConfig(self.eb_file, extra_options=extra_vars)
        self.assertEqual(ec['custom_key'], 'test')

        ec['custom_key'] = "not so default"
        self.assertEqual(ec['custom_key'], 'not so default')

        # test if extra toolchain options are being passed
        self.assertEqual(ec.toolchain.options['static'], True)

        # test extra mandatory parameters
        extra_vars.update({'mandatory_key': ['default', 'another mandatory key', easyconfig.MANDATORY]})
        self.assertErrorRegex(EasyBuildError, r"mandatory parameters not provided",
                              EasyConfig, self.eb_file, extra_options=extra_vars)

        self.contents += '\nmandatory_key = "value"'
        self.prep()

        ec = EasyConfig(self.eb_file, extra_options=extra_vars)

        self.assertEqual(ec['mandatory_key'], 'value')
        self.assertTrue(ec.is_mandatory_param('mandatory_key'))

        # check whether mandatory key is retained in dumped easyconfig file, even if it's set to the default value
        ec['mandatory_key'] = 'default'
        test_ecfile = os.path.join(self.test_prefix, 'test_dump_mandatory.eb')
        ec.dump(test_ecfile)

        regex = re.compile("^mandatory_key = 'default'$", re.M)
        ectxt = read_file(test_ecfile)
        self.assertTrue(regex.search(ectxt), "Pattern '%s' found in: %s" % (regex.pattern, ectxt))

        # parsing again should work fine (if mandatory easyconfig parameters are indeed retained)
        ec = EasyConfig(test_ecfile, extra_options=extra_vars)
        self.assertEqual(ec['mandatory_key'], 'default')

    def test_exts_list(self):
        """Test handling of list of extensions."""
        topdir = os.path.dirname(os.path.abspath(__file__))
        os.environ['EASYBUILD_SOURCEPATH'] = ':'.join([
            os.path.join(topdir, 'easyconfigs', 'test_ecs', 'g', 'gzip'),
            os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy'),
        ])
        init_config()
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = SYSTEM',
            'exts_default_options = {',
            '    "source_tmpl": "gzip-1.4.eb",',  # dummy source template to avoid downloading fail
            '    "source_urls": ["http://example.com/%(name)s/%(version)s"]',
            '}',
            'exts_list = [',
            '   ("ext1", "1.0"),',
            '   ("ext2", "2.0", {',
            '       "source_urls": [("http://example.com", "suffix")],'
            '       "patches": ["toy-0.0.eb"],',  # dummy patch to avoid downloading fail
            '       "checksums": [',
                        # SHA256 checksum for source (gzip-1.4.eb)
            '           "6a5abcab719cefa95dca4af0db0d2a9d205d68f775a33b452ec0f2b75b6a3a45",',
                        # SHA256 checksum for 'patch' (toy-0.0.eb)
            '           "2d964e0e8f05a7cce0dd83a3e68c9737da14b87b61b8b8b0291d58d4c8d1031c",',
            '       ],',
            '   }),',
            ']',
        ])
        self.prep()
        ec = EasyConfig(self.eb_file)
        eb = EasyBlock(ec)
        exts_sources = eb.fetch_extension_sources()

        self.assertEqual(len(exts_sources), 2)
        self.assertEqual(exts_sources[0]['name'], 'ext1')
        self.assertEqual(exts_sources[0]['version'], '1.0')
        self.assertEqual(exts_sources[0]['options'], {
            'source_tmpl': 'gzip-1.4.eb',
            'source_urls': ['http://example.com/%(name)s/%(version)s'],
        })
        self.assertEqual(exts_sources[1]['name'], 'ext2')
        self.assertEqual(exts_sources[1]['version'], '2.0')
        self.assertEqual(exts_sources[1]['options'], {
            'checksums': ['6a5abcab719cefa95dca4af0db0d2a9d205d68f775a33b452ec0f2b75b6a3a45',
                          '2d964e0e8f05a7cce0dd83a3e68c9737da14b87b61b8b8b0291d58d4c8d1031c'],
            'patches': ['toy-0.0.eb'],
            'source_tmpl': 'gzip-1.4.eb',
            'source_urls': [('http://example.com', 'suffix')],
        })

        modfile = os.path.join(eb.make_module_step(), 'pi', '3.14' + eb.module_generator.MODULE_FILE_EXTENSION)
        modtxt = read_file(modfile)
        regex = re.compile('EBEXTSLISTPI.*ext1-1.0,ext2-2.0')
        self.assertTrue(regex.search(modtxt), "Pattern '%s' found in: %s" % (regex.pattern, modtxt))

    def test_extensions_templates(self):
        """Test whether templates used in exts_list are resolved properly."""

        # put dummy source file in place to avoid download fail
        toy_tar_gz = os.path.join(self.test_sourcepath, 'toy', 'toy-0.0.tar.gz')
        copy_file(toy_tar_gz, os.path.join(self.test_prefix, 'toy-0.0-py3-test.tar.gz'))
        toy_patch_fn = 'toy-0.0_fix-silly-typo-in-printf-statement.patch'
        toy_patch = os.path.join(self.test_sourcepath, 'toy', toy_patch_fn)
        copy_file(toy_patch, self.test_prefix)

        os.environ['EASYBUILD_SOURCEPATH'] = self.test_prefix
        init_config(build_options={'silent': True})

        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'versionsuffix = "-test"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = SYSTEM',
            'dependencies = [("Python", "3.6.6")]',
            'exts_defaultclass = "EB_Toy"',
            # bogus, but useful to check whether this get resolved
            'exts_default_options = {"source_urls": [PYPI_SOURCE]}',
            'exts_list = [',
            '   ("toy", "0.0", {',
            # %(name)s and %(version_major_minor)s should be resolved using name/version of extension (not parent)
            # %(pymajver)s should get resolved because Python is listed as a (runtime) dep
            # %(versionsuffix)s should get resolved with value of parent
            '       "source_tmpl": "%(name)s-%(version_major_minor)s-py%(pymajver)s%(versionsuffix)s.tar.gz",',
            '       "patches": ["%(name)s-%(version)s_fix-silly-typo-in-printf-statement.patch"],',
            # use hacky prebuildopts that is picked up by 'EB_Toy' easyblock, to check whether templates are resolved
            '       "prebuildopts": "gcc -O2 %(name)s.c -o toy-%(version)s &&' +
            ' mv toy-%(version)s toy # echo installdir is %(installdir)s #",',
            '   }),',
            ']',
        ])
        self.prep()
        ec = EasyConfig(self.eb_file)
        eb = EasyBlock(ec)
        eb.fetch_step()

        # inject OS dependency that can not be fullfilled,
        # to check whether OS deps are validated again for each extension (they shouldn't be);
        # we need to tweak the contents of the easyconfig file via cfg.rawtxt, since that's what is used to re-parse
        # the easyconfig file for the extension
        eb.cfg.rawtxt += "\nosdependencies = ['this_os_dep_does_not_exist']"

        # run extensions step to install 'toy' extension
        eb.extensions_step()

        # check whether template values were resolved correctly in Extension instances that were created/used
        toy_ext = eb.ext_instances[0]
        self.assertEqual(os.path.basename(toy_ext.src), 'toy-0.0-py3-test.tar.gz')
        patches = []
        for patch in toy_ext.patches:
            patches.append(patch['path'])
        self.assertEqual(patches, [os.path.join(self.test_prefix, toy_patch_fn)])
        # define actual installation dir
        pi_installdir = os.path.join(self.test_installpath, 'software', 'pi', '3.14-test')
        expected_prebuildopts = 'gcc -O2 toy.c -o toy-0.0 && mv toy-0.0 toy # echo installdir is %s #' % pi_installdir
        expected = {
            'patches': ['toy-0.0_fix-silly-typo-in-printf-statement.patch'],
            'prebuildopts': expected_prebuildopts,
            'source_tmpl': 'toy-0.0-py3-test.tar.gz',
            'source_urls': ['https://pypi.python.org/packages/source/t/toy'],
        }
        self.assertEqual(toy_ext.options, expected)

        # also .cfg of Extension instance was updated correctly
        self.assertEqual(toy_ext.cfg['source_urls'], ['https://pypi.python.org/packages/source/t/toy'])
        self.assertEqual(toy_ext.cfg['patches'], [toy_patch_fn])
        self.assertEqual(toy_ext.cfg['prebuildopts'], expected_prebuildopts)

        # check whether files expected to be installed for 'toy' extension are in place
        self.assertTrue(os.path.exists(os.path.join(pi_installdir, 'bin', 'toy')))
        self.assertTrue(os.path.exists(os.path.join(pi_installdir, 'lib', 'libtoy.a')))

    def test_suggestions(self):
        """ If a typo is present, suggestions should be provided (if possible) """
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"GCC", "version": "4.6.3"}',
            'dependencis = [("first", "1.1"), {"name": "second", "version": "2.2"}]',
            'source_uls = ["http://example.com"]',
            'source_URLs = ["http://example.com"]',
            'sourceURLs = ["http://example.com"]',
        ])
        self.prep()
        self.assertErrorRegex(EasyBuildError, "dependencis -> dependencies", EasyConfig, self.eb_file)
        self.assertErrorRegex(EasyBuildError, "source_uls -> source_urls", EasyConfig, self.eb_file)
        self.assertErrorRegex(EasyBuildError, "source_URLs -> source_urls", EasyConfig, self.eb_file)
        self.assertErrorRegex(EasyBuildError, "sourceURLs -> source_urls", EasyConfig, self.eb_file)

        # No error for known params prefixed by "local_"
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"GCC", "version": "4.6.3"}',
            'local_source_urls = "https://example.com"',
            'source_urls = [local_source_urls]',
            'local_cuda_compute_capabilities = ["3.3"]',  # This is known that it triggered the typo detection before
            'cuda_compute_capabilities = local_cuda_compute_capabilities',
        ])
        self.prep()
        # Should not raise any error, sanity check that something was done below
        ec = EasyConfig(self.eb_file)
        self.assertEqual(ec['version'], '3.14')

    def test_tweaking(self):
        """test tweaking ability of easyconfigs"""

        fd, tweaked_fn = tempfile.mkstemp(prefix='easybuild-tweaked-', suffix='.eb')
        os.close(fd)
        remove_file(tweaked_fn)

        patches = ["t1.patch", ("t2.patch", 1), ("t3.patch", "test"), ("t4.h", "include")]
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'homepage = "http://www.example.com"',
            'description = "dummy description"',
            'version = "3.14"',
            'toolchain = {"name": "GCC", "version": "4.6.3"}',
            'patches = %s',
            'parallel = 1',
            'keepsymlinks = True',
        ]) % str(patches)
        self.prep()

        ver = "1.2.3"
        verpref = "myprefix"
        versuff = "mysuffix"
        tcname = "gompi"
        tcver = "2018a"
        new_patches = ['t5.patch', 't6.patch']
        homepage = "http://www.justatest.com"

        tweaks = {
            'version': ver,
            'versionprefix': verpref,
            'versionsuffix': versuff,
            'toolchain_version': tcver,
            'patches': new_patches,
            'keepsymlinks': 'True',  # Don't change this
            # It should be possible to overwrite values with True/False/None as they often have special meaning
            'runtest': 'False',
            'hidden': 'True',
            'parallel': 'None',  # Good example: parallel=None means "Auto detect"
            # Adding new options (added only by easyblock) should also be possible
            # and in case the string "True/False/None" is really wanted it is possible to quote it first
            'test_none': '"False"',
            'test_bool': '"True"',
            'test_123': '"None"',
        }
        tweak_one(self.eb_file, tweaked_fn, tweaks)

        eb = EasyConfig(tweaked_fn)
        self.assertEqual(eb['version'], ver)
        self.assertEqual(eb['versionprefix'], verpref)
        self.assertEqual(eb['versionsuffix'], versuff)
        self.assertEqual(eb['toolchain']['version'], tcver)
        self.assertEqual(eb['patches'], new_patches)
        self.assertTrue(eb['runtest'] is False)
        self.assertTrue(eb['hidden'] is True)
        self.assertTrue(eb['parallel'] is None)
        self.assertEqual(eb['test_none'], 'False')
        self.assertEqual(eb['test_bool'], 'True')
        self.assertEqual(eb['test_123'], 'None')

        remove_file(tweaked_fn)

        eb = EasyConfig(self.eb_file)
        # eb['toolchain']['version'] = tcver does not work as expected with templating enabled
        with eb.disable_templating():
            eb['version'] = ver
            eb['toolchain']['version'] = tcver
        eb.dump(self.eb_file)

        tweaks = {
            'toolchain_name': tcname,
            'patches': new_patches[:1],
            'homepage': homepage,
        }

        tweak_one(self.eb_file, tweaked_fn, tweaks)

        eb = EasyConfig(tweaked_fn)
        self.assertEqual(eb['toolchain']['name'], tcname)
        self.assertEqual(eb['toolchain']['version'], tcver)
        self.assertEqual(eb['patches'], new_patches[:1])
        self.assertEqual(eb['version'], ver)
        self.assertEqual(eb['homepage'], homepage)

        # specify patches as string, eb should promote it to a list because original value was a list
        tweaks['patches'] = new_patches[0]
        eb = EasyConfig(tweaked_fn)
        self.assertEqual(eb['patches'], [new_patches[0]])

        # cleanup
        os.remove(tweaked_fn)

    def test_installversion(self):
        """Test generation of install version."""

        ver = "3.14"
        verpref = "myprefix|"
        versuff = "|mysuffix"
        tcname = "GCC"
        tcver = "4.6.3"
        system = "system"

        correct_installver = "%s%s-%s-%s%s" % (verpref, ver, tcname, tcver, versuff)
        cfg = {
            'version': ver,
            'toolchain': {'name': tcname, 'version': tcver},
            'versionprefix': verpref,
            'versionsuffix': versuff,
        }
        installver = det_full_ec_version(cfg)
        self.assertEqual(installver, "%s%s-%s-%s%s" % (verpref, ver, tcname, tcver, versuff))

        correct_installver = "%s%s%s" % (verpref, ver, versuff)
        cfg = {
            'version': ver,
            'toolchain': {'name': system, 'version': tcver},
            'versionprefix': verpref,
            'versionsuffix': versuff,
        }
        installver = det_full_ec_version(cfg)
        self.assertEqual(installver, correct_installver)

        # only version key is strictly needed
        self.assertEqual(det_full_ec_version({'version': '1.2.3'}), '1.2.3')

    def test_obtain_easyconfig(self):
        """test obtaining an easyconfig file given certain specifications"""
        init_config(build_options={'silent': True})

        change_dir(self.test_prefix)

        tcname = 'GCC'
        tcver = '4.6.3'
        patches = ["one.patch"]

        # prepare a couple of eb files to test again
        fns = ["pi-3.14.eb",
               "pi-3.13-GCC-4.6.3.eb",
               "pi-3.15-GCC-4.6.3.eb",
               "pi-3.15-GCC-4.8.3.eb",
               "foo-1.2.3-GCC-4.6.3.eb"]
        eb_files = [
            (fns[0], "\n".join([
                'easyblock = "ConfigureMake"',
                'name = "pi"',
                'version = "3.12"',
                'homepage = "http://example.com"',
                'description = "test easyconfig"',
                'toolchain = SYSTEM',
                'patches = %s' % patches
            ])),
            (fns[1], "\n".join([
                'easyblock = "ConfigureMake"',
                'name = "pi"',
                'version = "3.13"',
                'homepage = "http://example.com"',
                'description = "test easyconfig"',
                'toolchain = {"name": "%s", "version": "%s"}' % (tcname, tcver),
                'patches = %s' % patches
            ])),
            (fns[2], "\n".join([
                'easyblock = "ConfigureMake"',
                'name = "pi"',
                'version = "3.15"',
                'homepage = "http://example.com"',
                'description = "test easyconfig"',
                'toolchain = {"name": "%s", "version": "%s"}' % (tcname, tcver),
                'patches = %s' % patches
            ])),
            (fns[3], "\n".join([
                'easyblock = "ConfigureMake"',
                'name = "pi"',
                'version = "3.15"',
                'homepage = "http://example.com"',
                'description = "test easyconfig"',
                'toolchain = {"name": "%s", "version": "4.9.2"}' % tcname,
                'patches = %s' % patches
            ])),
            (fns[4], "\n".join([
                'easyblock = "ConfigureMake"',
                'name = "foo"',
                'version = "1.2.3"',
                'homepage = "http://example.com"',
                'description = "test easyconfig"',
                'toolchain = {"name": "%s", "version": "%s"}' % (tcname, tcver),
                'local_foo_extra1 = "bar"',
            ]))
        ]

        for (fn, txt) in eb_files:
            write_file(os.path.join(self.test_prefix, fn), txt)

        # should crash when no suited easyconfig file (or template) is available
        specs = {'name': 'nosuchsoftware'}
        error_regexp = ".*No easyconfig files found for software %s, and no templates available. I'm all out of ideas."
        error_regexp = error_regexp % specs['name']
        self.assertErrorRegex(EasyBuildError, error_regexp, obtain_ec_for, specs, [self.test_prefix], None)

        # should find matching easyconfig file
        specs = {
            'name': 'foo',
            'version': '1.2.3'
        }
        res = obtain_ec_for(specs, [self.test_prefix], None)
        self.assertEqual(res[0], False)
        self.assertEqual(res[1], os.path.join(self.test_prefix, fns[-1]))
        remove_file(res[1])

        # should not pick between multiple available toolchain names
        name = "pi"
        ver = "3.12"
        suff = "mysuff"
        specs.update({
            'name': name,
            'version': ver,
            'versionsuffix': suff
        })
        error_regexp = ".*No toolchain name specified, and more than one available: .*"
        self.assertErrorRegex(EasyBuildError, error_regexp, obtain_ec_for, specs, [self.test_prefix], None)

        # should be able to generate an easyconfig file that slightly differs
        ver = '3.16'
        specs.update({
            'toolchain_name': tcname,
            'toolchain_version': tcver,
            'version': ver,
            'start_dir': 'bar123'
        })
        res = obtain_ec_for(specs, [self.test_prefix], None)
        self.assertEqual(res[1], "%s-%s-%s-%s%s.eb" % (name, ver, tcname, tcver, suff))

        self.assertEqual(res[0], True)
        ec = EasyConfig(res[1])
        self.assertEqual(ec['name'], specs['name'])
        self.assertEqual(ec['version'], specs['version'])
        self.assertEqual(ec['versionsuffix'], specs['versionsuffix'])
        self.assertEqual(ec['toolchain'], {'name': tcname, 'version': tcver})
        self.assertEqual(ec['start_dir'], specs['start_dir'])
        remove_file(res[1])

        # should pick correct version, i.e. not newer than what's specified, if a choice needs to be made
        ver = '3.14'
        specs.update({'version': ver})
        res = obtain_ec_for(specs, [self.test_prefix], None)
        self.assertEqual(res[0], True)
        ec = EasyConfig(res[1])
        self.assertEqual(ec['version'], specs['version'])
        txt = read_file(res[1])
        self.assertTrue(re.search("^version = [\"']%s[\"']$" % ver, txt, re.M))
        remove_file(res[1])

        # should pick correct toolchain version as well, i.e. now newer than what's specified,
        # if a choice needs to be made
        specs.update({
            'version': '3.15',
            'toolchain_version': '4.8.3',
        })
        res = obtain_ec_for(specs, [self.test_prefix], None)
        self.assertEqual(res[0], True)
        ec = EasyConfig(res[1])
        self.assertEqual(ec['version'], specs['version'])
        self.assertEqual(ec['toolchain']['version'], specs['toolchain_version'])
        txt = read_file(res[1])
        pattern = "^toolchain = .*version.*[\"']%s[\"'].*}$" % specs['toolchain_version']
        self.assertTrue(re.search(pattern, txt, re.M))
        os.remove(res[1])

        # should be able to prepend to list of patches and handle list of dependencies
        new_patches = ['two.patch', 'three.patch']
        specs.update({
            'patches': new_patches[:],
            'builddependencies': [('testbuildonly', '4.9.3-2.25')],
            'dependencies': [('foo', '1.2.3'), ('bar', '666', '-bleh', ('gompi', '2018a'))],
            'hiddendependencies': [('test', '3.2.1'), ('testbuildonly', '4.9.3-2.25')],
        })
        parsed_deps = [
            {
                'name': 'testbuildonly',
                'version': '4.9.3-2.25',
                'versionsuffix': '',
                'toolchain': ec['toolchain'],
                'toolchain_inherited': True,
                'system': False,
                'short_mod_name': 'testbuildonly/.4.9.3-2.25-GCC-4.8.3',
                'full_mod_name': 'testbuildonly/.4.9.3-2.25-GCC-4.8.3',
                'build_only': True,
                'hidden': True,
                'external_module': False,
                'external_module_metadata': {},
            },
            {
                'name': 'foo',
                'version': '1.2.3',
                'versionsuffix': '',
                'toolchain': ec['toolchain'],
                'toolchain_inherited': True,
                'system': False,
                'short_mod_name': 'foo/1.2.3-GCC-4.8.3',
                'full_mod_name': 'foo/1.2.3-GCC-4.8.3',
                'build_only': False,
                'hidden': False,
                'external_module': False,
                'external_module_metadata': {},
            },
            {
                'name': 'bar',
                'version': '666',
                'versionsuffix': '-bleh',
                'toolchain': {'name': 'gompi', 'version': '2018a'},
                'toolchain_inherited': False,
                'system': False,
                'short_mod_name': 'bar/666-gompi-2018a-bleh',
                'full_mod_name': 'bar/666-gompi-2018a-bleh',
                'build_only': False,
                'hidden': False,
                'external_module': False,
                'external_module_metadata': {},
            },
            {
                'name': 'test',
                'version': '3.2.1',
                'versionsuffix': '',
                'toolchain': ec['toolchain'],
                'toolchain_inherited': True,
                'system': False,
                'short_mod_name': 'test/.3.2.1-GCC-4.8.3',
                'full_mod_name': 'test/.3.2.1-GCC-4.8.3',
                'build_only': False,
                'hidden': True,
                'external_module': False,
                'external_module_metadata': {},
            },
        ]

        # hidden dependencies must be included in list of dependencies
        res = obtain_ec_for(specs, [self.test_prefix], None)
        self.assertEqual(res[0], True)
        error_pattern = r"Hidden deps with visible module names .* not in list of \(build\)dependencies: .*"
        self.assertErrorRegex(EasyBuildError, error_pattern, EasyConfig, res[1])
        remove_file(res[1])

        specs['dependencies'].append(('test', '3.2.1'))

        res = obtain_ec_for(specs, [self.test_prefix], None)
        self.assertEqual(res[0], True)
        ec = EasyConfig(res[1])
        self.assertEqual(ec['patches'], specs['patches'])
        self.assertEqual(ec.dependencies(), parsed_deps)

        # hidden dependencies are filtered from list of (build)dependencies
        self.assertFalse('test/3.2.1-GCC-4.8.3' in [d['full_mod_name'] for d in ec['dependencies']])
        self.assertTrue('test/.3.2.1-GCC-4.8.3' in [d['full_mod_name'] for d in ec['hiddendependencies']])
        self.assertFalse('testbuildonly/4.9.3-2.25-GCC-4.8.3' in [d['full_mod_name'] for d in ec['builddependencies']])
        self.assertTrue('testbuildonly/.4.9.3-2.25-GCC-4.8.3' in [d['full_mod_name'] for d in ec['hiddendependencies']])
        os.remove(res[1])

        # hidden dependencies are also filtered from list of dependencies when validation is skipped
        res = obtain_ec_for(specs, [self.test_prefix], None)
        ec = EasyConfig(res[1], validate=False)
        self.assertFalse('test/3.2.1-GCC-4.8.3' in [d['full_mod_name'] for d in ec['dependencies']])
        self.assertTrue('test/.3.2.1-GCC-4.8.3' in [d['full_mod_name'] for d in ec['hiddendependencies']])
        self.assertFalse('testbuildonly/4.9.3-2.25-GCC-4.8.3' in [d['full_mod_name'] for d in ec['builddependencies']])
        self.assertTrue('testbuildonly/.4.9.3-2.25-GCC-4.8.3' in [d['full_mod_name'] for d in ec['hiddendependencies']])
        os.remove(res[1])

        # verify append functionality for lists
        specs['patches'].insert(0, '')
        res = obtain_ec_for(specs, [self.test_prefix], None)
        self.assertEqual(res[0], True)
        ec = EasyConfig(res[1])
        self.assertEqual(ec['patches'], patches + new_patches)
        specs['patches'].remove('')
        os.remove(res[1])

        # verify prepend functionality for lists
        specs['patches'].append('')
        res = obtain_ec_for(specs, [self.test_prefix], None)
        self.assertEqual(res[0], True)
        ec = EasyConfig(res[1])
        self.assertEqual(ec['patches'], new_patches + patches)
        os.remove(res[1])

        # should use supplied filename
        fn = "my.eb"
        res = obtain_ec_for(specs, [self.test_prefix], fn)
        self.assertEqual(res[0], True)
        self.assertEqual(res[1], fn)
        os.remove(res[1])

        # should use a template if it's there
        tpl_path = os.path.join("share", "easybuild", "easyconfigs", "TEMPLATE.eb")

        def trim_path(path):
            dirs = path.split(os.path.sep)
            if len(dirs) > 3 and 'site-packages' in dirs:
                if path.endswith('.egg'):
                    path = os.path.join(*dirs[:-4])  # strip of lib/python2.7/site-packages/*.egg part
                else:
                    path = os.path.join(*dirs[:-3])  # strip of lib/python2.7/site-packages part

            return path

        tpl_full_path = find_full_path(tpl_path, trim=trim_path)

        # only run this test if the TEMPLATE.eb file is available
        # TODO: use unittest.skip for this (but only works from Python 2.7)
        if tpl_full_path:
            shutil.copy2(tpl_full_path, self.test_prefix)
            specs.update({'name': 'nosuchsoftware'})
            res = obtain_ec_for(specs, [self.test_prefix], None)
            self.assertEqual(res[0], True)
            ec = EasyConfig(res[1])
            self.assertEqual(ec['name'], specs['name'])
            os.remove(res[1])

    def test_templating_constants(self):
        """Test use of template values and constants in an easyconfig file."""
        inp = {
            'name': 'PI',
            # purposely using minor version that starts with a 0, to check for correct version_minor value
            'version': '3.04',
            'namelower': 'pi',
            'cmd': 'tar xfvz %s',
        }
        # don't use any escaping insanity here, since it is templated itself
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "%(name)s"',
            'version = "%(version)s"',
            'versionsuffix = "-Python-%%(pyver)s"',
            'homepage = "http://example.com/%%(nameletter)s/%%(nameletterlower)s/v%%(version_major)s/"',
            'description = "test easyconfig %%(name)s"',
            'toolchain = SYSTEM',
            'source_urls = [GOOGLECODE_SOURCE, GITHUB_SOURCE]',
            'sources = [SOURCE_TAR_GZ, (SOURCELOWER_TAR_BZ2, "%(cmd)s")]',
            'sanity_check_paths = {',
            '   "files": ["bin/pi_%%(version_major)s_%%(version_minor)s", "lib/python%%(pyshortver)s/site-packages"],',
            '   "dirs": ["libfoo.%%s" %% SHLIB_EXT, "lib/%%(arch)s/" + SYS_PYTHON_VERSION, "include/" + ARCH],',
            '}',
            'dependencies = [',
            '   ("CUDA", "10.1.105"),'
            '   ("Java", "1.7.80"),'
            '   ("Perl", "5.22.0"),'
            '   ("Python", "2.7.10"),'
            ']',
            'builddependencies = ['
            '   ("R", "3.2.3"),'
            ']',
            'modloadmsg = "%s"' % '; '.join([
                'CUDA: %%(cudaver)s, %%(cudamajver)s, %%(cudaminver)s, %%(cudashortver)s',
                'Java: %%(javaver)s, %%(javamajver)s, %%(javaminver)s, %%(javashortver)s',
                'Python: %%(pyver)s, %%(pymajver)s, %%(pyminver)s, %%(pyshortver)s',
                'Perl: %%(perlver)s, %%(perlmajver)s, %%(perlminver)s, %%(perlshortver)s',
                'R: %%(rver)s, %%(rmajver)s, %%(rminver)s, %%(rshortver)s',
            ]),
            'modextrapaths = {"PI_MOD_NAME": "%%(module_name)s"}',
            'license_file = HOME + "/licenses/PI/license.txt"',
            "github_account = 'easybuilders'",
        ]) % inp
        self.prep()
        eb = EasyConfig(self.eb_file, validate=False)
        eb.validate()

        # temporarily disable templating, just so we can check later whether it's *still* disabled
        with eb.disable_templating():
            eb.generate_template_values()
            self.assertFalse(eb.enable_templating)

        self.assertEqual(eb['description'], "test easyconfig PI")
        self.assertEqual(eb['sources'][0], 'PI-3.04.tar.gz')
        self.assertEqual(eb['sources'][1], ('pi-3.04.tar.bz2', "tar xfvz %s"))
        self.assertEqual(eb['source_urls'][0], 'http://pi.googlecode.com/files')
        self.assertEqual(eb['source_urls'][1], 'https://github.com/easybuilders/PI/archive')
        self.assertEqual(eb['versionsuffix'], '-Python-2.7.10')
        self.assertEqual(eb['sanity_check_paths']['files'][0], 'bin/pi_3_04')
        self.assertEqual(eb['sanity_check_paths']['files'][1], 'lib/python2.7/site-packages')
        self.assertEqual(eb['sanity_check_paths']['dirs'][0], 'libfoo.%s' % get_shared_lib_ext())
        # should match lib/x86_64/2.7.18, lib/aarch64/3.8.6, lib/ppc64le/3.9.2, etc.
        lib_arch_regex = re.compile(r'^lib/[a-z0-9_]+/[23]\.[0-9]+\.[0-9]+$')
        dirs1 = eb['sanity_check_paths']['dirs'][1]
        self.assertTrue(lib_arch_regex.match(dirs1), "Pattern '%s' should match '%s'" % (lib_arch_regex.pattern, dirs1))
        inc_regex = re.compile('^include/(aarch64|ppc64le|x86_64)$')
        dirs2 = eb['sanity_check_paths']['dirs'][2]
        self.assertTrue(inc_regex.match(dirs2), "Pattern '%s' should match '%s'" % (inc_regex, dirs2))
        self.assertEqual(eb['homepage'], "http://example.com/P/p/v3/")
        expected = ("CUDA: 10.1.105, 10, 1, 10.1; "
                    "Java: 1.7.80, 1, 7, 1.7; "
                    "Python: 2.7.10, 2, 7, 2.7; "
                    "Perl: 5.22.0, 5, 22, 5.22; "
                    "R: 3.2.3, 3, 2, 3.2")
        self.assertEqual(eb['modloadmsg'], expected)
        self.assertEqual(eb['modextrapaths'], {'PI_MOD_NAME': 'PI/3.04-Python-2.7.10'})
        self.assertEqual(eb['license_file'], os.path.join(os.environ['HOME'], 'licenses', 'PI', 'license.txt'))

        # test the escaping insanity here (ie all the crap we allow in easyconfigs)
        eb['description'] = "test easyconfig % %% %s% %%% %(name)s %%(name)s %%%(name)s %%%%(name)s"
        self.assertEqual(eb['description'], "test easyconfig % %% %s% %%% PI %(name)s %PI %%(name)s")

        # test use of %(mpi_cmd_prefix)s template
        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        gompi_ec = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0-gompi-2018a.eb')
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, read_file(gompi_ec) + "\nsanity_check_commands = ['%(mpi_cmd_prefix)s toy']")

        ec = EasyConfig(test_ec)
        self.assertEqual(ec['sanity_check_commands'], ['mpirun -n 1 toy'])

        init_config(build_options={'mpi_cmd_template': "mpiexec -np %(nr_ranks)s -- %(cmd)s  "})
        ec = EasyConfig(test_ec)
        self.assertEqual(ec['sanity_check_commands'], ['mpiexec -np 1 -- toy'])

    def test_templating_cuda_toolchain(self):
        """Test templates via toolchain component, like setting %(cudaver)s with fosscuda toolchain."""

        build_options = {'robot_path': [self.test_prefix]}
        init_config(build_options=build_options)

        # create fake easyconfig files, good enough to test with
        cuda_ec = os.path.join(self.test_prefix, 'CUDA-10.1.243')
        cuda_ec_txt = '\n'.join([
            "easyblock = 'Toolchain'",
            "name = 'CUDA'",
            "version = '10.1.243'",
            "homepage = 'https://example.com'",
            "description = 'CUDA'",
            "toolchain = SYSTEM",
        ])
        write_file(cuda_ec, cuda_ec_txt)

        fosscuda_ec = os.path.join(self.test_prefix, 'fosscuda-2021.02.eb')
        fosscuda_ec_txt = '\n'.join([
            "easyblock = 'Toolchain'",
            "name = 'fosscuda'",
            "version = '2021.02'",
            "homepage = 'https://example.com'",
            "description = 'fosscuda toolchain'",
            "toolchain = SYSTEM",
            "dependencies = [('CUDA', '10.1.243')]",
        ])
        write_file(fosscuda_ec, fosscuda_ec_txt)

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ec_txt = '\n'.join([
            "easyblock = 'Toolchain'",
            "name = 'test'",
            "version = '1.0'",
            "homepage = 'https://example.com'",
            "description = 'just a test'",
            "toolchain = {'name': 'fosscuda', 'version': '2021.02'}",
        ])
        write_file(test_ec, test_ec_txt)
        ec = EasyConfig(test_ec)
        self.assertEqual(ec.template_values['cudaver'], '10.1.243')
        self.assertEqual(ec.template_values['cudamajver'], '10')
        self.assertEqual(ec.template_values['cudashortver'], '10.1')

    def test_java_wrapper_templating(self):
        """test templating when the Java wrapper is a dep"""
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "https://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"GCC", "version": "4.6.3"}',
            'dependencies = [("Java", "11", "", True)]',
            'modloadmsg = "Java: %(javaver)s, %(javamajver)s, %(javashortver)s"',
        ])
        self.prep()
        eb = EasyConfig(self.eb_file)

        # no %(javaminver)s because there is no minor version for Java
        self.assertEqual(eb.template_values['javaver'], '11')
        self.assertEqual(eb.template_values['javamajver'], '11')
        self.assertEqual(eb.template_values['javashortver'], '11')
        self.assertFalse('javaminver' in eb.template_values)

        self.assertEqual(eb['modloadmsg'], "Java: 11, 11, 11")

    def test_python_whl_templating(self):
        """test templating for Python wheels"""

        self.contents = textwrap.dedent("""
            easyblock = "ConfigureMake"
            name = "Pi"
            version = "3.14"
            homepage = "https://example.com"
            description = "test easyconfig"
            toolchain = {"name":"GCC", "version": "4.6.3"}
            sources = [
                SOURCE_WHL,
                SOURCELOWER_WHL,
                SOURCE_PY2_WHL,
                SOURCELOWER_PY2_WHL,
                SOURCE_PY3_WHL,
                SOURCELOWER_PY3_WHL,
            ]
        """)
        self.prep()
        ec = EasyConfig(self.eb_file)

        sources = ec['sources']

        self.assertEqual(sources[0], 'Pi-3.14-py2.py3-none-any.whl')
        self.assertEqual(sources[1], 'pi-3.14-py2.py3-none-any.whl')
        self.assertEqual(sources[2], 'Pi-3.14-py2-none-any.whl')
        self.assertEqual(sources[3], 'pi-3.14-py2-none-any.whl')
        self.assertEqual(sources[4], 'Pi-3.14-py3-none-any.whl')
        self.assertEqual(sources[5], 'pi-3.14-py3-none-any.whl')

    def test_templating_doc(self):
        """test templating documentation"""
        doc = avail_easyconfig_templates()
        # expected length: 1 per constant and 1 extra per constantgroup
        temps = [
            easyconfig.templates.TEMPLATE_NAMES_EASYCONFIG,
            easyconfig.templates.TEMPLATE_SOFTWARE_VERSIONS * 2,
            easyconfig.templates.TEMPLATE_NAMES_CONFIG,
            easyconfig.templates.TEMPLATE_NAMES_LOWER,
            easyconfig.templates.TEMPLATE_NAMES_EASYBLOCK_RUN_STEP,
            easyconfig.templates.TEMPLATE_NAMES_DYNAMIC,
            easyconfig.templates.TEMPLATE_CONSTANTS,
        ]

        self.assertEqual(len(doc.split('\n')), sum([len(temps)] + [len(x) for x in temps]))

    def test_constant_doc(self):
        """test constant documentation"""
        doc = avail_easyconfig_constants()
        # expected length: 1 per constant and 1 extra per constantgroup
        temps = [
            easyconfig.constants.EASYCONFIG_CONSTANTS,
        ]
        self.assertEqual(len(doc.split('\n')), sum([len(temps)] + [len(x) for x in temps]))

    def test_build_options(self):
        """Test configure/build/install options, both strings and lists."""
        orig_contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = SYSTEM',
        ])
        self.contents = orig_contents
        self.prep()

        # configopts as string
        configopts = '--opt1 --opt2=foo'
        self.contents = orig_contents + "\nconfigopts = '%s'" % configopts
        self.prep()
        eb = EasyConfig(self.eb_file)

        self.assertEqual(eb['configopts'], configopts)

        # configopts as list
        configopts = ['--opt1 --opt2=foo', '--opt1 --opt2=bar']
        self.contents = orig_contents + "\nconfigopts = %s" % str(configopts)
        self.prep()
        eb = EasyConfig(self.eb_file)

        self.assertEqual(eb['configopts'][0], configopts[0])
        self.assertEqual(eb['configopts'][1], configopts[1])

        # also buildopts and installopts as lists
        buildopts = ['CC=foo', 'CC=bar']
        installopts = ['FOO=foo', 'BAR=bar']
        self.contents = orig_contents + '\n' + '\n'.join([
            "configopts = %s" % str(configopts),
            "buildopts = %s" % str(buildopts),
            "installopts = %s" % str(installopts),
        ])
        self.prep()
        eb = EasyConfig(self.eb_file)

        self.assertEqual(eb['configopts'][0], configopts[0])
        self.assertEqual(eb['configopts'][1], configopts[1])
        self.assertEqual(eb['buildopts'][0], buildopts[0])
        self.assertEqual(eb['buildopts'][1], buildopts[1])
        self.assertEqual(eb['installopts'][0], installopts[0])
        self.assertEqual(eb['installopts'][1], installopts[1])

        # error should be thrown if lists are not equal
        installopts = ['FOO=foo', 'BAR=bar', 'BAZ=baz']
        self.contents = orig_contents + '\n' + '\n'.join([
            "configopts = %s" % str(configopts),
            "buildopts = %s" % str(buildopts),
            "installopts = %s" % str(installopts),
        ])
        self.prep()
        eb = EasyConfig(self.eb_file, validate=False)
        self.assertErrorRegex(EasyBuildError, "Build option lists for iterated build should have same length",
                              eb.validate)

        # list with a single element is OK, is treated as a string
        installopts = ['FOO=foo']
        self.contents = orig_contents + '\n' + '\n'.join([
            "configopts = %s" % str(configopts),
            "buildopts = %s" % str(buildopts),
            "installopts = %s" % str(installopts),
        ])
        self.prep()
        eb = EasyConfig(self.eb_file)

    def test_buildininstalldir(self):
        """Test specifying build in install dir."""
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = SYSTEM',
            'buildininstalldir = True',
        ])
        self.prep()
        ec = EasyConfig(self.eb_file)
        eb = EasyBlock(ec)
        eb.gen_builddir()
        eb.gen_installdir()
        eb.make_builddir()
        eb.make_installdir()
        self.assertEqual(eb.builddir, eb.installdir)
        self.assertTrue(os.path.isdir(eb.builddir))

    def test_format_equivalence_basic(self):
        """Test whether easyconfigs in different formats are equivalent."""
        # hard enable experimental
        orig_experimental = easybuild.tools.build_log.EXPERIMENTAL
        easybuild.tools.build_log.EXPERIMENTAL = True

        easyconfigs_path = os.path.join(os.path.dirname(__file__), 'easyconfigs')

        # set max diff high enough to make sure the difference is shown in case of problems
        self.maxDiff = 10000

        for eb_file1, eb_file2, specs in [
            ('gzip-1.4.eb', 'gzip.eb', {}),
            ('gzip-1.4.eb', 'gzip.eb', {'version': '1.4'}),
            ('gzip-1.4.eb', 'gzip.eb', {'version': '1.4', 'toolchain': {'name': 'system', 'version': 'system'}}),
            ('gzip-1.4-GCC-4.6.3.eb', 'gzip.eb', {'version': '1.4', 'toolchain': {'name': 'GCC', 'version': '4.6.3'}}),
            ('gzip-1.5-foss-2018a.eb', 'gzip.eb',
             {'version': '1.5', 'toolchain': {'name': 'foss', 'version': '2018a'}}),
            ('gzip-1.5-intel-2018a.eb', 'gzip.eb',
             {'version': '1.5', 'toolchain': {'name': 'intel', 'version': '2018a'}}),
        ]:
            eb_file1 = glob.glob(os.path.join(easyconfigs_path, 'v1.0', '*', '*', eb_file1))[0]
            ec1 = EasyConfig(eb_file1, validate=False)
            ec2 = EasyConfig(os.path.join(easyconfigs_path, 'v2.0', eb_file2), validate=False, build_specs=specs)

            ec2_dict = ec2.asdict()
            # reset mandatory attributes from format2 that are not defined in format 1 easyconfigs
            for attr in ['docurls', 'software_license_urls']:
                ec2_dict[attr] = None

            self.assertEqual(ec1.asdict(), ec2_dict, "Parsed %s is equivalent with %s" % (eb_file1, eb_file2))

        # restore
        easybuild.tools.build_log.EXPERIMENTAL = orig_experimental

    def test_fetch_parameters_from_easyconfig(self):
        """Test fetch_parameters_from_easyconfig function."""
        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec_file = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0.eb')

        for ec_file, correct_name, correct_easyblock in [
            (toy_ec_file, 'toy', None),
            (os.path.join(test_ecs_dir, 'f', 'foss', 'foss-2018a.eb'), 'foss', 'Toolchain'),
        ]:
            name, easyblock = fetch_parameters_from_easyconfig(read_file(ec_file), ['name', 'easyblock'])
            self.assertEqual(name, correct_name)
            self.assertEqual(easyblock, correct_easyblock)

        expected = "Toy C program, 100% toy."
        self.assertEqual(fetch_parameters_from_easyconfig(read_file(toy_ec_file), ['description'])[0], expected)

        res = fetch_parameters_from_easyconfig("easyblock = 'ConfigureMake'  # test comment", ['easyblock'])
        self.assertEqual(res, ['ConfigureMake'])

    def test_get_easyblock_class(self):
        """Test get_easyblock_class function."""
        from easybuild.easyblocks.generic.configuremake import ConfigureMake
        from easybuild.easyblocks.generic.toolchain import Toolchain
        from easybuild.easyblocks.toy import EB_toy
        for easyblock, easyblock_class in [
            ('ConfigureMake', ConfigureMake),
            ('easybuild.easyblocks.generic.configuremake.ConfigureMake', ConfigureMake),
            ('Toolchain', Toolchain),
            ('EB_toy', EB_toy),
        ]:
            self.assertEqual(get_easyblock_class(easyblock), easyblock_class)

        error_pattern = "No software-specific easyblock 'EB_gzip' found"
        self.assertErrorRegex(EasyBuildError, error_pattern, get_easyblock_class, None, name='gzip')
        self.assertEqual(get_easyblock_class(None, name='gzip', error_on_missing_easyblock=False), None)
        self.assertEqual(get_easyblock_class(None, name='toy'), EB_toy)
        self.assertErrorRegex(EasyBuildError, "Failed to import EB_TOY", get_easyblock_class, None, name='TOY')
        self.assertEqual(get_easyblock_class(None, name='TOY', error_on_failed_import=False), None)

        # also test deprecated default_fallback named argument
        self.assertErrorRegex(EasyBuildError, "DEPRECATED", get_easyblock_class, None, name='gzip',
                              default_fallback=False)

        orig_value = easybuild.tools.build_log.CURRENT_VERSION
        easybuild.tools.build_log.CURRENT_VERSION = '3.9'
        self.mock_stderr(True)
        self.assertEqual(get_easyblock_class(None, name='gzip', default_fallback=False), None)
        self.mock_stderr(False)
        easybuild.tools.build_log.CURRENT_VERSION = orig_value

    def test_letter_dir(self):
        """Test letter_dir_for function."""
        test_cases = {
            'foo': 'f',
            'Bar': 'b',
            'CAPS': 'c',
            'R': 'r',
            '3to2': '0',
            '7zip': '0',
            '_bleh_': '0',
            '*': '*',
        }
        for name, letter in test_cases.items():
            self.assertEqual(letter_dir_for(name), letter)

    def test_easyconfig_paths(self):
        """Test create_paths function."""
        cand_paths = create_paths('/some/path', 'Foo', '1.2.3')
        expected_paths = [
            '/some/path/Foo/1.2.3.eb',
            '/some/path/Foo/Foo-1.2.3.eb',
            '/some/path/f/Foo/Foo-1.2.3.eb',
            '/some/path/Foo-1.2.3.eb',
        ]
        self.assertEqual(cand_paths, expected_paths)

        cand_paths = create_paths('foobar', '3to2', '1.1.1')
        expected_paths = [
            'foobar/3to2/1.1.1.eb',
            'foobar/3to2/3to2-1.1.1.eb',
            'foobar/0/3to2/3to2-1.1.1.eb',
            'foobar/3to2-1.1.1.eb',
        ]
        self.assertEqual(cand_paths, expected_paths)

    def test_toolchain_inspection(self):
        """Test whether available toolchain inspection functionality is working."""
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        build_options = {
            'robot_path': [test_ecs],
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)

        ec = EasyConfig(os.path.join(test_ecs, 'g', 'gzip', 'gzip-1.5-foss-2018a.eb'))
        tc_compilers = ['/'.join([x['name'], x['version']]) for x in det_toolchain_compilers(ec)]
        self.assertEqual(tc_compilers, ['GCC/6.4.0-2.28'])
        self.assertEqual(det_toolchain_mpi(ec)['name'], 'OpenMPI')

        ec = EasyConfig(os.path.join(test_ecs, 'h', 'hwloc', 'hwloc-1.11.8-GCC-6.4.0-2.28.eb'))
        tc_comps = det_toolchain_compilers(ec)
        expected = ['GCC/6.4.0-2.28']
        self.assertEqual(['/'.join([x['name'], x['version'] + x['versionsuffix']]) for x in tc_comps], expected)
        self.assertEqual(det_toolchain_mpi(ec), None)

        ec = EasyConfig(os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb'))
        self.assertEqual(det_toolchain_compilers(ec), None)
        self.assertEqual(det_toolchain_mpi(ec), None)

    def test_filter_deps(self):
        """Test filtered dependencies."""
        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        ec_file = os.path.join(test_ecs_dir, 'f', 'foss', 'foss-2018a.eb')
        ec = EasyConfig(ec_file)
        deps = sorted([dep['name'] for dep in ec.dependencies()])
        self.assertEqual(deps, ['FFTW', 'GCC', 'OpenBLAS', 'OpenMPI', 'ScaLAPACK'])

        # test filtering multiple deps
        init_config(build_options={'filter_deps': ['FFTW', 'ScaLAPACK']})
        deps = sorted([dep['name'] for dep in ec.dependencies()])
        self.assertEqual(deps, ['GCC', 'OpenBLAS', 'OpenMPI'])

        # test filtering of non-existing dep
        init_config(build_options={'filter_deps': ['zlib']})
        deps = sorted([dep['name'] for dep in ec.dependencies()])
        self.assertEqual(deps, ['FFTW', 'GCC', 'OpenBLAS', 'OpenMPI', 'ScaLAPACK'])

        # test parsing of value passed to --filter-deps
        opts = init_config(args=[])
        self.assertEqual(opts.filter_deps, None)
        opts = init_config(args=['--filter-deps=zlib'])
        self.assertEqual(opts.filter_deps, ['zlib'])
        opts = init_config(args=['--filter-deps=zlib,ncurses'])
        self.assertEqual(opts.filter_deps, ['zlib', 'ncurses'])

        # make sure --filter-deps is honored when combined with --minimal-toolchains,
        # i.e. that toolchain for dependencies which are filtered out is not being minized
        build_options = {
            'external_modules_metadata': ConfigObj(),
            'minimal_toolchains': True,
            'robot_path': [test_ecs_dir],
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)

        ec_file = os.path.join(self.test_prefix, 'test.eb')
        shutil.copy2(os.path.join(test_ecs_dir, 'o', 'OpenMPI', 'OpenMPI-2.1.2-GCC-6.4.0-2.28.eb'), ec_file)

        ec_txt = read_file(ec_file)
        ec_txt = ec_txt.replace('hwloc', 'deptobefiltered')
        write_file(ec_file, ec_txt)

        self.assertErrorRegex(EasyBuildError, "Failed to determine minimal toolchain for dep .*",
                              EasyConfig, ec_file, validate=False)

        build_options.update({'filter_deps': ['deptobefiltered']})
        init_config(build_options=build_options)
        ec = EasyConfig(ec_file, validate=False)
        self.assertEqual(ec.dependencies(), [])

    def test_replaced_easyconfig_parameters(self):
        """Test handling of replaced easyconfig parameters."""
        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        ec = EasyConfig(os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0.eb'))
        replaced_parameters = {
            'license': ('license_file', '2.0'),
            'makeopts': ('buildopts', '2.0'),
            'premakeopts': ('prebuildopts', '2.0'),
        }
        for key, (newkey, ver) in replaced_parameters.items():
            error_regex = "NO LONGER SUPPORTED since v%s.*'%s' is replaced by '%s'" % (ver, key, newkey)
            self.assertErrorRegex(EasyBuildError, error_regex, ec.get, key)
            self.assertErrorRegex(EasyBuildError, error_regex, lambda k: ec[k], key)

            def foo(key):
                ec[key] = 'foo'

            self.assertErrorRegex(EasyBuildError, error_regex, foo, key)

    def test_deprecated_easyconfig_parameters(self):
        """Test handling of replaced easyconfig parameters."""
        os.environ.pop('EASYBUILD_DEPRECATED')
        easybuild.tools.build_log.CURRENT_VERSION = self.orig_current_version
        init_config()

        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        ec = EasyConfig(os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0.eb'))

        orig_deprecated_parameters = copy.deepcopy(easyconfig.parser.DEPRECATED_PARAMETERS)
        easyconfig.parser.DEPRECATED_PARAMETERS.update({
            'foobar': ('barfoo', '0.0'),  # deprecated since forever
            'foobarbarfoo': ('barfoofoobar', '1000000000'),  # won't be actually deprecated for a while
        })

        # copy classes before reloading, so we can restore them (other isinstance checks fail)
        orig_EasyConfig = copy.deepcopy(easyconfig.easyconfig.EasyConfig)
        orig_ActiveMNS = copy.deepcopy(easyconfig.easyconfig.ActiveMNS)
        reload(easyconfig.parser)

        for key, (newkey, depr_ver) in easyconfig.parser.DEPRECATED_PARAMETERS.items():
            if LooseVersion(depr_ver) <= easybuild.tools.build_log.CURRENT_VERSION:
                # deprecation error
                error_regex = "DEPRECATED.*since v%s.*'%s' is deprecated.*use '%s' instead" % (depr_ver, key, newkey)
                self.assertErrorRegex(EasyBuildError, error_regex, ec.get, key)
                self.assertErrorRegex(EasyBuildError, error_regex, lambda k: ec[k], key)

                def foo(key):
                    ec[key] = 'foo'

                self.assertErrorRegex(EasyBuildError, error_regex, foo, key)
            else:
                # only deprecation warning, but key is replaced when getting/setting
                ec[key] = 'test123'
                self.assertEqual(ec[newkey], 'test123')
                self.assertEqual(ec[key], 'test123')
                ec[newkey] = '123test'
                self.assertEqual(ec[newkey], '123test')
                self.assertEqual(ec[key], '123test')

        easyconfig.parser.DEPRECATED_PARAMETERS = orig_deprecated_parameters
        reload(easyconfig.parser)
        reload(easyconfig.easyconfig)
        easyconfig.easyconfig.EasyConfig = orig_EasyConfig
        easyconfig.easyconfig.ActiveMNS = orig_ActiveMNS

    def test_unknown_easyconfig_parameter(self):
        """Check behaviour when unknown easyconfig parameters are used."""
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = SYSTEM',
        ])
        self.prep()
        ec = EasyConfig(self.eb_file)
        self.assertFalse('therenosucheasyconfigparameterlikethis' in ec)
        error_regex = "unknown easyconfig parameter"
        self.assertErrorRegex(EasyBuildError, error_regex, lambda k: ec[k], 'therenosucheasyconfigparameterlikethis')

        def set_ec_key(key):
            """Dummy function to set easyconfig parameter in 'ec' EasyConfig instance"""
            ec[key] = 'foobar'

        self.assertErrorRegex(EasyBuildError, error_regex, set_ec_key, 'therenosucheasyconfigparameterlikethis')

    def test_external_dependencies(self):
        """Test specifying external (build) dependencies."""
        topdir = os.path.dirname(os.path.abspath(__file__))
        ectxt = read_file(os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-deps.eb'))
        toy_ec = os.path.join(self.test_prefix, 'toy-0.0-external-deps.eb')

        # just specify some of the test modules we ship, doesn't matter where they come from
        ectxt += "\ndependencies += ["
        ectxt += "  ('foobar/1.2.3', EXTERNAL_MODULE), "
        ectxt += "  ('test/9.7.5', EXTERNAL_MODULE), "
        ectxt += "  ('pi/3.14', EXTERNAL_MODULE), "
        ectxt += "  ('hidden/.1.2.3', EXTERNAL_MODULE), "
        ectxt += "  ('cray-netcdf-hdf5parallel/1.10.6', EXTERNAL_MODULE), "
        ectxt += "]"
        ectxt += "\nbuilddependencies = [('somebuilddep/0.1', EXTERNAL_MODULE)]"
        ectxt += "\ntoolchain = {'name': 'GCC', 'version': '6.4.0-2.28'}"
        write_file(toy_ec, ectxt)

        ec = EasyConfig(toy_ec)

        builddeps = ec.builddependencies()
        self.assertEqual(len(builddeps), 1)
        self.assertEqual(builddeps[0]['short_mod_name'], 'somebuilddep/0.1')
        self.assertEqual(builddeps[0]['full_mod_name'], 'somebuilddep/0.1')
        self.assertEqual(builddeps[0]['external_module'], True)

        deps = ec.dependencies()
        self.assertEqual(len(deps), 8)
        correct_deps = ['somebuilddep/0.1', 'intel/2018a', 'GCC/6.4.0-2.28', 'foobar/1.2.3',
                        'test/9.7.5', 'pi/3.14', 'hidden/.1.2.3', 'cray-netcdf-hdf5parallel/1.10.6']
        self.assertEqual([d['short_mod_name'] for d in deps], correct_deps)
        self.assertEqual([d['full_mod_name'] for d in deps], correct_deps)
        self.assertEqual([d['external_module'] for d in deps], [True, False, True, True, True, True, True, True])
        self.assertEqual([d['hidden'] for d in deps], [False, False, False, False, False, False, True, False])
        # no metadata available for deps
        expected = [{}] * len(deps)
        self.assertEqual([d['external_module_metadata'] for d in deps], expected)

        # test probing done by handle_external_module_metadata via probe_external_module_metadata,
        # by adding a couple of matching module files with some useful data in them
        # (use Tcl syntax, so it works with all varieties of module tools)
        mod_dir = os.path.join(self.test_prefix, 'modules')

        pi_mod_txt = '\n'.join([
            "#%Module",
            "setenv PI_ROOT /software/pi/3.14",
            "setenv PI_VERSION 3.14",
        ])
        write_file(os.path.join(mod_dir, 'pi/3.14'), pi_mod_txt)

        cray_netcdf_mod_txt = '\n'.join([
            "#%Module",
            "setenv CRAY_NETCDF_HDF5PARALLEL_PREFIX /software/cray-netcdf-hdf5parallel/1.10.6",
            "setenv CRAY_NETCDF_HDF5PARALLEL_VERSION 1.10.6",
        ])
        write_file(os.path.join(mod_dir, 'cray-netcdf-hdf5parallel/1.10.6'), cray_netcdf_mod_txt)

        # foobar module with different version than the one used as an external dep;
        # will still be used for probing (as a fallback)
        foobar_mod_txt = '\n'.join([
            "#%Module",
            "setenv CRAY_FOOBAR_DIR /software/foobar/2.3.4",
            "setenv CRAY_FOOBAR_VERSION 2.3.4",
        ])
        write_file(os.path.join(mod_dir, 'foobar/2.3.4'), foobar_mod_txt)

        self.modtool.use(mod_dir)

        ec = EasyConfig(toy_ec)
        deps = ec.dependencies()

        self.assertEqual(len(deps), 8)

        for idx in [0, 1, 2, 4, 6]:
            self.assertEqual(deps[idx]['external_module_metadata'], {})

        self.assertEqual(deps[3]['full_mod_name'], 'foobar/1.2.3')
        foobar_metadata = {
            'name': ['foobar'],
            'prefix': 'CRAY_FOOBAR_DIR',
            'version': ['CRAY_FOOBAR_VERSION'],
        }
        self.assertEqual(deps[3]['external_module_metadata'], foobar_metadata)

        self.assertEqual(deps[5]['full_mod_name'], 'pi/3.14')
        pi_metadata = {
            'name': ['pi'],
            'prefix': 'PI_ROOT',
            'version': ['PI_VERSION'],
        }
        self.assertEqual(deps[5]['external_module_metadata'], pi_metadata)

        self.assertEqual(deps[7]['full_mod_name'], 'cray-netcdf-hdf5parallel/1.10.6')
        cray_netcdf_metadata = {
            'name': ['netcdf-hdf5parallel'],
            'prefix': 'CRAY_NETCDF_HDF5PARALLEL_PREFIX',
            'version': ['CRAY_NETCDF_HDF5PARALLEL_VERSION'],
        }
        self.assertEqual(deps[7]['external_module_metadata'], cray_netcdf_metadata)

        # provide file with partial metadata for some external modules;
        # metadata obtained from probing modules should be added to it...
        metadata = os.path.join(self.test_prefix, 'external_modules_metadata.cfg')
        metadatatxt = '\n'.join([
            '[pi/3.14]',
            'name = PI',
            'version = 3.14.0',
            '[foobar]',
            'version = 1.0',
            '[foobar/1.2.3]',
            'version = 1.2.3',
            '[test]',
            'name = TEST',
            '[cray-netcdf-hdf5parallel/1.10.6]',
            'name = HDF5',
            # purpose omit version, to see whether fallback of
            # resolving $CRAY_NETCDF_HDF5PARALLEL_VERSION at runtime is used
        ])
        write_file(metadata, metadatatxt)
        build_options = {
            'external_modules_metadata': parse_external_modules_metadata([metadata]),
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)
        ec = EasyConfig(toy_ec)
        deps = ec.dependencies()

        self.assertEqual(len(deps), 8)

        for idx in [0, 1, 2, 6]:
            self.assertEqual(deps[idx]['external_module_metadata'], {})

        self.assertEqual(deps[3]['full_mod_name'], 'foobar/1.2.3')
        foobar_metadata = {
            'name': ['foobar'],  # probed from 'foobar' module
            'prefix': 'CRAY_FOOBAR_DIR',  # probed from 'foobar' module
            'version': ['1.2.3'],  # from [foobar/1.2.3] entry in metadata file
        }
        self.assertEqual(deps[3]['external_module_metadata'], foobar_metadata)

        self.assertEqual(deps[4]['full_mod_name'], 'test/9.7.5')
        self.assertEqual(deps[4]['external_module_metadata'], {
            # from [test] entry in metadata file
            'name': ['TEST'],
        })

        self.assertEqual(deps[5]['full_mod_name'], 'pi/3.14')
        pi_metadata = {
            'name': ['PI'],  # from [pi/3.14] entry in metadata file
            'prefix': 'PI_ROOT',  # probed from 'pi/3.14' module
            'version': ['3.14.0'],  # from [pi/3.14] entry in metadata file
        }
        self.assertEqual(deps[5]['external_module_metadata'], pi_metadata)

        self.assertEqual(deps[7]['full_mod_name'], 'cray-netcdf-hdf5parallel/1.10.6')
        cray_netcdf_metadata = {
            'name': ['HDF5'],
            'prefix': 'CRAY_NETCDF_HDF5PARALLEL_PREFIX',
            'version': ['CRAY_NETCDF_HDF5PARALLEL_VERSION'],
        }
        self.assertEqual(deps[7]['external_module_metadata'], cray_netcdf_metadata)

        # provide file with full metadata for external modules;
        # this data wins over probed metadata from modules (for backwards compatibility)
        metadatatxt = '\n'.join([
            '[pi/3.14]',
            'name = PI',
            'version = 3.14',
            'prefix = PI_PREFIX',
            '[test/9.7.5]',
            'name = test',
            'version = 9.7.5',
            'prefix = TEST_INC/..',
            '[foobar/1.2.3]',
            'name = foo,bar',
            'version = 1.2.3, 3.2.1',
            'prefix = /foo/bar',
            '[cray-netcdf-hdf5parallel/1.10.6]',
            'name = HDF5',
            'version = 1.10.6-1',
            'prefix = /netcdf-par/1.10.6',
        ])
        write_file(metadata, metadatatxt)
        build_options = {
            'external_modules_metadata': parse_external_modules_metadata([metadata]),
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)
        ec = EasyConfig(toy_ec)
        deps = ec.dependencies()

        self.assertEqual(deps[3]['short_mod_name'], 'foobar/1.2.3')
        self.assertEqual(deps[3]['external_module'], True)
        metadata = {
            'name': ['foo', 'bar'],
            'version': ['1.2.3', '3.2.1'],
            'prefix': '/foo/bar',
        }
        self.assertEqual(deps[3]['external_module_metadata'], metadata)

        self.assertEqual(deps[4]['short_mod_name'], 'test/9.7.5')
        self.assertEqual(deps[4]['external_module'], True)
        metadata = {
            'name': ['test'],
            'version': ['9.7.5'],
            'prefix': 'TEST_INC/..',
        }
        self.assertEqual(deps[4]['external_module_metadata'], metadata)

        self.assertEqual(deps[5]['short_mod_name'], 'pi/3.14')
        self.assertEqual(deps[5]['external_module'], True)
        metadata = {
            'name': ['PI'],
            'version': ['3.14'],
            'prefix': 'PI_PREFIX',
        }
        self.assertEqual(deps[5]['external_module_metadata'], metadata)

        self.assertEqual(deps[7]['full_mod_name'], 'cray-netcdf-hdf5parallel/1.10.6')
        cray_netcdf_metadata = {
            'name': ['HDF5'],
            'prefix': '/netcdf-par/1.10.6',
            'version': ['1.10.6-1'],
        }
        self.assertEqual(deps[7]['external_module_metadata'], cray_netcdf_metadata)

        # get rid of modules first
        self.modtool.unuse(mod_dir)
        remove_dir(mod_dir)

        # check whether $EBROOT*/$EBVERSION* environment variables are defined correctly for external modules
        os.environ['PI_PREFIX'] = '/test/prefix/PI'
        os.environ['TEST_INC'] = '/test/prefix/test/include'
        ec.toolchain.dry_run = True
        ec.toolchain.prepare(deps=ec.dependencies(), silent=True)

        self.assertEqual(os.environ.get('EBROOTBAR'), '/foo/bar')
        self.assertEqual(os.environ.get('EBROOTFOO'), '/foo/bar')
        self.assertEqual(os.environ.get('EBROOTHIDDEN'), None)
        self.assertEqual(os.environ.get('EBROOTHDF5'), '/netcdf-par/1.10.6')
        self.assertEqual(os.environ.get('EBROOTPI'), '/test/prefix/PI')
        self.assertEqual(os.environ.get('EBROOTTEST'), '/test/prefix/test/include/../')
        self.assertEqual(os.environ.get('EBVERSIONBAR'), '3.2.1')
        self.assertEqual(os.environ.get('EBVERSIONFOO'), '1.2.3')
        self.assertEqual(os.environ.get('EBVERSIONHIDDEN'), None)
        self.assertEqual(os.environ.get('EBVERSIONHDF5'), '1.10.6-1')
        self.assertEqual(os.environ.get('EBVERSIONPI'), '3.14')
        self.assertEqual(os.environ.get('EBVERSIONTEST'), '9.7.5')

    def test_external_dependencies_templates(self):
        """Test use of templates for dependencies marked as external modules."""

        topdir = os.path.dirname(os.path.abspath(__file__))
        toy_ec = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        toy_ectxt = read_file(toy_ec)

        extra_ectxt = '\n'.join([
            "versionsuffix = '-Python-%(pyver)s-Perl-%(perlshortver)s'",
            '',
            "dependencies = [",
            "    ('cray-python/3.6.5.7', EXTERNAL_MODULE),",
            "    ('perl/5.30.0-1', EXTERNAL_MODULE),",
            "]",
        ])
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, toy_ectxt + '\n' + extra_ectxt)

        # put metadata in place so templates can be defined
        metadata = os.path.join(self.test_prefix, 'external_modules_metadata.cfg')
        metadatatxt = '\n'.join([
            '[cray-python]',
            'name = Python',
            '[cray-python/3.6.5.7]',
            'version = 3.6.5',
            '[perl/5.30.0-1]',
            'name = Perl',
            'version = 5.30.0',
        ])
        write_file(metadata, metadatatxt)
        build_options = {
            'external_modules_metadata': parse_external_modules_metadata([metadata]),
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)

        ec = EasyConfig(test_ec)

        expected_template_values = {
            'perlmajver': '5',
            'perlminver': '30',
            'perlshortver': '5.30',
            'perlver': '5.30.0',
            'pymajver': '3',
            'pyminver': '6',
            'pyshortver': '3.6',
            'pyver': '3.6.5',
        }
        for key in expected_template_values:
            self.assertEqual(ec.template_values[key], expected_template_values[key])

        self.assertEqual(ec['versionsuffix'], '-Python-3.6.5-Perl-5.30')

    def test_update(self):
        """Test use of update() method for EasyConfig instances."""
        topdir = os.path.abspath(os.path.dirname(__file__))
        toy_ebfile = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        ec = EasyConfig(toy_ebfile)

        # for string values: append
        ec.update('unpack_options', '--strip-components=1')
        self.assertEqual(ec['unpack_options'].strip(), '--strip-components=1')

        ec.update('description', "- just a test")
        self.assertEqual(ec['description'].strip(), "Toy C program, 100% toy. - just a test")

        # spaces in between multiple updates for string values
        ec.update('configopts', 'CC="$CC"')
        ec.update('configopts', 'CXX="$CXX"')
        self.assertTrue(ec['configopts'].strip().endswith('CC="$CC"  CXX="$CXX"'))
        # spaces in between multiple updates for string values from list
        ec.update('configopts', ['MORE_VALUE', 'EVEN_MORE'])
        self.assertTrue(ec['configopts'].strip().endswith('MORE_VALUE  EVEN_MORE'))

        # for list values: extend
        ec.update('patches', ['foo.patch', 'bar.patch'])
        toy_patch_fn = 'toy-0.0_fix-silly-typo-in-printf-statement.patch'
        self.assertEqual(ec['patches'], [toy_patch_fn, ('toy-extra.txt', 'toy-0.0'), 'foo.patch', 'bar.patch'])

        # for unallowed duplicates on string values
        ec.update('configopts', 'SOME_VALUE')
        configopts_tmp = ec['configopts']
        ec.update('configopts', 'SOME_VALUE', allow_duplicate=False)
        self.assertEqual(ec['configopts'], configopts_tmp)
        ec.update('configopts', ['CC="$CC"', 'SOME_VALUE'], allow_duplicate=False)
        self.assertEqual(ec['configopts'], configopts_tmp)

        # for unallowed duplicates when a list is used
        ec.update('patches', ['foo2.patch', 'bar2.patch'])
        patches_tmp = copy.deepcopy(ec['patches'])
        ec.update('patches', ['foo2.patch', 'bar2.patch'], allow_duplicate=False)
        self.assertEqual(ec['patches'], patches_tmp)

        # for dictionary values: extend, test for existence (not ordering)
        ec.update('sanity_check_paths', {'key1': 'value1'})
        self.assertTrue(ec['sanity_check_paths']['key1'] == 'value1')

    def test_hide_hidden_deps(self):
        """Test use of --hide-deps on hiddendependencies."""
        test_dir = os.path.dirname(os.path.abspath(__file__))
        ec_file = os.path.join(test_dir, 'easyconfigs', 'test_ecs', 'g', 'gzip', 'gzip-1.4-GCC-4.6.3.eb')
        ec = EasyConfig(ec_file)
        self.assertEqual(ec['hiddendependencies'][0]['full_mod_name'], 'toy/.0.0-deps')
        self.assertEqual(ec['dependencies'][0]['full_mod_name'], 'toy/.0.0-deps')

        build_options = {
            'hide_deps': ['toy'],
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)
        ec = EasyConfig(ec_file)
        self.assertEqual(ec['hiddendependencies'][0]['full_mod_name'], 'toy/.0.0-deps')
        self.assertEqual(ec['dependencies'][0]['full_mod_name'], 'toy/.0.0-deps')

    def test_quote_str(self):
        """Test quote_str function."""
        teststrings = {
            'foo': '"foo"',
            'foo\'bar': '"foo\'bar"',
            'foo\'bar"baz': '"""foo\'bar"baz"""',
            "foo\nbar": '"foo\nbar"',
            'foo bar': '"foo bar"',
            'foo\\bar': '"foo\\bar"',
        }

        for t in teststrings:
            self.assertEqual(quote_str(t), teststrings[t])

        # test escape_newline
        self.assertEqual(quote_str("foo\nbar", escape_newline=False), '"foo\nbar"')
        self.assertEqual(quote_str("foo\nbar", escape_newline=True), '"""foo\nbar"""')

        # test prefer_single_quotes
        self.assertEqual(quote_str("foo", prefer_single_quotes=True), "'foo'")
        self.assertEqual(quote_str('foo bar', prefer_single_quotes=True), '"foo bar"')
        self.assertEqual(quote_str("foo'bar", prefer_single_quotes=True), '"foo\'bar"')

        # test escape_backslash
        self.assertEqual(quote_str('foo\\bar', escape_backslash=False), '"foo\\bar"')
        self.assertEqual(quote_str('foo\\bar', escape_backslash=True), '"foo\\\\bar"')

        # non-string values
        n = 42
        self.assertEqual(quote_str(n), 42)
        self.assertEqual(quote_str(["foo", "bar"]), ["foo", "bar"])
        self.assertEqual(quote_str(('foo', 'bar')), ('foo', 'bar'))

    def test_quote_py_str(self):
        """Test quote_py_str function."""

        res = quote_py_str('description = """Example of\n multi-line\n description with \' quotes"""')
        self.assertEqual(res, '"""description = """Example of\n multi-line\n description with \' quotes""""""')

        res = quote_py_str('preconfigopts = "sed -i \'s/`which \\([a-z_]*\\)`/\\1/g;s/`//g\' foo.c && "')
        self.assertEqual(res, '"""preconfigopts = "sed -i \'s/`which \\\\([a-z_]*\\\\)`/\\\\1/g;s/`//g\' foo.c && """"')

    def test_dump(self):
        """Test EasyConfig's dump() method."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        build_options = {
            'check_osdeps': False,
            'robot_path': [test_ecs_dir],
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)
        ecfiles = [
            't/toy/toy-0.0.eb',
            'f/foss/foss-2018a.eb',
            's/ScaLAPACK/ScaLAPACK-2.0.2-gompi-2018a-OpenBLAS-0.2.20.eb',
            'g/gzip/gzip-1.4-GCC-4.6.3.eb',
            'p/Python/Python-2.7.10-intel-2018a.eb',
        ]
        for ecfile in ecfiles:
            test_ec = os.path.join(self.test_prefix, 'test.eb')

            ec = EasyConfig(os.path.join(test_ecs_dir, ecfile))
            ec.enable_templating = False
            ecdict = ec.asdict()
            ec.dump(test_ec)
            # dict representation of EasyConfig instance should not change after dump
            self.assertEqual(ecdict, ec.asdict())
            ectxt = read_file(test_ec)

            patterns = [
                r"^name = ['\"]",
                r"^version = ['0-9\.]",
                r'^description = ["\']',
                r"^toolchain = {'name': .*, 'version': .*}",
            ]
            for pattern in patterns:
                regex = re.compile(pattern, re.M)
                self.assertTrue(regex.search(ectxt), "Pattern '%s' found in: %s" % (regex.pattern, ectxt))

            # parse result again
            dumped_ec = EasyConfig(test_ec)
            dumped_ec.enable_templating = False

            # check that selected parameters still have the same value
            params = [
                'name',
                'toolchain',
                'dependencies',  # checking this is important w.r.t. filtered hidden dependencies being restored in dump
                'exts_list',  # exts_lists (in Python easyconfig) use another layer of templating so shouldn't change
            ]
            for param in params:
                if param in ec:
                    self.assertEqual(ec[param], dumped_ec[param])

    def test_toolchain_hierarchy_aware_dump(self):
        """Test that EasyConfig's dump() method is aware of the toolchain hierarchy."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        build_options = {
            'check_osdeps': False,
            'robot_path': [test_ecs_dir],
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)
        rawtxt = '\n'.join([
            "easyblock = 'EB_foo'",
            '',
            "name = 'foo'",
            "version = '0.0.1'",
            '',
            "toolchain = {'name': 'foss', 'version': '2018a'}",
            '',
            "homepage = 'http://foo.com/'",
            'description = "foo description"',
            '',
            'sources = [SOURCE_TAR_GZ]',
            'source_urls = ["http://example.com"]',
            'checksums = ["6af6ab95ce131c2dd467d2ebc8270e9c265cc32496210b069e51d3749f335f3d"]',
            '',
            "dependencies = [",
            "    ('toy', '0.0', '', ('gompi', '2018a')),",
            "    ('bar', '1.0'),",
            "    ('foobar/1.2.3', EXTERNAL_MODULE),",
            "]",
            '',
            "foo_extra1 = 'foobar'",
            '',
            'moduleclass = "tools"',
        ])

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        ec = EasyConfig(None, rawtxt=rawtxt)
        ecdict = ec.asdict()
        ec.dump(test_ec)
        # dict representation of EasyConfig instance should not change after dump
        self.assertEqual(ecdict, ec.asdict())
        ectxt = read_file(test_ec)
        dumped_ec = EasyConfig(test_ec)
        self.assertEqual(ecdict, dumped_ec.asdict())
        self.assertTrue(r"'toy', '0.0')," in ectxt)
        # test case where we ask for explicit toolchains
        ec.dump(test_ec, explicit_toolchains=True)
        self.assertEqual(ecdict, ec.asdict())
        ectxt = read_file(test_ec)
        dumped_ec = EasyConfig(test_ec)
        self.assertEqual(ecdict, dumped_ec.asdict())
        self.assertTrue(r"'toy', '0.0', '', ('gompi', '2018a'))," in ectxt)

    def test_dump_order(self):
        """Test order of easyconfig parameters in dumped easyconfig."""
        rawtxt = '\n'.join([
            "homepage = 'http://foo.com/'",
            '',
            "name = 'foo'",
            "versionsuffix = '_bar'",
            '',
            'patches = ["one.patch"]',
            "easyblock = 'EB_foo'",
            '',
            "toolchain = SYSTEM",
            '',
            'checksums = ["6af6ab95ce131c2dd467d2ebc8270e9c265cc32496210b069e51d3749f335f3d"]',
            "dependencies = [",
            "    ('GCC', '4.6.4', '-test'),",
            "    ('MPICH', '1.8', '', ('GCC', '4.6.4')),",
            "    ('bar', '1.0'),",
            "    ('foobar/1.2.3', EXTERNAL_MODULE),",
            "]",
            "version = '0.0.1'",
            'description = "foo description"',
            '',
            'source_urls = ["http://example.com"]',
            "foo_extra1 = 'foobar'",
            '',
            'sources = [SOURCE_TAR_GZ]',
            'moduleclass = "tools"',
        ])

        param_regex = re.compile('^(?P<param>[a-z0-9_]+) = |^$', re.M)

        # make sure regex finds all easyconfig parameters in the order they appear in the easyconfig
        expected = ['homepage', '', 'name', 'versionsuffix', '', 'patches', 'easyblock', '', 'toolchain', '',
                    'checksums', 'dependencies', 'version', 'description', '', 'source_urls', 'foo_extra1',
                    '', 'sources', 'moduleclass']
        self.assertEqual(param_regex.findall(rawtxt), expected)

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        ec = EasyConfig(None, rawtxt=rawtxt)
        ec.dump(test_ec)
        ectxt = read_file(test_ec)

        # easyconfig parameters should be properly ordered/grouped in dumped easyconfig
        expected = ['easyblock', '', 'name', 'version', 'versionsuffix', '', 'homepage', 'description', '',
                    'toolchain', '', 'source_urls', 'sources', 'patches', 'checksums', '', 'dependencies', '',
                    'foo_extra1', '', 'moduleclass', '']
        self.assertEqual(param_regex.findall(ectxt), expected)

    def test_dump_autopep8(self):
        """Test dump() with autopep8 usage enabled (only if autopep8 is available)."""
        try:
            import autopep8  # noqa
            os.environ['EASYBUILD_DUMP_AUTOPEP8'] = '1'
            init_config()
            self.test_dump()
            del os.environ['EASYBUILD_DUMP_AUTOPEP8']
        except ImportError:
            print("Skipping test_dump_autopep8, since autopep8 is not available")

    def test_dump_extra(self):
        """Test EasyConfig's dump() method for files containing extra values"""

        if not ('pycodestyle' in sys.modules or 'pep8' in sys.modules):
            print("Skipping test_dump_extra (no pycodestyle or pep8 available)")
            return

        rawtxt = '\n'.join([
            "easyblock = 'EB_foo'",
            '',
            "name = 'foo'",
            "version = '0.0.1'",
            "versionsuffix = '_bar'",
            '',
            "homepage = 'http://foo.com/'",
            'description = "foo description"',
            '',
            "toolchain = {'name': 'system', 'version': 'system'}",
            '',
            "dependencies = [",
            "    ('GCC', '4.6.4', '-test'),",
            "    ('MPICH', '1.8', '', ('GCC', '4.6.4')),",
            "    ('bar', '1.0'),",
            "    ('foobar/1.2.3', EXTERNAL_MODULE),",
            "]",
            '',
            "foo_extra1 = 'foobar'",
            '',
        ])

        handle, testec = tempfile.mkstemp(prefix=self.test_prefix, suffix='.eb')
        os.close(handle)

        ec = EasyConfig(None, rawtxt=rawtxt)
        ec.dump(testec)
        ectxt = read_file(testec)
        self.assertEqual(rawtxt, ectxt)

        # check parsing of dumped easyconfig
        EasyConfig(testec)

        check_easyconfigs_style([testec])

    def test_dump_template(self):
        """ Test EasyConfig's dump() method for files containing templates"""

        if not ('pycodestyle' in sys.modules or 'pep8' in sys.modules):
            print("Skipping test_dump_template (no pycodestyle or pep8 available)")
            return

        rawtxt = '\n'.join([
            "easyblock = 'EB_foo'",
            '',
            "name = 'Foo'",
            "version = '1.0.0'",
            "versionsuffix = '-test'",
            '',
            "homepage = 'http://foo.com/'",
            'description = "foo description"',
            '',
            "toolchain = {",
            "    'version': 'system',",
            "    'name': 'system',",
            '}',
            '',
            "sources = [",
            "    'foo-1.0.0.tar.gz',",
            ']',
            '',
            "dependencies = [",
            "    ('bar', '1.2.3', '-test'),",
            ']',
            '',
            "preconfigopts = '--opt1=%s' % name",
            "configopts = '--opt2=1.0.0'",
            '',
            'exts_default_options = {',
            "    'source_urls': ['https://example.com/files/1.0.0'],"
            '}',
            'exts_list = [',
            '  ("ext1", "1.0.0"),'
            '  ("ext2", "2.1.3"),'
            ']',
            "sanity_check_paths = {",
            "    'files': ['files/foo/foobar', 'files/x-test'],",
            "    'dirs':[],",
            '}',
            '',
            "foo_extra1 = 'foobar'",
            '',
            'moduleclass = "tools"',
        ])

        handle, testec = tempfile.mkstemp(prefix=self.test_prefix, suffix='.eb')
        os.close(handle)

        ec = EasyConfig(None, rawtxt=rawtxt)
        ec.dump(testec)
        ectxt = read_file(testec)

        self.assertTrue(ec.enable_templating)  # templating should still be enabled after calling dump()

        patterns = [
            r"easyblock = 'EB_foo'",
            r"name = 'Foo'",
            r"version = '1.0.0'",
            r"versionsuffix = '-test'",
            r"homepage = 'http://foo.com/'",
            r'description = "foo description"',  # no templating for description
            r"sources = \[SOURCELOWER_TAR_GZ\]",
            # use of templates in *dependencies is disabled for now, since it can cause problems
            # r"dependencies = \[\n    \('bar', '1.2.3', '%\(versionsuffix\)s'\),\n\]",
            r"preconfigopts = '--opt1=%\(name\)s'",
            r"configopts = '--opt2=%\(version\)s'",
            # no %(version)s template used in exts_default_options or exts_list
            # see https://github.com/easybuilders/easybuild-framework/issues/3091
            r"exts_default_options = {'source_urls': \['https://example.com/files/1\.0\.0'\]}",
            r"\('ext1', '1\.0\.0'\),",
            r"sanity_check_paths = {\n    'files': \['files/%\(namelower\)s/foobar', 'files/x-test'\]",
        ]

        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(ectxt), "Pattern '%s' found in: %s" % (regex.pattern, ectxt))

        ectxt.endswith('moduleclass = "tools"')

        # reparsing the dumped easyconfig file should work
        EasyConfig(testec)

        check_easyconfigs_style([testec])

    def test_dump_comments(self):
        """ Test dump() method for files containing comments """

        if not ('pycodestyle' in sys.modules or 'pep8' in sys.modules):
            print("Skipping test_dump_comments (no pycodestyle or pep8 available)")
            return

        rawtxt = '\n'.join([
            "# #",
            "# some header comment",
            "# #",
            "easyblock = 'EB_foo'",
            '',
            "name = 'Foo'  # name comment",
            "version = '0.0.1'",
            "versionsuffix = '-test'",
            '',
            "# comment on the homepage",
            "homepage = 'http://foo.com/'",
            'description = "foo description with a # in it"  # test',
            '',
            "# toolchain comment",
            '',
            "toolchain = {",
            "    'version': 'system',",
            "    'name': 'system'",
            '}',
            '',
            "sanity_check_paths = {",
            "    'files': ['files/foobar'],  # comment on files",
            "    'dirs':[]",
            '}',
            '',
            "foo_extra1 = 'foobar'",
            "# trailing comment",
        ])

        handle, testec = tempfile.mkstemp(prefix=self.test_prefix, suffix='.eb')
        os.close(handle)

        ec = EasyConfig(None, rawtxt=rawtxt)

        # check internal structure to keep track of comments
        self.assertEqual(ec.parser._formatter.comments['above'], {
            'homepage': ["# comment on the homepage"],
            'toolchain': ['# toolchain comment', ''],
        })
        self.assertEqual(ec.parser._formatter.comments['header'], ['# #', '# some header comment', '# #'])
        self.assertEqual(ec.parser._formatter.comments['inline'], {
            'description': '  # test',
            'name': "  # name comment",
        })
        self.assertEqual(ec.parser._formatter.comments['iterabove'], {})
        self.assertEqual(ec.parser._formatter.comments['iterinline'], {
            'sanity_check_paths': {"    'files': ['files/foobar'],": "  # comment on files"},
        })
        self.assertEqual(ec.parser._formatter.comments['tail'], ["# trailing comment"])

        ec.dump(testec)
        ectxt = read_file(testec)

        patterns = [
            r"# #\n# some header comment\n# #",
            r"name = 'Foo'  # name comment",
            r"# comment on the homepage\nhomepage = 'http://foo.com/'",
            r'description = "foo description with a # in it"  # test',
            r"# toolchain comment\n\ntoolchain = {",
            r"    'files': \['files/foobar'\],  # comment on files",
            r"    'dirs': \[\],",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(ectxt), "Pattern '%s' found in: %s" % (regex.pattern, ectxt))

        self.assertTrue(ectxt.endswith("# trailing comment\n"))

        # reparsing the dumped easyconfig file should work
        EasyConfig(testec)

        check_easyconfigs_style([testec])

        # another, more extreme example
        # inspired by https://github.com/easybuilders/easybuild-framework/issues/3082
        write_file(testec, '')
        rawtxt = '\n'.join([
            "# this is a header",
            "#",
            "# which may include empty comment lines",
            "    # weirdly indented lines",
            '  ',  # whitespace-only line, should get stripped (but no # added)
            "# or flat out empty lines",
            '',
            "easyblock = 'ConfigureMake'",
            '',
            "name = 'thisisjustatest'  # just a test",
            "# the version doesn't matter much here",
            "version = '1.2.3'",
            '',
            "homepage = 'https://example.com'  # may not be actual homepage",
            "description = \"\"\"Sneaky description with hashes, line #1",
            " line #2",
            " line without hashes",
            "#4 (yeah, sneaky, isn't it),",
            "end line",
            "\"\"\"",
            '',
            "toolchain = SYSTEM",
            "# after toolchain, before sources comment",
            '',
            "# this comment contains another #, uh-oh...",
            "sources = ['test-1.2.3.tar.gz']",
            "# how about # a comment with # multple additional hashes",
            "source_urls = [",
            "    # first possible source URL",
            "    'https://example.com',",
            "# annoying non-indented comment",
            "    'https://anotherexample.com',  # fallback URL",
            "]",
            '',
            "# this is a multiline comment above dependencies",
            "# I said multiline",
            "# multi > 3",
            "dependencies = [",
            "    # this dependency",
            "# has multiple lines above it",
            "    # some of which without proper indentation...",
            "    ('foo', '1.2.3'),  # and an inline comment too",
            "    ('nocomment', '4.5'),",
            "    # last dependency, I promise",
            "    ('last', '1.2.3'),",
            "    # trailing comments in dependencies",
            "    # a bit weird, but it happens",
            "]  # inline comment after closing dependencies",
            '',
            "# how about comments above and in a dict value?",
            "sanity_check_paths = {",
            "    # a bunch of files",
            "    'files': ['bin/foo', 'lib/libfoo.a'],",
            "    # no dirs!",
            "    'dirs': [],",
            "}",
            '',
            "moduleclass = 'tools'",
            "#",
            "# trailing comment",
            '',
            "# with an empty line in between",
            "# DONE!",
        ])
        ec = EasyConfig(None, rawtxt=rawtxt)

        # check internal structure to keep track of comments
        self.assertEqual(ec.parser._formatter.comments['above'], {
            'dependencies': [
                '# this is a multiline comment above dependencies',
                '# I said multiline',
                '# multi > 3',
            ],
            'sanity_check_paths': ['# how about comments above and in a dict value?'],
            'source_urls': ['# how about # a comment with # multple additional hashes'],
            'sources': ['# after toolchain, before sources comment',
                        '',
                        '# this comment contains another #, uh-oh...'],
            'version': ["# the version doesn't matter much here"],
        })
        self.assertEqual(ec.parser._formatter.comments['header'], [
            '# this is a header',
            '#',
            '# which may include empty comment lines',
            '# weirdly indented lines',
            '',
            '# or flat out empty lines',
            '',
        ])
        self.assertEqual(ec.parser._formatter.comments['inline'], {
            'homepage': '  # may not be actual homepage',
            'name': '  # just a test',
        })
        self.assertEqual(ec.parser._formatter.comments['iterabove'], {
            'dependencies': {
                "    ('foo', '1.2.3'),": ['# this dependency',
                                          '# has multiple lines above it',
                                          "# some of which without proper indentation..."],
                "    ('last', '1.2.3'),": ['# last dependency, I promise'],
                ']': ['# trailing comments in dependencies', '# a bit weird, but it happens'],
            },
            'sanity_check_paths': {
                "    'dirs': [],": ['# no dirs!'],
                "    'files': ['bin/foo', 'lib/libfoo.a'],": ['# a bunch of files'],
            },
            'source_urls': {
                "    'https://example.com',": ['# first possible source URL'],
                "    'https://anotherexample.com',": ['# annoying non-indented comment'],
            },
        })
        self.assertEqual(ec.parser._formatter.comments['iterinline'], {
            'dependencies': {
                "    ('foo', '1.2.3'),": '  # and an inline comment too',
                ']': "  # inline comment after closing dependencies",
            },
            'source_urls': {
                "    'https://anotherexample.com',": '  # fallback URL',
            },
        })
        self.assertEqual(ec.parser._formatter.comments['tail'], [
            '#',
            '# trailing comment',
            '',
            '# with an empty line in between',
            '# DONE!',
        ])

        ec.dump(testec)
        ectxt = read_file(testec)

        # reparsing the dumped easyconfig file should work
        EasyConfig(testec)

        check_easyconfigs_style([testec])

        self.assertTrue(ectxt.startswith('\n'.join([
            '# this is a header',
            '#',
            '# which may include empty comment lines',
            '# weirdly indented lines',
            '',
            '# or flat out empty lines',
            '',
        ])))

        patterns = [
            # inline comments
            r"^homepage = .*  # may not be actual homepage\n",
            r"^name = .*  # just a test",
            r"^    \('foo', '1\.2\.3'\),  # and an inline comment too",
            r"^    'https://anotherexample\.com',  # fallback URL",
            # comments above parameter definition
            '\n'.join([
                r'',
                r"# this is a multiline comment above dependencies",
                r"# I said multiline",
                r"# multi > 3",
                r"dependencies = ",
            ]),
            '\n'.join([
                r'',
                r"# how about comments above and in a dict value\?",
                r"sanity_check_paths = ",
            ]),
            '\n'.join([
                r'',
                r"# how about # a comment with # multple additional hashes",
                r"source_urls = ",
            ]),
            '\n'.join([
                r'',
                r"# after toolchain, before sources comment",
                r'',
                r"# this comment contains another #, uh-oh...",
                r"sources = ",
            ]),
            '\n'.join([
                r'',
                r"# the version doesn't matter much here",
                r"version = ",
            ]),
            '\n'.join([
                r'',
                r"    # trailing comments in dependencies",
                r"    # a bit weird, but it happens",
                r"\]  # inline comment after closing dependencies",
            ]),
            # comments above element of iterable parameter value
            '\n'.join([
                r'',
                r"    # this dependency",
                r"    # has multiple lines above it",
                r"    # some of which without proper indentation\.\.\.",
                r"    \('foo', '1\.2\.3'\),  # and an inline comment too",
            ]),
            '\n'.join([
                r'',
                r"    # last dependency, I promise",
                r"    \('last', '1\.2\.3'\),"
            ]),
            '\n'.join([
                '',
                r"    # no dirs\!",
                r"    'dirs': \[\],"
            ]),
            '\n'.join([
                '',
                r"    # a bunch of files",
                r"    'files': \['bin/foo', 'lib/libfoo\.a'\],",
            ]),
            '\n'.join([
                '',
                r"    # first possible source URL",
                r"    'https://example\.com',",
            ]),
            '\n'.join([
                '',
                r"    # annoying non-indented comment",
                r"    'https://anotherexample\.com',  # fallback URL",
            ]),
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(ectxt), "Pattern '%s' found in: %s" % (regex.pattern, ectxt))

        self.assertTrue(ectxt.endswith('\n'.join([
            '#',
            '# trailing comment',
            '',
            '# with an empty line in between',
            '# DONE!',
            '',
        ])))

    def test_to_template_str(self):
        """ Test for to_template_str method """

        # reverse dict of known template constants; template values (which are keys here) must be 'string-in-string
        templ_const = {
            "template": 'TEMPLATE_VALUE',
            "%(name)s-%(version)s": 'NAME_VERSION',
        }

        templ_val = {
            'foo': 'name',
            '0.0.1': 'version',
            '-test': 'special_char',
        }

        self.assertEqual(to_template_str('test', "template", templ_const, templ_val), 'TEMPLATE_VALUE')
        self.assertEqual(to_template_str('test', "foo/bar/0.0.1/", templ_const, templ_val), "%(name)s/bar/%(version)s/")
        self.assertEqual(to_template_str('test', "foo-0.0.1", templ_const, templ_val), 'NAME_VERSION')
        templ_list = to_template_str('test', "['-test', 'dontreplacenamehere']", templ_const, templ_val)
        self.assertEqual(templ_list, "['%(special_char)s', 'dontreplacenamehere']")
        templ_dict = to_template_str('test', "{'a': 'foo', 'b': 'notemplate'}", templ_const, templ_val)
        self.assertEqual(templ_dict, "{'a': '%(name)s', 'b': 'notemplate'}")
        templ_tuple = to_template_str('test', "('foo', '0.0.1')", templ_const, templ_val)
        self.assertEqual(templ_tuple, "('%(name)s', '%(version)s')")

        # if easyconfig parameter name and name of matching template are identical, no replacement
        templ_val = OrderedDict([('-Python-2.7.15', 'versionsuffix'), ('2.7.15', 'pyver'), ('2.7', 'pyshortver')])
        test_input = '-Python-2.7.15'
        self.assertEqual(to_template_str('versionsuffix', test_input, templ_const, templ_val), '-Python-%(pyver)s')
        self.assertEqual(to_template_str('test', test_input, templ_const, templ_val), '%(versionsuffix)s')

        # test special case for 'python%(pyshortver)s'
        test_input = "sanity_check_paths = {\n    'files': [],\n    'dirs': ['lib/python2.7/site-packages'],\n}"
        res = "sanity_check_paths = {\n    'files': [],\n    'dirs': ['lib/python%(pyshortver)s/site-packages'],\n}"
        self.assertEqual(to_template_str('sanity_check_paths', test_input, templ_const, templ_val), res)

    def test_dep_graph(self):
        """Test for dep_graph."""
        try:
            import pygraph  # noqa

            test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
            build_options = {
                'external_modules_metadata': ConfigObj(),
                'valid_module_classes': module_classes(),
                'robot_path': [test_easyconfigs],
                'silent': True,
            }
            init_config(build_options=build_options)

            ec_file = os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0-deps.eb')
            ec_files = [(ec_file, False)]
            ecs, _ = parse_easyconfigs(ec_files)

            dot_file = os.path.join(self.test_prefix, 'test.dot')
            ordered_ecs = resolve_dependencies(ecs, self.modtool, retain_all_deps=True)
            dep_graph(dot_file, ordered_ecs)

            # hard check for expect .dot file contents
            # 3 nodes should be there: 'GCC/6.4.0-2.28 (EXT)', 'toy', and 'intel/2018a'
            # and 2 edges: 'toy -> intel' and 'toy -> "GCC/6.4.0-2.28 (EXT)"'
            dottxt = read_file(dot_file)

            self.assertTrue(dottxt.startswith('digraph graphname {'))

            # compare sorted output, since order of lines can change
            ordered_dottxt = '\n'.join(sorted(dottxt.split('\n')))
            ordered_expected = '\n'.join(sorted(EXPECTED_DOTTXT_TOY_DEPS.split('\n')))
            self.assertEqual(ordered_dottxt, ordered_expected)

        except ImportError:
            print("Skipping test_dep_graph, since pygraph is not available")

    def test_dep_graph_multi_deps(self):
        """
        Test for dep_graph using easyconfig that uses multi_deps.
        """
        try:
            import pygraph  # noqa

            test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
            build_options = {
                'external_modules_metadata': ConfigObj(),
                'valid_module_classes': module_classes(),
                'robot_path': [test_easyconfigs],
                'silent': True,
            }
            init_config(build_options=build_options)

            toy_ec = os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb')
            toy_ec_txt = read_file(toy_ec)

            test_ec = os.path.join(self.test_prefix, 'test.eb')
            test_ec_txt = toy_ec_txt + "\nmulti_deps = {'GCC': ['4.6.3', '4.8.3', '7.3.0-2.30']}"
            write_file(test_ec, test_ec_txt)

            ec_files = [(test_ec, False)]
            ecs, _ = parse_easyconfigs(ec_files)

            dot_file = os.path.join(self.test_prefix, 'test.dot')
            ordered_ecs = resolve_dependencies(ecs, self.modtool, retain_all_deps=True)
            dep_graph(dot_file, ordered_ecs)

            # hard check for expect .dot file contents
            # 3 nodes should be there: 'GCC/6.4.0-2.28 (EXT)', 'toy', and 'intel/2018a'
            # and 2 edges: 'toy -> intel' and 'toy -> "GCC/6.4.0-2.28 (EXT)"'
            dottxt = read_file(dot_file)

            self.assertTrue(dottxt.startswith('digraph graphname {'))

            # just check for toy -> GCC deps
            # don't bother doing full output check
            # (different order for fields depending on Python version makes that tricky)
            for gccver in ['4.6.3', '4.8.3', '7.3.0-2.30']:
                self.assertTrue('"GCC/%s";' % gccver in dottxt)
                self.assertTrue('"toy/0.0" -> "GCC/%s"' % gccver in dottxt)

        except ImportError:
            print("Skipping test_dep_graph, since pygraph is not available")

    def test_ActiveMNS_singleton(self):
        """Make sure ActiveMNS is a singleton class."""

        mns1 = ActiveMNS()
        mns2 = ActiveMNS()
        self.assertEqual(id(mns1), id(mns2))

    def test_ActiveMNS_det_full_module_name(self):
        """Test det_full_module_name method of ActiveMNS."""
        build_options = {
            'valid_module_classes': module_classes(),
            'external_modules_metadata': ConfigObj(),
        }

        init_config(build_options=build_options)
        topdir = os.path.dirname(os.path.abspath(__file__))
        ec_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-deps.eb')
        ec = EasyConfig(ec_file)

        self.assertEqual(ActiveMNS().det_full_module_name(ec), 'toy/0.0-deps')
        self.assertEqual(ActiveMNS().det_full_module_name(ec['dependencies'][0]), 'intel/2018a')
        self.assertEqual(ActiveMNS().det_full_module_name(ec['dependencies'][1]), 'GCC/6.4.0-2.28')

        ec_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 'g', 'gzip', 'gzip-1.4-GCC-4.6.3.eb')
        ec = EasyConfig(ec_file)
        hiddendep = ec['hiddendependencies'][0]
        self.assertEqual(ActiveMNS().det_full_module_name(hiddendep), 'toy/.0.0-deps')
        self.assertEqual(ActiveMNS().det_full_module_name(hiddendep, force_visible=True), 'toy/0.0-deps')

    def test_find_related_easyconfigs(self):
        """Test find_related_easyconfigs function."""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        ec_file = os.path.join(test_easyconfigs, 'g', 'GCC', 'GCC-4.6.3.eb')
        ec = EasyConfig(ec_file)

        # exact match: GCC-4.6.3.eb
        res = [os.path.basename(x) for x in find_related_easyconfigs(test_easyconfigs, ec)]
        self.assertEqual(res, ['GCC-4.6.3.eb'])

        # tweak version to 4.6.1, GCC/4.6.x easyconfigs are found as closest match
        ec['version'] = '4.6.1'
        res = [os.path.basename(x) for x in find_related_easyconfigs(test_easyconfigs, ec)]
        self.assertEqual(res, ['GCC-4.6.3.eb', 'GCC-4.6.4.eb'])

        # tweak version to 4.5.0, GCC/4.x easyconfigs are found as closest match
        ec['version'] = '4.5.0'
        res = [os.path.basename(x) for x in find_related_easyconfigs(test_easyconfigs, ec)]
        expected = ['GCC-4.6.3.eb', 'GCC-4.6.4.eb', 'GCC-4.8.2.eb', 'GCC-4.8.3.eb', 'GCC-4.9.2.eb']
        self.assertEqual(res, expected)

        ec_file = os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0-deps.eb')
        ec = EasyConfig(ec_file)

        # exact match
        res = [os.path.basename(x) for x in find_related_easyconfigs(test_easyconfigs, ec)]
        self.assertEqual(res, ['toy-0.0-deps.eb'])

        # tweak toolchain name/version and versionsuffix => closest match with same toolchain name is found
        ec['toolchain'] = {'name': 'gompi', 'version': '1.5.16'}
        ec['versionsuffix'] = '-foobar'
        res = [os.path.basename(x) for x in find_related_easyconfigs(test_easyconfigs, ec)]
        self.assertEqual(res, ['toy-0.0-gompi-2018a-test.eb', 'toy-0.0-gompi-2018a.eb'])

        # restore original versionsuffix => matching versionsuffix wins over matching toolchain (name)
        ec['versionsuffix'] = '-deps'
        res = [os.path.basename(x) for x in find_related_easyconfigs(test_easyconfigs, ec)]
        self.assertEqual(res, ['toy-0.0-deps.eb'])

        # no matches for unknown software name
        ec['name'] = 'nosuchsoftware'
        self.assertEqual(find_related_easyconfigs(test_easyconfigs, ec), [])

        # no problem with special characters in software name
        ec['name'] = 'nosuchsoftware++'
        testplusplus = os.path.join(self.test_prefix, '%s-1.2.3.eb' % ec['name'])
        write_file(testplusplus, "name = %s" % ec['name'])
        res = find_related_easyconfigs(self.test_prefix, ec)
        self.assertTrue(res and os.path.samefile(res[0], testplusplus))

    def test_modaltsoftname(self):
        """Test specifying an alternative name for the software name, to use when determining module name."""
        topdir = os.path.dirname(os.path.abspath(__file__))
        ec_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-deps.eb')
        ectxt = read_file(ec_file)
        modified_ec_file = os.path.join(self.test_prefix, os.path.basename(ec_file))
        write_file(modified_ec_file, ectxt + "\nmodaltsoftname = 'notreallyatoy'")
        ec = EasyConfig(modified_ec_file)
        self.assertEqual(ec.full_mod_name, 'notreallyatoy/0.0-deps')
        self.assertEqual(ec.short_mod_name, 'notreallyatoy/0.0-deps')
        self.assertEqual(ec['name'], 'toy')

    def test_software_license(self):
        """Tests related to software_license easyconfig parameter."""
        # default: None
        topdir = os.path.dirname(os.path.abspath(__file__))
        ec_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        ec = EasyConfig(ec_file)
        ec.validate_license()
        self.assertEqual(ec['software_license'], None)
        self.assertEqual(ec.software_license, None)

        # specified software license gets handled correctly
        ec_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 'g', 'gzip', 'gzip-1.4.eb')
        ec = EasyConfig(ec_file)
        ec.validate_license()
        # constant GPLv3 is resolved as string
        self.assertEqual(ec['software_license'], 'LicenseGPLv3')
        # software_license is defined as License subclass
        self.assertTrue(isinstance(ec.software_license, LicenseGPLv3))
        self.assertTrue(issubclass(ec.software_license.__class__, License))

        ec['software_license'] = 'LicenseThatDoesNotExist'
        err_pat = r"Invalid license LicenseThatDoesNotExist \(known licenses:"
        self.assertErrorRegex(EasyBuildError, err_pat, ec.validate_license)

    def test_param_value_type_checking(self):
        """Test value tupe checking of easyconfig parameters."""
        topdir = os.path.dirname(os.path.abspath(__file__))
        ec_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 'g', 'gzip', 'gzip-1.4-broken.eb')
        # version parameter has values of wrong type in this broken easyconfig
        error_msg_pattern = "Type checking of easyconfig parameter values failed: .*'version'.*"
        self.assertErrorRegex(EasyBuildError, error_msg_pattern, EasyConfig, ec_file, auto_convert_value_types=False)

        # test default behaviour: auto-converting of mismatching value types
        ec = EasyConfig(ec_file)
        self.assertEqual(ec['version'], '1.4')

    def test_copy(self):
        """Test copy method of EasyConfig object."""
        init_config(build_options={'silent': True})

        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        ec1 = EasyConfig(os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb'))

        # inject fake template value, just to check whether they are copied over too
        ec1.template_values['pyshortver'] = '3.7'

        ec2 = ec1.copy()

        self.assertEqual(ec1, ec2)
        self.assertEqual(ec1.rawtxt, ec2.rawtxt)
        self.assertEqual(ec1.path, ec2.path)
        self.assertEqual(ec1.template_values, ec2.template_values)
        self.assertFalse(ec1.template_values is ec2.template_values)

    def test_eq_hash(self):
        """Test comparing two EasyConfig instances."""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        ec1 = EasyConfig(os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb'))
        ec2 = EasyConfig(os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb'))

        # different instances, same parsed easyconfig
        self.assertFalse(ec1 is ec2)
        self.assertEqual(ec1, ec2)
        self.assertTrue(ec1 == ec2)
        self.assertFalse(ec1 != ec2)

        # hashes should also be identical
        self.assertEqual(hash(ec1), hash(ec2))

        # other parsed easyconfig is not equal
        ec3 = EasyConfig(os.path.join(test_easyconfigs, 'g', 'gzip', 'gzip-1.4.eb'))
        self.assertFalse(ec1 == ec3)
        self.assertTrue(ec1 != ec3)

    def test_copy_easyconfigs(self):
        """Test copy_easyconfigs function."""
        init_config(build_options={'silent': True})
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')

        target_dir = os.path.join(self.test_prefix, 'copied_ecs')
        # easybuild/easyconfigs subdir is expected to exist
        ecs_target_dir = os.path.join(target_dir, 'easybuild', 'easyconfigs')
        mkdir(ecs_target_dir, parents=True)

        # passing an empty list of paths is fine
        res = copy_easyconfigs([], target_dir)
        self.assertEqual(res, {'ecs': [], 'new': [], 'new_file_in_existing_folder': [],
                               'new_folder': [], 'paths': [], 'paths_in_repo': []})
        self.assertEqual(os.listdir(ecs_target_dir), [])

        # copy test easyconfigs, purposely under a different name
        test_ecs = [
            ('g/GCC/GCC-6.4.0-2.28.eb', 'GCC.eb'),
            ('o/OpenMPI/OpenMPI-2.1.2-GCC-6.4.0-2.28.eb', 'openmpi164.eb'),
            ('t/toy/toy-0.0-gompi-2018a-test.eb', 'foo.eb'),
            ('t/toy/toy-0.0.eb', 'TOY.eb'),
        ]
        ecs_to_copy = []
        for (src_ec, target_ec) in test_ecs:
            ecs_to_copy.append(os.path.join(self.test_prefix, target_ec))
            shutil.copy2(os.path.join(test_ecs_dir, src_ec), ecs_to_copy[-1])

        res = copy_easyconfigs(ecs_to_copy, target_dir)
        self.assertEqual(sorted(res.keys()), ['ecs', 'new', 'new_file_in_existing_folder',
                                              'new_folder', 'paths', 'paths_in_repo'])
        self.assertEqual(len(res['ecs']), len(test_ecs))
        self.assertTrue(all(isinstance(ec, EasyConfig) for ec in res['ecs']))
        self.assertTrue(all(res['new']))
        expected = os.path.join(target_dir, 'easybuild', 'easyconfigs', 'g', 'GCC', 'GCC-6.4.0-2.28.eb')
        self.assertTrue(os.path.samefile(res['paths_in_repo'][0], expected))

        # check whether easyconfigs were copied (unmodified) to correct location
        for orig_ec, src_ec in test_ecs:
            orig_ec = os.path.basename(orig_ec)
            copied_ec = os.path.join(ecs_target_dir, orig_ec[0].lower(), orig_ec.split('-')[0], orig_ec)
            self.assertTrue(os.path.exists(copied_ec), "File %s exists" % copied_ec)
            self.assertEqual(read_file(copied_ec), read_file(os.path.join(self.test_prefix, src_ec)))

        # create test easyconfig that includes comments & build stats, just like an archived easyconfig
        toy_ec = os.path.join(self.test_prefix, 'toy.eb')
        copy_file(os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0.eb'), toy_ec)
        toy_ec_txt = read_file(toy_ec)
        toy_ec_txt = '\n'.join([
            "# Built with EasyBuild version 3.1.2 on 2017-04-25_21-35-15",
            toy_ec_txt,
            "# Build statistics",
            "buildstats = [{",
            '   "build_time": 8.34,',
            '   "os_type": "Linux",',
            "}]",
        ])
        write_file(toy_ec, toy_ec_txt)

        # copy single easyconfig with buildstats included for running further tests
        res = copy_easyconfigs([toy_ec], target_dir)

        self.assertEqual([len(x) for x in res.values()], [1, 1, 1, 1, 1, 1])
        self.assertEqual(res['ecs'][0].full_mod_name, 'toy/0.0')

        # toy-0.0.eb was already copied into target_dir, so should not be marked as new anymore
        self.assertFalse(res['new'][0])

        copied_toy_ec = os.path.join(ecs_target_dir, 't', 'toy', 'toy-0.0.eb')
        self.assertTrue(os.path.samefile(res['paths_in_repo'][0], copied_toy_ec))

        # verify whether copied easyconfig gets cleaned up (stripping out 'Built with' comment + build stats)
        txt = read_file(copied_toy_ec)
        regexs = [
            r"# Built with EasyBuild",
            r"# Build statistics",
            r"buildstats\s*=",
        ]
        for regex in regexs:
            regex = re.compile(regex, re.M)
            self.assertFalse(regex.search(txt), "Pattern '%s' NOT found in: %s" % (regex.pattern, txt))

        # make sure copied easyconfig still parses
        ec = EasyConfig(copied_toy_ec)
        self.assertEqual(ec.name, 'toy')
        self.assertEqual(ec['buildstats'], None)

    def test_template_constant_dict(self):
        """Test template_constant_dict function."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        ec = EasyConfig(os.path.join(test_ecs_dir, 'g', 'gzip', 'gzip-1.5-foss-2018a.eb'))

        arch_regex = re.compile('^[a-z0-9_]+$')

        expected = {
            'bitbucket_account': 'gzip',
            'github_account': 'gzip',
            'module_name': 'gzip/1.5-foss-2018a',
            'name': 'gzip',
            'namelower': 'gzip',
            'nameletter': 'g',
            'nameletterlower': 'g',
            'parallel': None,
            'toolchain_name': 'foss',
            'toolchain_version': '2018a',
            'version': '1.5',
            'version_major': '1',
            'version_major_minor': '1.5',
            'version_minor': '5',
            'versionprefix': '',
            'versionsuffix': '',
        }
        res = template_constant_dict(ec)

        # 'arch' needs to be handled separately, since value depends on system architecture
        self.assertTrue('arch' in res)
        arch = res.pop('arch')
        self.assertTrue(arch_regex.match(arch), "'%s' matches with pattern '%s'" % (arch, arch_regex.pattern))

        self.assertEqual(res, expected)

        # mock get_avail_core_count which is used by set_parallel -> det_parallelism
        try:
            del st.det_parallelism._default_parallelism  # Remove cache value
        except AttributeError:
            pass  # Ignore if not present
        orig_get_avail_core_count = st.get_avail_core_count
        st.get_avail_core_count = lambda: 42

        # also check template values after running check_readiness_step (which runs set_parallel)
        eb = EasyBlock(ec)
        eb.check_readiness_step()

        st.get_avail_core_count = orig_get_avail_core_count

        res = template_constant_dict(ec)
        res.pop('arch')
        expected['parallel'] = 42
        self.assertEqual(res, expected)

        toy_ec = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0-deps.eb')
        toy_ec_txt = read_file(toy_ec)

        # fiddle with version to check version_minor template ('0' should be retained)
        toy_ec_txt = re.sub('version = .*', 'version = "0.01"', toy_ec_txt)

        my_arch = st.get_cpu_architecture()

        # add Java dep with version specified using a dict value
        toy_ec_txt += '\n'.join([
            "dependencies += [",
            "  ('Python', '3.7.2'),"
            "  ('Java', {",
            "    'arch=%s': '1.8.0_221'," % my_arch,
            "    'arch=fooarch': '1.8.0-foo',",
            "  })",
            "]",
            "builddependencies = [",
            "  ('CMake', '3.18.4'),",
            "]",
        ])

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, toy_ec_txt)

        expected = {
            'bitbucket_account': 'toy',
            'github_account': 'toy',
            'javamajver': '1',
            'javaminver': '8',
            'javashortver': '1.8',
            'javaver': '1.8.0_221',
            'module_name': 'toy/0.01-deps',
            'name': 'toy',
            'namelower': 'toy',
            'nameletter': 't',
            'toolchain_name': 'system',
            'toolchain_version': 'system',
            'nameletterlower': 't',
            'parallel': None,
            'pymajver': '3',
            'pyminver': '7',
            'pyshortver': '3.7',
            'pyver': '3.7.2',
            'version': '0.01',
            'version_major': '0',
            'version_major_minor': '0.01',
            'version_minor': '01',
            'versionprefix': '',
            'versionsuffix': '-deps',
        }

        # proper EasyConfig instance
        ec = EasyConfig(test_ec)

        # CMake should *not* be included, since it's a build-only dependency
        dep_names = [x['name'] for x in ec['dependencies']]
        self.assertFalse('CMake' in dep_names, "CMake should not be included in list of dependencies: %s" % dep_names)
        res = template_constant_dict(ec)
        dep_names = [x['name'] for x in ec['dependencies']]
        self.assertFalse('CMake' in dep_names, "CMake should not be included in list of dependencies: %s" % dep_names)

        self.assertTrue('arch' in res)
        arch = res.pop('arch')
        self.assertTrue(arch_regex.match(arch), "'%s' matches with pattern '%s'" % (arch, arch_regex.pattern))

        self.assertEqual(res, expected)

        # only perform shallow/quick parse (as is done in list_software function)
        ec = EasyConfigParser(filename=test_ec).get_config_dict()

        expected['module_name'] = None
        for key in ('bitbucket_account', 'github_account', 'parallel', 'versionprefix'):
            del expected[key]

        dep_names = [x[0] for x in ec['dependencies']]
        self.assertFalse('CMake' in dep_names, "CMake should not be included in list of dependencies: %s" % dep_names)
        res = template_constant_dict(ec)
        dep_names = [x[0] for x in ec['dependencies']]
        self.assertFalse('CMake' in dep_names, "CMake should not be included in list of dependencies: %s" % dep_names)

        self.assertTrue('arch' in res)
        arch = res.pop('arch')
        self.assertTrue(arch_regex.match(arch), "'%s' matches with pattern '%s'" % (arch, arch_regex.pattern))

        self.assertEqual(res, expected)

        # also check result of template_constant_dict when dict representing extension is passed
        ext_dict = {
            'name': 'foo',
            'version': '1.2.3',
            'options': {
                'source_urls': ['https://example.com'],
                'source_tmpl': '%(name)s-%(version)s.tar.gz',
            },
        }
        res = template_constant_dict(ext_dict)

        self.assertTrue('arch' in res)
        arch = res.pop('arch')
        self.assertTrue(arch_regex.match(arch), "'%s' matches with pattern '%s'" % (arch, arch_regex.pattern))

        expected = {
            'module_name': None,
            'name': 'foo',
            'namelower': 'foo',
            'nameletter': 'f',
            'nameletterlower': 'f',
            'version': '1.2.3',
            'version_major': '1',
            'version_major_minor': '1.2',
            'version_minor': '2'
        }
        self.assertEqual(res, expected)

    def test_parse_deps_templates(self):
        """Test whether handling of templates defined by dependencies is done correctly."""
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')

        pyec = os.path.join(self.test_prefix, 'Python-2.7.10-foss-2018a.eb')
        shutil.copy2(os.path.join(test_ecs, 'p', 'Python', 'Python-2.7.10-intel-2018a.eb'), pyec)
        write_file(pyec, "\ntoolchain = {'name': 'foss', 'version': '2018a'}", append=True)

        ec_txt = '\n'.join([
            "easyblock = 'ConfigureMake'",
            "name = 'test'",
            "version = '1.2.3'",
            "versionsuffix = '-Python-%(pyver)s'",
            "homepage = 'http://example.com'",
            "description = 'test'",
            "toolchain = {'name': 'foss', 'version': '2018a'}",
            "dependencies = [('Python', '2.7.10'), ('pytest', '1.2.3', versionsuffix)]",
        ])
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, ec_txt)

        pytest_ec_txt = '\n'.join([
            "easyblock = 'ConfigureMake'",
            "name = 'pytest'",
            "version = '1.2.3'",
            "versionsuffix = '-Python-%(pyver)s'",
            "homepage = 'http://example.com'",
            "description = 'test'",
            "toolchain = {'name': 'foss', 'version': '2018a'}",
            "dependencies = [('Python', '2.7.10')]",
        ])
        write_file(os.path.join(self.test_prefix, 'pytest-1.2.3-foss-2018a-Python-2.7.10.eb'), pytest_ec_txt)

        build_options = {
            'external_modules_metadata': ConfigObj(),
            'robot_path': [test_ecs, self.test_prefix],
            'valid_module_classes': module_classes(),
            'validate': False,
        }
        init_config(args=['--module-naming-scheme=HierarchicalMNS'], build_options=build_options)

        # check if parsing of easyconfig & resolving dependencies works correctly
        ecs, _ = parse_easyconfigs([(test_ec, False)])
        ordered_ecs = resolve_dependencies(ecs, self.modtool, retain_all_deps=True)

        # verify module names of dependencies, by accessing raw config via _.config
        expected = [
            'MPI/GCC/6.4.0-2.28/OpenMPI/2.1.2/Python/2.7.10',
            'MPI/GCC/6.4.0-2.28/OpenMPI/2.1.2/pytest/1.2.3-Python-2.7.10',
        ]
        dep_full_mod_names = [d['full_mod_name'] for d in ordered_ecs[-1]['ec']._config['dependencies'][0]]
        self.assertEqual(dep_full_mod_names, expected)

    def test_hidden_toolchain(self):
        """Test hiding of toolchain via easyconfig parameter."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        ec_txt = read_file(os.path.join(test_ecs_dir, 'g', 'gzip', 'gzip-1.6-GCC-4.9.2.eb'))

        new_tc = "toolchain = {'name': 'GCC', 'version': '4.9.2', 'hidden': True}"
        ec_txt = re.sub("toolchain = .*", new_tc, ec_txt, re.M)

        ec_file = os.path.join(self.test_prefix, 'test.eb')
        write_file(ec_file, ec_txt)

        args = [
            ec_file,
            '--dry-run',
        ]
        outtxt = self.eb_main(args, raise_error=True)
        self.assertTrue(re.search(r'module: GCC/\.4\.9\.2', outtxt))
        self.assertTrue(re.search(r'module: gzip/1\.6-GCC-4\.9\.2', outtxt))

    def test_categorize_files_by_type(self):
        """Test categorize_files_by_type"""
        self.assertEqual({'easyconfigs': [], 'files_to_delete': [], 'patch_files': [], 'py_files': []},
                         categorize_files_by_type([]))

        test_dir = os.path.dirname(os.path.abspath(__file__))
        test_ecs_dir = os.path.join(test_dir, 'easyconfigs')
        toy_patch_fn = 'toy-0.0_fix-silly-typo-in-printf-statement.patch'
        toy_patch = os.path.join(os.path.dirname(test_ecs_dir), 'sandbox', 'sources', 'toy', toy_patch_fn)

        easyblocks_dir = os.path.join(test_dir, 'sandbox', 'easybuild', 'easyblocks')
        configuremake = os.path.join(easyblocks_dir, 'generic', 'configuremake.py')
        toy_easyblock = os.path.join(easyblocks_dir, 't', 'toy.py')

        gzip_ec = os.path.join(test_ecs_dir, 'test_ecs', 'g', 'gzip', 'gzip-1.4.eb')
        paths = [
            'bzip2-1.0.6.eb',
            toy_easyblock,
            gzip_ec,
            toy_patch,
            'foo',
            ':toy-0.0-deps.eb',
            configuremake,
        ]
        res = categorize_files_by_type(paths)
        expected = [
            'bzip2-1.0.6.eb',
            gzip_ec,
            'foo',
        ]
        self.assertEqual(res['easyconfigs'], expected)
        self.assertEqual(res['files_to_delete'], ['toy-0.0-deps.eb'])
        self.assertEqual(res['patch_files'], [toy_patch])
        self.assertEqual(res['py_files'], [toy_easyblock, configuremake])

        # Error cases
        tmpdir = tempfile.mkdtemp()
        non_existing = os.path.join(tmpdir, 'does_not_exist.patch')
        self.assertErrorRegex(EasyBuildError,
                              "File %s does not exist" % non_existing,
                              categorize_files_by_type, [non_existing])
        patch_dir = os.path.join(tmpdir, 'folder.patch')
        os.mkdir(patch_dir)
        self.assertErrorRegex(EasyBuildError,
                              "File %s is expected to be a regular file" % patch_dir,
                              categorize_files_by_type, [patch_dir])
        invalid_patch = os.path.join(tmpdir, 'invalid.patch')
        copy_file(gzip_ec, invalid_patch)
        self.assertErrorRegex(EasyBuildError,
                              "%s is not detected as a valid patch file" % invalid_patch,
                              categorize_files_by_type, [invalid_patch])

    def test_resolve_template(self):
        """Test resolve_template function."""
        self.assertEqual(resolve_template('', {}), '')
        tmpl_dict = {
            'name': 'FooBar',
            'namelower': 'foobar',
            'version': '1.2.3',
        }
        self.assertEqual(resolve_template('%(namelower)s-%(version)s', tmpl_dict), 'foobar-1.2.3')

        value, expected = ['%(namelower)s-%(version)s', 'name:%(name)s'], ['foobar-1.2.3', 'name:FooBar']
        self.assertEqual(resolve_template(value, tmpl_dict), expected)

        value, expected = ('%(namelower)s-%(version)s', 'name:%(name)s'), ('foobar-1.2.3', 'name:FooBar')
        self.assertEqual(resolve_template(value, tmpl_dict), expected)

        value, expected = {'%(namelower)s-%(version)s': 'name:%(name)s'}, {'foobar-1.2.3': 'name:FooBar'}
        self.assertEqual(resolve_template(value, tmpl_dict), expected)

        # nested value
        value = [
            {'%(name)s': '%(namelower)s', '%(version)s': '1.2.3', 'bleh': '%(name)s-%(version)s'},
            ('%(namelower)s', '%(version)s'),
            ['%(name)s', ('%(namelower)s-%(version)s',)],
        ]
        expected = [
            {'FooBar': 'foobar', '1.2.3': '1.2.3', 'bleh': 'FooBar-1.2.3'},
            ('foobar', '1.2.3'),
            ['FooBar', ('foobar-1.2.3',)],
        ]
        self.assertEqual(resolve_template(value, tmpl_dict), expected)

        # escaped template value
        self.assertEqual(resolve_template('%%(name)s', tmpl_dict), '%(name)s')

        # '%(name)' is not a correct template spec (missing trailing 's')
        self.assertEqual(resolve_template('%(name)', tmpl_dict), '%(name)')

    def test_det_subtoolchain_version(self):
        """Test det_subtoolchain_version function"""
        _, all_tc_classes = search_toolchain('')
        subtoolchains = dict((tc_class.NAME, getattr(tc_class, 'SUBTOOLCHAIN', None)) for tc_class in all_tc_classes)
        optional_toolchains = set(tc_class.NAME for tc_class in all_tc_classes if getattr(tc_class, 'OPTIONAL', False))

        current_tc = {'name': 'fosscuda', 'version': '2018a'}
        # missing gompic and double golfc should both give exceptions
        cands = [{'name': 'golfc', 'version': '2018a'},
                 {'name': 'golfc', 'version': '2018.01'}]
        self.assertErrorRegex(EasyBuildError,
                              "No version found for subtoolchain gompic in dependencies of fosscuda",
                              det_subtoolchain_version, current_tc, 'gompic', optional_toolchains, cands)
        self.assertErrorRegex(EasyBuildError,
                              "Multiple versions of golfc found in dependencies of toolchain fosscuda: 2018.01, 2018a",
                              det_subtoolchain_version, current_tc, 'golfc', optional_toolchains, cands)

        # missing candidate for golfc, ok for optional
        cands = [{'name': 'gompic', 'version': '2018a'}]
        versions = [det_subtoolchain_version(current_tc, subtoolchain_name, optional_toolchains, cands)
                    for subtoolchain_name in subtoolchains[current_tc['name']]]
        self.assertEqual(versions, ['2018a', None])

        # 'system', 'system' should be ok: return None for GCCcore, and None or '' for 'system'.
        current_tc = {'name': 'GCC', 'version': '6.4.0-2.28'}
        cands = [{'name': 'system', 'version': 'system'}]
        versions = [det_subtoolchain_version(current_tc, subtoolchain_name, optional_toolchains, cands)
                    for subtoolchain_name in subtoolchains[current_tc['name']]]
        self.assertEqual(versions, [None, None])

        init_config(build_options={'add_system_to_minimal_toolchains': True})

        versions = [det_subtoolchain_version(current_tc, subtoolchain_name, optional_toolchains, cands)
                    for subtoolchain_name in subtoolchains[current_tc['name']]]
        self.assertEqual(versions, [None, ''])

        # --add-dummy-to-minimal-toolchains is still supported, but deprecated
        self.allow_deprecated_behaviour()
        init_config(build_options={'add_system_to_minimal_toolchains': False, 'add_dummy_to_minimal_toolchains': True})
        self.mock_stderr(True)
        versions = [det_subtoolchain_version(current_tc, subtoolchain_name, optional_toolchains, cands)
                    for subtoolchain_name in subtoolchains[current_tc['name']]]
        stderr = self.get_stderr()
        self.mock_stderr(False)
        self.assertEqual(versions, [None, ''])
        depr_msg = "WARNING: Deprecated functionality, will no longer work in v5.0: "
        depr_msg += "Use --add-system-to-minimal-toolchains instead of --add-dummy-to-minimal-toolchains"
        self.assertTrue(depr_msg in stderr)

        # and GCCcore if existing too
        init_config(build_options={'add_system_to_minimal_toolchains': True})
        current_tc = {'name': 'GCC', 'version': '4.9.3-2.25'}
        cands = [{'name': 'GCCcore', 'version': '4.9.3'}]
        versions = [det_subtoolchain_version(current_tc, subtoolchain_name, optional_toolchains, cands)
                    for subtoolchain_name in subtoolchains[current_tc['name']]]
        self.assertEqual(versions, ['4.9.3', ''])

        # test det_subtoolchain_version when two alternatives for subtoolchain are specified
        current_tc = {'name': 'gompi', 'version': '2018b'}
        cands = [{'name': 'GCC', 'version': '7.3.0-2.30'}]
        subtc_version = det_subtoolchain_version(current_tc, ('GCCcore', 'GCC'), optional_toolchains, cands)
        self.assertEqual(subtc_version, '7.3.0-2.30')

    def test_verify_easyconfig_filename(self):
        """Test verify_easyconfig_filename function"""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0-gompi-2018a-test.eb')
        toy_ec_name = os.path.basename(toy_ec)
        specs = {
            'name': 'toy',
            'toolchain': {'name': 'gompi', 'version': '2018a'},
            'version': '0.0',
            'versionsuffix': '-test'
        }

        # all is well
        verify_easyconfig_filename(toy_ec, specs)

        # pass parsed easyconfig
        parsed_ecs = process_easyconfig(toy_ec)
        verify_easyconfig_filename(toy_ec, specs, parsed_ec=parsed_ecs)
        verify_easyconfig_filename(toy_ec, specs, parsed_ec=parsed_ecs[0]['ec'])

        # incorrect spec
        specs['versionsuffix'] = ''
        error_pattern = "filename '%s' does not match with expected filename 'toy-0.0-gompi-2018a.eb' " % toy_ec_name
        error_pattern += r"\(specs: name: 'toy'; version: '0.0'; versionsuffix: ''; "
        error_pattern += r"toolchain name, version: 'gompi', '2018a'\)"
        self.assertErrorRegex(EasyBuildError, error_pattern, verify_easyconfig_filename, toy_ec, specs)
        specs['versionsuffix'] = '-test'

        # incorrect file name
        toy_txt = read_file(toy_ec)
        toy_ec = os.path.join(self.test_prefix, 'toy.eb')
        write_file(toy_ec, toy_txt)
        error_pattern = "filename 'toy.eb' does not match with expected filename 'toy-0.0-gompi-2018a-test.eb' "
        error_pattern += r"\(specs: name: 'toy'; version: '0.0'; versionsuffix: '-test'; "
        error_pattern += r"toolchain name, version: 'gompi', '2018a'\)"
        self.assertErrorRegex(EasyBuildError, error_pattern, verify_easyconfig_filename, toy_ec, specs)

        # incorrect file contents
        error_pattern = r"Contents of .*/%s does not match with filename" % os.path.basename(toy_ec)
        toy_txt = toy_txt.replace("versionsuffix = '-test'", "versionsuffix = ''")
        toy_ec = os.path.join(self.test_prefix, 'toy-0.0-gompi-2018a-test.eb')
        write_file(toy_ec, toy_txt)
        error_pattern = "Contents of .*/%s does not match with filename" % os.path.basename(toy_ec)
        self.assertErrorRegex(EasyBuildError, error_pattern, verify_easyconfig_filename, toy_ec, specs)

    def test_get_paths_for(self):
        """Test for get_paths_for"""
        orig_path = os.getenv('PATH', '')

        # get_paths_for should be robust against not having any 'eb' command available through $PATH
        path = []
        for subdir in orig_path.split(os.pathsep):
            if not os.path.exists(os.path.join(subdir, 'eb')):
                path.append(subdir)
        os.environ['PATH'] = os.pathsep.join(path)

        top_dir = os.path.dirname(os.path.abspath(__file__))
        mkdir(os.path.join(self.test_prefix, 'easybuild'))
        test_ecs = os.path.join(top_dir, 'easyconfigs')
        symlink(test_ecs, os.path.join(self.test_prefix, 'easybuild', 'easyconfigs'))

        # temporarily mock stderr to avoid printed warning (because 'eb' is not available via $PATH)
        self.mock_stderr(True)

        # locations listed in 'robot_path' named argument are taken into account
        res = get_paths_for(subdir='easyconfigs', robot_path=[self.test_prefix])
        self.mock_stderr(False)
        self.assertTrue(os.path.samefile(test_ecs, res[0]))

        # Can't have EB_SCRIPT_PATH set (for some of) these tests
        env_eb_script_path = os.getenv('EB_SCRIPT_PATH')
        if env_eb_script_path:
            del os.environ['EB_SCRIPT_PATH']

        # easyconfigs location can also be derived from location of 'eb'
        write_file(os.path.join(self.test_prefix, 'bin', 'eb'), "#!/bin/bash; echo 'This is a fake eb'")
        adjust_permissions(os.path.join(self.test_prefix, 'bin', 'eb'), stat.S_IXUSR)
        os.environ['PATH'] = '%s:%s' % (os.path.join(self.test_prefix, 'bin'), orig_path)

        res = get_paths_for(subdir='easyconfigs', robot_path=None)
        self.assertTrue(os.path.samefile(test_ecs, res[-1]))

        # also works when 'eb' resides in a symlinked location
        altbin = os.path.join(self.test_prefix, 'some', 'other', 'symlinked', 'bin')
        mkdir(os.path.dirname(altbin), parents=True)
        symlink(os.path.join(self.test_prefix, 'bin'), altbin)
        os.environ['PATH'] = '%s:%s' % (altbin, orig_path)
        res = get_paths_for(subdir='easyconfigs', robot_path=None)
        self.assertTrue(os.path.samefile(test_ecs, res[-1]))

        # Restore (temporarily) EB_SCRIPT_PATH value if set originally
        if env_eb_script_path:
            os.environ['EB_SCRIPT_PATH'] = env_eb_script_path

        # also locations in sys.path are considered
        os.environ['PATH'] = orig_path
        sys.path.insert(0, self.test_prefix)
        res = get_paths_for(subdir='easyconfigs', robot_path=None)
        self.assertTrue(os.path.samefile(test_ecs, res[0]))

        # put mock 'eb' back in $PATH
        os.environ['PATH'] = '%s:%s' % (os.path.join(self.test_prefix, 'bin'), orig_path)

        # if $EB_SCRIPT_PATH is specified, this is picked up to determine location to easyconfigs
        someprefix = os.path.join(self.test_prefix, 'someprefix')
        test_easyconfigs_dir = os.path.join(someprefix, 'easybuild', 'easyconfigs')
        mkdir(test_easyconfigs_dir, parents=True)
        write_file(os.path.join(someprefix, 'bin', 'eb'), '')

        # put symlink in place, both original path and resolved path should be considered
        symlinked_prefix = os.path.join(self.test_prefix, 'symlinked_prefix')
        symlink(someprefix, symlinked_prefix)

        os.environ['EB_SCRIPT_PATH'] = os.path.join(symlinked_prefix, 'bin', 'eb')

        res = get_paths_for(subdir='easyconfigs', robot_path=None)

        # last path is symlinked path
        self.assertEqual(res[-1], os.path.join(symlinked_prefix, 'easybuild', 'easyconfigs'))

        # wipe sys.path. then only path found via $EB_SCRIPT_PATH is found
        sys.path = []
        res = get_paths_for(subdir='easyconfigs', robot_path=None)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0], os.path.join(symlinked_prefix, 'easybuild', 'easyconfigs'))

        # if $EB_SCRIPT_PATH is not defined, then paths determined via 'eb' found through $PATH are picked up
        del os.environ['EB_SCRIPT_PATH']

        res = get_paths_for(subdir='easyconfigs', robot_path=None)
        expected = os.path.join(self.test_prefix, 'easybuild', 'easyconfigs')
        self.assertTrue(os.path.samefile(res[-1], expected))

        # also check with $EB_SCRIPT_PATH set to a symlink which doesn't allow
        # directly deriving path to easybuild/easyconfigs dir, but resolved symlink does
        # cfr. https://github.com/easybuilders/easybuild-framework/pull/2248
        eb_symlink = os.path.join(self.test_prefix, 'eb')
        symlink(os.path.join(someprefix, 'bin', 'eb'), eb_symlink)
        os.environ['EB_SCRIPT_PATH'] = eb_symlink

        res = get_paths_for(subdir='easyconfigs', robot_path=None)
        self.assertTrue(os.path.exists(res[0]))
        self.assertTrue(os.path.samefile(res[0], os.path.join(someprefix, 'easybuild', 'easyconfigs')))

        # Finally restore EB_SCRIPT_PATH value if set
        if env_eb_script_path:
            os.environ['EB_SCRIPT_PATH'] = env_eb_script_path

    def test_is_generic_easyblock(self):
        """Test for is_generic_easyblock function."""

        # is_generic_easyblock in easyconfig.py is deprecated, moved to filetools.py
        self.allow_deprecated_behaviour()

        self.mock_stderr(True)

        for name in ['Binary', 'ConfigureMake', 'CMakeMake', 'PythonPackage', 'JAR']:
            self.assertTrue(is_generic_easyblock(name))

        for name in ['EB_bzip2', 'EB_DL_underscore_POLY_underscore_Classic', 'EB_GCC', 'EB_WRF_minus_Fire']:
            self.assertFalse(is_generic_easyblock(name))

        self.mock_stderr(False)

    def test_get_module_path(self):
        """Test get_module_path function."""
        self.assertEqual(get_module_path('EB_bzip2', generic=False), 'easybuild.easyblocks.bzip2')
        self.assertEqual(get_module_path('EB_bzip2'), 'easybuild.easyblocks.bzip2')

        self.assertEqual(get_module_path('RPackage'), 'easybuild.easyblocks.generic.rpackage')
        self.assertEqual(get_module_path('RPackage', generic=True), 'easybuild.easyblocks.generic.rpackage')

    def test_not_an_easyconfig(self):
        """Test error reporting when a file that's not actually an easyconfig file is provided."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs',)
        # run test on an easyconfig file that was downloaded using wget using a non-raw GitHub URL
        # cfr. https://github.com/easybuilders/easybuild-framework/issues/2383
        not_an_ec = os.path.join(os.path.dirname(test_ecs_dir), 'sandbox', 'not_an_easyconfig.eb')

        error_pattern = "Parsing easyconfig file failed: invalid syntax"
        self.assertErrorRegex(EasyBuildError, error_pattern, EasyConfig, not_an_ec)

    def test_check_sha256_checksums(self):
        """Test for check_sha256_checksums function."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec)

        checksums_regex = re.compile(r'^checksums = \[\[(.|\n)*\]\]', re.M)

        # wipe out specified checksums, to make check fail
        test_ec = os.path.join(self.test_prefix, 'toy-0.0-fail.eb')
        write_file(test_ec, checksums_regex.sub('checksums = []', toy_ec_txt))
        ecs, _ = parse_easyconfigs([(test_ec, False)])
        ecs = [ec['ec'] for ec in ecs]

        # result is non-empty list with strings describing checksum issues
        res = check_sha256_checksums(ecs)
        # result should be non-empty, i.e. contain a list of messages highlighting checksum issues
        self.assertTrue(res)
        self.assertTrue(res[0].startswith('Checksums missing for one or more sources/patches in toy-0.0-fail.eb'))

        # test use of whitelist regex patterns: check passes because easyconfig is whitelisted by filename
        for regex in [r'toy-.*', r'.*-0\.0-fail\.eb']:
            res = check_sha256_checksums(ecs, whitelist=[regex])
            self.assertFalse(res)

        # re-test with MD5 checksum to make test fail
        toy_md5 = 'be662daa971a640e40be5c804d9d7d10'
        test_ec_txt = checksums_regex.sub('checksums = ["%s"]' % toy_md5, toy_ec_txt)

        test_ec = os.path.join(self.test_prefix, 'toy-0.0-md5.eb')
        write_file(test_ec, test_ec_txt)
        ecs, _ = parse_easyconfigs([(test_ec, False)])
        ecs = [ec['ec'] for ec in ecs]

        res = check_sha256_checksums(ecs)
        self.assertTrue(res)
        self.assertTrue(res[-1].startswith("Non-SHA256 checksum(s) found for toy-0.0.tar.gz"))

        # re-test with right checksum in place
        toy_sha256 = '44332000aa33b99ad1e00cbd1a7da769220d74647060a10e807b916d73ea27bc'
        test_ec_txt = checksums_regex.sub('checksums = ["%s"]' % toy_sha256, toy_ec_txt)
        test_ec_txt = re.sub(r'patches = \[(.|\n)*\]', '', test_ec_txt)

        test_ec = os.path.join(self.test_prefix, 'toy-0.0-ok.eb')
        write_file(test_ec, test_ec_txt)
        ecs, _ = parse_easyconfigs([(test_ec, False)])
        ecs = [ec['ec'] for ec in ecs]

        # if no checksum issues are found, result is an empty list
        self.assertEqual(check_sha256_checksums(ecs), [])

        # also test toy easyconfig with extensions, for which some checksums are missing
        toy_ec = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0-gompi-2018a-test.eb')
        ecs, _ = parse_easyconfigs([(toy_ec, False)])
        ecs = [ec['ec'] for ec in ecs]

        # checksum issues found, so result is non-empty
        res = check_sha256_checksums(ecs)
        self.assertTrue(res)
        # multiple checksums listed for source tarball, while exactly one (SHA256) checksum is expected
        self.assertTrue(res[1].startswith("Non-SHA256 checksum(s) found for toy-0.0.tar.gz: "))

    def test_deprecated(self):
        """Test use of 'deprecated' easyconfig parameter."""
        topdir = os.path.dirname(os.path.abspath(__file__))
        toy_ec_txt = read_file(os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb'))
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, toy_ec_txt + "\ndeprecated = 'this is just a test'")

        error_pattern = r"easyconfig file '.*/test.eb' is marked as deprecated:\nthis is just a test\n \(see also"
        self.assertErrorRegex(EasyBuildError, error_pattern, EasyConfig, test_ec)

    def test_filename(self):
        """Test filename method of EasyConfig class."""
        init_config(build_options={'silent': True})
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')

        test_ecs = [
            os.path.join('g', 'GCC', 'GCC-4.6.4.eb'),
            os.path.join('g', 'gzip', 'gzip-1.5-foss-2018a.eb'),
            os.path.join('s', 'ScaLAPACK', 'ScaLAPACK-2.0.2-gompic-2018a-OpenBLAS-0.2.20.eb'),
            os.path.join('o', 'OpenBLAS', 'OpenBLAS-0.2.8-GCC-4.8.2-LAPACK-3.4.2.eb'),
            os.path.join('t', 'toy', 'toy-0.0.eb'),
            os.path.join('t', 'toy', 'toy-0.0-deps.eb'),
        ]
        for test_ec in test_ecs:
            test_ec = os.path.join(test_ecs_dir, test_ec)
            ec = EasyConfig(test_ec)
            self.assertTrue(ec.filename(), os.path.basename(test_ec))

    def test_get_ref(self):
        """Test get_ref method."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        ec = EasyConfig(os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0-iter.eb'))

        # without using get_ref, we get a (templated) copy rather than the original value
        sources = ec['sources']
        self.assertEqual(sources, ['toy-0.0.tar.gz'])
        self.assertFalse(sources is ec._config['sources'][0])

        # same for .get
        sources = ec.get('sources')
        self.assertEqual(sources, ['toy-0.0.tar.gz'])
        self.assertFalse(sources is ec._config['sources'][0])

        # with get_ref, we get the original untemplated value
        sources_ref = ec.get_ref('sources')
        self.assertEqual(sources_ref, ['%(name)s-%(version)s.tar.gz'])
        self.assertTrue(sources_ref is ec._config['sources'][0])

        sanity_check_paths_ref = ec.get_ref('sanity_check_paths')
        self.assertTrue(sanity_check_paths_ref is ec._config['sanity_check_paths'][0])

        # also items inside are still references to original (i.e. not copies)
        self.assertTrue(sanity_check_paths_ref['files'] is ec._config['sanity_check_paths'][0]['files'])

        # get_ref also works for values other than lists/dicts
        self.assertEqual(ec['description'], "Toy C program, 100% toy.")
        descr_ref = ec.get_ref('description')
        self.assertEqual(descr_ref, "Toy C program, 100% %(name)s.")
        self.assertTrue(descr_ref is ec._config['description'][0])

    def test_multi_deps(self):
        """Test handling of multi_deps easyconfig parameter."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec)

        ec = EasyConfig(toy_ec)
        self.assertEqual(ec['builddependencies'], [])
        self.assertEqual(ec['multi_deps'], {})
        self.assertEqual(ec.multi_deps, [])

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ec_txt = toy_ec_txt + "\nmulti_deps = {'GCC': ['4.6.3', '4.8.3', '7.3.0-2.30']}"
        write_file(test_ec, test_ec_txt)

        ec = EasyConfig(test_ec)

        # builddependencies should now be a non-empty list of lists, each with one entry corresponding to a GCC version
        builddeps = ec['builddependencies']
        self.assertTrue(builddeps)
        self.assertTrue(isinstance(builddeps, list))
        self.assertEqual(len(builddeps), 3)
        self.assertTrue(all(isinstance(bd, list) for bd in builddeps))
        self.assertTrue(all(len(bd) == 1 for bd in builddeps))
        self.assertTrue(all(bd[0]['name'] == 'GCC' for bd in builddeps))
        self.assertEqual(sorted(bd[0]['version'] for bd in builddeps), ['4.6.3', '4.8.3', '7.3.0-2.30'])

        # get_parsed_multi_deps() method basically returns same list
        multi_deps = ec.get_parsed_multi_deps()
        self.assertTrue(isinstance(multi_deps, list))
        self.assertEqual(len(multi_deps), 3)
        self.assertTrue(all(isinstance(bd, list) for bd in multi_deps))
        self.assertTrue(all(len(bd) == 1 for bd in multi_deps))
        self.assertTrue(all(bd[0]['name'] == 'GCC' for bd in multi_deps))
        self.assertEqual(sorted(bd[0]['version'] for bd in multi_deps), ['4.6.3', '4.8.3', '7.3.0-2.30'])

        # if builddependencies is also specified, then these build deps are added to each sublist
        write_file(test_ec, test_ec_txt + "\nbuilddependencies = [('CMake', '3.12.1'), ('foo', '1.2.3')]")
        ec = EasyConfig(test_ec)
        builddeps = ec['builddependencies']
        self.assertTrue(builddeps)
        self.assertTrue(isinstance(builddeps, list))
        self.assertEqual(len(builddeps), 3)
        self.assertTrue(all(isinstance(bd, list) for bd in builddeps))
        self.assertTrue(all(len(bd) == 3 for bd in builddeps))
        self.assertTrue(all(bd[0]['name'] == 'GCC' for bd in builddeps))
        self.assertEqual(sorted(bd[0]['version'] for bd in builddeps), ['4.6.3', '4.8.3', '7.3.0-2.30'])
        self.assertTrue(all(bd[1]['name'] == 'CMake' for bd in builddeps))
        self.assertTrue(all(bd[1]['version'] == '3.12.1' for bd in builddeps))
        self.assertTrue(all(bd[1]['full_mod_name'] == 'CMake/3.12.1' for bd in builddeps))
        self.assertTrue(all(bd[2]['name'] == 'foo' for bd in builddeps))
        self.assertTrue(all(bd[2]['version'] == '1.2.3' for bd in builddeps))
        self.assertTrue(all(bd[2]['full_mod_name'] == 'foo/1.2.3' for bd in builddeps))

        # get_parsed_multi_deps() method returns same list, but CMake & foo are not included
        multi_deps = ec.get_parsed_multi_deps()
        self.assertTrue(isinstance(multi_deps, list))
        self.assertEqual(len(multi_deps), 3)
        self.assertTrue(all(isinstance(bd, list) for bd in multi_deps))
        self.assertTrue(all(len(bd) == 1 for bd in multi_deps))
        self.assertTrue(all(bd[0]['name'] == 'GCC' for bd in multi_deps))
        self.assertEqual(sorted(bd[0]['version'] for bd in multi_deps), ['4.6.3', '4.8.3', '7.3.0-2.30'])

        # trying to combine multi_deps with a list of lists in builddependencies is not allowed
        write_file(test_ec, test_ec_txt + "\nbuilddependencies = [[('CMake', '3.12.1')], [('CMake', '3.9.1')]]")
        error_pattern = "Can't combine multi_deps with builddependencies specified as list of lists"
        self.assertErrorRegex(EasyBuildError, error_pattern, EasyConfig, test_ec)

        # test with different number of dependency versions in multi_deps, should result in a clean error
        test_ec_txt = toy_ec_txt + "\nmulti_deps = {'one': ['1.0'], 'two': ['2.0', '2.1']}"
        write_file(test_ec, test_ec_txt)

        error_pattern = "Not all the dependencies listed in multi_deps have the same number of versions!"
        self.assertErrorRegex(EasyBuildError, error_pattern, EasyConfig, test_ec)

    def test_multi_deps_templated_builddeps(self):
        """Test effect of multi_deps on builddependencies w.r.t. resolving templates like %(pyver)s."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec)

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ec_txt = toy_ec_txt + "\nmulti_deps = {'Python': ['3.7.2', '2.7.15']}"
        write_file(test_ec, test_ec_txt + "\nbuilddependencies = [('SWIG', '3.0.12', '-Python-%(pyver)s')]")
        ec = EasyConfig(test_ec)
        eb = EasyBlock(ec)
        eb.silent = True

        # start iteration #0
        eb.handle_iterate_opts()

        builddeps = ec['builddependencies']

        self.assertTrue(isinstance(builddeps, list))
        self.assertEqual(len(builddeps), 2)
        self.assertTrue(all(isinstance(bd, dict) for bd in builddeps))

        # 1st listed build dep should be first version of Python (via multi_deps)
        self.assertEqual(builddeps[0]['name'], 'Python')
        self.assertEqual(builddeps[0]['version'], '3.7.2')
        self.assertEqual(builddeps[0]['full_mod_name'], 'Python/3.7.2')

        # 2nd listed build dep should be SWIG
        self.assertEqual(builddeps[1]['name'], 'SWIG')
        self.assertEqual(builddeps[1]['version'], '3.0.12')
        # template %(pyver)s values should be resolved correctly based on 1st item in multi_deps
        self.assertEqual(builddeps[1]['versionsuffix'], '-Python-3.7.2')
        self.assertEqual(builddeps[1]['full_mod_name'], 'SWIG/3.0.12-Python-3.7.2')

        eb.handle_iterate_opts()
        builddeps = ec['builddependencies']

        # 1st listed build dep should be second version of Python (via multi_deps)
        self.assertEqual(builddeps[0]['name'], 'Python')
        self.assertEqual(builddeps[0]['version'], '2.7.15')
        self.assertEqual(builddeps[0]['full_mod_name'], 'Python/2.7.15')

        # 2nd listed build dep should be SWIG
        self.assertEqual(builddeps[1]['name'], 'SWIG')
        self.assertEqual(builddeps[1]['version'], '3.0.12')
        # template %(pyver)s values should be resolved correctly based on 2nd item in multi_deps
        self.assertEqual(builddeps[1]['versionsuffix'], '-Python-2.7.15')
        self.assertEqual(builddeps[1]['full_mod_name'], 'SWIG/3.0.12-Python-2.7.15')

    def test_iter_builddeps_templates(self):
        """Test whether iterative builddependencies are taken into account to define *ver and *shortver templates."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = read_file(toy_ec)

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ec_txt = toy_ec_txt + "\nmulti_deps = {'Python': ['2.7.15', '3.6.6']}"

        # inject extension that uses %(pyshortver)s, to check whether the template value is properly resolved
        test_ec_txt += '\n'.join([
            '',
            "exts_defaultclass = 'Toy_Extension'",
            "exts_list = [('bar', '0.0', {'preinstallopts': 'echo \\'py%(pyshortver)s\\' && '})]",
        ])

        write_file(test_ec, test_ec_txt)

        ec = EasyConfig(test_ec)

        # %(pyver)s and %(pyshortver)s template are not defined when not in iterative mode
        self.assertFalse('pyver' in ec.template_values)
        self.assertFalse('pyshortver' in ec.template_values)

        # save reference to original list of lists of build dependencies
        builddeps = ec['builddependencies']

        ec.start_iterating()

        # start with first list of build dependencies (i.e. Python 2.7.15)
        ec['builddependencies'] = builddeps[0]

        ec.generate_template_values()
        self.assertTrue('pyver' in ec.template_values)
        self.assertEqual(ec.template_values['pyver'], '2.7.15')
        self.assertTrue('pyshortver' in ec.template_values)
        self.assertEqual(ec.template_values['pyshortver'], '2.7')

        # put next list of build dependencies in place (i.e. Python 3.7.2)
        ec['builddependencies'] = builddeps[1]

        ec.generate_template_values()
        self.assertTrue('pyver' in ec.template_values)
        self.assertEqual(ec.template_values['pyver'], '3.6.6')
        self.assertTrue('pyshortver' in ec.template_values)
        self.assertEqual(ec.template_values['pyshortver'], '3.6')

        # check that extensions inherit these template values too
        # cfr. https://github.com/easybuilders/easybuild-framework/issues/3317
        eb = EasyBlock(ec)
        eb.silent = True
        eb.extensions_step(fetch=True, install=False)
        ext = eb.ext_instances[0]
        self.assertEqual(ext.cfg['preinstallopts'], "echo 'py3.6' && ")

    def test_fix_deprecated_easyconfigs(self):
        """Test fix_deprecated_easyconfigs function."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0.eb')
        gzip_ec = os.path.join(test_ecs_dir, 'g', 'gzip', 'gzip-1.4.eb')

        gzip_ec_txt = read_file(gzip_ec)
        toy_ec_txt = read_file(toy_ec)

        test_ec = os.path.join(self.test_prefix, 'test.eb')

        # need to allow triggering deprecated behaviour, since that's exactly what we're fixing...
        self.allow_deprecated_behaviour()

        test_ectxt = toy_ec_txt
        # inject local variables with names that need to be tweaked (or not for single-letter ones)
        regex = re.compile('^(sanity_check_paths)', re.M)
        # purposely define configopts via local variable 'foo', which has value that also contains 'foo' substring;
        # that way, we can check whether only the 'foo' variable name is replaced with 'local_foo'
        test_ectxt = regex.sub(r'foo = "--foobar --barfoo --barfoobaz"\nconfigopts = foo\n\n\1', toy_ec_txt)
        regex = re.compile(r'^(toolchain\s*=.*)$', re.M)
        test_ectxt = regex.sub(r'\1\n\nsome_list = [x + "1" for x in ["one", "two", "three"]]', test_ectxt)

        # test fixing the use of 'dummy' toolchain to SYSTEM
        tc_regex = re.compile('^toolchain = .*', re.M)
        tc_strs = [
            "{'name': 'dummy', 'version': 'dummy'}",
            "{'name': 'dummy', 'version': ''}",
            "{'name': 'dummy', 'version': '1.2.3'}",
            "{'version': '', 'name': 'dummy'}",
            "{'version': 'dummy', 'name': 'dummy'}",
        ]

        unknown_params_error_pattern = "Use of 2 unknown easyconfig parameters detected in test.eb: foo, some_list"

        for tc_str in tc_strs:
            # first check if names of local variables get fixed if 'dummy' toolchain is not used
            init_config(build_options={'local_var_naming_check': 'error', 'silent': True})

            write_file(test_ec, test_ectxt)
            self.assertErrorRegex(EasyBuildError, unknown_params_error_pattern, EasyConfig, test_ec)

            self.mock_stderr(True)
            self.mock_stdout(True)
            fix_deprecated_easyconfigs([test_ec])
            stderr, stdout = self.get_stderr(), self.get_stdout()
            self.mock_stderr(False)
            self.mock_stdout(False)
            self.assertFalse(stderr)
            self.assertTrue("test.eb... FIXED!" in stdout)

            # parsing now works
            ec = EasyConfig(test_ec)

            # cleanup
            remove_file(glob.glob(os.path.join(test_ec + '.orig*'))[0])

            # now inject use of 'dummy' toolchain
            write_file(test_ec, tc_regex.sub("toolchain = %s" % tc_str, test_ectxt))

            test_ec_txt = read_file(test_ec)
            regex = re.compile("^toolchain = {.*'name': 'dummy'.*$", re.M)
            self.assertTrue(regex.search(test_ec_txt), "Pattern '%s' found in: %s" % (regex.pattern, test_ec_txt))

            # mimic default behaviour where only warnings are being printed;
            # use of dummy toolchain or local variables not following recommended naming scheme is not fatal by default
            init_config(build_options={'local_var_naming_check': 'warn', 'silent': False})
            self.mock_stderr(True)
            self.mock_stdout(True)
            ec = EasyConfig(test_ec)
            stderr, stdout = self.get_stderr(), self.get_stdout()
            self.mock_stderr(False)
            self.mock_stdout(False)

            self.assertFalse(stdout)

            warnings = [
                "WARNING: Use of 2 unknown easyconfig parameters detected in test.eb: foo, some_list",
                "Use of 'dummy' toolchain is deprecated, use 'system' toolchain instead",
            ]
            for warning in warnings:
                self.assertTrue(warning in stderr, "Found warning '%s' in stderr output: %s" % (warning, stderr))

            init_config(build_options={'local_var_naming_check': 'error', 'silent': True})

            # easyconfig doesn't parse because of local variables with name other than 'local_*'
            self.assertErrorRegex(EasyBuildError, unknown_params_error_pattern, EasyConfig, test_ec)

            self.mock_stderr(True)
            self.mock_stdout(True)
            fix_deprecated_easyconfigs([toy_ec, test_ec, gzip_ec])
            stderr, stdout = self.get_stderr(), self.get_stdout()
            self.mock_stderr(False)
            self.mock_stdout(False)

            ectxt = read_file(test_ec)
            self.assertFalse(regex.search(ectxt), "Pattern '%s' *not* found in: %s" % (regex.pattern, ectxt))
            regex = re.compile("^toolchain = SYSTEM$", re.M)
            self.assertTrue(regex.search(ectxt), "Pattern '%s' found in: %s" % (regex.pattern, ectxt))

            self.assertEqual(gzip_ec_txt, read_file(gzip_ec))
            self.assertEqual(toy_ec_txt, read_file(toy_ec))
            self.assertTrue(test_ec_txt != read_file(test_ec))

            # original easyconfig is backed up automatically
            test_ecs = sorted([f for f in os.listdir(self.test_prefix) if f.startswith('test.eb')])
            self.assertEqual(len(test_ecs), 2)
            backup_test_ec = os.path.join(self.test_prefix, test_ecs[1])
            self.assertEqual(test_ec_txt, read_file(backup_test_ec))

            remove_file(backup_test_ec)

            # parsing works now, toolchain is replaced with system toolchain
            ec = EasyConfig(test_ec)
            self.assertEqual(ec['toolchain'], {'name': 'system', 'version': 'system'})
            self.assertEqual(ec['configopts'], "--foobar --barfoo --barfoobaz")

            self.assertFalse(stderr)
            stdout = stdout.split('\n')
            self.assertEqual(len(stdout), 8)
            patterns = [
                r"^\* \[1/3\] fixing .*/t/toy/toy-0.0.eb\.\.\. \(no changes made\)$",
                r"^\* \[2/3\] fixing .*/test.eb\.\.\. FIXED!$",
                r"^\s*\(changes made in place, original copied to .*/test.eb.orig_[0-9_]+\)$",
                r"^\* \[3/3\] fixing .*/g/gzip/gzip-1.4.eb\.\.\. \(no changes made\)$",
                r'^$',
                r"^All done! Fixed 1 easyconfigs \(out of 3 found\).$",
                r'^$',
                r'^$',
            ]
            for idx, pattern in enumerate(patterns):
                self.assertTrue(re.match(pattern, stdout[idx]), "Pattern '%s' matches '%s'" % (pattern, stdout[idx]))

    def test_parse_list_comprehension_scope(self):
        """Test parsing of an easyconfig file that uses a local variable in list comprehension."""
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ectxt = '\n'.join([
            "easyblock = 'ConfigureMake'",
            "name = 'test'",
            "version = '1.2.3'",
            "homepage = 'https://example.com'",
            "description = 'test'",
            "toolchain = SYSTEM",
            "local_bindir = 'bin'",
            "local_binaries = ['foo', 'bar']",
            "sanity_check_paths = {",
            # using local variable 'bindir' in list comprehension in sensitive w.r.t. scope,
            # especially in Python 3 where list comprehensions have their own scope
            # cfr. https://github.com/easybuilders/easybuild-easyconfigs/pull/7848
            "   'files': ['%s/%s' % (local_bindir, x) for x in local_binaries],",
            "   'dirs': [],",
            "}",
        ])
        write_file(test_ec, test_ectxt)
        ec = EasyConfig(test_ec)
        expected_sanity_check_paths = {
            'files': ['bin/foo', 'bin/bar'],
            'dirs': [],
        }
        self.assertEqual(ec['sanity_check_paths'], expected_sanity_check_paths)

    def test_triage_easyconfig_params(self):
        """Test for triage_easyconfig_params function."""
        variables = {
            'foobar': 'foobar',
            'local_foo': 'test123',
            '_bar': 'bar',
            'name': 'example',
            'version': '1.2.3',
            'toolchain': {'name': 'system', 'version': 'system'},
            'homepage': 'https://example.com',
            'bleh': "just a local var",
            'x': "single letter local var",
        }
        ec = {
            'name': None,
            'version': None,
            'homepage': None,
            'toolchain': None,
        }
        ec_params, unknown_keys = triage_easyconfig_params(variables, ec)
        expected = {
            'name': 'example',
            'version': '1.2.3',
            'homepage': 'https://example.com',
            'toolchain': {'name': 'system', 'version': 'system'},
        }
        self.assertEqual(ec_params, expected)
        self.assertEqual(sorted(unknown_keys), ['bleh', 'foobar'])

        # check behaviour when easyconfig parameters that use a name indicating a local variable were defined
        ec.update({
            'x': None,
            'local_foo': None,
            '_foo': None,
            '_': None,
        })
        error = "Found 4 easyconfig parameters that are considered local variables: _, _foo, local_foo, x"
        self.assertErrorRegex(EasyBuildError, error, triage_easyconfig_params, variables, ec)

    def test_local_vars_detection(self):
        """Test detection of using unknown easyconfig parameters that are likely local variables."""

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ectxt = '\n'.join([
            "easyblock = 'ConfigureMake'",
            "name = 'test'",
            "version = '1.2.3'",
            "homepage = 'https://example.com'",
            "description = 'test'",
            "toolchain = SYSTEM",
            "foobar = 'xxx'",
            "_foo = 'foo'",  # not reported
            "local_bar = 'bar'",  # not reported
        ])
        write_file(test_ec, test_ectxt)
        expected_error = "Use of 1 unknown easyconfig parameters detected in test.eb: foobar"
        self.assertErrorRegex(EasyBuildError, expected_error, EasyConfig, test_ec, local_var_naming_check='error')

        # all unknown keys are detected at once, and reported alphabetically
        # single-letter local variables are not a problem
        test_ectxt = '\n'.join([
            'zzz_test = ["one", "two"]',
            test_ectxt,
            'a = "blah"',
            'local_foo = "foo"',  # matches local variable naming scheme, so not reported!
            'test_list = [x for x in ["1", "2", "3"]]',
            '_bar = "bar"',  # matches local variable naming scheme, so not reported!
            'an_unknown_key = 123',
        ])
        write_file(test_ec, test_ectxt)

        expected_error = "Use of 4 unknown easyconfig parameters detected in test.eb: "
        expected_error += "an_unknown_key, foobar, test_list, zzz_test"
        self.assertErrorRegex(EasyBuildError, expected_error, EasyConfig, test_ec, local_var_naming_check='error')

    def test_arch_specific_dependency(self):
        """Tests that the correct version is chosen for this architecture"""

        my_arch = st.get_cpu_architecture()
        expected_version = '1.2.3'
        dep_str = "[('foo', {'arch=%s': '%s', 'arch=Foo': 'bar'})]" % (my_arch, expected_version)

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ectxt = '\n'.join([
            "easyblock = 'ConfigureMake'",
            "name = 'test'",
            "version = '0.2'",
            "homepage = 'https://example.com'",
            "description = 'test'",
            "toolchain = SYSTEM",
            "dependencies = %s" % dep_str,
        ])
        write_file(test_ec, test_ectxt)

        ec = EasyConfig(test_ec)
        self.assertEqual(ec.dependencies()[0]['version'], expected_version)

    def test_unexpected_version_keys_caught(self):
        """Tests that unexpected keys in a version dictionary are caught"""

        my_arch = st.get_cpu_architecture()
        expected_version = '1.2.3'

        for dep_str in ("[('foo', {'bar=%s': '%s', 'arch=Foo': 'bar'})]" % (my_arch, expected_version),
                        "[('foo', {'blah': 'bar'})]"):
            test_ec = os.path.join(self.test_prefix, 'test.eb')
            test_ectxt = '\n'.join([
                "easyblock = 'ConfigureMake'",
                "name = 'test'",
                "version = '0.2'",
                "homepage = 'https://example.com'",
                "description = 'test'",
                "toolchain = SYSTEM",
                "dependencies = %s" % dep_str,
            ])
            write_file(test_ec, test_ectxt)

            self.assertRaises(EasyBuildError, EasyConfig, test_ec)

    def test_resolve_exts_filter_template(self):
        """Test for resolve_exts_filter_template function."""
        class TestExtension(object):
            def __init__(self, values):
                self.name = values['name']
                self.version = values.get('version')
                self.src = values.get('src')
                self.options = values.get('options', {})

        error_msg = 'exts_filter should be a list or tuple'
        self.assertErrorRegex(EasyBuildError, error_msg, resolve_exts_filter_template,
                              '[ 1 == 1 ]', {})
        self.assertErrorRegex(EasyBuildError, error_msg, resolve_exts_filter_template,
                              ['[ 1 == 1 ]'], {})
        self.assertErrorRegex(EasyBuildError, error_msg, resolve_exts_filter_template,
                              ['[ 1 == 1 ]', 'true', 'false'], {})

        test_cases = [
            # Minimal case: just name
            (['%(ext_name)s', None],
             {'name': 'foo'},
             ('foo', None),
             ),
            # Minimal case with input
            (['%(ext_name)s', '>%(ext_name)s'],
             {'name': 'foo'},
             ('foo', '>foo'),
             ),
            # All values
            (['%(ext_name)s-%(ext_version)s-%(src)s', '>%(ext_name)s-%(ext_version)s-%(src)s'],
             {'name': 'foo', 'version': 42, 'src': 'bar.tgz'},
             ('foo-42-bar.tgz', '>foo-42-bar.tgz'),
             ),
            # options dict is accepted
            (['%(ext_name)s-%(ext_version)s-%(src)s', '>%(ext_name)s-%(ext_version)s-%(src)s'],
             {'name': 'foo', 'version': 42, 'src': 'bar.tgz', 'options': {'dummy': 'value'}},
             ('foo-42-bar.tgz', '>foo-42-bar.tgz'),
             ),
            # modulename overwrites name
            (['%(ext_name)s-%(ext_version)s-%(src)s', '>%(ext_name)s-%(ext_version)s-%(src)s'],
             {'name': 'foo', 'version': 42, 'src': 'bar.tgz', 'options': {'modulename': 'baz'}},
             ('baz-42-bar.tgz', '>baz-42-bar.tgz'),
             ),
        ]
        for exts_filter, ext, expected_value in test_cases:
            value = resolve_exts_filter_template(exts_filter, ext)
            self.assertEqual(value, expected_value)
            value = resolve_exts_filter_template(exts_filter, TestExtension(ext))
            self.assertEqual(value, expected_value)

    def test_cuda_compute_capabilities(self):
        """Tests that the cuda_compute_capabilities templates are correct"""

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ectxt = '\n'.join([
            "easyblock = 'ConfigureMake'",
            "name = 'test'",
            "version = '0.2'",
            "homepage = 'https://example.com'",
            "description = 'test'",
            "toolchain = SYSTEM",
            "cuda_compute_capabilities = ['5.1', '7.0', '7.1']",
            "installopts = '%(cuda_compute_capabilities)s'",
            "preinstallopts = '%(cuda_cc_space_sep)s'",
            "prebuildopts = '%(cuda_cc_semicolon_sep)s'",
            "configopts = '%(cuda_sm_comma_sep)s'",
            "preconfigopts = '%(cuda_sm_space_sep)s'",
        ])
        write_file(test_ec, test_ectxt)

        ec = EasyConfig(test_ec)
        self.assertEqual(ec['installopts'], '5.1,7.0,7.1')
        self.assertEqual(ec['preinstallopts'], '5.1 7.0 7.1')
        self.assertEqual(ec['prebuildopts'], '5.1;7.0;7.1')
        self.assertEqual(ec['configopts'], 'sm_51,sm_70,sm_71')
        self.assertEqual(ec['preconfigopts'], 'sm_51 sm_70 sm_71')

        # build options overwrite it
        init_config(build_options={'cuda_compute_capabilities': ['4.2', '6.3']})
        ec = EasyConfig(test_ec)
        self.assertEqual(ec['installopts'], '4.2,6.3')
        self.assertEqual(ec['preinstallopts'], '4.2 6.3')
        self.assertEqual(ec['prebuildopts'], '4.2;6.3')
        self.assertEqual(ec['configopts'], 'sm_42,sm_63')
        self.assertEqual(ec['preconfigopts'], 'sm_42 sm_63')

    def test_det_copy_ec_specs(self):
        """Test det_copy_ec_specs function."""

        cwd = os.getcwd()

        # no problems on empty list as input
        paths, target_path = det_copy_ec_specs([], None)
        self.assertEqual(paths, [])
        self.assertEqual(target_path, None)

        # single-element list, no --from-pr => use current directory as target location
        paths, target_path = det_copy_ec_specs(['test.eb'], None)
        self.assertEqual(paths, ['test.eb'])
        self.assertTrue(os.path.samefile(target_path, cwd))

        # multi-element list, no --from-pr => last element is used as target location
        for args in (['test.eb', 'dir'], ['test1.eb', 'test2.eb', 'dir']):
            paths, target_path = det_copy_ec_specs(args, None)
            self.assertEqual(paths, args[:-1])
            self.assertEqual(target_path, args[-1])

        # use fixed PR (speeds up the test due to caching in fetch_files_from_pr;
        # see https://github.com/easybuilders/easybuild-easyconfigs/pull/8007
        from_pr = 8007
        arrow_ec_fn = 'Arrow-0.7.1-intel-2017b-Python-3.6.3.eb'
        bat_ec_fn = 'bat-0.3.3-intel-2017b-Python-3.6.3.eb'
        bat_patch_fn = 'bat-0.3.3-fix-pyspark.patch'
        pr_files = [
            arrow_ec_fn,
            bat_ec_fn,
            bat_patch_fn,
        ]

        # if no paths are specified, default is to copy all files touched by PR to current working directory
        paths, target_path = det_copy_ec_specs([], from_pr)
        self.assertEqual(len(paths), 3)
        filenames = sorted([os.path.basename(x) for x in paths])
        self.assertEqual(filenames, sorted(pr_files))
        self.assertTrue(os.path.samefile(target_path, cwd))

        # last argument is used as target directory,
        # unless it corresponds to a file touched by PR
        args = [bat_ec_fn, 'target_dir']
        paths, target_path = det_copy_ec_specs(args, from_pr)
        self.assertEqual(len(paths), 1)
        self.assertEqual(os.path.basename(paths[0]), bat_ec_fn)
        self.assertEqual(target_path, 'target_dir')

        args = [bat_ec_fn]
        paths, target_path = det_copy_ec_specs(args, from_pr)
        self.assertEqual(len(paths), 1)
        self.assertEqual(os.path.basename(paths[0]), bat_ec_fn)
        self.assertTrue(os.path.samefile(target_path, cwd))

        args = [arrow_ec_fn, bat_ec_fn]
        paths, target_path = det_copy_ec_specs(args, from_pr)
        self.assertEqual(len(paths), 2)
        self.assertEqual(os.path.basename(paths[0]), arrow_ec_fn)
        self.assertEqual(os.path.basename(paths[1]), bat_ec_fn)
        self.assertTrue(os.path.samefile(target_path, cwd))

        args = [bat_ec_fn, bat_patch_fn]
        paths, target_path = det_copy_ec_specs(args, from_pr)
        self.assertEqual(len(paths), 2)
        self.assertEqual(os.path.basename(paths[0]), bat_ec_fn)
        self.assertEqual(os.path.basename(paths[1]), bat_patch_fn)
        self.assertTrue(os.path.samefile(target_path, cwd))

        # also test with combination of local files and files from PR
        args = [arrow_ec_fn, 'test.eb', 'test.patch', bat_patch_fn]
        paths, target_path = det_copy_ec_specs(args, from_pr)
        self.assertEqual(len(paths), 4)
        self.assertEqual(os.path.basename(paths[0]), arrow_ec_fn)
        self.assertEqual(paths[1], 'test.eb')
        self.assertEqual(paths[2], 'test.patch')
        self.assertEqual(os.path.basename(paths[3]), bat_patch_fn)
        self.assertTrue(os.path.samefile(target_path, cwd))

    def test_recursive_module_unload(self):
        """Test use of recursive_module_unload easyconfig parameter."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs_dir, 'f', 'foss', 'foss-2018a.eb')
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ec_txt = read_file(toy_ec)
        write_file(test_ec, test_ec_txt)

        test_module = os.path.join(self.test_installpath, 'modules', 'all', 'foss', '2018a')
        gcc_modname = 'GCC/6.4.0-2.28'
        if get_module_syntax() == 'Lua':
            test_module += '.lua'
            guarded_load_pat = r'if not \( isloaded\("%(mod)s"\) \) then\n\s*load\("%(mod)s"\)'
            recursive_unload_pat = r'if mode\(\) == "unload" or not \( isloaded\("%(mod)s"\) \) then\n'
            recursive_unload_pat += r'\s*load\("%(mod)s"\)'
        else:
            guarded_load_pat = r'if { \!\[ is-loaded %(mod)s \] } {\n\s*module load %(mod)s'
            recursive_unload_pat = r'if { \[ module-info mode remove \] \|\| \!\[ is-loaded %(mod)s \] } {\n'
            recursive_unload_pat += r'\s*module load %(mod)s'

        guarded_load_regex = re.compile(guarded_load_pat % {'mod': gcc_modname}, re.M)
        recursive_unload_regex = re.compile(recursive_unload_pat % {'mod': gcc_modname}, re.M)

        # by default, recursive module unloading is disabled everywhere
        # (--recursive-module-unload configuration option is disabled,
        # recursive_module_unload easyconfig parameter is None)
        self.assertFalse(build_option('recursive_mod_unload'))
        ec = EasyConfig(test_ec)
        self.assertFalse(ec['recursive_module_unload'])
        eb = EasyBlock(ec)
        eb.builddir = self.test_prefix
        eb.prepare_step()
        eb.make_module_step()
        modtxt = read_file(test_module)
        fail_msg = "Pattern '%s' should be found in: %s" % (guarded_load_regex.pattern, modtxt)
        self.assertTrue(guarded_load_regex.search(modtxt), fail_msg)
        fail_msg = "Pattern '%s' should not be found in: %s" % (recursive_unload_regex.pattern, modtxt)
        self.assertFalse(recursive_unload_regex.search(modtxt), fail_msg)

        remove_file(test_module)

        # recursive_module_unload easyconfig parameter is honored
        test_ec_bis = os.path.join(self.test_prefix, 'test_bis.eb')
        test_ec_bis_txt = read_file(toy_ec) + '\nrecursive_module_unload = True'
        write_file(test_ec_bis, test_ec_bis_txt)

        ec_bis = EasyConfig(test_ec_bis)
        self.assertTrue(ec_bis['recursive_module_unload'])
        eb_bis = EasyBlock(ec_bis)
        eb_bis.builddir = self.test_prefix
        eb_bis.prepare_step()
        eb_bis.make_module_step()
        modtxt = read_file(test_module)
        fail_msg = "Pattern '%s' should not be found in: %s" % (guarded_load_regex.pattern, modtxt)
        self.assertFalse(guarded_load_regex.search(modtxt), fail_msg)
        fail_msg = "Pattern '%s' should be found in: %s" % (recursive_unload_regex.pattern, modtxt)
        self.assertTrue(recursive_unload_regex.search(modtxt), fail_msg)

        # recursive_mod_unload build option is honored
        update_build_option('recursive_mod_unload', True)
        eb = EasyBlock(ec)
        eb.builddir = self.test_prefix
        eb.prepare_step()
        eb.make_module_step()
        modtxt = read_file(test_module)
        fail_msg = "Pattern '%s' should not be found in: %s" % (guarded_load_regex.pattern, modtxt)
        self.assertFalse(guarded_load_regex.search(modtxt), fail_msg)
        fail_msg = "Pattern '%s' should be found in: %s" % (recursive_unload_regex.pattern, modtxt)
        self.assertTrue(recursive_unload_regex.search(modtxt), fail_msg)

        # disabling via easyconfig parameter works even when recursive_mod_unload build option is enabled
        self.assertTrue(build_option('recursive_mod_unload'))
        test_ec_bis = os.path.join(self.test_prefix, 'test_bis.eb')
        test_ec_bis_txt = read_file(toy_ec) + '\nrecursive_module_unload = False'
        write_file(test_ec_bis, test_ec_bis_txt)
        ec_bis = EasyConfig(test_ec_bis)
        self.assertEqual(ec_bis['recursive_module_unload'], False)
        eb_bis = EasyBlock(ec_bis)
        eb_bis.builddir = self.test_prefix
        eb_bis.prepare_step()
        eb_bis.make_module_step()
        modtxt = read_file(test_module)
        fail_msg = "Pattern '%s' should be found in: %s" % (guarded_load_regex.pattern, modtxt)
        self.assertTrue(guarded_load_regex.search(modtxt), fail_msg)
        fail_msg = "Pattern '%s' should not be found in: %s" % (recursive_unload_regex.pattern, modtxt)
        self.assertFalse(recursive_unload_regex.search(modtxt), fail_msg)

    def test_pure_ec(self):
        """
        Test whether we can get a 'pure' view on the easyconfig file,
        which correctly reflects what's defined in the easyconfig file.
        """
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = EasyConfig(os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0.eb'))

        ec_dict = toy_ec.parser.get_config_dict()
        self.assertEqual(ec_dict.get('version'), '0.0')
        self.assertEqual(ec_dict.get('sources'), ['%(name)s-%(version)s.tar.gz'])
        self.assertEqual(ec_dict.get('exts_default_options'), None)
        self.assertEqual(ec_dict.get('sanity_check_paths'), {'dirs': ['bin'], 'files': [('bin/yot', 'bin/toy')]})

        # manipulating easyconfig parameter values should not affect the result of parser.get_config_dict()
        with toy_ec.disable_templating():
            toy_ec['version'] = '1.2.3'
            toy_ec['sources'].append('test.tar.gz')
            toy_ec['sanity_check_paths']['files'].append('bin/foobar.exe')

        ec_dict_bis = toy_ec.parser.get_config_dict()
        self.assertEqual(ec_dict_bis.get('version'), '0.0')
        self.assertEqual(ec_dict_bis.get('sources'), ['%(name)s-%(version)s.tar.gz'])
        self.assertEqual(ec_dict_bis.get('exts_default_options'), None)
        self.assertEqual(ec_dict.get('sanity_check_paths'), {'dirs': ['bin'], 'files': [('bin/yot', 'bin/toy')]})

    def test_easyconfig_import(self):
        """
        Test parsing of an easyconfig file that includes import statements.
        """
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0.eb')

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ec_txt = read_file(toy_ec)
        test_ec_txt += '\n' + '\n'.join([
            "import os",
            "local_test = os.getenv('TEST_TOY')",
            "sanity_check_commands = ['toy | grep %s' % local_test]",
        ])
        write_file(test_ec, test_ec_txt)

        os.environ['TEST_TOY'] = '123'

        ec = EasyConfig(test_ec)

        self.assertEqual(ec['sanity_check_commands'], ['toy | grep 123'])

        # inject weird stuff, like a class definition that creates a logger instance
        # and a local variable with a list of imported modules, to check clean error handling
        test_ec_txt += '\n' + '\n'.join([
            "import logging",
            "class _TestClass(object):",
            "    def __init__(self):",
            "        self.log = logging.Logger('alogger')",
            "local_test = _TestClass()",
            "local_modules = [logging, os]",
        ])
        write_file(test_ec, test_ec_txt)

        error_pattern = r"Failed to copy '.*' easyconfig parameter"
        self.assertErrorRegex(EasyBuildError, error_pattern, EasyConfig, test_ec)

    def test_get_cuda_cc_template_value(self):
        """
        Test getting template value based on --cuda-compute-capabilities / cuda_compute_capabilities.
        """
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = SYSTEM',
        ])
        self.prep()
        ec = EasyConfig(self.eb_file)

        error_pattern = "foobar is not a template value based on --cuda-compute-capabilities/cuda_compute_capabilities"
        self.assertErrorRegex(EasyBuildError, error_pattern, ec.get_cuda_cc_template_value, 'foobar')

        error_pattern = r"Template value '%s' is not defined!\n"
        error_pattern += r"Make sure that either the --cuda-compute-capabilities EasyBuild configuration "
        error_pattern += "option is set, or that the cuda_compute_capabilities easyconfig parameter is defined."
        cuda_template_values = {
            'cuda_compute_capabilities': '6.5,7.0',
            'cuda_cc_space_sep': '6.5 7.0',
            'cuda_cc_semicolon_sep': '6.5;7.0',
            'cuda_sm_comma_sep': 'sm_65,sm_70',
            'cuda_sm_space_sep': 'sm_65 sm_70',
        }
        for key in cuda_template_values:
            self.assertErrorRegex(EasyBuildError, error_pattern % key, ec.get_cuda_cc_template_value, key)

        update_build_option('cuda_compute_capabilities', ['6.5', '7.0'])
        ec = EasyConfig(self.eb_file)

        for key in cuda_template_values:
            self.assertEqual(ec.get_cuda_cc_template_value(key), cuda_template_values[key])

        update_build_option('cuda_compute_capabilities', None)
        ec = EasyConfig(self.eb_file)

        for key in cuda_template_values:
            self.assertErrorRegex(EasyBuildError, error_pattern % key, ec.get_cuda_cc_template_value, key)

        self.contents += "\ncuda_compute_capabilities = ['6.5', '7.0']"
        self.prep()
        ec = EasyConfig(self.eb_file)

        for key in cuda_template_values:
            self.assertEqual(ec.get_cuda_cc_template_value(key), cuda_template_values[key])


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(EasyConfigTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
