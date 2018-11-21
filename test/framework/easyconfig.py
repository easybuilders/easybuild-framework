# #
# Copyright 2012-2018 Ghent University
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
from distutils.version import LooseVersion
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner
from vsc.utils.fancylogger import setLogLevelDebug, logToScreen

import easybuild.tools.build_log
import easybuild.framework.easyconfig as easyconfig
from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig.constants import EXTERNAL_MODULE_MARKER
from easybuild.framework.easyconfig.easyconfig import ActiveMNS, EasyConfig, create_paths, copy_easyconfigs
from easybuild.framework.easyconfig.easyconfig import get_easyblock_class, get_module_path, letter_dir_for
from easybuild.framework.easyconfig.easyconfig import process_easyconfig, resolve_template
from easybuild.framework.easyconfig.easyconfig import det_subtoolchain_version, verify_easyconfig_filename
from easybuild.framework.easyconfig.licenses import License, LicenseGPLv3
from easybuild.framework.easyconfig.parser import fetch_parameters_from_easyconfig
from easybuild.framework.easyconfig.templates import template_constant_dict, to_template_str
from easybuild.framework.easyconfig.tools import categorize_files_by_type, check_sha256_checksums, dep_graph
from easybuild.framework.easyconfig.tools import find_related_easyconfigs, get_paths_for, parse_easyconfigs
from easybuild.framework.easyconfig.tweak import obtain_ec_for, tweak_one
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import module_classes
from easybuild.tools.configobj import ConfigObj
from easybuild.tools.docs import avail_easyconfig_constants, avail_easyconfig_templates
from easybuild.tools.filetools import adjust_permissions, copy_file, mkdir, read_file, remove_file, symlink
from easybuild.tools.filetools import which, write_file
from easybuild.tools.module_naming_scheme.toolchain import det_toolchain_compilers, det_toolchain_mpi
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.options import parse_external_modules_metadata
from easybuild.tools.robot import resolve_dependencies
from easybuild.tools.systemtools import get_shared_lib_ext
from easybuild.tools.toolchain.utilities import search_toolchain
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
        error_pattern = "Parsing easyconfig file failed: EOL while scanning string literal"
        self.assertErrorRegex(EasyBuildError, error_pattern, EasyConfig, self.eb_file)

        # introduce "TypeError: format requires mapping" issue"
        self.contents = self.contents.replace("syntax_error'", "foo = '%(name)s %s' % version")
        self.prep()
        error_pattern = "Parsing easyconfig file failed: format requires a mapping \(line 8\)"
        self.assertErrorRegex(EasyBuildError, error_pattern, EasyConfig, self.eb_file)

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
            'toolchain = {"name": "dummy", "version": "dummy"}',
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
            '           "6f281b6d7a3965476324a23b9d80232bd4ffe3967da85e4b7c01d9d81d649a09",',
                        # SHA256 checksum for 'patch' (toy-0.0.eb)
            '           "a79ba0ef5dceb5b8829268247feae8932bed2034c6628ff1d92c84bf45e9a546",',
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
            'checksums': ['6f281b6d7a3965476324a23b9d80232bd4ffe3967da85e4b7c01d9d81d649a09',
                          'a79ba0ef5dceb5b8829268247feae8932bed2034c6628ff1d92c84bf45e9a546'],
            'patches': ['toy-0.0.eb'],
            'source_tmpl': 'gzip-1.4.eb',
            'source_urls': [('http://example.com', 'suffix')],
        })

        modfile = os.path.join(eb.make_module_step(), 'pi', '3.14' + eb.module_generator.MODULE_FILE_EXTENSION)
        modtxt = read_file(modfile)
        regex = re.compile('EBEXTSLISTPI.*ext1-1.0,ext2-2.0')
        self.assertTrue(regex.search(modtxt), "Pattern '%s' found in: %s" % (regex.pattern, modtxt))

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

        remove_file(tweaked_fn)

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

        # only version key is strictly needed
        self.assertEqual(det_full_ec_version({'version': '1.2.3'}), '1.2.3')

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
        remove_file(res[1])

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
        remove_file(res[1])

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
                'toolchain_inherited': True,
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
                'toolchain_inherited': False,
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
                'toolchain_inherited': True,
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
                'toolchain_inherited': True,
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
        remove_file(res[1])

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
            'toolchain = {"name":"dummy", "version": "dummy2"}',
            'source_urls = [GOOGLECODE_SOURCE, GITHUB_SOURCE]',
            'sources = [SOURCE_TAR_GZ, (SOURCELOWER_TAR_BZ2, "%(cmd)s")]',
            'sanity_check_paths = {',
            '   "files": ["bin/pi_%%(version_major)s_%%(version_minor)s", "lib/python%%(pyshortver)s/site-packages"],',
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
            "github_account = 'easybuilders'",
        ]) % inp
        self.prep()
        eb = EasyConfig(self.eb_file, validate=False)
        eb.validate()

        # temporarily disable templating, just so we can check later whether it's *still* disabled
        eb.enable_templating = False

        eb.generate_template_values()

        self.assertFalse(eb.enable_templating)
        eb.enable_templating = True

        self.assertEqual(eb['description'], "test easyconfig PI")
        self.assertEqual(eb['sources'][0], 'PI-3.04.tar.gz')
        self.assertEqual(eb['sources'][1], ('pi-3.04.tar.bz2', "tar xfvz %s"))
        self.assertEqual(eb['source_urls'][0], 'http://pi.googlecode.com/files')
        self.assertEqual(eb['source_urls'][1], 'https://github.com/easybuilders/PI/archive')
        self.assertEqual(eb['versionsuffix'], '-Python-2.7.10')
        self.assertEqual(eb['sanity_check_paths']['files'][0], 'bin/pi_3_04')
        self.assertEqual(eb['sanity_check_paths']['files'][1], 'lib/python2.7/site-packages')
        self.assertEqual(eb['sanity_check_paths']['dirs'][0], 'libfoo.%s' % get_shared_lib_ext())
        self.assertEqual(eb['homepage'], "http://example.com/P/p/v3/")
        self.assertEqual(eb['modloadmsg'], "Java: 1.7.80, 1.7; Python: 2.7.10, 2.7; Perl: 5.22.0, 5.22; R: 3.2.3, 3.2")
        self.assertEqual(eb['license_file'], os.path.join(os.environ['HOME'], 'licenses', 'PI', 'license.txt'))

        # test the escaping insanity here (ie all the crap we allow in easyconfigs)
        eb['description'] = "test easyconfig % %% %s% %%% %(name)s %%(name)s %%%(name)s %%%%(name)s"
        self.assertEqual(eb['description'], "test easyconfig % %% %s% %%% PI %(name)s %PI %%(name)s")

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
            (os.path.join(test_ecs_dir, 'g', 'goolf', 'goolf-1.4.10.eb'), 'goolf', 'Toolchain'),
        ]:
            name, easyblock = fetch_parameters_from_easyconfig(read_file(ec_file), ['name', 'easyblock'])
            self.assertEqual(name, correct_name)
            self.assertEqual(easyblock, correct_easyblock)

        self.assertEqual(fetch_parameters_from_easyconfig(read_file(toy_ec_file), ['description'])[0], "Toy C program, 100% toy.")

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
        self.assertEqual(get_easyblock_class(None, name='gzip', default_fallback=False), None)
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

        ec = EasyConfig(os.path.join(test_ecs, 'g', 'gzip', 'gzip-1.5-goolf-1.4.10.eb'))
        self.assertEqual(['/'.join([x['name'], x['version']]) for x in det_toolchain_compilers(ec)], ['GCC/4.7.2'])
        self.assertEqual(det_toolchain_mpi(ec)['name'], 'OpenMPI')

        ec = EasyConfig(os.path.join(test_ecs, 'h', 'hwloc', 'hwloc-1.6.2-GCC-4.6.4.eb'))
        tc_comps = det_toolchain_compilers(ec)
        self.assertEqual(['/'.join([x['name'], x['version']]) for x in tc_comps], ['GCC/4.6.4'])
        self.assertEqual(det_toolchain_mpi(ec), None)

        ec = EasyConfig(os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb'))
        self.assertEqual(det_toolchain_compilers(ec), None)
        self.assertEqual(det_toolchain_mpi(ec), None)

    def test_filter_deps(self):
        """Test filtered dependencies."""
        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        ec_file = os.path.join(test_ecs_dir, 'g', 'goolf', 'goolf-1.4.10.eb')
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
        shutil.copy2(os.path.join(test_ecs_dir, 'o', 'OpenMPI', 'OpenMPI-1.6.4-GCC-4.6.4.eb'), ec_file)

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
        topdir = os.path.dirname(os.path.abspath(__file__))
        ectxt = read_file(os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-deps.eb'))
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
        topdir = os.path.abspath(os.path.dirname(__file__))
        toy_ebfile = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        ec = EasyConfig(toy_ebfile)

        # for string values: append
        ec.update('unpack_options', '--strip-components=1')
        self.assertEqual(ec['unpack_options'].strip(), '--strip-components=1')

        ec.update('description', "- just a test")
        self.assertEqual(ec['description'].strip(), "Toy C program, 100% toy. - just a test")

        # spaces in between multiple updates for stirng values
        ec.update('configopts', 'CC="$CC"')
        ec.update('configopts', 'CXX="$CXX"')
        self.assertTrue(ec['configopts'].strip().endswith('CC="$CC"  CXX="$CXX"'))

        # for list values: extend
        ec.update('patches', ['foo.patch', 'bar.patch'])
        toy_patch_fn = 'toy-0.0_fix-silly-typo-in-printf-statement.patch'
        self.assertEqual(ec['patches'], [toy_patch_fn, ('toy-extra.txt', 'toy-0.0'), 'foo.patch', 'bar.patch'])

    def test_hide_hidden_deps(self):
        """Test use of --hide-deps on hiddendependencies."""
        test_dir = os.path.dirname(os.path.abspath(__file__))
        ec_file = os.path.join(test_dir, 'easyconfigs', 'test_ecs', 'g', 'gzip', 'gzip-1.4-GCC-4.6.3.eb')
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
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        ecfiles = [
            't/toy/toy-0.0.eb',
            'g/goolf/goolf-1.4.10.eb',
            's/ScaLAPACK/ScaLAPACK-2.0.2-gompi-1.4.10-OpenBLAS-0.2.6-LAPACK-3.4.2.eb',
            'g/gzip/gzip-1.4-GCC-4.6.3.eb',
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
        topdir = os.path.dirname(os.path.abspath(__file__))
        ec_file = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-deps.eb')
        ec = EasyConfig(ec_file)

        self.assertEqual(ActiveMNS().det_full_module_name(ec), 'toy/0.0-deps')
        self.assertEqual(ActiveMNS().det_full_module_name(ec['dependencies'][0]), 'ictce/4.1.13')
        self.assertEqual(ActiveMNS().det_full_module_name(ec['dependencies'][1]), 'GCC/4.7.2')

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
        expected = ['GCC-4.6.3.eb', 'GCC-4.6.4.eb', 'GCC-4.7.2.eb', 'GCC-4.8.2.eb', 'GCC-4.8.3.eb', 'GCC-4.9.2.eb']
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
        self.assertEqual(res, ['toy-0.0-gompi-1.3.12-test.eb', 'toy-0.0-gompi-1.3.12.eb'])

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
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        ec1 = EasyConfig(os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb'))

        ec2 = ec1.copy()

        self.assertEqual(ec1, ec2)
        self.assertEqual(ec1.rawtxt, ec2.rawtxt)
        self.assertEqual(ec1.path, ec2.path)

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
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')

        target_dir = os.path.join(self.test_prefix, 'copied_ecs')
        # easybuild/easyconfigs subdir is expected to exist
        ecs_target_dir = os.path.join(target_dir, 'easybuild', 'easyconfigs')
        mkdir(ecs_target_dir, parents=True)

        # passing an empty list of paths is fine
        res = copy_easyconfigs([], target_dir)
        self.assertEqual(res, {'ecs': [], 'new': [], 'new_file_in_existing_folder': [],
                               'new_folder': [], 'paths_in_repo': []})
        self.assertEqual(os.listdir(ecs_target_dir), [])

        # copy test easyconfigs, purposely under a different name
        test_ecs = [
            ('g/GCC/GCC-4.6.3.eb', 'GCC.eb'),
            ('o/OpenMPI/OpenMPI-1.6.4-GCC-4.6.4.eb', 'openmpi164.eb'),
            ('t/toy/toy-0.0-gompi-1.3.12-test.eb', 'foo.eb'),
            ('t/toy/toy-0.0.eb', 'TOY.eb'),
        ]
        ecs_to_copy = []
        for (src_ec, target_ec) in test_ecs:
            ecs_to_copy.append(os.path.join(self.test_prefix, target_ec))
            shutil.copy2(os.path.join(test_ecs_dir, src_ec), ecs_to_copy[-1])

        res = copy_easyconfigs(ecs_to_copy, target_dir)
        self.assertEqual(sorted(res.keys()), ['ecs', 'new', 'new_file_in_existing_folder',
                                              'new_folder', 'paths_in_repo'])
        self.assertEqual(len(res['ecs']), len(test_ecs))
        self.assertTrue(all(isinstance(ec, EasyConfig) for ec in res['ecs']))
        self.assertTrue(all(res['new']))
        expected = os.path.join(target_dir, 'easybuild', 'easyconfigs', 'g', 'GCC', 'GCC-4.6.3.eb')
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

        self.assertEqual([len(x) for x in res.values()], [1, 1, 1, 1, 1])
        self.assertEqual(res['ecs'][0].full_mod_name, 'toy/0.0')

        # toy-0.0.eb was already copied into target_dir, so should not be marked as new anymore
        self.assertFalse(res['new'][0])

        copied_toy_ec = os.path.join(ecs_target_dir, 't', 'toy', 'toy-0.0.eb')
        self.assertTrue(os.path.samefile(res['paths_in_repo'][0], copied_toy_ec))

        # verify whether copied easyconfig gets cleaned up (stripping out 'Built with' comment + build stats)
        txt = read_file(copied_toy_ec)
        regexs = [
            "# Built with EasyBuild",
            "# Build statistics",
            "buildstats\s*=",
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
        ec = EasyConfig(os.path.join(test_ecs_dir, 'g', 'gzip', 'gzip-1.5-goolf-1.4.10.eb'))

        expected = {
            'bitbucket_account': 'gzip',
            'github_account': 'gzip',
            'name': 'gzip',
            'nameletter': 'g',
            'toolchain_name': 'goolf',
            'toolchain_version': '1.4.10',
            'version': '1.5',
            'version_major': '1',
            'version_major_minor': '1.5',
            'version_minor': '5',
            'versionprefix': '',
            'versionsuffix': '',
        }
        self.assertEqual(template_constant_dict(ec), expected)

        ec = EasyConfig(os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0-deps.eb'))
        # fiddle with version to check version_minor template ('0' should be retained)
        ec['version'] = '0.01'

        expected = {
            'bitbucket_account': 'toy',
            'github_account': 'toy',
            'name': 'toy',
            'nameletter': 't',
            'toolchain_name': 'dummy',
            'toolchain_version': 'dummy',
            'version': '0.01',
            'version_major': '0',
            'version_major_minor': '0.01',
            'version_minor': '01',
            'versionprefix': '',
            'versionsuffix': '-deps',
        }
        self.assertEqual(template_constant_dict(ec), expected)

    def test_parse_deps_templates(self):
        """Test whether handling of templates defined by dependencies is done correctly."""
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')

        pyec = os.path.join(self.test_prefix, 'Python-2.7.10-goolf-1.4.10.eb')
        shutil.copy2(os.path.join(test_ecs, 'p', 'Python', 'Python-2.7.10-ictce-4.1.13.eb'), pyec)
        write_file(pyec, "\ntoolchain = {'name': 'goolf', 'version': '1.4.10'}", append=True)

        ec_txt = '\n'.join([
            "easyblock = 'ConfigureMake'",
            "name = 'test'",
            "version = '1.2.3'",
            "versionsuffix = '-Python-%(pyver)s'",
            "homepage = 'http://example.com'",
            "description = 'test'",
            "toolchain = {'name': 'goolf', 'version': '1.4.10'}",
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
            "toolchain = {'name': 'goolf', 'version': '1.4.10'}",
            "dependencies = [('Python', '2.7.10')]",
        ])
        write_file(os.path.join(self.test_prefix, 'pytest-1.2.3-goolf-1.4.10-Python-2.7.10.eb'), pytest_ec_txt)

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
            'MPI/GCC/4.7.2/OpenMPI/1.6.4/Python/2.7.10',
            'MPI/GCC/4.7.2/OpenMPI/1.6.4/pytest/1.2.3-Python-2.7.10',
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
        outtxt = self.eb_main(args)
        self.assertTrue(re.search('module: GCC/\.4\.9\.2', outtxt))
        self.assertTrue(re.search('module: gzip/1\.6-GCC-4\.9\.2', outtxt))

    def test_categorize_files_by_type(self):
        """Test categorize_files_by_type"""
        self.assertEqual({'easyconfigs': [], 'files_to_delete': [], 'patch_files': []}, categorize_files_by_type([]))

        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs',)
        toy_patch_fn = 'toy-0.0_fix-silly-typo-in-printf-statement.patch'
        toy_patch = os.path.join(os.path.dirname(test_ecs_dir), 'sandbox', 'sources', 'toy', toy_patch_fn)
        paths = [
            'bzip2-1.0.6.eb',
            os.path.join(test_ecs_dir, 'test_ecs', 'g', 'gzip', 'gzip-1.4.eb'),
            toy_patch,
            'foo',
            ':toy-0.0-deps.eb',
        ]
        res = categorize_files_by_type(paths)
        expected = [
            'bzip2-1.0.6.eb',
            os.path.join(test_ecs_dir, 'test_ecs', 'g', 'gzip', 'gzip-1.4.eb'),
            'foo',
        ]
        self.assertEqual(res['easyconfigs'], expected)
        self.assertEqual(res['files_to_delete'], ['toy-0.0-deps.eb'])
        self.assertEqual(res['patch_files'], [toy_patch])

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

        current_tc = {'name': 'goolfc', 'version': '2.6.10'}
        # missing gompic and double golfc should both give exceptions
        cands = [{'name': 'golfc', 'version': '2.6.10'},
                 {'name': 'golfc', 'version': '2.6.11'}]
        self.assertErrorRegex(EasyBuildError,
                              "No version found for subtoolchain gompic in dependencies of goolfc",
                              det_subtoolchain_version, current_tc, 'gompic', optional_toolchains, cands)
        self.assertErrorRegex(EasyBuildError,
                              "Multiple versions of golfc found in dependencies of toolchain goolfc: 2.6.10, 2.6.11",
                              det_subtoolchain_version, current_tc, 'golfc', optional_toolchains, cands)

        # missing candidate for golfc, ok for optional
        cands = [{'name': 'gompic', 'version': '2.6.10'}]
        versions = [det_subtoolchain_version(current_tc, subtoolchain_name, optional_toolchains, cands)
                    for subtoolchain_name in subtoolchains[current_tc['name']]]
        self.assertEqual(versions, ['2.6.10', None])

        # 'dummy', 'dummy' should be ok: return None for GCCcore, and None or '' for 'dummy'.
        current_tc = {'name': 'GCC', 'version': '4.8.2'}
        cands = [{'name': 'dummy', 'version': 'dummy'}]
        versions = [det_subtoolchain_version(current_tc, subtoolchain_name, optional_toolchains, cands)
                    for subtoolchain_name in subtoolchains[current_tc['name']]]
        self.assertEqual(versions, [None, None])

        init_config(build_options={
            'add_dummy_to_minimal_toolchains': True})

        versions = [det_subtoolchain_version(current_tc, subtoolchain_name, optional_toolchains, cands)
                    for subtoolchain_name in subtoolchains[current_tc['name']]]
        self.assertEqual(versions, [None, ''])

        # and GCCcore if existing too
        current_tc = {'name': 'GCC', 'version': '4.9.3-2.25'}
        cands = [{'name': 'GCCcore', 'version': '4.9.3'}]
        versions = [det_subtoolchain_version(current_tc, subtoolchain_name, optional_toolchains, cands)
                    for subtoolchain_name in subtoolchains[current_tc['name']]]
        self.assertEqual(versions, ['4.9.3', ''])

    def test_verify_easyconfig_filename(self):
        """Test verify_easyconfig_filename function"""
        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0-gompi-1.3.12-test.eb')
        toy_ec_name = os.path.basename(toy_ec)
        specs = {
            'name': 'toy',
            'toolchain': {'name': 'gompi', 'version': '1.3.12'},
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
        error_pattern = "filename '%s' does not match with expected filename 'toy-0.0-gompi-1.3.12.eb' " % toy_ec_name
        error_pattern += "\(specs: name: 'toy'; version: '0.0'; versionsuffix: ''; "
        error_pattern += "toolchain name, version: 'gompi', '1.3.12'\)"
        self.assertErrorRegex(EasyBuildError, error_pattern, verify_easyconfig_filename, toy_ec, specs)
        specs['versionsuffix'] = '-test'

        # incorrect file name
        toy_txt = read_file(toy_ec)
        toy_ec = os.path.join(self.test_prefix, 'toy.eb')
        write_file(toy_ec, toy_txt)
        error_pattern = "filename 'toy.eb' does not match with expected filename 'toy-0.0-gompi-1.3.12-test.eb' "
        error_pattern += "\(specs: name: 'toy'; version: '0.0'; versionsuffix: '-test'; "
        error_pattern += "toolchain name, version: 'gompi', '1.3.12'\)"
        self.assertErrorRegex(EasyBuildError, error_pattern, verify_easyconfig_filename, toy_ec, specs)

        # incorrect file contents
        error_pattern = r"Contents of .*/%s does not match with filename" % os.path.basename(toy_ec)
        toy_txt = toy_txt.replace("versionsuffix = '-test'", "versionsuffix = ''")
        toy_ec = os.path.join(self.test_prefix, 'toy-0.0-gompi-1.3.12-test.eb')
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

        # locations listed in 'robot_path' named argument are taken into account
        res = get_paths_for(subdir='easyconfigs', robot_path=[self.test_prefix])
        self.assertTrue(os.path.samefile(test_ecs, res[0]))

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

        # also locations in sys.path are considered
        os.environ['PATH'] = orig_path
        sys.path.insert(0, self.test_prefix)
        res = get_paths_for(subdir='easyconfigs', robot_path=None)
        self.assertTrue(os.path.samefile(test_ecs, res[0]))

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

        checksums_regex = re.compile('^checksums = \[\[(.|\n)*\]\]', re.M)

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
        for regex in ['toy-.*', '.*-0\.0-fail\.eb']:
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
        self.assertTrue(res[-1].startswith("Non-SHA256 checksum found for toy-0.0.tar.gz"))

        # re-test with right checksum in place
        toy_sha256 = '44332000aa33b99ad1e00cbd1a7da769220d74647060a10e807b916d73ea27bc'
        test_ec_txt = checksums_regex.sub('checksums = ["%s"]' % toy_sha256, toy_ec_txt)
        test_ec_txt = re.sub('patches = \[(.|\n)*\]', '', test_ec_txt)

        test_ec = os.path.join(self.test_prefix, 'toy-0.0-ok.eb')
        write_file(test_ec, test_ec_txt)
        ecs, _ = parse_easyconfigs([(test_ec, False)])
        ecs = [ec['ec'] for ec in ecs]

        # if no checksum issues are found, result is an empty list
        self.assertEqual(check_sha256_checksums(ecs), [])

        # also test toy easyconfig with extensions, for which some checksums are missing
        toy_ec = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0-gompi-1.3.12-test.eb')
        ecs, _ = parse_easyconfigs([(toy_ec, False)])
        ecs = [ec['ec'] for ec in ecs]

        # checksum issues found, so result is non-empty
        res = check_sha256_checksums(ecs)
        self.assertTrue(res)
        # multiple checksums listed for source tarball, while exactly one (SHA256) checksum is expected
        self.assertTrue(res[1].startswith("Non-SHA256 checksum found for toy-0.0.tar.gz: "))


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(EasyConfigTest, sys.argv[1:])


if __name__ == '__main__':
    # also check the setUp for debug
    # logToScreen(enable=True)
    # setLogLevelDebug()
    TextTestRunner(verbosity=1).run(suite())
