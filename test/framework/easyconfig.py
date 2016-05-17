# #
# Copyright 2012-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
Unit tests for easyconfig.py

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""
import copy
import os
import re
import shutil
import tempfile
from distutils.version import LooseVersion
from test.framework.utilities import EnhancedTestCase, init_config
from unittest import TestLoader, main
from vsc.utils.fancylogger import setLogLevelDebug, logToScreen

import easybuild.tools.build_log
import easybuild.framework.easyconfig as easyconfig
from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig.constants import EXTERNAL_MODULE_MARKER
from easybuild.framework.easyconfig.easyconfig import ActiveMNS, EasyConfig
from easybuild.framework.easyconfig.easyconfig import create_paths, copy_easyconfigs, get_easyblock_class
from easybuild.framework.easyconfig.licenses import License, LicenseGPLv3
from easybuild.framework.easyconfig.parser import fetch_parameters_from_easyconfig
from easybuild.framework.easyconfig.templates import to_template_str
from easybuild.framework.easyconfig.tools import dep_graph, find_related_easyconfigs
from easybuild.framework.easyconfig.tools import parse_easyconfigs
from easybuild.framework.easyconfig.tweak import obtain_ec_for, tweak_one
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import module_classes
from easybuild.tools.configobj import ConfigObj
from easybuild.tools.filetools import mkdir, read_file, write_file
from easybuild.tools.module_naming_scheme.toolchain import det_toolchain_compilers, det_toolchain_mpi
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.options import parse_external_modules_metadata
from easybuild.tools.robot import resolve_dependencies
from easybuild.tools.systemtools import get_shared_lib_ext
from easybuild.tools.utilities import quote_str
from test.framework.utilities import find_full_path


EXPECTED_DOTTXT_TOY_DEPS = """digraph graphname {
"GCC/4.7.2 (EXT)";
toy;
ictce;
toy -> ictce;
toy -> "GCC/4.7.2 (EXT)";
}
"""


