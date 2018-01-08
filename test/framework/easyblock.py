##
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
##
"""
Unit tests for easyblock.py

@author: Jens Timmerman (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""
import os
import re
import shutil
import sys
import tempfile
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner

from easybuild.framework.easyblock import EasyBlock, get_easyblock_instance
from easybuild.framework.easyconfig import CUSTOM
from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.framework.easyconfig.tools import process_easyconfig
from easybuild.framework.extensioneasyblock import ExtensionEasyBlock
from easybuild.tools import config
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import get_module_syntax
from easybuild.tools.filetools import copy_file, mkdir, read_file, remove_file, write_file
from easybuild.tools.modules import modules_tool


class EasyBlockTest(EnhancedTestCase):
    """ Baseclass for easyblock testcases """

    def writeEC(self):
        """ create temporary easyconfig file """
        write_file(self.eb_file, self.contents)

    def setUp(self):
        """ setup """
        super(EasyBlockTest, self).setUp()

        fd, self.eb_file = tempfile.mkstemp(prefix='easyblock_test_file_', suffix='.eb')
        os.close(fd)

        self.test_tmp_logdir = tempfile.mkdtemp()
        os.environ['EASYBUILD_TMP_LOGDIR'] = self.test_tmp_logdir

    def test_empty(self):
        self.contents = "# empty"
        self.writeEC()
        """ empty files should not parse! """
        self.assertRaises(EasyBuildError, EasyConfig, self.eb_file)
        self.assertErrorRegex(EasyBuildError, "Value of incorrect type passed", EasyBlock, "")

    def test_easyblock(self):
        """ make sure easyconfigs defining extensions work"""

        def check_extra_options_format(extra_options):
            """Make sure extra_options value is of correct format."""
            # EasyBuild v2.0: dict with <string> keys and <list> values
            # (breaks backward compatibility compared to v1.x)
            self.assertTrue(isinstance(extra_options, dict))  # conversion to a dict works
            extra_options.items()
            extra_options.keys()
            extra_options.values()
            for key in extra_options.keys():
                self.assertTrue(isinstance(extra_options[key], list))
                self.assertTrue(len(extra_options[key]), 3)

        name = "pi"
        version = "3.14"
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "%s"' % name,
            'version = "%s"' % version,
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"dummy", "version": "dummy"}',
            'exts_list = ["ext1"]',
        ])
        self.writeEC()
        stdoutorig = sys.stdout
        sys.stdout = open("/dev/null", 'w')
        ec = EasyConfig(self.eb_file)
        eb = EasyBlock(ec)
        self.assertEqual(eb.cfg['name'], name)
        self.assertEqual(eb.cfg['version'], version)
        self.assertRaises(NotImplementedError, eb.run_all_steps, True)
        check_extra_options_format(eb.extra_options())
        sys.stdout.close()
        sys.stdout = stdoutorig

        # check whether 'This is easyblock' log message is there
        tup = ('EasyBlock', 'easybuild.framework.easyblock', '.*easybuild/framework/easyblock.pyc*')
        eb_log_msg_re = re.compile(r"INFO This is easyblock %s from module %s (%s)" % tup, re.M)
        logtxt = read_file(eb.logfile)
        self.assertTrue(eb_log_msg_re.search(logtxt), "Pattern '%s' found in: %s" % (eb_log_msg_re.pattern, logtxt))

        # test extensioneasyblock, as extension
        exeb1 = ExtensionEasyBlock(eb, {'name': 'foo', 'version': '0.0'})
        self.assertEqual(exeb1.cfg['name'], 'foo')
        extra_options = exeb1.extra_options()
        check_extra_options_format(extra_options)
        self.assertTrue('options' in extra_options)

        # test extensioneasyblock, as easyblock
        exeb2 = ExtensionEasyBlock(ec)
        self.assertEqual(exeb2.cfg['name'], 'pi')
        self.assertEqual(exeb2.cfg['version'], '3.14')
        extra_options = exeb2.extra_options()
        check_extra_options_format(extra_options)
        self.assertTrue('options' in extra_options)

        class TestExtension(ExtensionEasyBlock):
            @staticmethod
            def extra_options():
                return ExtensionEasyBlock.extra_options({'extra_param': [None, "help", CUSTOM]})
        texeb = TestExtension(eb, {'name': 'bar'})
        self.assertEqual(texeb.cfg['name'], 'bar')
        extra_options = texeb.extra_options()
        check_extra_options_format(extra_options)
        self.assertTrue('options' in extra_options)
        self.assertEqual(extra_options['extra_param'], [None, "help", CUSTOM])

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

    def test_fake_module_load(self):
        """Testcase for fake module load"""
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name": "dummy", "version": "dummy"}',
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.installdir = config.build_path()
        fake_mod_data = eb.load_fake_module()
        eb.clean_up_fake_module(fake_mod_data)

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

    def test_make_module_extend_modpath(self):
        """Test for make_module_extend_modpath"""
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"dummy", "version": "dummy"}',
            'moduleclass = "compiler"',
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.installdir = config.install_path()

        # no $MODULEPATH extensions for default module naming scheme (EasyBuildMNS)
        self.assertEqual(eb.make_module_extend_modpath(), '')
        usermodsdir = 'my/own/modules'
        modclasses = ['compiler', 'tools']
        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'CategorizedHMNS'
        build_options = {
            'subdir_user_modules': usermodsdir,
            'valid_module_classes': modclasses,
            'suffix_modules_path': 'funky',
        }
        init_config(build_options=build_options)
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.installdir = config.install_path()

        txt = eb.make_module_extend_modpath()
        if get_module_syntax() == 'Tcl':
            regexs = [r'^module use ".*/modules/funky/Compiler/pi/3.14/%s"$' % c for c in modclasses]
            home = r'\$env\(HOME\)'
            regexs.extend([
                # extension for user modules is guarded
                r'if { \[ file isdirectory \[ file join %s "%s/funky/Compiler/pi/3.14" \] \] } {$' % (home, usermodsdir),
                # no per-moduleclass extension for user modules
                r'^\s+module use \[ file join %s "%s/funky/Compiler/pi/3.14"\ ]$' % (home, usermodsdir),
            ])
        elif get_module_syntax() == 'Lua':
            regexs = [r'^prepend_path\("MODULEPATH", ".*/modules/funky/Compiler/pi/3.14/%s"\)$' % c for c in modclasses]
            home = r'os.getenv\("HOME"\)'
            regexs.extend([
                # extension for user modules is guarded
                r'if isDir\(pathJoin\(%s, "%s/funky/Compiler/pi/3.14"\)\) then' % (home, usermodsdir),
                # no per-moduleclass extension for user modules
                r'\s+prepend_path\("MODULEPATH", pathJoin\(%s, "%s/funky/Compiler/pi/3.14"\)\)' % (home, usermodsdir),
            ])
        else:
            self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())
        for regex in regexs:
            regex = re.compile(regex, re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))

    def test_make_module_req(self):
        """Testcase for make_module_req"""
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name":"dummy", "version": "dummy"}',
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.installdir = config.install_path()

        # create fake directories and files that should be guessed
        os.makedirs(eb.installdir)
        open(os.path.join(eb.installdir, 'foo.jar'), 'w').write('foo.jar')
        open(os.path.join(eb.installdir, 'bla.jar'), 'w').write('bla.jar')
        os.mkdir(os.path.join(eb.installdir, 'bin'))
        os.mkdir(os.path.join(eb.installdir, 'share'))
        os.mkdir(os.path.join(eb.installdir, 'share', 'man'))
        # this is not a path that should be picked up
        os.mkdir(os.path.join(eb.installdir, 'CPATH'))

        guess = eb.make_module_req()

        if get_module_syntax() == 'Tcl':
            self.assertTrue(re.search(r"^prepend-path\s+CLASSPATH\s+\$root/bla.jar$", guess, re.M))
            self.assertTrue(re.search(r"^prepend-path\s+CLASSPATH\s+\$root/foo.jar$", guess, re.M))
            self.assertTrue(re.search(r"^prepend-path\s+MANPATH\s+\$root/share/man$", guess, re.M))
            self.assertTrue(re.search(r"^prepend-path\s+PATH\s+\$root/bin$", guess, re.M))
            self.assertFalse(re.search(r"^prepend-path\s+CPATH\s+.*$", guess, re.M))
        elif get_module_syntax() == 'Lua':
            self.assertTrue(re.search(r'^prepend_path\("CLASSPATH", pathJoin\(root, "bla.jar"\)\)$', guess, re.M))
            self.assertTrue(re.search(r'^prepend_path\("CLASSPATH", pathJoin\(root, "foo.jar"\)\)$', guess, re.M))
            self.assertTrue(re.search(r'^prepend_path\("MANPATH", pathJoin\(root, "share/man"\)\)$', guess, re.M))
            self.assertTrue(re.search(r'^prepend_path\("PATH", pathJoin\(root, "bin"\)\)$', guess, re.M))
            self.assertFalse(re.search(r'^prepend_path\("CPATH", .*\)$', guess, re.M))
        else:
            self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())

        # check for behavior when a string value is used as dict value by make_module_req_guesses
        eb.make_module_req_guess = lambda: {'PATH': 'bin'}
        txt = eb.make_module_req()
        if get_module_syntax() == 'Tcl':
            self.assertTrue(re.match(r"^\nprepend-path\s+PATH\s+\$root/bin\n$", txt, re.M))
        elif get_module_syntax() == 'Lua':
            self.assertTrue(re.match(r'^\nprepend_path\("PATH", pathJoin\(root, "bin"\)\)\n$', txt, re.M))
        else:
            self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())

        # check for correct behaviour if empty string is specified as one of the values
        # prepend-path statements should be included for both the 'bin' subdir and the install root
        eb.make_module_req_guess = lambda: {'PATH': ['bin', '']}
        txt = eb.make_module_req()
        if get_module_syntax() == 'Tcl':
            self.assertTrue(re.search(r"\nprepend-path\s+PATH\s+\$root/bin\n", txt, re.M))
            self.assertTrue(re.search(r"\nprepend-path\s+PATH\s+\$root\n", txt, re.M))
        elif get_module_syntax() == 'Lua':
            self.assertTrue(re.search(r'\nprepend_path\("PATH", pathJoin\(root, "bin"\)\)\n', txt, re.M))
            self.assertTrue(re.search(r'\nprepend_path\("PATH", root\)\n', txt, re.M))
        else:
            self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

    def test_make_module_extra(self):
        """Test for make_module_extra."""
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            "toolchain = {'name': 'gompi', 'version': '1.1.0-no-OFED'}",
            'dependencies = [',
            "   ('FFTW', '3.3.1'),",
            "   ('LAPACK', '3.4.0'),",
            ']',
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.installdir = os.path.join(config.install_path(), 'pi', '3.14')

        if get_module_syntax() == 'Tcl':
            expected_default = re.compile(r'\n'.join([
                r'setenv\s+EBROOTPI\s+\"\$root"',
                r'setenv\s+EBVERSIONPI\s+"3.14"',
                r'setenv\s+EBDEVELPI\s+"\$root/easybuild/pi-3.14-gompi-1.1.0-no-OFED-easybuild-devel"',
            ]))
            expected_alt = re.compile(r'\n'.join([
                r'setenv\s+EBROOTPI\s+"/opt/software/tau/6.28"',
                r'setenv\s+EBVERSIONPI\s+"6.28"',
                r'setenv\s+EBDEVELPI\s+"\$root/easybuild/pi-3.14-gompi-1.1.0-no-OFED-easybuild-devel"',
            ]))
        elif get_module_syntax() == 'Lua':
            expected_default = re.compile(r'\n'.join([
                r'setenv\("EBROOTPI", root\)',
                r'setenv\("EBVERSIONPI", "3.14"\)',
                r'setenv\("EBDEVELPI", pathJoin\(root, "easybuild/pi-3.14-gompi-1.1.0-no-OFED-easybuild-devel"\)\)',
            ]))
            expected_alt = re.compile(r'\n'.join([
                r'setenv\("EBROOTPI", "/opt/software/tau/6.28"\)',
                r'setenv\("EBVERSIONPI", "6.28"\)',
                r'setenv\("EBDEVELPI", pathJoin\(root, "easybuild/pi-3.14-gompi-1.1.0-no-OFED-easybuild-devel"\)\)',
            ]))
        else:
            self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())

        defaulttxt = eb.make_module_extra().strip()
        self.assertTrue(expected_default.match(defaulttxt),
                        "Pattern %s found in %s" % (expected_default.pattern, defaulttxt))

        alttxt = eb.make_module_extra(altroot='/opt/software/tau/6.28', altversion='6.28').strip()
        self.assertTrue(expected_alt.match(alttxt),
                        "Pattern %s found in %s" % (expected_alt.pattern, alttxt))

        installver = '3.14-gompi-1.1.0-no-OFED'

        # also check how absolute paths specified in modexself.contents = '\n'.join([
        self.contents += "\nmodextrapaths = {'TEST_PATH_VAR': ['foo', '/test/absolute/path', 'bar']}"
        self.writeEC()
        ec = EasyConfig(self.eb_file)
        eb = EasyBlock(ec)
        eb.installdir = os.path.join(config.install_path(), 'pi', installver)
        eb.check_readiness_step()

        # absolute paths are not allowed by default
        error_pattern = "Absolute path .* passed to update_paths which only expects relative paths"
        self.assertErrorRegex(EasyBuildError, error_pattern, eb.make_module_step)

        # allow use of absolute paths, and verify contents of module
        self.contents += "\nallow_prepend_abs_path = True"
        self.writeEC()
        ec = EasyConfig(self.eb_file)
        eb = EasyBlock(ec)
        eb.installdir = os.path.join(config.install_path(), 'pi', installver)
        eb.check_readiness_step()

        modrootpath = eb.make_module_step()

        modpath = os.path.join(modrootpath, 'pi', installver)
        if get_module_syntax() == 'Lua':
            modpath += '.lua'

        self.assertTrue(os.path.exists(modpath), "%s exists" % modpath)
        txt = read_file(modpath)
        patterns = [
            r"^prepend[-_]path.*TEST_PATH_VAR.*root.*foo",
            r"^prepend[-_]path.*TEST_PATH_VAR.*/test/absolute/path",
            r"^prepend[-_]path.*TEST_PATH_VAR.*root.*bar",
        ]
        for pattern in patterns:
            self.assertTrue(re.search(pattern, txt, re.M), "Pattern '%s' found in: %s" % (pattern, txt))

    def test_make_module_dep(self):
        """Test for make_module_dep"""
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            "toolchain = {'name': 'gompi', 'version': '1.1.0-no-OFED'}",
            'dependencies = [',
            "   ('FFTW', '3.3.1'),",
            "   ('LAPACK', '3.4.0'),",
            ']',
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))

        eb.installdir = os.path.join(config.install_path(), 'pi', '3.14')
        eb.check_readiness_step()

        if get_module_syntax() == 'Tcl':
            tc_load = '\n'.join([
                "if { ![ is-loaded gompi/1.1.0-no-OFED ] } {",
                "    module load gompi/1.1.0-no-OFED",
                "}",
            ])
            fftw_load = '\n'.join([
                "if { ![ is-loaded FFTW/3.3.1-gompi-1.1.0-no-OFED ] } {",
                "    module load FFTW/3.3.1-gompi-1.1.0-no-OFED",
                "}",
            ])
            lapack_load = '\n'.join([
                "if { ![ is-loaded LAPACK/3.4.0-gompi-1.1.0-no-OFED ] } {",
                "    module load LAPACK/3.4.0-gompi-1.1.0-no-OFED",
                "}",
            ])
        elif get_module_syntax() == 'Lua':
            tc_load = '\n'.join([
                'if not isloaded("gompi/1.1.0-no-OFED") then',
                '    load("gompi/1.1.0-no-OFED")',
                'end',
            ])
            fftw_load = '\n'.join([
                'if not isloaded("FFTW/3.3.1-gompi-1.1.0-no-OFED") then',
                '    load("FFTW/3.3.1-gompi-1.1.0-no-OFED")',
                'end',
            ])
            lapack_load = '\n'.join([
                'if not isloaded("LAPACK/3.4.0-gompi-1.1.0-no-OFED") then',
                '    load("LAPACK/3.4.0-gompi-1.1.0-no-OFED")',
                'end',
            ])
        else:
            self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())

        expected = tc_load + '\n\n' + fftw_load + '\n\n' + lapack_load
        self.assertEqual(eb.make_module_dep().strip(), expected)

        # provide swap info for FFTW to trigger an extra 'unload FFTW'
        unload_info = {
            'FFTW/3.3.1-gompi-1.1.0-no-OFED': 'FFTW',
        }

        if get_module_syntax() == 'Tcl':
            fftw_load = '\n'.join([
                "if { ![ is-loaded FFTW/3.3.1-gompi-1.1.0-no-OFED ] } {",
                "    module unload FFTW",
                "    module load FFTW/3.3.1-gompi-1.1.0-no-OFED",
                "}",
            ])
        elif get_module_syntax() == 'Lua':
            fftw_load = '\n'.join([
                'if not isloaded("FFTW/3.3.1-gompi-1.1.0-no-OFED") then',
                '    unload("FFTW")',
                '    load("FFTW/3.3.1-gompi-1.1.0-no-OFED")',
                'end',
            ])
        else:
            self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())
        expected = tc_load + '\n\n' + fftw_load + '\n\n' + lapack_load
        self.assertEqual(eb.make_module_dep(unload_info=unload_info).strip(), expected)

    def test_make_module_dep_hmns(self):
        """Test for make_module_dep under HMNS"""
        test_ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        all_stops = [x[0] for x in EasyBlock.get_steps()]
        build_options = {
            'check_osdeps': False,
            'robot_path': [test_ecs_path],
            'valid_stops': all_stops,
            'validate': False,
        }
        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'HierarchicalMNS'
        init_config(build_options=build_options)
        self.setup_hierarchical_modules()

        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            "toolchain = {'name': 'gompi', 'version': '1.4.10'}",
            'dependencies = [',
            "   ('FFTW', '3.3.3'),",
            ']',
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))

        eb.installdir = os.path.join(config.install_path(), 'pi', '3.14')
        eb.check_readiness_step()
        eb.make_builddir()
        eb.prepare_step()

        # GCC, OpenMPI and hwloc modules should *not* be included in loads for dependencies
        mod_dep_txt = eb.make_module_dep()
        for mod in ['GCC/4.7.2', 'OpenMPI/1.6.4']:
            regex = re.compile('load.*%s' % mod)
            self.assertFalse(regex.search(mod_dep_txt), "Pattern '%s' found in: %s" % (regex.pattern, mod_dep_txt))

        regex = re.compile('load.*FFTW/3.3.3')
        self.assertTrue(regex.search(mod_dep_txt), "Pattern '%s' found in: %s" % (regex.pattern, mod_dep_txt))

    def test_make_module_dep_of_dep_hmns(self):
        """Test for make_module_dep under HMNS with dependencies of dependencies"""
        test_ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        all_stops = [x[0] for x in EasyBlock.get_steps()]
        build_options = {
            'check_osdeps': False,
            'robot_path': [test_ecs_path],
            'valid_stops': all_stops,
            'validate': False,
        }
        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'HierarchicalMNS'
        init_config(build_options=build_options)
        self.setup_hierarchical_modules()

        # GCC and OpenMPI extend $MODULEPATH; hwloc is a dependency of OpenMPI.
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            "toolchain = {'name': 'goolf', 'version': '1.4.10'}",
            'dependencies = [',
            "   ('GCC', '4.7.2', '', True),"
            "   ('hwloc', '1.6.2', '', ('GCC', '4.7.2')),",
            "   ('OpenMPI', '1.6.4', '', ('GCC', '4.7.2')),"
            ']',
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))

        eb.installdir = os.path.join(config.install_path(), 'pi', '3.14')
        eb.check_readiness_step()

        # GCC, OpenMPI and hwloc modules should *not* be included in loads for dependencies
        mod_dep_txt = eb.make_module_dep()
        for mod in ['GCC/4.7.2', 'OpenMPI/1.6.4', 'hwloc/1.6.2']:
            regex = re.compile('load.*%s' % mod)
            self.assertFalse(regex.search(mod_dep_txt), "Pattern '%s' found in: %s" % (regex.pattern, mod_dep_txt))

    def test_extensions_step(self):
        """Test the extensions_step"""
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name": "dummy", "version": "dummy"}',
            'exts_list = ["ext1"]',
        ])
        self.writeEC()
        """Testcase for extensions"""
        # test for proper error message without the exts_defaultclass set
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.installdir = config.install_path()
        self.assertRaises(EasyBuildError, eb.extensions_step, fetch=True)
        self.assertErrorRegex(EasyBuildError, "No default extension class set", eb.extensions_step, fetch=True)

        # test if everything works fine if set
        self.contents += "\nexts_defaultclass = 'DummyExtension'"
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.builddir = config.build_path()
        eb.installdir = config.install_path()
        eb.extensions_step(fetch=True)

        # test for proper error message when skip is set, but no exts_filter is set
        self.assertRaises(EasyBuildError, eb.skip_extensions)
        self.assertErrorRegex(EasyBuildError, "no exts_filter set", eb.skip_extensions)

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

    def test_skip_extensions_step(self):
        """Test the skip_extensions_step"""
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name": "dummy", "version": "dummy"}',
            'exts_list = ["ext1", "ext2"]',
            'exts_filter = ("if [ %(ext_name)s == \'ext2\' ]; then exit 0; else exit 1; fi", "")',
            'exts_defaultclass = "DummyExtension"',
        ])
        # check if skip skips correct extensions
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.builddir = config.build_path()
        eb.installdir = config.install_path()
        eb.skip = True
        eb.extensions_step(fetch=True)
        # 'ext1' should be in eb.exts
        self.assertTrue('ext1' in [y for x in eb.exts for y in x.values()])
        # 'ext2' should not
        self.assertFalse('ext2' in [y for x in eb.exts for y in x.values()])

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

    def test_make_module_step(self):
        """Test the make_module_step"""
        name = "pi"
        version = "3.14"
        # purposely use a 'nasty' description, that includes (unbalanced) special chars: [, ], {, }
        descr = "This {is a}} [fancy]] [[description]]. {{[[TEST}]"
        deps = [('GCC', '4.6.4')]
        modextravars = {'PI': '3.1415', 'FOO': 'bar'}
        modextrapaths = {'PATH': 'pibin', 'CPATH': 'pi/include'}
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "%s"' % name,
            'version = "%s"' % version,
            'homepage = "http://example.com"',
            'description = "%s"' % descr,
            "toolchain = {'name': 'dummy', 'version': 'dummy'}",
            "dependencies = [('GCC', '4.6.4'), ('toy', '0.0-deps')]",
            "builddependencies = [('OpenMPI', '1.6.4-GCC-4.6.4')]",
            # hidden deps must be included in list of (build)deps
            "hiddendependencies = [('toy', '0.0-deps'), ('OpenMPI', '1.6.4-GCC-4.6.4')]",
            "modextravars = %s" % str(modextravars),
            "modextrapaths = %s" % str(modextrapaths),
        ])

        test_dir = os.path.dirname(os.path.abspath(__file__))
        os.environ['MODULEPATH'] = os.path.join(test_dir, 'modules')

        # test if module is generated correctly
        self.writeEC()
        ec = EasyConfig(self.eb_file)
        eb = EasyBlock(ec)
        eb.installdir = os.path.join(config.install_path(), 'pi', '3.14')
        eb.check_readiness_step()

        modpath = os.path.join(eb.make_module_step(), name, version)
        if get_module_syntax() == 'Lua':
            modpath += '.lua'
        self.assertTrue(os.path.exists(modpath), "%s exists" % modpath)

        # verify contents of module
        txt = read_file(modpath)
        if get_module_syntax() == 'Tcl':
            self.assertTrue(re.search(r"^#%Module", txt.split('\n')[0]))
            self.assertTrue(re.search(r"^conflict\s+%s$" % name, txt, re.M))

            self.assertTrue(re.search(r"^set\s+root\s+%s$" % eb.installdir, txt, re.M))
            ebroot_regex = re.compile(r'^setenv\s+EBROOT%s\s+"\$root"\s*$' % name.upper(), re.M)
            self.assertTrue(ebroot_regex.search(txt), "%s in %s" % (ebroot_regex.pattern, txt))
            self.assertTrue(re.search(r'^setenv\s+EBVERSION%s\s+"%s"$' % (name.upper(), version), txt, re.M))

        elif get_module_syntax() == 'Lua':
            ebroot_regex = re.compile(r'^setenv\("EBROOT%s", root\)$' % name.upper(), re.M)
            self.assertTrue(ebroot_regex.search(txt), "%s in %s" % (ebroot_regex.pattern, txt))
            self.assertTrue(re.search(r'^setenv\("EBVERSION%s", "%s"\)$' % (name.upper(), version), txt, re.M))

        else:
            self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())

        for (key, val) in modextravars.items():
            if get_module_syntax() == 'Tcl':
                regex = re.compile(r'^setenv\s+%s\s+"%s"$' % (key, val), re.M)
            elif get_module_syntax() == 'Lua':
                regex = re.compile(r'^setenv\("%s", "%s"\)$' % (key, val), re.M)
            else:
                self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())
            self.assertTrue(regex.search(txt), "Pattern %s found in %s" % (regex.pattern, txt))

        for (key, val) in modextrapaths.items():
            if get_module_syntax() == 'Tcl':
                regex = re.compile(r'^prepend-path\s+%s\s+\$root/%s$' % (key, val), re.M)
            elif get_module_syntax() == 'Lua':
                regex = re.compile(r'^prepend_path\("%s", pathJoin\(root, "%s"\)\)$' % (key, val), re.M)
            else:
                self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())
            self.assertTrue(regex.search(txt), "Pattern %s found in %s" % (regex.pattern, txt))

        for (name, ver) in [('GCC', '4.6.4')]:
            if get_module_syntax() == 'Tcl':
                regex = re.compile(r'^\s*module load %s\s*$' % os.path.join(name, ver), re.M)
            elif get_module_syntax() == 'Lua':
                regex = re.compile(r'^\s*load\("%s"\)$' % os.path.join(name, ver), re.M)
            else:
                self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())
            self.assertTrue(regex.search(txt), "Pattern %s found in %s" % (regex.pattern, txt))

        for (name, ver) in [('toy', '0.0-deps')]:
            if get_module_syntax() == 'Tcl':
                regex = re.compile(r'^\s*module load %s/.%s\s*$' % (name, ver), re.M)
            elif get_module_syntax() == 'Lua':
                regex = re.compile(r'^\s*load\("%s/.%s"\)$' % (name, ver), re.M)
            else:
                self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())
            self.assertTrue(regex.search(txt), "Pattern %s found in %s" % (regex.pattern, txt))

        for (name, ver) in [('OpenMPI', '1.6.4-GCC-4.6.4')]:
            if get_module_syntax() == 'Tcl':
                regex = re.compile(r'^\s*module load %s/.?%s\s*$' % (name, ver), re.M)
            elif get_module_syntax() == 'Lua':
                regex = re.compile(r'^\s*load\("%s/.?%s"\)$' % (name, ver), re.M)
            else:
                self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())
            self.assertFalse(regex.search(txt), "Pattern '%s' *not* found in %s" % (regex.pattern, txt))

        # also check whether generated module can be loaded
        self.modtool.load(['pi/3.14'])
        self.modtool.unload(['pi/3.14'])

        # [==[ or ]==] in description is fatal
        if get_module_syntax() == 'Lua':
            error_pattern = "Found unwanted '\[==\[' or '\]==\]' in: .*"
            for descr in ["test [==[", "]==] foo"]:
                ectxt = read_file(self.eb_file)
                write_file(self.eb_file, re.sub('description.*', 'description = "%s"' % descr, ectxt))
                ec = EasyConfig(self.eb_file)
                eb = EasyBlock(ec)
                eb.installdir = os.path.join(config.install_path(), 'pi', '3.14')
                eb.check_readiness_step()
                self.assertErrorRegex(EasyBuildError, error_pattern, eb.make_module_step)

    def test_gen_dirs(self):
        """Test methods that generate/set build/install directory names."""
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            "name = 'pi'",
            "version = '3.14'",
            "homepage = 'http://example.com'",
            "description = 'test easyconfig'",
            "toolchain = {'name': 'dummy', 'version': 'dummy'}",
        ])
        self.writeEC()
        stdoutorig = sys.stdout
        sys.stdout = open("/dev/null", 'w')
        eb = EasyBlock(EasyConfig(self.eb_file))
        resb = eb.gen_builddir()
        resi = eb.gen_installdir()
        eb.make_builddir()
        eb.make_installdir()
        # doesn't return anything
        self.assertEqual(resb, None)
        self.assertEqual(resi, None)
        # directories are set, and exist
        self.assertTrue(os.path.isdir(eb.builddir))
        self.assertTrue(os.path.isdir(eb.installdir))

        # make sure cleaning up old build dir is default
        self.assertTrue(eb.cfg['cleanupoldbuild'] or eb.cfg.get('cleanupoldbuild', True))
        builddir = eb.builddir
        eb.gen_builddir()
        self.assertEqual(builddir, eb.builddir)
        eb.cfg['cleanupoldbuild'] = True
        eb.gen_builddir()
        self.assertEqual(builddir, eb.builddir)

        # make sure build dir is unique
        eb.cfg['cleanupoldbuild'] = False
        builddir = eb.builddir
        for i in range(3):
            eb.gen_builddir()
            self.assertEqual(eb.builddir, "%s.%d" % (builddir, i))
            eb.make_builddir()

        # cleanup
        sys.stdout.close()
        sys.stdout = stdoutorig
        eb.close_log()

    def test_get_easyblock_instance(self):
        """Test get_easyblock_instance function."""
        from easybuild.easyblocks.toy import EB_toy
        testdir = os.path.abspath(os.path.dirname(__file__))

        ec = process_easyconfig(os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb'))[0]
        eb = get_easyblock_instance(ec)
        self.assertTrue(isinstance(eb, EB_toy))

        # check whether 'This is easyblock' log message is there
        tup = ('EB_toy', 'easybuild.easyblocks.toy', '.*test/framework/sandbox/easybuild/easyblocks/t/toy.pyc*')
        eb_log_msg_re = re.compile(r"INFO This is easyblock %s from module %s (%s)" % tup, re.M)
        logtxt = read_file(eb.logfile)
        self.assertTrue(eb_log_msg_re.search(logtxt), "Pattern '%s' found in: %s" % (eb_log_msg_re.pattern, logtxt))

    def test_fetch_sources(self):
        """Test fetch_sources method."""
        testdir = os.path.abspath(os.path.dirname(__file__))
        ec = process_easyconfig(os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb'))[0]
        eb = get_easyblock_instance(ec)

        toy_source = os.path.join(testdir, 'sandbox', 'sources', 'toy', 'toy-0.0.tar.gz')

        eb.fetch_sources()
        self.assertEqual(len(eb.src), 1)
        self.assertTrue(os.path.samefile(eb.src[0]['path'], toy_source))
        self.assertEqual(eb.src[0]['name'], 'toy-0.0.tar.gz')
        self.assertEqual(eb.src[0]['cmd'], None)
        self.assertEqual(len(eb.src[0]['checksum']), 7)
        self.assertEqual(eb.src[0]['checksum'][0], 'be662daa971a640e40be5c804d9d7d10')
        self.assertEqual(eb.src[0]['checksum'][1], '44332000aa33b99ad1e00cbd1a7da769220d74647060a10e807b916d73ea27bc')

        # reconfigure EasyBuild so we can check 'downloaded' sources
        os.environ['EASYBUILD_SOURCEPATH'] = self.test_prefix
        init_config()

        eb.cfg['source_urls'] = ['file://%s' % os.path.dirname(toy_source)]

        # reset and try with provided list of sources
        eb.src = []
        sources = [
            {'filename': 'toy-0.0-extra.txt', 'download_filename': 'toy-extra.txt'},
            {'filename': 'toy-0.0_gzip.patch.gz', 'extract_cmd': "gunzip %s"},
            {'filename': 'toy-0.0-renamed.tar.gz', 'download_filename': 'toy-0.0.tar.gz', 'extract_cmd': "tar xfz %s"},
        ]
        eb.fetch_sources(sources, checksums=[])

        toy_source_dir = os.path.join(self.test_prefix, 't', 'toy')
        expected_sources = ['toy-0.0-extra.txt', 'toy-0.0_gzip.patch.gz', 'toy-0.0-renamed.tar.gz']

        # make source sources were downloaded, using correct filenames
        self.assertEqual(len(eb.src), 3)
        for idx in range(3):
            self.assertEqual(eb.src[idx]['name'], expected_sources[idx])
            self.assertTrue(os.path.exists(eb.src[idx]['path']))
            source_loc = os.path.join(toy_source_dir, expected_sources[idx])
            self.assertTrue(os.path.exists(source_loc))
            self.assertTrue(os.path.samefile(eb.src[idx]['path'], source_loc))
        self.assertEqual(eb.src[0]['cmd'], None)
        self.assertEqual(eb.src[1]['cmd'], "gunzip %s")
        self.assertEqual(eb.src[2]['cmd'], "tar xfz %s")

        # old format for specifying source with custom extract command is deprecated
        eb.src = []
        error_msg = "DEPRECATED \(since v4.0\).*Using a 2-element list/tuple.*"
        self.assertErrorRegex(EasyBuildError, error_msg, eb.fetch_sources,
                              [('toy-0.0_gzip.patch.gz', "gunzip %s")], checksums=[])

    def test_fetch_patches(self):
        """Test fetch_patches method."""
        testdir = os.path.abspath(os.path.dirname(__file__))
        ec = process_easyconfig(os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb'))[0]
        eb = get_easyblock_instance(ec)

        eb.fetch_patches()
        self.assertEqual(len(eb.patches), 2)
        self.assertEqual(eb.patches[0]['name'], 'toy-0.0_typo.patch')
        self.assertFalse('level' in eb.patches[0])

        # reset
        eb.patches = []

        patches = [
            ('toy-0.0_typo.patch', 0),  # should also be level 0 (not None or something else)
            ('toy-0.0_typo.patch', 4),   # should be level 4
            ('toy-0.0_typo.patch', 'foobar'),  # sourcepath should be set to 'foobar'
            ('toy-0.0.tar.gz', 'some/path'),  # copy mode (not a .patch file)
        ]
        # check if patch levels are parsed correctly
        eb.fetch_patches(patch_specs=patches)

        self.assertEqual(len(eb.patches), 4)
        self.assertEqual(eb.patches[0]['name'], 'toy-0.0_typo.patch')
        self.assertEqual(eb.patches[0]['level'], 0)
        self.assertEqual(eb.patches[1]['name'], 'toy-0.0_typo.patch')
        self.assertEqual(eb.patches[1]['level'], 4)
        self.assertEqual(eb.patches[2]['name'], 'toy-0.0_typo.patch')
        self.assertEqual(eb.patches[2]['sourcepath'], 'foobar')
        self.assertEqual(eb.patches[3]['name'], 'toy-0.0.tar.gz'),
        self.assertEqual(eb.patches[3]['copy'], 'some/path')

        patches = [
            ('toy-0.0_level4.patch', False),  # should throw an error, only int's an strings allowed here
        ]
        self.assertRaises(EasyBuildError, eb.fetch_patches, patch_specs=patches)

    def test_obtain_file(self):
        """Test obtain_file method."""
        toy_tarball = 'toy-0.0.tar.gz'
        testdir = os.path.abspath(os.path.dirname(__file__))
        sandbox_sources = os.path.join(testdir, 'sandbox', 'sources')
        toy_tarball_path = os.path.join(sandbox_sources, 'toy', toy_tarball)
        tmpdir = tempfile.mkdtemp()
        tmpdir_subdir = os.path.join(tmpdir, 'testing')
        mkdir(tmpdir_subdir, parents=True)
        del os.environ['EASYBUILD_SOURCEPATH']  # defined by setUp

        ec = process_easyconfig(os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb'))[0]
        eb = EasyBlock(ec['ec'])

        # 'downloading' a file to (first) sourcepath works
        init_config(args=["--sourcepath=%s:/no/such/dir:%s" % (tmpdir, testdir)])
        shutil.copy2(toy_tarball_path, tmpdir_subdir)
        res = eb.obtain_file(toy_tarball, urls=['file://%s' % tmpdir_subdir])
        self.assertEqual(res, os.path.join(tmpdir, 't', 'toy', toy_tarball))

        # finding a file in sourcepath works
        init_config(args=["--sourcepath=%s:/no/such/dir:%s" % (sandbox_sources, tmpdir)])
        res = eb.obtain_file(toy_tarball)
        self.assertEqual(res, toy_tarball_path)

        # sourcepath has preference over downloading
        res = eb.obtain_file(toy_tarball, urls=['file://%s' % tmpdir_subdir])
        self.assertEqual(res, toy_tarball_path)

        init_config(args=["--sourcepath=%s:%s" % (tmpdir, sandbox_sources)])

        # clean up toy tarballs in tmpdir, so the one in sourcepath is found
        remove_file(os.path.join(tmpdir, toy_tarball))
        remove_file(os.path.join(tmpdir, 't', 'toy', toy_tarball))

        # enabling force_download results in re-downloading, even if file is already in sourcepath
        self.mock_stderr(True)
        self.mock_stdout(True)
        res = eb.obtain_file(toy_tarball, urls=['file://%s' % tmpdir_subdir], force_download=True)
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertEqual(stdout, '')
        msg = "WARNING: Found file toy-0.0.tar.gz at %s, but re-downloading it anyway..." % toy_tarball_path
        self.assertEqual(stderr.strip(), msg)

        # toy tarball was indeed re-downloaded to tmpdir
        self.assertEqual(res, os.path.join(tmpdir, 't', 'toy', toy_tarball))
        self.assertTrue(os.path.exists(os.path.join(tmpdir, 't', 'toy', toy_tarball)))

        # obtain_file yields error for non-existing files
        fn = 'thisisclearlyanonexistingfile'
        error_regex = "Couldn't find file %s anywhere, and downloading it didn't work either" % fn
        self.assertErrorRegex(EasyBuildError, error_regex, eb.obtain_file, fn, urls=['file://%s' % tmpdir_subdir])

        # file specifications via URL also work, are downloaded to (first) sourcepath
        init_config(args=["--sourcepath=%s:/no/such/dir:%s" % (tmpdir, sandbox_sources)])
        urls = [
            "https://easybuilders.github.io/easybuild/index.html",
            "https://easybuilders.github.io/easybuild/index.html",
        ]
        for file_url in urls:
            fn = os.path.basename(file_url)
            res = None
            try:
                res = eb.obtain_file(file_url)
            except EasyBuildError, err:
                # if this fails, it should be because there's no online access
                download_fail_regex = re.compile('socket error')
                self.assertTrue(download_fail_regex.search(str(err)))

            # result may be None during offline testing
            if res is not None:
                loc = os.path.join(tmpdir, 't', 'toy', fn)
                self.assertEqual(res, loc)
                self.assertTrue(os.path.exists(loc), "%s file is found at %s" % (fn, loc))
                txt = open(loc, 'r').read()
                eb_regex = re.compile("EasyBuild: building software with ease")
                self.assertTrue(eb_regex.search(txt), "Pattern '%s' found in: %s" % (eb_regex.pattern, txt))
            else:
                print "ignoring failure to download %s in test_obtain_file, testing offline?" % file_url

        shutil.rmtree(tmpdir)

    def test_check_readiness(self):
        """Test check_readiness method."""
        init_config(build_options={'validate': False})

        # check that check_readiness step works (adding dependencies, etc.)
        ec_file = 'OpenMPI-1.6.4-GCC-4.6.4.eb'
        topdir = os.path.dirname(os.path.abspath(__file__))
        ec_path = os.path.join(topdir, 'easyconfigs', 'test_ecs', 'o', 'OpenMPI', ec_file)
        ec = EasyConfig(ec_path)
        eb = EasyBlock(ec)
        eb.check_readiness_step()

        # a proper error should be thrown for dependencies that can't be resolved (module should be there)
        tmpdir = tempfile.mkdtemp()
        shutil.copy2(ec_path, tmpdir)
        ec_path = os.path.join(tmpdir, ec_file)
        f = open(ec_path, 'a')
        f.write("\ndependencies += [('nosuchsoftware', '1.2.3')]\n")
        f.close()
        ec = EasyConfig(ec_path)
        eb = EasyBlock(ec)
        try:
            eb.check_readiness_step()
        except EasyBuildError, err:
            err_regex = re.compile("Missing modules for one or more dependencies: nosuchsoftware/1.2.3-GCC-4.6.4")
            self.assertTrue(err_regex.search(str(err)), "Pattern '%s' found in '%s'" % (err_regex.pattern, err))

        shutil.rmtree(tmpdir)

    def test_exclude_path_to_top_of_module_tree(self):
        """
        Make sure that modules under the HierarchicalMNS are correct,
        w.r.t. not including any load statements for modules that build up the path to the top of the module tree.
        """
        self.orig_module_naming_scheme = config.get_module_naming_scheme()
        test_ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        all_stops = [x[0] for x in EasyBlock.get_steps()]
        build_options = {
            'check_osdeps': False,
            'robot_path': [test_ecs_path],
            'valid_stops': all_stops,
            'validate': False,
        }
        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'HierarchicalMNS'
        init_config(build_options=build_options)
        self.setup_hierarchical_modules()

        intel_ver = '2013.5.192-GCC-4.8.3'
        impi_modfile_path = os.path.join('Compiler', 'intel', intel_ver, 'impi', '4.1.3.049')
        imkl_modfile_path = os.path.join('MPI', 'intel', intel_ver, 'impi', '4.1.3.049', 'imkl', '11.1.2.144')
        if get_module_syntax() == 'Lua':
            impi_modfile_path += '.lua'
            imkl_modfile_path += '.lua'

        # example: for imkl on top of iimpi toolchain with HierarchicalMNS, no module load statements should be included
        # not for the toolchain or any of the toolchain components,
        # since both icc/ifort and impi form the path to the top of the module tree
        iccifort_mods = ['icc', 'ifort', 'iccifort']
        tests = [
            ('i/impi/impi-4.1.3.049-iccifort-2013.5.192-GCC-4.8.3.eb', impi_modfile_path, iccifort_mods),
            ('i/imkl/imkl-11.1.2.144-iimpi-5.5.3-GCC-4.8.3.eb', imkl_modfile_path, iccifort_mods + ['iimpi', 'impi']),
        ]
        for ec_file, modfile_path, excluded_deps in tests:
            ec = EasyConfig(os.path.join(test_ecs_path, ec_file))
            eb = EasyBlock(ec)
            eb.toolchain.prepare()
            modpath = eb.make_module_step()
            modfile_path = os.path.join(modpath, modfile_path)
            modtxt = read_file(modfile_path)

            for dep in excluded_deps:
                tup = (dep, modfile_path, modtxt)
                failmsg = "No 'module load' statement found for '%s' not found in module %s: %s" % tup
                if get_module_syntax() == 'Tcl':
                    self.assertFalse(re.search('module load %s' % dep, modtxt), failmsg)
                elif get_module_syntax() == 'Lua':
                    self.assertFalse(re.search('load("%s")' % dep, modtxt), failmsg)
                else:
                    self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())

        # modpath_extensions_for should spit out correct result, even if modules are loaded
        icc_mod = 'icc/%s' % intel_ver
        impi_mod = 'impi/4.1.3.049'
        self.modtool.load([icc_mod])
        self.assertTrue(impi_modfile_path in self.modtool.show(impi_mod))
        self.modtool.load([impi_mod])
        expected = {
            icc_mod: [os.path.join(modpath, 'Compiler', 'intel', intel_ver)],
            impi_mod: [os.path.join(modpath, 'MPI', 'intel', intel_ver, 'impi', '4.1.3.049')],
        }
        self.assertEqual(self.modtool.modpath_extensions_for([icc_mod, impi_mod]), expected)

    def test_patch_step(self):
        """Test patch step."""
        test_easyconfigs = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        ec = process_easyconfig(os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb'))[0]
        orig_sources = ec['ec']['sources'][:]

        toy_patches = [
            'toy-0.0_typo.patch',  # test for applying patch
            ('toy-extra.txt', 'toy-0.0'), # test for patch-by-copy
        ]
        self.assertEqual(ec['ec']['patches'], toy_patches)

        # test applying patches without sources
        ec['ec']['sources'] = []
        eb = EasyBlock(ec['ec'])
        eb.fetch_step()
        eb.extract_step()
        self.assertErrorRegex(EasyBuildError, '.*', eb.patch_step)

        # test actual patching of unpacked sources
        ec['ec']['sources'] = orig_sources
        eb = EasyBlock(ec['ec'])
        eb.fetch_step()
        eb.extract_step()
        eb.patch_step()
        # verify that patches were applied
        toydir = os.path.join(eb.builddir, 'toy-0.0')
        self.assertEqual(sorted(os.listdir(toydir)), ['toy-extra.txt', 'toy.source', 'toy.source.orig'])
        self.assertTrue("and very proud of it" in read_file(os.path.join(toydir, 'toy.source')))
        self.assertEqual(read_file(os.path.join(toydir, 'toy-extra.txt')), 'moar!\n')

    def test_extensions_sanity_check(self):
        """Test sanity check aspect of extensions."""
        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = EasyConfig(os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0-gompi-1.3.12-test.eb'))

        # purposely put sanity check command in place that breaks the build,
        # to check whether sanity check is only run once;
        # sanity check commands are checked after checking sanity check paths, so this should work
        toy_ec.update('sanity_check_commands', [("%(installdir)s/bin/toy && rm %(installdir)s/bin/toy", '')])

        # this import only works here, since EB_toy is a test easyblock
        from easybuild.easyblocks.toy import EB_toy
        eb = EB_toy(toy_ec)
        eb.silent = True
        eb.run_all_steps(True)

    def test_parallel(self):
        """Test defining of parallellism."""
        topdir = os.path.abspath(os.path.dirname(__file__))
        toy_ec = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        toytxt = read_file(toy_ec)

        handle, toy_ec1 = tempfile.mkstemp(prefix='easyblock_test_file_', suffix='.eb')
        os.close(handle)
        write_file(toy_ec1, toytxt + "\nparallel = 123")

        handle, toy_ec2 = tempfile.mkstemp(prefix='easyblock_test_file_', suffix='.eb')
        os.close(handle)
        write_file(toy_ec2, toytxt + "\nparallel = 123\nmaxparallel = 67")

        # default: parallellism is derived from # available cores + ulimit
        test_eb = EasyBlock(EasyConfig(toy_ec))
        test_eb.check_readiness_step()
        self.assertTrue(isinstance(test_eb.cfg['parallel'], int) and test_eb.cfg['parallel'] > 0)

        # only 'parallel' easyconfig parameter specified (no 'parallel' build option)
        test_eb = EasyBlock(EasyConfig(toy_ec1))
        test_eb.check_readiness_step()
        self.assertEqual(test_eb.cfg['parallel'], 123)

        # both 'parallel' and 'maxparallel' easyconfig parameters specified (no 'parallel' build option)
        test_eb = EasyBlock(EasyConfig(toy_ec2))
        test_eb.check_readiness_step()
        self.assertEqual(test_eb.cfg['parallel'], 67)

        # only 'parallel' build option specified
        init_config(build_options={'parallel': '97', 'validate': False})
        test_eb = EasyBlock(EasyConfig(toy_ec))
        test_eb.check_readiness_step()
        self.assertEqual(test_eb.cfg['parallel'], 97)

        # both 'parallel' build option and easyconfig parameter specified (no 'maxparallel')
        test_eb = EasyBlock(EasyConfig(toy_ec1))
        test_eb.check_readiness_step()
        self.assertEqual(test_eb.cfg['parallel'], 97)

        # both 'parallel' and 'maxparallel' easyconfig parameters specified + 'parallel' build option
        test_eb = EasyBlock(EasyConfig(toy_ec2))
        test_eb.check_readiness_step()
        self.assertEqual(test_eb.cfg['parallel'], 67)

    def test_guess_start_dir(self):
        """Test guessing the start dir."""
        test_easyconfigs = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        ec = process_easyconfig(os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb'))[0]

        def check_start_dir(expected_start_dir):
            """Check start dir."""
            eb = EasyBlock(ec['ec'])
            eb.silent = True
            eb.cfg['stop'] = 'patch'
            eb.run_all_steps(False)
            eb.guess_start_dir()
            abs_expected_start_dir = os.path.join(eb.builddir, expected_start_dir)
            self.assertTrue(os.path.samefile(eb.cfg['start_dir'], abs_expected_start_dir))
            self.assertTrue(os.path.samefile(os.getcwd(), abs_expected_start_dir))

        # default (no start_dir specified): use unpacked dir as start dir
        self.assertEqual(ec['ec']['start_dir'], None)
        check_start_dir('toy-0.0')

        # using start_dir equal to the one we're in is OK
        ec['ec']['start_dir'] = '%(name)s-%(version)s'
        self.assertEqual(ec['ec']['start_dir'], 'toy-0.0')
        check_start_dir('toy-0.0')

        # clean error when specified start dir does not exist
        ec['ec']['start_dir'] = 'thisstartdirisnotthere'
        err_pattern = "Specified start dir .*/toy-0.0/thisstartdirisnotthere does not exist"
        self.assertErrorRegex(EasyBuildError, err_pattern, check_start_dir, 'whatever')

    def test_prepare_step(self):
        """Test prepare step (setting up build environment)."""
        test_easyconfigs = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        ec = process_easyconfig(os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb'))[0]

        mkdir(os.path.join(self.test_buildpath, 'toy', '0.0', 'dummy-dummy'), parents=True)
        eb = EasyBlock(ec['ec'])
        eb.silent = True
        eb.prepare_step()
        self.assertEqual(self.modtool.list(), [])

        os.environ['THIS_IS_AN_UNWANTED_ENV_VAR'] = 'foo'
        eb.cfg['unwanted_env_vars'] = ['THIS_IS_AN_UNWANTED_ENV_VAR']

        eb.cfg['allow_system_deps'] = [('Python', '1.2.3')]

        init_config(build_options={'extra_modules': ['GCC/4.7.2']})

        eb.prepare_step()

        self.assertEqual(os.environ.get('THIS_IS_AN_UNWANTED_ENV_VAR'), None)
        self.assertEqual(os.environ.get('EBROOTPYTHON'), 'Python')
        self.assertEqual(os.environ.get('EBVERSIONPYTHON'), '1.2.3')
        self.assertEqual(len(self.modtool.list()), 1)
        self.assertEqual(self.modtool.list()[0]['mod_name'], 'GCC/4.7.2')

    def test_checksum_step(self):
        """Test checksum step"""
        testdir = os.path.abspath(os.path.dirname(__file__))
        toy_ec = os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-gompi-1.3.12-test.eb')

        ec = process_easyconfig(toy_ec)[0]
        eb = get_easyblock_instance(ec)
        eb.fetch_sources()
        eb.checksum_step()

        # fiddle with checksum to check whether faulty checksum is catched
        copy_file(toy_ec, self.test_prefix)
        toy_ec = os.path.join(self.test_prefix, os.path.basename(toy_ec))
        ectxt = read_file(toy_ec)
        # replace MD5 checksum for toy-0.0.tar.gz
        ectxt = ectxt.replace('be662daa971a640e40be5c804d9d7d10', '00112233445566778899aabbccddeeff')
        # replace SHA256 checksums for source of bar extension
        ectxt = ectxt.replace('f3676716b610545a4e8035087f5be0a0248adee0abb3930d3edb76d498ae91e7', '01234567' * 8)
        write_file(toy_ec, ectxt)

        ec = process_easyconfig(toy_ec)[0]
        eb = get_easyblock_instance(ec)
        eb.fetch_sources()
        error_msg  ="Checksum verification for .*/toy-0.0.tar.gz using .* failed"
        self.assertErrorRegex(EasyBuildError, error_msg, eb.checksum_step)

        # also check verification of checksums for extensions, which is part of fetch_extension_sources
        error_msg = "Checksum verification for extension source bar-0.0.tar.gz failed"
        self.assertErrorRegex(EasyBuildError, error_msg, eb.fetch_extension_sources)

        # if --ignore-checksums is enabled, faulty checksums are reported but otherwise ignored (no error)
        build_options = {
            'ignore_checksums': True,
        }
        init_config(build_options=build_options)

        self.mock_stderr(True)
        self.mock_stdout(True)
        eb.checksum_step()
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertEqual(stdout, '')
        self.assertEqual(stderr.strip(), "WARNING: Ignoring failing checksum verification for toy-0.0.tar.gz")

        self.mock_stderr(True)
        self.mock_stdout(True)
        eb.fetch_extension_sources()
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertEqual(stdout, '')
        self.assertEqual(stderr.strip(), "WARNING: Ignoring failing checksum verification for bar-0.0.tar.gz")


def suite():
    """ return all the tests in this file """
    return TestLoaderFiltered().loadTestsFromTestCase(EasyBlockTest, sys.argv[1:])

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
