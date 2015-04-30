# #
# Copyright 2012-2015 Ghent University
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
from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.framework.easyconfig.easyconfig import create_paths
from easybuild.framework.easyconfig.easyconfig import get_easyblock_class
from easybuild.framework.easyconfig.parser import fetch_parameters_from_easyconfig
from easybuild.framework.easyconfig.tweak import obtain_ec_for, tweak_one
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import module_classes
from easybuild.tools.configobj import ConfigObj
from easybuild.tools.filetools import read_file, write_file
from easybuild.tools.module_naming_scheme.toolchain import det_toolchain_compilers, det_toolchain_mpi
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.systemtools import get_shared_lib_ext
from test.framework.utilities import find_full_path


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
            '           "787393bfc465c85607a5b24486e861c5",',  # MD5 checksum for source (gzip-1.4.eb)
            '           "ddd5161154f5db67701525123129ff09",',  # MD5 checksum for patch (toy-0.0.eb)
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
            'toolchain = {"name":"GCC", "version": "4.6.3"}',
            'patches = %s',
        ]) % str(patches)
        self.prep()

        ver = "1.2.3"
        verpref = "myprefix"
        versuff = "mysuffix"
        tcname = "mytc"
        tcver = "4.1.2"
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
            'dependencies': [('foo', '1.2.3'), ('bar', '666', '-bleh', ('gompi', '1.4.10'))],
            'hiddendependencies': [('test', '3.2.1')],
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
                'hidden': True,
                'external_module': False,
                'external_module_metadata': {},
            },
        ]

        # hidden dependencies must be included in list of dependencies
        res = obtain_ec_for(specs, [self.ec_dir], None)
        self.assertEqual(res[0], True)
        error_pattern = "Hidden dependencies with visible module names .* not in list of dependencies: .*"
        self.assertErrorRegex(EasyBuildError, error_pattern, EasyConfig, res[1])

        specs['dependencies'].append(('test', '3.2.1'))

        res = obtain_ec_for(specs, [self.ec_dir], None)
        self.assertEqual(res[0], True)
        ec = EasyConfig(res[1])
        self.assertEqual(ec['patches'], specs['patches'])
        self.assertEqual(ec.dependencies(), parsed_deps)

        # hidden dependencies are filtered from list of dependencies
        self.assertFalse('test/3.2.1-GCC-4.4.5' in [d['full_mod_name'] for d in ec['dependencies']])
        self.assertTrue('test/.3.2.1-GCC-4.4.5' in [d['full_mod_name'] for d in ec['hiddendependencies']])
        os.remove(res[1])

        # hidden dependencies are also filtered from list of dependencies when validation is skipped
        res = obtain_ec_for(specs, [self.ec_dir], None)
        ec = EasyConfig(res[1], validate=False)
        self.assertFalse('test/3.2.1-GCC-4.4.5' in [d['full_mod_name'] for d in ec['dependencies']])
        self.assertTrue('test/.3.2.1-GCC-4.4.5' in [d['full_mod_name'] for d in ec['hiddendependencies']])
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
            'homepage = "http://example.com/%%(nameletter)s/%%(nameletterlower)s"',
            'description = "test easyconfig %%(name)s"',
            'toolchain = {"name":"dummy", "version": "dummy2"}',
            'source_urls = [(GOOGLECODE_SOURCE)]',
            'sources = [SOURCE_TAR_GZ, (SOURCELOWER_TAR_GZ, "%(cmd)s")]',
            'sanity_check_paths = {"files": [], "dirs": ["libfoo.%%s" %% SHLIB_EXT]}',
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
        self.assertEqual(eb['sanity_check_paths']['dirs'][0], 'libfoo.%s' % get_shared_lib_ext())
        self.assertEqual(eb['homepage'], "http://example.com/P/p")

        # test the escaping insanity here (ie all the crap we allow in easyconfigs)
        eb['description'] = "test easyconfig % %% %s% %%% %(name)s %%(name)s %%%(name)s %%%%(name)s"
        self.assertEqual(eb['description'], "test easyconfig % %% %s% %%% PI %(name)s %PI %%(name)s")

    def test_templating_doc(self):
        """test templating documentation"""
        doc = easyconfig.templates.template_documentation()
        # expected length: 1 per constant and 1 extra per constantgroup
        temps = [
                 easyconfig.templates.TEMPLATE_NAMES_EASYCONFIG,
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
            ('gzip-1.5-goolf-1.4.10.eb', 'gzip.eb', {'version': '1.5', 'toolchain': {'name': 'goolf', 'version': '1.4.10'}}),
            ('gzip-1.5-ictce-4.1.13.eb', 'gzip.eb', {'version': '1.5', 'toolchain': {'name': 'ictce', 'version': '4.1.13'}}),
        ]:
            ec1 = EasyConfig(os.path.join(easyconfigs_path, 'v1.0', eb_file1), validate=False)
            ec2 = EasyConfig(os.path.join(easyconfigs_path, 'v2.0', eb_file2), validate=False, build_specs=specs)

            ec2_dict = ec2.asdict()
            # reset mandatory attributes from format2 that are not in format 1
            for attr in ['docurls', 'software_license', 'software_license_urls']:
                ec2_dict[attr] = None

            self.assertEqual(ec1.asdict(), ec2_dict)

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
        ectxt += "\ndependencies += [('foobar/1.2.3', EXTERNAL_MODULE)]"
        ectxt += "\nbuilddependencies = [('somebuilddep/0.1', EXTERNAL_MODULE)]"
        write_file(toy_ec, ectxt)

        build_options = {
            'valid_module_classes': module_classes(),
            'external_modules_metadata': ConfigObj(),
        }
        init_config(build_options=build_options)
        ec = EasyConfig(toy_ec)

        builddeps = ec.builddependencies()
        self.assertEqual(len(builddeps), 1)
        self.assertEqual(builddeps[0]['short_mod_name'], 'somebuilddep/0.1')
        self.assertEqual(builddeps[0]['full_mod_name'], 'somebuilddep/0.1')
        self.assertEqual(builddeps[0]['external_module'], True)

        deps = ec.dependencies()
        self.assertEqual(len(deps), 3)
        self.assertEqual([d['short_mod_name'] for d in deps], ['ictce/4.1.13', 'foobar/1.2.3', 'somebuilddep/0.1'])
        self.assertEqual([d['full_mod_name'] for d in deps], ['ictce/4.1.13', 'foobar/1.2.3', 'somebuilddep/0.1'])
        self.assertEqual([d['external_module'] for d in deps], [False, True, True])

        metadata = os.path.join(self.test_prefix, 'external_modules_metadata.cfg')
        metadatatxt = '\n'.join(['[foobar/1.2.3]', 'name = foo,bar', 'version = 1.2.3,3.2.1', 'prefix = /foo/bar'])
        write_file(metadata, metadatatxt)
        cfg = init_config(args=['--external-modules-metadata=%s' % metadata])
        build_options = {
            'external_modules_metadata': cfg.external_modules_metadata,
            'valid_module_classes': module_classes(),
        }
        init_config(build_options=build_options)
        ec = EasyConfig(toy_ec)
        self.assertEqual(ec.dependencies()[1]['short_mod_name'], 'foobar/1.2.3')
        self.assertEqual(ec.dependencies()[1]['external_module'], True)
        metadata = {
            'name': ['foo', 'bar'],
            'version': ['1.2.3', '3.2.1'],
            'prefix': '/foo/bar',
        }
        self.assertEqual(ec.dependencies()[1]['external_module_metadata'], metadata)

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
        self.assertEqual(ec['patches'], ['toy-0.0_typo.patch', 'foo.patch', 'bar.patch'])


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(EasyConfigTest)


if __name__ == '__main__':
    # also check the setUp for debug
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