class EasyConfigTest(EnhancedTestCase):
    """ easyconfig tests """
    contents = None
    eb_file = ''

    def setUp(self):
        """Set up everything for running a unit test."""
        super(EasyConfigTest, self).setUp()

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
            'toolchain = {"name": "dummy", "version": "dummy"}',
        ])
        self.prep()

        eb = EasyConfig(self.eb_file)

        self.assertEqual(eb['name'], "pi")
        self.assertEqual(eb['version'], "3.14")
        self.assertEqual(eb['homepage'], "http://example.com")
        self.assertEqual(eb['toolchain'], {"name":"dummy", "version": "dummy"})
        self.assertEqual(eb['description'], "test easyconfig")

    def test_validation(self):
        """ test other validations beside mandatory parameters """
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"dummy", "version": "dummy"}',
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

        # dummy toolchain, installversion == version
        self.assertEqual(det_full_ec_version(ec), "3.14")

        os.chmod(self.eb_file, 0000)
        self.assertErrorRegex(EasyBuildError, "Permission denied", EasyConfig, self.eb_file)
        os.chmod(self.eb_file, 0755)

        self.contents += "\nsyntax_error'"
        self.prep()
        self.assertErrorRegex(EasyBuildError, "SyntaxError", EasyConfig, self.eb_file)

    def test_shlib_ext(self):
        """ inside easyconfigs shared_lib_ext should be set """
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"dummy", "version": "dummy"}',
            'sanity_check_paths = { "files": ["lib/lib.%s" % SHLIB_EXT] }',
        ])
        self.prep()
        eb = EasyConfig(self.eb_file)
        self.assertEqual(eb['sanity_check_paths']['files'][0], "lib/lib.%s" % get_shared_lib_ext())

    def test_dependency(self):
        """ test all possible ways of specifying dependencies """
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"GCC", "version": "4.6.3"}',
            'dependencies = [("first", "1.1"), {"name": "second", "version": "2.2"}]',
            'builddependencies = [("first", "1.1"), {"name": "second", "version": "2.2"}]',
        ])
        self.prep()
        eb = EasyConfig(self.eb_file)
        # should include builddependencies
        self.assertEqual(len(eb.dependencies()), 4)
        self.assertEqual(len(eb.builddependencies()), 2)

        first = eb.dependencies()[0]
        second = eb.dependencies()[1]

        self.assertEqual(first['name'], "first")
        self.assertEqual(second['name'], "second")

        self.assertEqual(first['version'], "1.1")
        self.assertEqual(second['version'], "2.2")

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

    def test_extra_options(self):
        """ extra_options should allow other variables to be stored """
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

        eb = EasyConfig(self.eb_file, extra_options=extra_vars)
        self.assertEqual(eb['custom_key'], 'default')

        eb['custom_key'] = "not so default"
        self.assertEqual(eb['custom_key'], 'not so default')

        self.contents += "\ncustom_key = 'test'"

        self.prep()

        eb = EasyConfig(self.eb_file, extra_options=extra_vars)
        self.assertEqual(eb['custom_key'], 'test')

        eb['custom_key'] = "not so default"
        self.assertEqual(eb['custom_key'], 'not so default')

        # test if extra toolchain options are being passed
        self.assertEqual(eb.toolchain.options['static'], True)

        # test extra mandatory parameters
        extra_vars.update({'mandatory_key': ['default', 'another mandatory key', easyconfig.MANDATORY]})
        self.assertErrorRegex(EasyBuildError, r"mandatory parameters not provided",
                              EasyConfig, self.eb_file, extra_options=extra_vars)

        self.contents += '\nmandatory_key = "value"'
        self.prep()

        eb = EasyConfig(self.eb_file, extra_options=extra_vars)

        self.assertEqual(eb['mandatory_key'], 'value')

    def test_exts_list(self):
        """Test handling of list of extensions."""
        os.environ['EASYBUILD_SOURCEPATH'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        init_config()
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name": "dummy", "version": "dummy"}',
            'exts_list = [',
            '   ("ext1", "ext_ver1", {',
            '       "source_tmpl": "gzip-1.4.eb",',  # dummy source template to avoid downloading fail
            '       "source_urls": ["http://example.com/"]',
            '   }),',
            '   ("ext2", "ext_ver2", {',
            '       "source_tmpl": "gzip-1.4.eb",',  # dummy source template to avoid downloading fail
            '       "source_urls": [("http://example.com", "suffix")],'
            '       "patches": ["toy-0.0.eb"],',  # dummy patch to avoid downloading fail
            '       "checksums": [',
            '           "9e9485921c6afe15f62aedfead2c8f6e",',  # MD5 checksum for source (gzip-1.4.eb)
            '           "fad34da3432ee2fd4d6554b86c8df4bf",',  # MD5 checksum for patch (toy-0.0.eb)
            '       ],',
            '   }),',
            ']',
        ])
        self.prep()
        ec = EasyConfig(self.eb_file)
        eb = EasyBlock(ec)
        exts_sources = eb.fetch_extension_sources()

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

    def test_tweaking(self):
        """test tweaking ability of easyconfigs"""

        fd, tweaked_fn = tempfile.mkstemp(prefix='easybuild-tweaked-', suffix='.eb')
        os.close(fd)
        patches = ["t1.patch", ("t2.patch", 1), ("t3.patch", "test"), ("t4.h", "include")]
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'homepage = "http://www.example.com"',
            'description = "dummy description"',
            'version = "3.14"',
            'toolchain = {"name": "GCC", "version": "4.6.3"}',
            'patches = %s',
        ]) % str(patches)
        self.prep()

        ver = "1.2.3"
        verpref = "myprefix"
        versuff = "mysuffix"
        tcname = "gompi"
        tcver = "1.4.10"
        new_patches = ['t5.patch', 't6.patch']
        homepage = "http://www.justatest.com"

        tweaks = {
                  'version': ver,
                  'versionprefix': verpref,
                  'versionsuffix': versuff,
                  'toolchain_version': tcver,
                  'patches': new_patches
                 }
        tweak_one(self.eb_file, tweaked_fn, tweaks)

        eb = EasyConfig(tweaked_fn)
        self.assertEqual(eb['version'], ver)
        self.assertEqual(eb['versionprefix'], verpref)
        self.assertEqual(eb['versionsuffix'], versuff)
        self.assertEqual(eb['toolchain']['version'], tcver)
        self.assertEqual(eb['patches'], new_patches)

        eb = EasyConfig(self.eb_file)
        # eb['toolchain']['version'] = tcver does not work as expected with templating enabled
        eb.enable_templating = False
        eb['version'] = ver
        eb['toolchain']['version'] = tcver
        eb.enable_templating = True
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
        dummy = "dummy"

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
            'toolchain': {'name': dummy, 'version': tcver},
            'versionprefix': verpref,
            'versionsuffix': versuff,
        }
        installver = det_full_ec_version(cfg)
        self.assertEqual(installver, correct_installver)

    def test_obtain_easyconfig(self):
        """test obtaining an easyconfig file given certain specifications"""

        tcname = 'GCC'
        tcver = '4.3.2'
        patches = ["one.patch"]

        # prepare a couple of eb files to test again
        fns = ["pi-3.14.eb",
               "pi-3.13-GCC-4.3.2.eb",
               "pi-3.15-GCC-4.3.2.eb",
               "pi-3.15-GCC-4.4.5.eb",
               "foo-1.2.3-GCC-4.3.2.eb"]
        eb_files = [(fns[0], "\n".join([
                        'easyblock = "ConfigureMake"',
                        'name = "pi"',
                        'version = "3.12"',
                        'homepage = "http://example.com"',
                        'description = "test easyconfig"',
                        'toolchain = {"name": "dummy", "version": "dummy"}',
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
                        'toolchain = {"name": "%s", "version": "4.5.1"}' % tcname,
                        'patches = %s' % patches
                    ])),
                    (fns[4], "\n".join([
                        'easyblock = "ConfigureMake"',
                        'name = "foo"',
                        'version = "1.2.3"',
                        'homepage = "http://example.com"',
                        'description = "test easyconfig"',
                        'toolchain = {"name": "%s", "version": "%s"}' % (tcname, tcver),
                        'foo_extra1 = "bar"',
                    ]))
                   ]


        self.ec_dir = tempfile.mkdtemp()

        for (fn, txt) in eb_files:
            write_file(os.path.join(self.ec_dir, fn), txt)

        # should crash when no suited easyconfig file (or template) is available
        specs = {'name': 'nosuchsoftware'}
        error_regexp = ".*No easyconfig files found for software %s, and no templates available. I'm all out of ideas." % specs['name']
        self.assertErrorRegex(EasyBuildError, error_regexp, obtain_ec_for, specs, [self.ec_dir], None)

        # should find matching easyconfig file
        specs = {
            'name': 'foo',
            'version': '1.2.3'
        }
        res = obtain_ec_for(specs, [self.ec_dir], None)
        self.assertEqual(res[0], False)
        self.assertEqual(res[1], os.path.join(self.ec_dir, fns[-1]))

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
        self.assertErrorRegex(EasyBuildError, error_regexp, obtain_ec_for, specs, [self.ec_dir], None)

        # should be able to generate an easyconfig file that slightly differs
        ver = '3.16'
        specs.update({
            'toolchain_name': tcname,
            'toolchain_version': tcver,
            'version': ver,
            'start_dir': 'bar123'
        })
        res = obtain_ec_for(specs, [self.ec_dir], None)
        self.assertEqual(res[1], "%s-%s-%s-%s%s.eb" % (name, ver, tcname, tcver, suff))

        self.assertEqual(res[0], True)
        ec = EasyConfig(res[1])
        self.assertEqual(ec['name'], specs['name'])
        self.assertEqual(ec['version'], specs['version'])
        self.assertEqual(ec['versionsuffix'], specs['versionsuffix'])
        self.assertEqual(ec['toolchain'], {'name': tcname, 'version': tcver})
        self.assertEqual(ec['start_dir'], specs['start_dir'])
        os.remove(res[1])

        specs.update({
            'foo': 'bar123'
        })
        self.assertErrorRegex(EasyBuildError, "Unkown easyconfig parameter: foo",
                              obtain_ec_for, specs, [self.ec_dir], None)
        del specs['foo']

        # should pick correct version, i.e. not newer than what's specified, if a choice needs to be made
        ver = '3.14'
        specs.update({'version': ver})
        res = obtain_ec_for(specs, [self.ec_dir], None)
        self.assertEqual(res[0], True)
        ec = EasyConfig(res[1])
        self.assertEqual(ec['version'], specs['version'])
        txt = read_file(res[1])
        self.assertTrue(re.search("^version = [\"']%s[\"']$" % ver, txt, re.M))
        os.remove(res[1])

        # should pick correct toolchain version as well, i.e. now newer than what's specified, if a choice needs to be made
        specs.update({
            'version': '3.15',
            'toolchain_version': '4.4.5',
        })
        res = obtain_ec_for(specs, [self.ec_dir], None)
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
            'builddependencies': [('testbuildonly', '4.5.6')],
            'dependencies': [('foo', '1.2.3'), ('bar', '666', '-bleh', ('gompi', '1.4.10'))],
            'hiddendependencies': [('test', '3.2.1'), ('testbuildonly', '4.5.6')],
        })
        parsed_deps = [
            {
                'name': 'foo',
                'version': '1.2.3',
                'versionsuffix': '',
                'toolchain': ec['toolchain'],
                'dummy': False,
                'short_mod_name': 'foo/1.2.3-GCC-4.4.5',
                'full_mod_name': 'foo/1.2.3-GCC-4.4.5',
                'build_only': False,
                'hidden': False,
                'external_module': False,
                'external_module_metadata': {},
            },
            {
                'name': 'bar',
                'version': '666',
                'versionsuffix': '-bleh',
                'toolchain': {'name': 'gompi', 'version': '1.4.10'},
                'dummy': False,
                'short_mod_name': 'bar/666-gompi-1.4.10-bleh',
                'full_mod_name': 'bar/666-gompi-1.4.10-bleh',
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
                'dummy': False,
                'short_mod_name': 'test/.3.2.1-GCC-4.4.5',
                'full_mod_name': 'test/.3.2.1-GCC-4.4.5',
                'build_only': False,
                'hidden': True,
                'external_module': False,
                'external_module_metadata': {},
            },
            {
                'name': 'testbuildonly',
                'version': '4.5.6',
                'versionsuffix': '',
                'toolchain': ec['toolchain'],
                'dummy': False,
                'short_mod_name': 'testbuildonly/.4.5.6-GCC-4.4.5',
                'full_mod_name': 'testbuildonly/.4.5.6-GCC-4.4.5',
                'build_only': True,
                'hidden': True,
                'external_module': False,
                'external_module_metadata': {},
            },
        ]

        # hidden dependencies must be included in list of dependencies
        res = obtain_ec_for(specs, [self.ec_dir], None)
        self.assertEqual(res[0], True)
        error_pattern = "Hidden deps with visible module names .* not in list of \(build\)dependencies: .*"
        self.assertErrorRegex(EasyBuildError, error_pattern, EasyConfig, res[1])

        specs['dependencies'].append(('test', '3.2.1'))

        res = obtain_ec_for(specs, [self.ec_dir], None)
        self.assertEqual(res[0], True)
        ec = EasyConfig(res[1])
        self.assertEqual(ec['patches'], specs['patches'])
        self.assertEqual(ec.dependencies(), parsed_deps)

        # hidden dependencies are filtered from list of (build)dependencies
        self.assertFalse('test/3.2.1-GCC-4.4.5' in [d['full_mod_name'] for d in ec['dependencies']])
        self.assertTrue('test/.3.2.1-GCC-4.4.5' in [d['full_mod_name'] for d in ec['hiddendependencies']])
        self.assertFalse('testbuildonly/4.5.6-GCC-4.4.5' in [d['full_mod_name'] for d in ec['builddependencies']])
        self.assertTrue('testbuildonly/.4.5.6-GCC-4.4.5' in [d['full_mod_name'] for d in ec['hiddendependencies']])
        os.remove(res[1])

        # hidden dependencies are also filtered from list of dependencies when validation is skipped
        res = obtain_ec_for(specs, [self.ec_dir], None)
        ec = EasyConfig(res[1], validate=False)
        self.assertFalse('test/3.2.1-GCC-4.4.5' in [d['full_mod_name'] for d in ec['dependencies']])
        self.assertTrue('test/.3.2.1-GCC-4.4.5' in [d['full_mod_name'] for d in ec['hiddendependencies']])
        self.assertFalse('testbuildonly/4.5.6-GCC-4.4.5' in [d['full_mod_name'] for d in ec['builddependencies']])
        self.assertTrue('testbuildonly/.4.5.6-GCC-4.4.5' in [d['full_mod_name'] for d in ec['hiddendependencies']])
        os.remove(res[1])

        # verify append functionality for lists
        specs['patches'].insert(0, '')
        res = obtain_ec_for(specs, [self.ec_dir], None)
        self.assertEqual(res[0], True)
        ec = EasyConfig(res[1])
        self.assertEqual(ec['patches'], patches + new_patches)
        specs['patches'].remove('')
        os.remove(res[1])

        # verify prepend functionality for lists
        specs['patches'].append('')
        res = obtain_ec_for(specs, [self.ec_dir], None)
        self.assertEqual(res[0], True)
        ec = EasyConfig(res[1])
        self.assertEqual(ec['patches'], new_patches + patches)
        os.remove(res[1])

        # should use supplied filename
        fn = "my.eb"
        res = obtain_ec_for(specs, [self.ec_dir], fn)
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
            shutil.copy2(tpl_full_path, self.ec_dir)
            specs.update({'name': 'nosuchsoftware'})
            res = obtain_ec_for(specs, [self.ec_dir], None)
            self.assertEqual(res[0], True)
            ec = EasyConfig(res[1])
            self.assertEqual(ec['name'], specs['name'])
            os.remove(res[1])

        # cleanup
        shutil.rmtree(self.ec_dir)

    def test_templating(self):
        """ test easyconfig templating """
        inp = {
           'name': 'PI',
           'version': '3.14',
           'namelower': 'pi',
           'cmd': 'tar xfvz %s',
        }
        # don't use any escaping insanity here, since it is templated itself
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "%(name)s"',
            'version = "%(version)s"',
            'versionsuffix = "-Python-%%(pyver)s"',
            'homepage = "http://example.com/%%(nameletter)s/%%(nameletterlower)s"',
            'description = "test easyconfig %%(name)s"',
            'toolchain = {"name":"dummy", "version": "dummy2"}',
            'source_urls = [(GOOGLECODE_SOURCE)]',
            'sources = [SOURCE_TAR_GZ, (SOURCELOWER_TAR_GZ, "%(cmd)s")]',
            'sanity_check_paths = {',
            '   "files": ["lib/python%%(pyshortver)s/site-packages"],',
            '   "dirs": ["libfoo.%%s" %% SHLIB_EXT],',
            '}',
            'dependencies = [',
            '   ("Java", "1.7.80"),'
            '   ("Perl", "5.22.0"),'
            '   ("Python", "2.7.10"),'
            '   ("R", "3.2.3"),'
            ']',
            'modloadmsg = "%s"' % '; '.join([
                'Java: %%(javaver)s, %%(javashortver)s',
                'Python: %%(pyver)s, %%(pyshortver)s',
                'Perl: %%(perlver)s, %%(perlshortver)s',
                'R: %%(rver)s, %%(rshortver)s',
            ]),
            'license_file = HOME + "/licenses/PI/license.txt"',
        ]) % inp
        self.prep()
        eb = EasyConfig(self.eb_file, validate=False)
        eb.validate()
        eb.generate_template_values()

        self.assertEqual(eb['description'], "test easyconfig PI")
        const_dict = dict([(x[0], x[1]) for x in easyconfig.templates.TEMPLATE_CONSTANTS])
        self.assertEqual(eb['sources'][0], const_dict['SOURCE_TAR_GZ'] % inp)
        self.assertEqual(eb['sources'][1][0], const_dict['SOURCELOWER_TAR_GZ'] % inp)
        self.assertEqual(eb['sources'][1][1], 'tar xfvz %s')
        self.assertEqual(eb['source_urls'][0], const_dict['GOOGLECODE_SOURCE'] % inp)
        self.assertEqual(eb['versionsuffix'], '-Python-2.7.10')
        self.assertEqual(eb['sanity_check_paths']['files'][0], 'lib/python2.7/site-packages')
        self.assertEqual(eb['sanity_check_paths']['dirs'][0], 'libfoo.%s' % get_shared_lib_ext())
        self.assertEqual(eb['homepage'], "http://example.com/P/p")
        self.assertEqual(eb['modloadmsg'], "Java: 1.7.80, 1.7; Python: 2.7.10, 2.7; Perl: 5.22.0, 5.22; R: 3.2.3, 3.2")
        self.assertEqual(eb['license_file'], os.path.join(os.environ['HOME'], 'licenses', 'PI', 'license.txt'))

        # test the escaping insanity here (ie all the crap we allow in easyconfigs)
        eb['description'] = "test easyconfig % %% %s% %%% %(name)s %%(name)s %%%(name)s %%%%(name)s"
        self.assertEqual(eb['description'], "test easyconfig % %% %s% %%% PI %(name)s %PI %%(name)s")

    def test_templating_doc(self):
        """test templating documentation"""
        doc = easyconfig.templates.template_documentation()
        # expected length: 1 per constant and 1 extra per constantgroup
        temps = [
            easyconfig.templates.TEMPLATE_NAMES_EASYCONFIG,
            easyconfig.templates.TEMPLATE_SOFTWARE_VERSIONS * 2,
            easyconfig.templates.TEMPLATE_NAMES_CONFIG,
            easyconfig.templates.TEMPLATE_NAMES_LOWER,
            easyconfig.templates.TEMPLATE_NAMES_EASYBLOCK_RUN_STEP,
            easyconfig.templates.TEMPLATE_CONSTANTS,
        ]
        self.assertEqual(len(doc.split('\n')), sum([len(temps)] + [len(x) for x in temps]))

    def test_constant_doc(self):
        """test constant documentation"""
        doc = easyconfig.constants.constant_documentation()
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
            'toolchain = {"name":"dummy", "version": "dummy"}',
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
        buildopts = ['CC=foo' , 'CC=bar']
        installopts = ['FOO=foo' , 'BAR=bar']
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
            'toolchain = {"name": "dummy", "version": "dummy"}',
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
            ('gzip-1.4.eb', 'gzip.eb', {'version': '1.4', 'toolchain': {'name': 'dummy', 'version': 'dummy'}}),
            ('gzip-1.4-GCC-4.6.3.eb', 'gzip.eb', {'version': '1.4', 'toolchain': {'name': 'GCC', 'version': '4.6.3'}}),
            ('gzip-1.5-goolf-1.4.10.eb', 'gzip.eb',
             {'version': '1.5', 'toolchain': {'name': 'goolf', 'version': '1.4.10'}}),
            ('gzip-1.5-ictce-4.1.13.eb', 'gzip.eb',
             {'version': '1.5', 'toolchain': {'name': 'ictce', 'version': '4.1.13'}}),
        ]:
            ec1 = EasyConfig(os.path.join(easyconfigs_path, 'v1.0', eb_file1), validate=False)
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
        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs')
        toy_ec_file = os.path.join(test_ecs_dir, 'toy-0.0.eb')

        for ec_file, correct_name, correct_easyblock in [
            (toy_ec_file, 'toy', None),
            (os.path.join(test_ecs_dir, 'goolf-1.4.10.eb'), 'goolf', 'Toolchain'),
        ]:
            name, easyblock = fetch_parameters_from_easyconfig(read_file(ec_file), ['name', 'easyblock'])
            self.assertEqual(name, correct_name)
            self.assertEqual(easyblock, correct_easyblock)

        self.assertEqual(fetch_parameters_from_easyconfig(read_file(toy_ec_file), ['description'])[0], "Toy C program.")

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

        self.assertEqual(get_easyblock_class(None, name='gzip', default_fallback=False), None)
        self.assertEqual(get_easyblock_class(None, name='toy'), EB_toy)
        self.assertErrorRegex(EasyBuildError, "Failed to import EB_TOY", get_easyblock_class, None, name='TOY')
        self.assertEqual(get_easyblock_class(None, name='TOY', error_on_failed_import=False), None)

    def test_easyconfig_paths(self):
        """Test create_paths function."""
        cand_paths = create_paths("/some/path", "Foo", "1.2.3")
        expected_paths = [
            "/some/path/Foo/1.2.3.eb",
            "/some/path/Foo/Foo-1.2.3.eb",
            "/some/path/f/Foo/Foo-1.2.3.eb",
            "/some/path/Foo-1.2.3.eb",
        ]
        self.assertEqual(cand_paths, expected_paths)

    def test_toolchain_inspection(self):
        """Test whether available toolchain inspection functionality is working."""
        build_options = {
            'robot_path': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs'),
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)

        ec = EasyConfig(os.path.join(os.path.dirname(__file__), 'easyconfigs', 'gzip-1.5-goolf-1.4.10.eb'))
        self.assertEqual(['/'.join([x['name'], x['version']]) for x in det_toolchain_compilers(ec)], ['GCC/4.7.2'])
        self.assertEqual(det_toolchain_mpi(ec)['name'], 'OpenMPI')

        ec = EasyConfig(os.path.join(os.path.dirname(__file__), 'easyconfigs', 'hwloc-1.6.2-GCC-4.6.4.eb'))
        tc_comps = det_toolchain_compilers(ec)
        self.assertEqual(['/'.join([x['name'], x['version']]) for x in tc_comps], ['GCC/4.6.4'])
        self.assertEqual(det_toolchain_mpi(ec), None)

        ec = EasyConfig(os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb'))
        self.assertEqual(det_toolchain_compilers(ec), None)
        self.assertEqual(det_toolchain_mpi(ec), None)

    def test_filter_deps(self):
        """Test filtered dependencies."""
        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs')
        ec_file = os.path.join(test_ecs_dir, 'goolf-1.4.10.eb')
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

    def test_replaced_easyconfig_parameters(self):
        """Test handling of replaced easyconfig parameters."""
        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs')
        ec = EasyConfig(os.path.join(test_ecs_dir, 'toy-0.0.eb'))
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

        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs')
        ec = EasyConfig(os.path.join(test_ecs_dir, 'toy-0.0.eb'))

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
            'toolchain = {"name": "dummy", "version": "dummy"}',
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
        ectxt = read_file(os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0-deps.eb'))
        toy_ec = os.path.join(self.test_prefix, 'toy-0.0-external-deps.eb')

        # just specify some of the test modules we ship, doesn't matter where they come from
        ectxt += "\ndependencies += ["
        ectxt += "  ('foobar/1.2.3', EXTERNAL_MODULE), "
        ectxt += "  ('test/9.7.5', EXTERNAL_MODULE), "
        ectxt += "  ('pi/3.14', EXTERNAL_MODULE), "
        ectxt += "  ('hidden/.1.2.3', EXTERNAL_MODULE), "
        ectxt += "]"
        ectxt += "\nbuilddependencies = [('somebuilddep/0.1', EXTERNAL_MODULE)]"
        ectxt += "\ntoolchain = {'name': 'GCC', 'version': '4.7.2'}"
        write_file(toy_ec, ectxt)

        ec = EasyConfig(toy_ec)

        builddeps = ec.builddependencies()
        self.assertEqual(len(builddeps), 1)
        self.assertEqual(builddeps[0]['short_mod_name'], 'somebuilddep/0.1')
        self.assertEqual(builddeps[0]['full_mod_name'], 'somebuilddep/0.1')
        self.assertEqual(builddeps[0]['external_module'], True)

        deps = ec.dependencies()
        self.assertEqual(len(deps), 7)
        correct_deps = ['ictce/4.1.13', 'GCC/4.7.2', 'foobar/1.2.3', 'test/9.7.5', 'pi/3.14', 'hidden/.1.2.3',
                        'somebuilddep/0.1']
        self.assertEqual([d['short_mod_name'] for d in deps], correct_deps)
        self.assertEqual([d['full_mod_name'] for d in deps], correct_deps)
        self.assertEqual([d['external_module'] for d in deps], [False, True, True, True, True, True, True])
        self.assertEqual([d['hidden'] for d in deps], [False, False, False, False, False, True, False])

        metadata = os.path.join(self.test_prefix, 'external_modules_metadata.cfg')
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
        ])
        write_file(metadata, metadatatxt)
        build_options = {
            'external_modules_metadata': parse_external_modules_metadata([metadata]),
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)
        ec = EasyConfig(toy_ec)
        self.assertEqual(ec.dependencies()[2]['short_mod_name'], 'foobar/1.2.3')
        self.assertEqual(ec.dependencies()[2]['external_module'], True)
        metadata = {
            'name': ['foo', 'bar'],
            'version': ['1.2.3', '3.2.1'],
            'prefix': '/foo/bar',
        }
        self.assertEqual(ec.dependencies()[2]['external_module_metadata'], metadata)

        self.assertEqual(ec.dependencies()[3]['short_mod_name'], 'test/9.7.5')
        self.assertEqual(ec.dependencies()[3]['external_module'], True)
        metadata = {
            'name': ['test'],
            'version': ['9.7.5'],
            'prefix': 'TEST_INC/..',
        }
        self.assertEqual(ec.dependencies()[3]['external_module_metadata'], metadata)

        self.assertEqual(ec.dependencies()[4]['short_mod_name'], 'pi/3.14')
        self.assertEqual(ec.dependencies()[4]['external_module'], True)
        metadata = {
            'name': ['PI'],
            'version': ['3.14'],
            'prefix': 'PI_PREFIX',
        }
        self.assertEqual(ec.dependencies()[4]['external_module_metadata'], metadata)

        # check whether $EBROOT*/$EBVERSION* environment variables are defined correctly for external modules
        os.environ['PI_PREFIX'] = '/test/prefix/PI'
        os.environ['TEST_INC'] = '/test/prefix/test/include'
        ec.toolchain.dry_run = True
        ec.toolchain.add_dependencies(ec.dependencies())
        ec.toolchain.prepare(silent=True)

        self.assertEqual(os.environ.get('EBROOTBAR'), '/foo/bar')
        self.assertEqual(os.environ.get('EBROOTFOO'), '/foo/bar')
        self.assertEqual(os.environ.get('EBROOTHIDDEN'), None)
        self.assertEqual(os.environ.get('EBROOTPI'), '/test/prefix/PI')
        self.assertEqual(os.environ.get('EBROOTTEST'), '/test/prefix/test/include/../')
        self.assertEqual(os.environ.get('EBVERSIONBAR'), '3.2.1')
        self.assertEqual(os.environ.get('EBVERSIONFOO'), '1.2.3')
        self.assertEqual(os.environ.get('EBVERSIONHIDDEN'), None)
        self.assertEqual(os.environ.get('EBVERSIONPI'), '3.14')
        self.assertEqual(os.environ.get('EBVERSIONTEST'), '9.7.5')

    def test_update(self):
        """Test use of update() method for EasyConfig instances."""
        toy_ebfile = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'toy-0.0.eb')
        ec = EasyConfig(toy_ebfile)

        # for string values: append
        ec.update('unpack_options', '--strip-components=1')
        self.assertEqual(ec['unpack_options'].strip(), '--strip-components=1')

        ec.update('description', "- just a test")
        self.assertEqual(ec['description'].strip(), "Toy C program. - just a test")

        # spaces in between multiple updates for stirng values
        ec.update('configopts', 'CC="$CC"')
        ec.update('configopts', 'CXX="$CXX"')
        self.assertTrue(ec['configopts'].strip().endswith('CC="$CC"  CXX="$CXX"'))

        # for list values: extend
        ec.update('patches', ['foo.patch', 'bar.patch'])
        self.assertEqual(ec['patches'], ['toy-0.0_typo.patch', ('toy-extra.txt', 'toy-0.0'), 'foo.patch', 'bar.patch'])

    def test_hide_hidden_deps(self):
        """Test use of --hide-deps on hiddendependencies."""
        test_dir = os.path.dirname(os.path.abspath(__file__))
        ec_file = os.path.join(test_dir, 'easyconfigs', 'gzip-1.4-GCC-4.6.3.eb')
        ec = EasyConfig(ec_file)
        self.assertEqual(ec['hiddendependencies'][0]['full_mod_name'], 'toy/.0.0-deps')
        self.assertEqual(ec['dependencies'], [])

        build_options = {
            'hide_deps': ['toy'],
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)
        ec = EasyConfig(ec_file)
        self.assertEqual(ec['hiddendependencies'][0]['full_mod_name'], 'toy/.0.0-deps')
        self.assertEqual(ec['dependencies'], [])

    def test_quote_str(self):
        """Test quote_str function."""
        teststrings = {
            'foo' : '"foo"',
            'foo\'bar' : '"foo\'bar"',
            'foo\'bar"baz' : '"""foo\'bar"baz"""',
            "foo'bar\"baz" : '"""foo\'bar"baz"""',
            "foo\nbar" : '"foo\nbar"',
            'foo bar' : '"foo bar"'
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

        # non-string values
        n = 42
        self.assertEqual(quote_str(n), 42)
        self.assertEqual(quote_str(["foo", "bar"]), ["foo", "bar"])
        self.assertEqual(quote_str(('foo', 'bar')), ('foo', 'bar'))

    def test_dump(self):
        """Test EasyConfig's dump() method."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        ecfiles = [
            'toy-0.0.eb',
            'goolf-1.4.10.eb',
            'ScaLAPACK-2.0.2-gompi-1.4.10-OpenBLAS-0.2.6-LAPACK-3.4.2.eb',
            'gzip-1.4-GCC-4.6.3.eb',
        ]
        for ecfile in ecfiles:
            test_ec = os.path.join(self.test_prefix, 'test.eb')

            ec = EasyConfig(os.path.join(test_ecs_dir, ecfile))
            ecdict = ec.asdict()
            ec.dump(test_ec)
            # dict representation of EasyConfig instance should not change after dump
            self.assertEqual(ecdict, ec.asdict())
            ectxt = read_file(test_ec)

            patterns = [r"^name = ['\"]", r"^version = ['0-9\.]", r'^description = ["\']']
            for pattern in patterns:
                regex = re.compile(pattern, re.M)
                self.assertTrue(regex.search(ectxt), "Pattern '%s' found in: %s" % (regex.pattern, ectxt))

            # parse result again
            dumped_ec = EasyConfig(test_ec)

            # check that selected parameters still have the same value
            params = [
                'name',
                'toolchain',
                'dependencies',  # checking this is important w.r.t. filtered hidden dependencies being restored in dump
            ]
            for param in params:
                self.assertEqual(ec[param], dumped_ec[param])

    def test_dump_autopep8(self):
        """Test dump() with autopep8 usage enabled (only if autopep8 is available)."""
        try:
            import autopep8
            os.environ['EASYBUILD_DUMP_AUTOPEP8'] = '1'
            init_config()
            self.test_dump()
            del os.environ['EASYBUILD_DUMP_AUTOPEP8']
        except ImportError:
            print "Skipping test_dump_autopep8, since autopep8 is not available"

    def test_dump_extra(self):
        """Test EasyConfig's dump() method for files containing extra values"""
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
            "toolchain = {'version': 'dummy', 'name': 'dummy'}",
            '',
            "dependencies = [",
            "    ('GCC', '4.6.4', '-test'),",
            "    ('MPICH', '1.8', '', ('GCC', '4.6.4')),",
            "    ('bar', '1.0'),",
            "    ('foobar/1.2.3', EXTERNAL_MODULE),",
            "]",
            '',
            "foo_extra1 = 'foobar'",
        ])

        handle, testec = tempfile.mkstemp(prefix=self.test_prefix, suffix='.eb')
        os.close(handle)

        ec = EasyConfig(None, rawtxt=rawtxt)
        ec.dump(testec)
        ectxt = read_file(testec)
        self.assertEqual(rawtxt, ectxt)

        dumped_ec = EasyConfig(testec)

    def test_dump_template(self):
        """ Test EasyConfig's dump() method for files containing templates"""
        rawtxt = '\n'.join([
            "easyblock = 'EB_foo'",
            '',
            "name = 'Foo'",
            "version = '0.0.1'",
            "versionsuffix = '-test'",
            '',
            "homepage = 'http://foo.com/'",
            'description = "foo description"',
            '',
            "toolchain = {",
            "    'version': 'dummy',",
            "    'name': 'dummy',",
            '}',
            '',
            "sources = [",
            "    'foo-0.0.1.tar.gz',",
            ']',
            '',
            "dependencies = [",
            "    ('bar', '1.2.3', '-test'),",
            ']',
            '',
            "preconfigopts = '--opt1=%s' % name",
            "configopts = '--opt2=0.0.1'",
            '',
            "sanity_check_paths = {",
            "    'files': ['files/foo/foobar', 'files/x-test'],",
            "    'dirs':[],",
            '}',
            '',
            "foo_extra1 = 'foobar'"
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
            r"version = '0.0.1'",
            r"versionsuffix = '-test'",
            r"homepage = 'http://foo.com/'",
            r'description = "foo description"',  # no templating for description
            r"sources = \[SOURCELOWER_TAR_GZ\]",
            # use of templates in *dependencies is disabled for now, since it can cause problems
            #r"dependencies = \[\n    \('bar', '1.2.3', '%\(versionsuffix\)s'\),\n\]",
            r"preconfigopts = '--opt1=%\(name\)s'",
            r"configopts = '--opt2=%\(version\)s'",
            r"sanity_check_paths = {\n    'files': \['files/%\(namelower\)s/foobar', 'files/x-test'\]",
        ]

        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(ectxt), "Pattern '%s' found in: %s" % (regex.pattern, ectxt))

        # reparsing the dumped easyconfig file should work
        ecbis = EasyConfig(testec)

    def test_dump_comments(self):
        """ Test dump() method for files containing comments """
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
            "    'version': 'dummy',",
            "    'name': 'dummy'",
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
        ec.dump(testec)
        ectxt = read_file(testec)

        patterns = [
            r"# #\n# some header comment\n# #",
            r"name = 'Foo'  # name comment",
            r"# comment on the homepage\nhomepage = 'http://foo.com/'",
            r'description = "foo description with a # in it"  # test',
            r"# toolchain comment\ntoolchain = {",
            r"    'files': \['files/foobar'\],  # comment on files",
            r"    'dirs': \[\],",
        ]

        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(ectxt), "Pattern '%s' found in: %s" % (regex.pattern, ectxt))

        self.assertTrue(ectxt.endswith("# trailing comment"))

        # reparsing the dumped easyconfig file should work
        ecbis = EasyConfig(testec)

    def test_to_template_str(self):
        """ Test for to_template_str method """

        # reverse dict of known template constants; template values (which are keys here) must be 'string-in-string
        templ_const = {
            "template":'TEMPLATE_VALUE',
            "%(name)s-%(version)s": 'NAME_VERSION',
        }

        templ_val = {
            'foo':'name',
            '0.0.1':'version',
            '-test':'special_char',
        }

        self.assertEqual(to_template_str("template", templ_const, templ_val), 'TEMPLATE_VALUE')
        self.assertEqual(to_template_str("foo/bar/0.0.1/", templ_const, templ_val), "%(name)s/bar/%(version)s/")
        self.assertEqual(to_template_str("foo-0.0.1", templ_const, templ_val), 'NAME_VERSION')
        templ_list = to_template_str("['-test', 'dontreplacenamehere']", templ_const, templ_val)
        self.assertEqual(templ_list, "['%(special_char)s', 'dontreplacenamehere']")
        templ_dict = to_template_str("{'a': 'foo', 'b': 'notemplate'}", templ_const, templ_val)
        self.assertEqual(templ_dict, "{'a': '%(name)s', 'b': 'notemplate'}")
        self.assertEqual(to_template_str("('foo', '0.0.1')", templ_const, templ_val), "('%(name)s', '%(version)s')")

    def test_dep_graph(self):
        """Test for dep_graph."""
        try:
            import pygraph

            test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
            build_options = {
                'external_modules_metadata': ConfigObj(),
                'valid_module_classes': module_classes(),
                'robot_path': [test_easyconfigs],
                'silent': True,
            }
            init_config(build_options=build_options)

            ec_file = os.path.join(test_easyconfigs, 'toy-0.0-deps.eb')
            ec_files = [(ec_file, False)]
            ecs, _ = parse_easyconfigs(ec_files)

            dot_file = os.path.join(self.test_prefix, 'test.dot')
            ordered_ecs = resolve_dependencies(ecs, self.modtool, retain_all_deps=True)
            dep_graph(dot_file, ordered_ecs)

            # hard check for expect .dot file contents
            # 3 nodes should be there: 'GCC/4.7.2 (EXT)', 'toy', and 'ictce/4.1.13'
            # and 2 edges: 'toy -> ictce' and 'toy -> "GCC/4.7.2 (EXT)"'
            dottxt = read_file(dot_file)
            self.assertEqual(dottxt, EXPECTED_DOTTXT_TOY_DEPS)

        except ImportError:
            print "Skipping test_dep_graph, since pygraph is not available"

    def test_ActiveMNS_det_full_module_name(self):
        """Test det_full_module_name method of ActiveMNS."""
        build_options = {
            'valid_module_classes': module_classes(),
            'external_modules_metadata': ConfigObj(),
        }

        init_config(build_options=build_options)
        ec_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'toy-0.0-deps.eb')
        ec = EasyConfig(ec_file)

        self.assertEqual(ActiveMNS().det_full_module_name(ec), 'toy/0.0-deps')
        self.assertEqual(ActiveMNS().det_full_module_name(ec['dependencies'][0]), 'ictce/4.1.13')
        self.assertEqual(ActiveMNS().det_full_module_name(ec['dependencies'][1]), 'GCC/4.7.2')

        ec_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'gzip-1.4-GCC-4.6.3.eb')
        ec = EasyConfig(ec_file)
        hiddendep = ec['hiddendependencies'][0]
        self.assertEqual(ActiveMNS().det_full_module_name(hiddendep), 'toy/.0.0-deps')
        self.assertEqual(ActiveMNS().det_full_module_name(hiddendep, force_visible=True), 'toy/0.0-deps')

    def test_find_related_easyconfigs(self):
        """Test find_related_easyconfigs function."""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        ec_file = os.path.join(test_easyconfigs, 'GCC-4.6.3.eb')
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
        expected = ['GCC-4.6.3.eb', 'GCC-4.6.4.eb', 'GCC-4.7.2.eb', 'GCC-4.8.2.eb', 'GCC-4.8.3.eb', 'GCC-4.9.2.eb']
        self.assertEqual(res, expected)

        ec_file = os.path.join(test_easyconfigs, 'toy-0.0-deps.eb')
        ec = EasyConfig(ec_file)

        # exact match
        res = [os.path.basename(x) for x in find_related_easyconfigs(test_easyconfigs, ec)]
        self.assertEqual(res, ['toy-0.0-deps.eb'])

        # tweak toolchain name/version and versionsuffix => closest match with same toolchain name is found
        ec['toolchain'] = {'name': 'gompi', 'version': '1.5.16'}
        ec['versionsuffix'] = '-foobar'
        res = [os.path.basename(x) for x in find_related_easyconfigs(test_easyconfigs, ec)]
        self.assertEqual(res, ['toy-0.0-gompi-1.3.12-test.eb'])

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
        ec_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'toy-0.0-deps.eb')
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
        ec_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'toy-0.0.eb')
        ec = EasyConfig(ec_file)
        ec.validate_license()
        self.assertEqual(ec['software_license'], None)
        self.assertEqual(ec.software_license, None)

        # specified software license gets handled correctly
        ec_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'gzip-1.4.eb')
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
        ec_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'gzip-1.4-broken.eb')
        # version parameter has values of wrong type in this broken easyconfig
        error_msg_pattern = "Type checking of easyconfig parameter values failed: .*'version'.*"
        self.assertErrorRegex(EasyBuildError, error_msg_pattern, EasyConfig, ec_file, auto_convert_value_types=False)

        # test default behaviour: auto-converting of mismatching value types
        ec = EasyConfig(ec_file)
        self.assertEqual(ec['version'], '1.4')

    def test_eq_hash(self):
        """Test comparing two EasyConfig instances."""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        ec1 = EasyConfig(os.path.join(test_easyconfigs, 'toy-0.0.eb'))
        ec2 = EasyConfig(os.path.join(test_easyconfigs, 'toy-0.0.eb'))

        # different instances, same parsed easyconfig
        self.assertFalse(ec1 is ec2)
        self.assertEqual(ec1, ec2)
        self.assertTrue(ec1 == ec2)
        self.assertFalse(ec1 != ec2)

        # hashes should also be identical
        self.assertEqual(hash(ec1), hash(ec2))

        # other parsed easyconfig is not equal
        ec3 = EasyConfig(os.path.join(test_easyconfigs, 'gzip-1.4.eb'))
        self.assertFalse(ec1 == ec3)
        self.assertTrue(ec1 != ec3)

    def test_copy_easyconfigs(self):
        """Test copy_easyconfigs function."""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')

        target_dir = os.path.join(self.test_prefix, 'copied_ecs')
        # easybuild/easyconfigs subdir is expected to exist
        ecs_target_dir = os.path.join(target_dir, 'easybuild', 'easyconfigs')
        mkdir(ecs_target_dir, parents=True)

        # passing an empty list of paths is fine
        res = copy_easyconfigs([], target_dir)
        self.assertEqual(res, {'ecs': [], 'new': [], 'paths_in_repo': []})
        self.assertEqual(os.listdir(os.path.join(target_dir, 'easybuild', 'easyconfigs')), [])

        # copy test easyconfigs, purposely under a different name
        test_ecs = [
            ('GCC-4.6.3.eb', 'GCC.eb'),
            ('OpenMPI-1.6.4-GCC-4.6.4.eb', 'openmpi164.eb'),
            ('toy-0.0-gompi-1.3.12-test.eb', 'foo.eb'),
        ]
        ecs_to_copy = []
        for (src_ec, target_ec) in test_ecs:
            ecs_to_copy.append(os.path.join(self.test_prefix, target_ec))
            shutil.copy2(os.path.join(test_ecs_dir, src_ec), ecs_to_copy[-1])

        copy_easyconfigs(ecs_to_copy, target_dir)

        # check whether easyconfigs were copied (unmodified) to correct location
        for orig_ec, src_ec in test_ecs:
            copied_ec = os.path.join(ecs_target_dir, orig_ec[0].lower(), orig_ec.split('-')[0], orig_ec)
            self.assertTrue(os.path.exists(copied_ec), "File %s exists" % copied_ec)
            self.assertEqual(read_file(copied_ec), read_file(os.path.join(self.test_prefix, src_ec)))


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(EasyConfigTest)


if __name__ == '__main__':
    # also check the setUp for debug
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
