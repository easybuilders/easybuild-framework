##
# Copyright 2012-2023 Ghent University
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
@author: Maxime Boissonneault (Compute Canada)
"""
import os
import re
import shutil
import sys
import tempfile
from inspect import cleandoc
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner

import easybuild.tools.systemtools as st
from easybuild.base import fancylogger
from easybuild.framework.easyblock import EasyBlock, get_easyblock_instance
from easybuild.framework.easyconfig import CUSTOM
from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.framework.easyconfig.tools import avail_easyblocks, process_easyconfig
from easybuild.framework.extensioneasyblock import ExtensionEasyBlock
from easybuild.tools import LooseVersion, config
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import get_module_syntax, update_build_option
from easybuild.tools.filetools import change_dir, copy_dir, copy_file, mkdir, read_file, remove_dir, remove_file
from easybuild.tools.filetools import verify_checksum, write_file
from easybuild.tools.module_generator import module_generator
from easybuild.tools.modules import EnvironmentModules, Lmod, reset_module_caches
from easybuild.tools.version import get_git_revision, this_is_easybuild
from easybuild.tools.py2vs3 import string_type


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
            self.assertIsInstance(extra_options, dict)  # conversion to a dict works
            extra_options.items()
            extra_options.keys()
            extra_options.values()
            for key in extra_options.keys():
                self.assertIsInstance(extra_options[key], list)
                self.assertEqual(len(extra_options[key]), 3)

        name = "pi"
        version = "3.14"
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "%s"' % name,
            'version = "%s"' % version,
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = SYSTEM',
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
        self.assertIn('options', extra_options)
        # Reporting test failure should work also for the extension EB
        self.assertRaises(EasyBuildError, exeb1.report_test_failure, "Fails")

        # test extensioneasyblock, as easyblock
        exeb2 = ExtensionEasyBlock(ec)
        self.assertEqual(exeb2.cfg['name'], 'pi')
        self.assertEqual(exeb2.cfg['version'], '3.14')
        extra_options = exeb2.extra_options()
        check_extra_options_format(extra_options)
        self.assertIn('options', extra_options)
        # Reporting test failure should work also for the extension EB
        self.assertRaises(EasyBuildError, exeb2.report_test_failure, "Fails")

        class TestExtension(ExtensionEasyBlock):
            @staticmethod
            def extra_options():
                return ExtensionEasyBlock.extra_options({'extra_param': [None, "help", CUSTOM]})
        texeb = TestExtension(eb, {'name': 'bar'})
        self.assertEqual(texeb.cfg['name'], 'bar')
        extra_options = texeb.extra_options()
        check_extra_options_format(extra_options)
        self.assertIn('options', extra_options)
        self.assertEqual(extra_options['extra_param'], [None, "help", CUSTOM])

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

    def test_load_module(self):
        """Test load_module method."""
        # copy OpenMPI module used in gompi/2018a to fiddle with it, i.e. to fake bump OpenMPI version used in it
        tmp_modules = os.path.join(self.test_prefix, 'modules')
        mkdir(tmp_modules)

        test_dir = os.path.abspath(os.path.dirname(__file__))
        copy_dir(os.path.join(test_dir, 'modules', 'OpenMPI'), os.path.join(tmp_modules, 'OpenMPI'))

        openmpi_module = os.path.join(tmp_modules, 'OpenMPI', '2.1.2-GCC-6.4.0-2.28')
        ompi_mod_txt = read_file(openmpi_module)
        write_file(openmpi_module, ompi_mod_txt.replace('2.1.2', '2.0.2'))

        self.modtool.use(tmp_modules)

        orig_tmpdir = os.path.join(self.test_prefix, 'verylongdirectorythatmaycauseproblemswithopenmpi2')
        os.environ['TMPDIR'] = orig_tmpdir

        self.contents = '\n'.join([
            "easyblock = 'ConfigureMake'",
            "name = 'pi'",
            "version = '3.14'",
            "homepage = 'http://example.com'",
            "description = 'test easyconfig'",
            "toolchain = {'name': 'gompi', 'version': '2018a'}",
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.installdir = config.build_path()

        # $TMPDIR is not touched yet at this point
        self.assertEqual(os.environ.get('TMPDIR'), orig_tmpdir)

        self.mock_stderr(True)
        self.mock_stdout(True)
        eb.prepare_step(start_dir=False)
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertFalse(stdout)
        self.assertTrue(stderr.strip().startswith("WARNING: Long $TMPDIR path may cause problems with OpenMPI 2.x"))

        # we expect $TMPDIR to be tweaked by the prepare step (OpenMPI 2.x doesn't like long $TMPDIR values)
        tweaked_tmpdir = os.environ.get('TMPDIR')
        self.assertNotEqual(tweaked_tmpdir, orig_tmpdir)

        eb.make_module_step()
        eb.load_module()

        # $TMPDIR does *not* get reset to original value after loading of module
        # (which involves resetting the environment before loading the module)
        self.assertEqual(os.environ.get('TMPDIR'), tweaked_tmpdir)

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
            'toolchain = SYSTEM',
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.installdir = config.build_path()
        fake_mod_data = eb.load_fake_module()

        pi_modfile = os.path.join(fake_mod_data[0], 'pi', '3.14')
        if get_module_syntax() == 'Lua':
            pi_modfile += '.lua'

        self.assertExists(pi_modfile)

        # check whether temporary module file is marked as default
        if get_module_syntax() == 'Lua':
            default_symlink = os.path.join(fake_mod_data[0], 'pi', 'default')
            self.assertTrue(os.path.samefile(default_symlink, pi_modfile))
        else:
            dot_version_txt = read_file(os.path.join(fake_mod_data[0], 'pi', '.version'))
            self.assertIn("set ModulesVersion 3.14", dot_version_txt)

        eb.clean_up_fake_module(fake_mod_data)

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

    def test_make_module_extend_modpath(self):
        """Test for make_module_extend_modpath"""

        module_syntax = get_module_syntax()

        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = SYSTEM',
            'moduleclass = "compiler"',
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.installdir = config.install_path()

        # no $MODULEPATH extensions for default module naming scheme (EasyBuildMNS)
        self.assertEqual(eb.make_module_extend_modpath(), '')
        usermodsdir = 'my_own_modules'
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
        if module_syntax == 'Tcl':
            regexs = [r'^module use ".*/modules/funky/Compiler/pi/3.14/%s"$' % c for c in modclasses]
            home = r'\[if { \[info exists ::env\(HOME\)\] } { concat \$::env\(HOME\) } '
            home += r'else { concat "HOME_NOT_DEFINED" } \]'
            fj_usermodsdir = 'file join "%s" "funky" "Compiler/pi/3.14"' % usermodsdir
            regexs.extend([
                # extension for user modules is guarded
                r'if { \[ file isdirectory \[ file join %s \[ %s \] \] \] } {$' % (home, fj_usermodsdir),
                # no per-moduleclass extension for user modules
                r'^\s+module use \[ file join %s \[ %s \] \]$' % (home, fj_usermodsdir),
            ])
        elif module_syntax == 'Lua':
            regexs = [r'^prepend_path\("MODULEPATH", ".*/modules/funky/Compiler/pi/3.14/%s"\)$' % c for c in modclasses]
            home = r'os.getenv\("HOME"\) or "HOME_NOT_DEFINED"'
            pj_usermodsdir = r'pathJoin\("%s", "funky", "Compiler/pi/3.14"\)' % usermodsdir
            regexs.extend([
                # extension for user modules is guarded
                r'if isDir\(pathJoin\(%s, %s\)\) then' % (home, pj_usermodsdir),
                # no per-moduleclass extension for user modules
                r'\s+prepend_path\("MODULEPATH", pathJoin\(%s, %s\)\)' % (home, pj_usermodsdir),
            ])
        else:
            self.fail("Unknown module syntax: %s" % module_syntax)

        for regex in regexs:
            regex = re.compile(regex, re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))

        # Repeat this but using an alternate envvars (instead of $HOME)
        list_of_envvars = ['SITE_INSTALLS', 'USER_INSTALLS']

        build_options = {
            'envvars_user_modules': list_of_envvars,
            'subdir_user_modules': usermodsdir,
            'valid_module_classes': modclasses,
            'suffix_modules_path': 'funky',
        }
        init_config(build_options=build_options)
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.installdir = config.install_path()

        txt = eb.make_module_extend_modpath()
        for envvar in list_of_envvars:
            if module_syntax == 'Tcl':
                regexs = [r'^module use ".*/modules/funky/Compiler/pi/3.14/%s"$' % c for c in modclasses]
                module_envvar = r'\[if \{ \[info exists ::env\(%s\)\] \} ' % envvar
                module_envvar += r'\{ concat \$::env\(%s\) \} ' % envvar
                module_envvar += r'else { concat "%s" } \]' % (envvar + '_NOT_DEFINED')
                fj_usermodsdir = 'file join "%s" "funky" "Compiler/pi/3.14"' % usermodsdir
                regexs.extend([
                    # extension for user modules is guarded
                    r'if { \[ file isdirectory \[ file join %s \[ %s \] \] \] } {$' % (module_envvar, fj_usermodsdir),
                    # no per-moduleclass extension for user modules
                    r'^\s+module use \[ file join %s \[ %s \] \]$' % (module_envvar, fj_usermodsdir),
                ])
            elif module_syntax == 'Lua':
                regexs = [r'^prepend_path\("MODULEPATH", ".*/modules/funky/Compiler/pi/3.14/%s"\)$' % c
                          for c in modclasses]
                module_envvar = r'os.getenv\("%s"\) or "%s"' % (envvar, envvar + "_NOT_DEFINED")
                pj_usermodsdir = r'pathJoin\("%s", "funky", "Compiler/pi/3.14"\)' % usermodsdir
                regexs.extend([
                    # extension for user modules is guarded
                    r'if isDir\(pathJoin\(%s, %s\)\) then' % (module_envvar, pj_usermodsdir),
                    # no per-moduleclass extension for user modules
                    r'\s+prepend_path\("MODULEPATH", pathJoin\(%s, %s\)\)' % (module_envvar, pj_usermodsdir),
                ])
            else:
                self.fail("Unknown module syntax: %s" % module_syntax)

            for regex in regexs:
                regex = re.compile(regex, re.M)
                self.assertTrue(regex.search(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))
            os.unsetenv(envvar)

        # Check behaviour when directories do and do not exist
        usermodsdir_extension = os.path.join(usermodsdir, "funky", "Compiler/pi/3.14")
        site_install_path = os.path.join(config.install_path(), 'site')
        site_modules = os.path.join(site_install_path, usermodsdir_extension)
        user_install_path = os.path.join(config.install_path(), 'user')
        user_modules = os.path.join(user_install_path, usermodsdir_extension)

        # make a modules directory so that we can create our module files
        temp_module_file_dir = os.path.join(site_install_path, usermodsdir, "temp_module_files")
        mkdir(temp_module_file_dir, parents=True)

        # write out a module file
        if module_syntax == 'Tcl':
            module_file = os.path.join(temp_module_file_dir, "mytest")
            module_txt = "#%Module\n" + txt
        elif module_syntax == 'Lua':
            module_file = os.path.join(temp_module_file_dir, "mytest.lua")
            module_txt = txt
        write_file(module_file, module_txt)

        # Set MODULEPATH and check the effect of `module load`
        os.environ['MODULEPATH'] = temp_module_file_dir

        # Let's switch to a dir where the paths we will use exist to make sure they can
        # not be accidentally picked up if the variable is not defined but the paths exist
        # relative to the current directory
        cwd = os.getcwd()
        mkdir(os.path.join(config.install_path(), "existing_dir", usermodsdir_extension), parents=True)
        change_dir(os.path.join(config.install_path(), "existing_dir"))
        self.modtool.run_module('load', 'mytest')
        self.assertNotIn(usermodsdir_extension, os.environ['MODULEPATH'])
        self.modtool.run_module('unload', 'mytest')
        change_dir(cwd)

        # Now define our environment variables
        os.environ['SITE_INSTALLS'] = site_install_path
        os.environ['USER_INSTALLS'] = user_install_path

        # Check MODULEPATH when neither directories exist
        self.modtool.run_module('load', 'mytest')
        self.assertNotIn(site_modules, os.environ['MODULEPATH'])
        self.assertNotIn(user_modules, os.environ['MODULEPATH'])
        self.modtool.run_module('unload', 'mytest')
        # Now create the directory for site modules
        mkdir(site_modules, parents=True)
        self.modtool.run_module('load', 'mytest')
        self.assertTrue(os.environ['MODULEPATH'].startswith(site_modules))
        self.assertNotIn(user_modules, os.environ['MODULEPATH'])
        self.modtool.run_module('unload', 'mytest')
        # Now create the directory for user modules
        mkdir(user_modules, parents=True)
        self.modtool.run_module('load', 'mytest')
        self.assertTrue(os.environ['MODULEPATH'].startswith(user_modules + ":" + site_modules))
        self.modtool.run_module('unload', 'mytest')

    def test_make_module_req(self):
        """Testcase for make_module_req"""
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = SYSTEM',
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.installdir = config.install_path()

        # create fake directories and files that should be guessed
        os.makedirs(eb.installdir)
        write_file(os.path.join(eb.installdir, 'foo.jar'), 'foo.jar')
        write_file(os.path.join(eb.installdir, 'bla.jar'), 'bla.jar')
        for path in ('bin', ('bin', 'testdir'), 'sbin', 'share', ('share', 'man'), 'lib', 'lib64'):
            if isinstance(path, string_type):
                path = (path, )
            os.mkdir(os.path.join(eb.installdir, *path))
        # this is not a path that should be picked up
        os.mkdir(os.path.join(eb.installdir, 'CPATH'))

        with eb.module_generator.start_module_creation():
            guess = eb.make_module_req()

        if get_module_syntax() == 'Tcl':
            self.assertTrue(re.search(r"^prepend-path\s+CLASSPATH\s+\$root/bla.jar$", guess, re.M))
            self.assertTrue(re.search(r"^prepend-path\s+CLASSPATH\s+\$root/foo.jar$", guess, re.M))
            self.assertTrue(re.search(r"^prepend-path\s+MANPATH\s+\$root/share/man$", guess, re.M))
            self.assertTrue(re.search(r"^prepend-path\s+CMAKE_PREFIX_PATH\s+\$root$", guess, re.M))
            # bin/ is not added to $PATH if it doesn't include files
            self.assertFalse(re.search(r"^prepend-path\s+PATH\s+\$root/bin$", guess, re.M))
            self.assertFalse(re.search(r"^prepend-path\s+PATH\s+\$root/sbin$", guess, re.M))
            # no include/ subdirectory, so no $CPATH update statement
            self.assertFalse(re.search(r"^prepend-path\s+CPATH\s+.*$", guess, re.M))
        elif get_module_syntax() == 'Lua':
            self.assertTrue(re.search(r'^prepend_path\("CLASSPATH", pathJoin\(root, "bla.jar"\)\)$', guess, re.M))
            self.assertTrue(re.search(r'^prepend_path\("CLASSPATH", pathJoin\(root, "foo.jar"\)\)$', guess, re.M))
            self.assertTrue(re.search(r'^prepend_path\("MANPATH", pathJoin\(root, "share/man"\)\)$', guess, re.M))
            self.assertIn('prepend_path("CMAKE_PREFIX_PATH", root)', guess)
            # bin/ is not added to $PATH if it doesn't include files
            self.assertFalse(re.search(r'^prepend_path\("PATH", pathJoin\(root, "bin"\)\)$', guess, re.M))
            self.assertFalse(re.search(r'^prepend_path\("PATH", pathJoin\(root, "sbin"\)\)$', guess, re.M))
            # no include/ subdirectory, so no $CPATH update statement
            self.assertFalse(re.search(r'^prepend_path\("CPATH", .*\)$', guess, re.M))
        else:
            self.fail("Unknown module syntax: %s" % get_module_syntax())

        # check that bin is only added to PATH if there are files in there
        write_file(os.path.join(eb.installdir, 'bin', 'test'), 'test')
        with eb.module_generator.start_module_creation():
            guess = eb.make_module_req()
        if get_module_syntax() == 'Tcl':
            self.assertTrue(re.search(r"^prepend-path\s+PATH\s+\$root/bin$", guess, re.M))
            self.assertFalse(re.search(r"^prepend-path\s+PATH\s+\$root/sbin$", guess, re.M))
        elif get_module_syntax() == 'Lua':
            self.assertTrue(re.search(r'^prepend_path\("PATH", pathJoin\(root, "bin"\)\)$', guess, re.M))
            self.assertFalse(re.search(r'^prepend_path\("PATH", pathJoin\(root, "sbin"\)\)$', guess, re.M))
        else:
            self.fail("Unknown module syntax: %s" % get_module_syntax())

        # Check that lib64 is only added to CMAKE_LIBRARY_PATH if there are files in there
        # but only if it is not a symlink to lib
        # -- No Files
        if get_module_syntax() == 'Tcl':
            self.assertFalse(re.search(r"^prepend-path\s+CMAKE_LIBRARY_PATH\s+\$root/lib64$", guess, re.M))
        elif get_module_syntax() == 'Lua':
            self.assertNotIn('prepend_path("CMAKE_LIBRARY_PATH", pathJoin(root, "lib64"))', guess)
        # -- With files
        write_file(os.path.join(eb.installdir, 'lib64', 'libfoo.so'), 'test')
        with eb.module_generator.start_module_creation():
            guess = eb.make_module_req()
        if get_module_syntax() == 'Tcl':
            self.assertTrue(re.search(r"^prepend-path\s+CMAKE_LIBRARY_PATH\s+\$root/lib64$", guess, re.M))
        elif get_module_syntax() == 'Lua':
            self.assertIn('prepend_path("CMAKE_LIBRARY_PATH", pathJoin(root, "lib64"))', guess)
        # -- With files in lib and lib64 symlinks to lib
        write_file(os.path.join(eb.installdir, 'lib', 'libfoo.so'), 'test')
        shutil.rmtree(os.path.join(eb.installdir, 'lib64'))
        os.symlink('lib', os.path.join(eb.installdir, 'lib64'))
        with eb.module_generator.start_module_creation():
            guess = eb.make_module_req()
        if get_module_syntax() == 'Tcl':
            self.assertFalse(re.search(r"^prepend-path\s+CMAKE_LIBRARY_PATH\s+\$root/lib64$", guess, re.M))
        elif get_module_syntax() == 'Lua':
            self.assertNotIn('prepend_path("CMAKE_LIBRARY_PATH", pathJoin(root, "lib64"))', guess)

        # With files in /lib and /lib64 symlinked to /lib there should be exactly 1 entry for (LD_)LIBRARY_PATH
        # pointing to /lib
        for var in ('LIBRARY_PATH', 'LD_LIBRARY_PATH'):
            if get_module_syntax() == 'Tcl':
                self.assertFalse(re.search(r"^prepend-path\s+%s\s+\$root/lib64$" % var, guess, re.M))
                self.assertEqual(len(re.findall(r"^prepend-path\s+%s\s+\$root/lib$" % var, guess, re.M)), 1)
            elif get_module_syntax() == 'Lua':
                self.assertFalse(re.search(r'^prepend_path\("%s", pathJoin\(root, "lib64"\)\)$' % var, guess, re.M))
                self.assertEqual(len(re.findall(r'^prepend_path\("%s", pathJoin\(root, "lib"\)\)$' % var,
                                                guess, re.M)), 1)

        # check for behavior when a string value is used as dict value by make_module_req_guesses
        eb.make_module_req_guess = lambda: {'PATH': 'bin'}
        with eb.module_generator.start_module_creation():
            txt = eb.make_module_req()
        if get_module_syntax() == 'Tcl':
            self.assertTrue(re.match(r"^\nprepend-path\s+PATH\s+\$root/bin\n$", txt, re.M))
        elif get_module_syntax() == 'Lua':
            self.assertTrue(re.match(r'^\nprepend_path\("PATH", pathJoin\(root, "bin"\)\)\n$', txt, re.M))
        else:
            self.fail("Unknown module syntax: %s" % get_module_syntax())

        # check for correct behaviour if empty string is specified as one of the values
        # prepend-path statements should be included for both the 'bin' subdir and the install root
        eb.make_module_req_guess = lambda: {'PATH': ['bin', '']}
        with eb.module_generator.start_module_creation():
            txt = eb.make_module_req()
        if get_module_syntax() == 'Tcl':
            self.assertTrue(re.search(r"\nprepend-path\s+PATH\s+\$root/bin\n", txt, re.M))
            self.assertTrue(re.search(r"\nprepend-path\s+PATH\s+\$root\n", txt, re.M))
        elif get_module_syntax() == 'Lua':
            self.assertTrue(re.search(r'\nprepend_path\("PATH", pathJoin\(root, "bin"\)\)\n', txt, re.M))
            self.assertTrue(re.search(r'\nprepend_path\("PATH", root\)\n', txt, re.M))
        else:
            self.fail("Unknown module syntax: %s" % get_module_syntax())

        # check for correct order of prepend statements when providing a list (and that no duplicates are allowed)
        eb.make_module_req_guess = lambda: {'LD_LIBRARY_PATH': ['lib/pathC', 'lib/pathA', 'lib/pathB', 'lib/pathA']}
        for path in ['pathA', 'pathB', 'pathC']:
            os.mkdir(os.path.join(eb.installdir, 'lib', path))
            write_file(os.path.join(eb.installdir, 'lib', path, 'libfoo.so'), 'test')
        with eb.module_generator.start_module_creation():
            txt = eb.make_module_req()
        if get_module_syntax() == 'Tcl':
            self.assertTrue(re.search(r"\nprepend-path\s+LD_LIBRARY_PATH\s+\$root/lib/pathC\n" +
                                      r"prepend-path\s+LD_LIBRARY_PATH\s+\$root/lib/pathA\n" +
                                      r"prepend-path\s+LD_LIBRARY_PATH\s+\$root/lib/pathB\n",
                                      txt, re.M))
            self.assertFalse(re.search(r"\nprepend-path\s+LD_LIBRARY_PATH\s+\$root/lib/pathB\n" +
                                       r"prepend-path\s+LD_LIBRARY_PATH\s+\$root/lib/pathA\n",
                                       txt, re.M))
        elif get_module_syntax() == 'Lua':
            self.assertTrue(re.search(r'\nprepend_path\("LD_LIBRARY_PATH", pathJoin\(root, "lib/pathC"\)\)\n' +
                                      r'prepend_path\("LD_LIBRARY_PATH", pathJoin\(root, "lib/pathA"\)\)\n' +
                                      r'prepend_path\("LD_LIBRARY_PATH", pathJoin\(root, "lib/pathB"\)\)\n',
                                      txt, re.M))
            self.assertFalse(re.search(r'\nprepend_path\("LD_LIBRARY_PATH", pathJoin\(root, "lib/pathB"\)\)\n' +
                                       r'prepend_path\("LD_LIBRARY_PATH", pathJoin\(root, "lib/pathA"\)\)\n',
                                       txt, re.M))
        else:
            self.fail("Unknown module syntax: %s" % get_module_syntax())

        # If PATH or LD_LIBRARY_PATH contain only folders, do not add an entry
        sub_lib_path = os.path.join('lib', 'path_folders')
        sub_path_path = os.path.join('bin', 'path_folders')
        eb.make_module_req_guess = lambda: {'LD_LIBRARY_PATH': sub_lib_path, 'PATH': sub_path_path}
        for path in (sub_lib_path, sub_path_path):
            full_path = os.path.join(eb.installdir, path, 'subpath')
            os.makedirs(full_path)
            write_file(os.path.join(full_path, 'any.file'), 'test')
        txt = eb.make_module_req()
        if get_module_syntax() == 'Tcl':
            self.assertFalse(re.search(r"prepend-path\s+LD_LIBRARY_PATH\s+\$%s\n" % sub_lib_path,
                                       txt, re.M))
            self.assertFalse(re.search(r"prepend-path\s+PATH\s+\$%s\n" % sub_path_path, txt, re.M))
        else:
            assert get_module_syntax() == 'Lua'
            self.assertFalse(re.search(r'prepend_path\("LD_LIBRARY_PATH", pathJoin\(root, "%s"\)\)\n' % sub_lib_path,
                                       txt, re.M))
            self.assertFalse(re.search(r'prepend_path\("PATH", pathJoin\(root, "%s"\)\)\n' % sub_path_path, txt, re.M))

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

    def test_make_module_extra(self):
        """Test for make_module_extra."""
        init_config(build_options={'silent': True})

        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            "toolchain = {'name': 'gompi', 'version': '2018a'}",
            'dependencies = [',
            "   ('FFTW', '3.3.7'),",
            "   ('OpenBLAS', '0.2.20'),",
            ']',
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.installdir = os.path.join(config.install_path(), 'pi', '3.14')

        if get_module_syntax() == 'Tcl':
            expected_default = re.compile(r'\n'.join([
                r'setenv\s+EBROOTPI\s+\"\$root"',
                r'setenv\s+EBVERSIONPI\s+"3.14"',
                r'setenv\s+EBDEVELPI\s+"\$root/easybuild/pi-3.14-gompi-2018a-easybuild-devel"',
            ]))
            expected_alt = re.compile(r'\n'.join([
                r'setenv\s+EBROOTPI\s+"/opt/software/tau/6.28"',
                r'setenv\s+EBVERSIONPI\s+"6.28"',
                r'setenv\s+EBDEVELPI\s+"\$root/easybuild/pi-3.14-gompi-2018a-easybuild-devel"',
            ]))
        elif get_module_syntax() == 'Lua':
            expected_default = re.compile(r'\n'.join([
                r'setenv\("EBROOTPI", root\)',
                r'setenv\("EBVERSIONPI", "3.14"\)',
                r'setenv\("EBDEVELPI", pathJoin\(root, "easybuild/pi-3.14-gompi-2018a-easybuild-devel"\)\)',
            ]))
            expected_alt = re.compile(r'\n'.join([
                r'setenv\("EBROOTPI", "/opt/software/tau/6.28"\)',
                r'setenv\("EBVERSIONPI", "6.28"\)',
                r'setenv\("EBDEVELPI", pathJoin\(root, "easybuild/pi-3.14-gompi-2018a-easybuild-devel"\)\)',
            ]))
        else:
            self.fail("Unknown module syntax: %s" % get_module_syntax())

        defaulttxt = eb.make_module_extra().strip()
        self.assertTrue(expected_default.match(defaulttxt),
                        "Pattern %s found in %s" % (expected_default.pattern, defaulttxt))

        alttxt = eb.make_module_extra(altroot='/opt/software/tau/6.28', altversion='6.28').strip()
        self.assertTrue(expected_alt.match(alttxt),
                        "Pattern %s found in %s" % (expected_alt.pattern, alttxt))

        installver = '3.14-gompi-2018a'

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

        self.assertExists(modpath)
        txt = read_file(modpath)
        patterns = [
            r"^prepend[-_]path.*TEST_PATH_VAR.*root.*foo",
            r"^prepend[-_]path.*TEST_PATH_VAR.*/test/absolute/path",
            r"^prepend[-_]path.*TEST_PATH_VAR.*root.*bar",
        ]
        for pattern in patterns:
            self.assertTrue(re.search(pattern, txt, re.M), "Pattern '%s' found in: %s" % (pattern, txt))

    def test_make_module_deppaths(self):
        """Test for make_module_deppaths"""
        init_config(build_options={'silent': True})

        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            "toolchain = {'name': 'gompi', 'version': '2018a'}",
            'moddependpaths = "/path/to/mods"',
            'dependencies = [',
            "   ('FFTW', '3.3.7'),",
            ']',
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))

        eb.installdir = os.path.join(config.install_path(), 'pi', '3.14')
        eb.check_readiness_step()
        eb.make_builddir()
        eb.prepare_step()

        if get_module_syntax() == 'Tcl':
            use_load = '\n'.join([
                'if { [ file isdirectory "/path/to/mods" ] } {',
                '    module use "/path/to/mods"',
                '}',
            ])
        elif get_module_syntax() == 'Lua':
            use_load = '\n'.join([
                'if isDir("/path/to/mods") then',
                '    prepend_path("MODULEPATH", "/path/to/mods")',
                'end',
            ])
        else:
            self.fail("Unknown module syntax: %s" % get_module_syntax())

        expected = use_load
        self.assertEqual(eb.make_module_deppaths().strip(), expected)

    def test_make_module_dep(self):
        """Test for make_module_dep"""
        init_config(build_options={'silent': True})

        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            "toolchain = {'name': 'gompi', 'version': '2018a'}",
            'dependencies = [',
            "   ('FFTW', '3.3.7'),",
            "   ('OpenBLAS', '0.2.20', '', ('GCC', '6.4.0-2.28')),",
            ']',
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))

        eb.installdir = os.path.join(config.install_path(), 'pi', '3.14')
        eb.check_readiness_step()
        eb.make_builddir()
        eb.prepare_step()

        if get_module_syntax() == 'Tcl':
            tc_load = '\n'.join([
                "if { ![ is-loaded gompi/2018a ] } {",
                "    module load gompi/2018a",
                "}",
            ])
            fftw_load = '\n'.join([
                "if { ![ is-loaded FFTW/3.3.7-gompi-2018a ] } {",
                "    module load FFTW/3.3.7-gompi-2018a",
                "}",
            ])
            lapack_load = '\n'.join([
                "if { ![ is-loaded OpenBLAS/0.2.20-GCC-6.4.0-2.28 ] } {",
                "    module load OpenBLAS/0.2.20-GCC-6.4.0-2.28",
                "}",
            ])
        elif get_module_syntax() == 'Lua':
            tc_load = '\n'.join([
                'if not ( isloaded("gompi/2018a") ) then',
                '    load("gompi/2018a")',
                'end',
            ])
            fftw_load = '\n'.join([
                'if not ( isloaded("FFTW/3.3.7-gompi-2018a") ) then',
                '    load("FFTW/3.3.7-gompi-2018a")',
                'end',
            ])
            lapack_load = '\n'.join([
                'if not ( isloaded("OpenBLAS/0.2.20-GCC-6.4.0-2.28") ) then',
                '    load("OpenBLAS/0.2.20-GCC-6.4.0-2.28")',
                'end',
            ])
        else:
            self.fail("Unknown module syntax: %s" % get_module_syntax())

        expected = tc_load + '\n\n' + fftw_load + '\n\n' + lapack_load
        self.assertEqual(eb.make_module_dep().strip(), expected)

        # provide swap info for FFTW to trigger an extra 'unload FFTW'
        unload_info = {
            'FFTW/3.3.7-gompi-2018a': 'FFTW',
        }

        if get_module_syntax() == 'Tcl':
            fftw_load = '\n'.join([
                "if { ![ is-loaded FFTW/3.3.7-gompi-2018a ] } {",
                "    module unload FFTW",
                "    module load FFTW/3.3.7-gompi-2018a",
                "}",
            ])
        elif get_module_syntax() == 'Lua':
            fftw_load = '\n'.join([
                'if not ( isloaded("FFTW/3.3.7-gompi-2018a") ) then',
                '    unload("FFTW")',
                '    load("FFTW/3.3.7-gompi-2018a")',
                'end',
            ])
        else:
            self.fail("Unknown module syntax: %s" % get_module_syntax())
        expected = tc_load + '\n\n' + fftw_load + '\n\n' + lapack_load
        self.assertEqual(eb.make_module_dep(unload_info=unload_info).strip(), expected)

    def test_make_module_dep_hmns(self):
        """Test for make_module_dep under HMNS"""
        test_ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        all_stops = [x[0] for x in EasyBlock.get_steps()]
        build_options = {
            'check_osdeps': False,
            'robot_path': [test_ecs_path],
            'silent': True,
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
            "toolchain = {'name': 'gompi', 'version': '2018a'}",
            'dependencies = [',
            "   ('FFTW', '3.3.7'),",
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
        for mod in ['GCC/6.4.0-2.28', 'OpenMPI/2.1.2']:
            regex = re.compile('load.*%s' % mod)
            self.assertFalse(regex.search(mod_dep_txt), "Pattern '%s' found in: %s" % (regex.pattern, mod_dep_txt))

        regex = re.compile('load.*FFTW/3.3.7')
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
            "toolchain = {'name': 'foss', 'version': '2018a'}",
            'dependencies = [',
            "   ('GCC', '6.4.0-2.28', '', SYSTEM),"
            "   ('hwloc', '1.11.8', '', ('GCC', '6.4.0-2.28')),",
            "   ('OpenMPI', '2.1.2', '', ('GCC', '6.4.0-2.28')),"
            ']',
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))

        eb.installdir = os.path.join(config.install_path(), 'pi', '3.14')
        eb.check_readiness_step()

        # toolchain must be loaded such that dependencies are accessible
        self.modtool.load(['foss/2018a'])

        # GCC, OpenMPI and hwloc modules should *not* be included in loads for dependencies
        mod_dep_txt = eb.make_module_dep()
        for mod in ['GCC/6.4.0-2.28', 'OpenMPI/2.1.2', 'hwloc/1.11.8']:
            regex = re.compile('load.*%s' % mod)
            self.assertFalse(regex.search(mod_dep_txt), "Pattern '%s' found in: %s" % (regex.pattern, mod_dep_txt))

    def test_det_iter_cnt(self):
        """Test det_iter_cnt method."""

        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = SYSTEM',
        ])

        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))

        # default value should be 1
        self.assertEqual(eb.det_iter_cnt(), 1)

        # adding a list of build deps shouldn't affect the default
        self.contents += "\nbuilddependencies = [('one', '1.0'), ('two', '2.0'), ('three', '3.0')]"
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        self.assertEqual(eb.det_iter_cnt(), 1)

        # list of configure options to iterate over affects iteration count
        self.contents += "\nconfigopts = ['--one', '--two', '--three', '--four']"
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        self.assertEqual(eb.det_iter_cnt(), 4)

        # different lengths for iterative easyconfig parameters mean trouble during validation of iterative parameters
        self.contents += "\nbuildopts = ['FOO=one', 'FOO=two']"
        self.writeEC()

        error_pattern = "lists for iterated build should have same length"
        self.assertErrorRegex(EasyBuildError, error_pattern, EasyConfig, self.eb_file)

    def test_handle_iterate_opts(self):
        """Test for handle_iterate_opts method."""
        testdir = os.path.abspath(os.path.dirname(__file__))
        toy_ec = os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        write_file(test_ec, read_file(toy_ec) + "\nconfigopts = ['--opt1 --anotheropt', '--opt2', '--opt3 --optbis']")

        ec = process_easyconfig(test_ec)[0]
        eb = get_easyblock_instance(ec)

        # check initial state
        self.assertEqual(eb.iter_idx, 0)
        self.assertEqual(eb.iter_opts, {})
        self.assertEqual(eb.cfg.iterating, False)
        self.assertEqual(eb.cfg.iterate_options, [])
        self.assertEqual(eb.cfg['configopts'], ["--opt1 --anotheropt", "--opt2", "--opt3 --optbis"])

        expected_iter_opts = {'configopts': ["--opt1 --anotheropt", "--opt2", "--opt3 --optbis"]}

        # once iteration mode is set, we're still in iteration #0
        self.mock_stdout(True)
        eb.handle_iterate_opts()
        stdout = self.get_stdout()
        self.mock_stdout(False)
        self.assertEqual(eb.iter_idx, 0)
        self.assertEqual(stdout, "== starting iteration #0 ...\n")
        self.assertEqual(eb.cfg.iterating, True)
        self.assertEqual(eb.cfg.iterate_options, ['configopts'])
        self.assertEqual(eb.cfg['configopts'], "--opt1 --anotheropt")
        self.assertEqual(eb.iter_opts, expected_iter_opts)

        # when next iteration is start, iteration index gets bumped
        self.mock_stdout(True)
        eb.handle_iterate_opts()
        stdout = self.get_stdout()
        self.mock_stdout(False)
        self.assertEqual(eb.iter_idx, 1)
        self.assertEqual(stdout, "== starting iteration #1 ...\n")
        self.assertEqual(eb.cfg.iterating, True)
        self.assertEqual(eb.cfg.iterate_options, ['configopts'])
        self.assertEqual(eb.cfg['configopts'], "--opt2")
        self.assertEqual(eb.iter_opts, expected_iter_opts)

        self.mock_stdout(True)
        eb.handle_iterate_opts()
        stdout = self.get_stdout()
        self.mock_stdout(False)
        self.assertEqual(eb.iter_idx, 2)
        self.assertEqual(stdout, "== starting iteration #2 ...\n")
        self.assertEqual(eb.cfg.iterating, True)
        self.assertEqual(eb.cfg.iterate_options, ['configopts'])
        self.assertEqual(eb.cfg['configopts'], "--opt3 --optbis")
        self.assertEqual(eb.iter_opts, expected_iter_opts)

        eb.post_iter_step()
        self.assertEqual(eb.cfg.iterating, False)
        self.assertEqual(eb.cfg['configopts'], ["--opt1 --anotheropt", "--opt2", "--opt3 --optbis"])

    def test_extensions_step(self):
        """Test the extensions_step"""
        init_config(build_options={'silent': True})

        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = SYSTEM',
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

    def test_init_extensions(self):
        """Test creating extension instances."""

        testdir = os.path.abspath(os.path.dirname(__file__))
        toy_ec_file = os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-gompi-2018a-test.eb')
        toy_ec_txt = read_file(toy_ec_file)

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ec_txt = toy_ec_txt.replace("('barbar', '1.2', {", "('barbar', '1.2', {'easyblock': 'DummyExtension',")
        write_file(test_ec, test_ec_txt)
        ec = process_easyconfig(test_ec)[0]
        eb = get_easyblock_instance(ec)

        eb.prepare_for_extensions()
        eb.init_ext_instances()
        ext_inst_class_names = [x.__class__.__name__ for x in eb.ext_instances]
        expected = [
            'Toy_Extension',  # 'ls' extension
            'Toy_Extension',  # 'bar' extension
            'DummyExtension',  # 'barbar' extension
            'EB_toy',  # 'toy' extension
        ]
        self.assertEqual(ext_inst_class_names, expected)

        # check what happen if we specify an easyblock that doesn't derive from Extension,
        # and hence can't be used to install extensions...
        test_ec = os.path.join(self.test_prefix, 'test_broken.eb')
        test_ec_txt = test_ec_txt.replace('DummyExtension', 'ConfigureMake')
        write_file(test_ec, test_ec_txt)
        ec = process_easyconfig(test_ec)[0]
        eb = get_easyblock_instance(ec)

        eb.prepare_for_extensions()
        error_pattern = "ConfigureMake easyblock can not be used to install extensions"
        self.assertErrorRegex(EasyBuildError, error_pattern, eb.init_ext_instances)

    def test_extension_source_tmpl(self):
        """Test type checking for 'source_tmpl' value of an extension."""
        self.contents = '\n'.join([
            "easyblock = 'ConfigureMake'",
            "name = 'toy'",
            "version = '0.0'",
            "homepage = 'https://example.com'",
            "description = 'test'",
            "toolchain = SYSTEM",
            "exts_list = [",
            "    ('bar', '0.0', {",
            "         'source_tmpl': [SOURCE_TAR_GZ],",
            "    }),",
            "]",
        ])
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))

        error_pattern = r"source_tmpl value must be a string! "
        error_pattern += r"\(found value of type 'list'\): \['bar-0\.0\.tar\.gz'\]"
        self.assertErrorRegex(EasyBuildError, error_pattern, eb.fetch_step)

        self.contents = self.contents.replace("'source_tmpl': [SOURCE_TAR_GZ]", "'source_tmpl': SOURCE_TAR_GZ")
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.fetch_step()

    def test_skip_extensions_step(self):
        """Test the skip_extensions_step"""

        self.contents = cleandoc("""
            easyblock = "ConfigureMake"
            name = "pi"
            version = "3.14"
            homepage = "http://example.com"
            description = "test easyconfig"
            toolchain = SYSTEM
            exts_list = [
                "ext1",
                ("EXT-2", "42", {"source_tmpl": "dummy.tgz"}),
                ("ext3", "1.1", {"source_tmpl": "dummy.tgz", "modulename": "real_ext"}),
                "ext4",
            ]
            exts_filter = ("\
                if [ %(ext_name)s == 'ext_2' ] && [ %(ext_version)s == '42' ] && [[ %(src)s == *dummy.tgz ]];\
                    then exit 0;\
                elif [ %(ext_name)s == 'real_ext' ]; then exit 0;\
                else exit 1; fi", "")
            exts_defaultclass = "DummyExtension"
        """)
        # check if skip skips correct extensions
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.builddir = config.build_path()
        eb.installdir = config.install_path()
        eb.skip = True

        self.mock_stdout(True)
        eb.extensions_step(fetch=True)
        stdout = self.get_stdout()
        self.mock_stdout(False)

        patterns = [
            r"^== skipping extension EXT-2",
            r"^== skipping extension ext3",
            r"^== installing extension ext1  \(1/2\)\.\.\.",
            r"^== installing extension ext4  \(2/2\)\.\.\.",
        ]
        for pattern in patterns:
            regex = re.compile(pattern, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        # 'ext1' should be in eb.ext_instances
        eb_exts = [x.name for x in eb.ext_instances]
        self.assertIn('ext1', eb_exts)
        # 'EXT-2' should not
        self.assertNotIn('EXT-2', eb_exts)
        self.assertNotIn('ext_2', eb_exts)
        # 'ext3' should not
        self.assertNotIn('ext3', eb_exts)

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

    def test_make_module_step(self):
        """Test the make_module_step"""

        # put dummy hidden modules in place for test123 dependency
        test_mods = os.path.join(self.test_prefix, 'modules')
        write_file(os.path.join(test_mods, 'test', '.1.2.3'), '#%Module')
        self.modtool.use(test_mods)

        name = "pi"
        version = "3.14"
        # purposely use a 'nasty' description, that includes (unbalanced) special chars: [, ], {, }
        descr = "This {is a}} [fancy]] [[description]]. {{[[TEST}]"
        modextravars = {
            'PI': '3.1415',
            'FOO': 'bar',
        }

        # also test setting environment variables via pushenv for Lmod or recent Environment Modules
        is_modtool_ver51 = LooseVersion(self.modtool.version) >= LooseVersion('5.1')
        if isinstance(self.modtool, Lmod) or (isinstance(self.modtool, EnvironmentModules) and is_modtool_ver51):
            modextravars['TEST_PUSHENV'] = {'value': '123', 'pushenv': True}

        modextrapaths = {
            'PATH': ('xbin', 'pibin'),
            'CPATH': 'pi/include',
        }
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "%s"' % name,
            'version = "%s"' % version,
            'homepage = "http://example.com"',
            'description = "%s"' % descr,
            "toolchain = SYSTEM",
            "dependencies = [('GCC', '6.4.0-2.28'), ('test', '1.2.3')]",
            "builddependencies = [('OpenMPI', '2.1.2-GCC-6.4.0-2.28')]",
            # hidden deps must be included in list of (build)deps
            "hiddendependencies = [('test', '1.2.3'), ('OpenMPI', '2.1.2-GCC-6.4.0-2.28')]",
            "modextravars = %s" % str(modextravars),
            "modextrapaths = %s" % str(modextrapaths),
        ])

        # test if module is generated correctly
        self.writeEC()
        ec = EasyConfig(self.eb_file)
        eb = EasyBlock(ec)
        eb.installdir = os.path.join(config.install_path(), 'pi', '3.14')
        eb.check_readiness_step()
        eb.make_builddir()
        eb.prepare_step()

        # Create a dummy file in bin to test if the duplicate entry of modextrapaths is ignored
        os.makedirs(os.path.join(eb.installdir, 'bin'))
        write_file(os.path.join(eb.installdir, 'bin', 'dummy_exe'), 'hello')

        modpath = os.path.join(eb.make_module_step(), name, version)
        if get_module_syntax() == 'Lua':
            modpath += '.lua'
        self.assertExists(modpath)

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
            self.fail("Unknown module syntax: %s" % get_module_syntax())

        for (key, val) in modextravars.items():
            pushenv = False
            if isinstance(val, dict):
                pushenv = val.get('pushenv', False)
                val = val['value']

            env_setter = 'pushenv' if pushenv else 'setenv'

            if get_module_syntax() == 'Tcl':
                regex = re.compile(r'^%s\s+%s\s+"%s"$' % (env_setter, key, val), re.M)
            elif get_module_syntax() == 'Lua':
                regex = re.compile(r'^%s\("%s", "%s"\)$' % (env_setter, key, val), re.M)
            else:
                self.fail("Unknown module syntax: %s" % get_module_syntax())
            self.assertTrue(regex.search(txt), "Pattern %s found in %s" % (regex.pattern, txt))

        for (key, vals) in modextrapaths.items():
            if isinstance(vals, string_type):
                vals = [vals]
            for val in vals:
                if get_module_syntax() == 'Tcl':
                    regex = re.compile(r'^prepend-path\s+%s\s+\$root/%s$' % (key, val), re.M)
                elif get_module_syntax() == 'Lua':
                    regex = re.compile(r'^prepend_path\("%s", pathJoin\(root, "%s"\)\)$' % (key, val), re.M)
                else:
                    self.fail("Unknown module syntax: %s" % get_module_syntax())
                self.assertTrue(regex.search(txt), "Pattern %s found in %s" % (regex.pattern, txt))
                # Check for duplicates
                num_prepends = len(regex.findall(txt))
                self.assertEqual(num_prepends, 1, "Expected exactly 1 %s command in %s" % (regex.pattern, txt))

        for (name, ver) in [('GCC', '6.4.0-2.28')]:
            if get_module_syntax() == 'Tcl':
                regex = re.compile(r'^\s*module load %s\s*$' % os.path.join(name, ver), re.M)
            elif get_module_syntax() == 'Lua':
                regex = re.compile(r'^\s*load\("%s"\)$' % os.path.join(name, ver), re.M)
            else:
                self.fail("Unknown module syntax: %s" % get_module_syntax())
            self.assertTrue(regex.search(txt), "Pattern %s found in %s" % (regex.pattern, txt))

        for (name, ver) in [('test', '1.2.3')]:
            if get_module_syntax() == 'Tcl':
                regex = re.compile(r'^\s*module load %s/.%s\s*$' % (name, ver), re.M)
            elif get_module_syntax() == 'Lua':
                regex = re.compile(r'^\s*load\("%s/.%s"\)$' % (name, ver), re.M)
            else:
                self.fail("Unknown module syntax: %s" % get_module_syntax())
            self.assertTrue(regex.search(txt), "Pattern %s found in %s" % (regex.pattern, txt))

        for (name, ver) in [('OpenMPI', '2.1.2-GCC-6.4.0-2.28')]:
            if get_module_syntax() == 'Tcl':
                regex = re.compile(r'^\s*module load %s/.?%s\s*$' % (name, ver), re.M)
            elif get_module_syntax() == 'Lua':
                regex = re.compile(r'^\s*load\("%s/.?%s"\)$' % (name, ver), re.M)
            else:
                self.fail("Unknown module syntax: %s" % get_module_syntax())
            self.assertFalse(regex.search(txt), "Pattern '%s' *not* found in %s" % (regex.pattern, txt))

        os.environ['TEST_PUSHENV'] = '0'

        # also check whether generated module can be loaded
        self.modtool.load(['pi/3.14'])

        # check value for $TEST_PUSHENV
        if 'TEST_PUSHENV' in modextravars:
            self.assertEqual(os.environ['TEST_PUSHENV'], '123')

        self.modtool.unload(['pi/3.14'])
        self.assertEqual(os.environ['TEST_PUSHENV'], '0')

        # [==[ or ]==] in description is fatal
        if get_module_syntax() == 'Lua':
            error_pattern = r"Found unwanted '\[==\[' or '\]==\]' in: .*"
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
            "toolchain = SYSTEM",
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

    def test_make_builddir(self):
        """Test make_dir method."""
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            "name = 'pi'",
            "version = '3.14'",
            "homepage = 'http://example.com'",
            "description = 'test easyconfig'",
            "toolchain = SYSTEM",
        ])
        self.writeEC()

        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.gen_builddir()

        # by default, make_builddir will re-create the build directory (i.e. remove existing & re-create)
        eb.make_builddir()
        builddir = eb.builddir
        testfile = os.path.join(builddir, 'test123', 'foobar.txt')
        write_file(testfile, 'test123')
        self.assertExists(testfile)

        eb.make_builddir()
        self.assertEqual(builddir, eb.builddir)
        # file is gone because directory was removed and re-created
        self.assertNotExists(testfile)
        self.assertNotExists(os.path.dirname(testfile))
        self.assertEqual(os.listdir(eb.builddir), [])

        # make sure that build directory does *not* get re-created when we're building in installation directory
        # and we're iterating over a list of (pre)config/build/installopts
        eb.build_in_installdir = True
        eb.make_builddir()
        # also need to create install directory since build dir == install dir
        eb.make_installdir()
        builddir = eb.builddir
        testfile = os.path.join(builddir, 'test123', 'foobar.txt')
        write_file(testfile, 'test123')
        self.assertExists(testfile)
        self.assertEqual(os.listdir(eb.builddir), ['test123'])
        self.assertEqual(os.listdir(os.path.join(eb.builddir, 'test123')), ['foobar.txt'])

        # with iteration count > 0, build directory is not re-created because of build-in-installdir
        eb.iter_idx = 1
        eb.make_builddir()
        eb.make_installdir()
        self.assertEqual(builddir, eb.builddir)
        self.assertExists(testfile)
        self.assertEqual(os.listdir(eb.builddir), ['test123'])
        self.assertEqual(os.listdir(os.path.join(eb.builddir, 'test123')), ['foobar.txt'])

        # resetting iteration index to 0 results in re-creating build directory
        eb.iter_idx = 0
        eb.make_builddir()
        eb.make_installdir()
        self.assertEqual(builddir, eb.builddir)
        self.assertNotExists(testfile)
        self.assertNotExists(os.path.dirname(testfile))
        self.assertEqual(os.listdir(eb.builddir), [])

    def test_get_easyblock_instance(self):
        """Test get_easyblock_instance function."""
        from easybuild.easyblocks.toy import EB_toy
        testdir = os.path.abspath(os.path.dirname(__file__))

        ec = process_easyconfig(os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb'))[0]
        eb = get_easyblock_instance(ec)
        self.assertIsInstance(eb, EB_toy)

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

        custom_source_url = os.path.join(self.test_prefix, 'custom')
        toy_extra_txt = "This is a custom toy-extra.txt"
        write_file(os.path.join(custom_source_url, 'toy-extra.txt'), toy_extra_txt)

        # reset and try with provided list of sources
        eb.src = []
        sources = [
            {
                'download_filename': 'toy-extra.txt',
                'filename': 'toy-0.0-extra.txt',
                'source_urls': ['file://%s' % custom_source_url],
            },
            {
                'filename': 'toy-0.0_gzip.patch.gz',
                'extract_cmd': "gunzip %s",
            },
            {
                'download_filename': 'toy-0.0.tar.gz',
                'filename': 'toy-0.0-renamed.tar.gz',
                'extract_cmd': "tar xfz %s",
            },
        ]
        eb.fetch_sources(sources, checksums=[])

        toy_source_dir = os.path.join(self.test_prefix, 't', 'toy')
        expected_sources = ['toy-0.0-extra.txt', 'toy-0.0_gzip.patch.gz', 'toy-0.0-renamed.tar.gz']

        # make source sources were downloaded, using correct filenames
        self.assertEqual(len(eb.src), 3)
        for idx in range(3):
            self.assertEqual(eb.src[idx]['name'], expected_sources[idx])
            self.assertExists(eb.src[idx]['path'])
            source_loc = os.path.join(toy_source_dir, expected_sources[idx])
            self.assertExists(source_loc)
            self.assertTrue(os.path.samefile(eb.src[idx]['path'], source_loc))
        self.assertEqual(eb.src[0]['cmd'], None)
        self.assertEqual(eb.src[1]['cmd'], "gunzip %s")
        self.assertEqual(eb.src[2]['cmd'], "tar xfz %s")

        # make sure custom toy-extra.txt was picked up
        self.assertEqual(read_file(eb.src[0]['path']), toy_extra_txt)
        orig_toy_extra_txt = read_file(os.path.join(os.path.dirname(toy_source), 'toy-extra.txt'))
        self.assertNotEqual(read_file(eb.src[0]['path']), orig_toy_extra_txt)

        # old format for specifying source with custom extract command is deprecated
        eb.src = []
        error_msg = r"DEPRECATED \(since v4.0\).*Using a 2-element list/tuple.*"
        self.assertErrorRegex(EasyBuildError, error_msg, eb.fetch_sources,
                              [('toy-0.0_gzip.patch.gz', "gunzip %s")], checksums=[])

        # unknown dict keys in sources are reported
        sources[0]['nosuchkey'] = 'foobar'
        error_pattern = "Found one or more unexpected keys in 'sources' specification: {'nosuchkey': 'foobar'}"
        self.assertErrorRegex(EasyBuildError, error_pattern, eb.fetch_sources, sources, checksums=[])

    def test_download_instructions(self):
        """Test use of download_instructions easyconfig parameter."""

        # skip test when using Python 2, since it somehow fails then,
        # cfr. https://github.com/easybuilders/easybuild-framework/pull/4333
        if sys.version_info[0] == 2:
            print("Skipping test_download_instructions because Python 2.x is being used")
            return

        orig_test_ec = '\n'.join([
            "easyblock = 'ConfigureMake'",
            "name = 'software_with_missing_sources'",
            "version = '0.0'",
            "homepage = 'https://example.com'",
            "description = 'test'",
            "toolchain = SYSTEM",
            "sources = [SOURCE_TAR_GZ]",
            "exts_list = [",
            "    ('ext_with_missing_sources', '0.0', {",
            "         'sources': [SOURCE_TAR_GZ],",
            "    }),",
            "]",
        ])
        self.contents = orig_test_ec
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))

        common_error_pattern = "^Couldn't find file software_with_missing_sources-0.0.tar.gz anywhere"
        error_pattern = common_error_pattern + ", and downloading it didn't work either"
        self.assertErrorRegex(EasyBuildError, error_pattern, eb.fetch_step)

        download_instructions = "download_instructions = 'Manual download from example.com required'"
        sources = "sources = [SOURCE_TAR_GZ]"
        self.contents = self.contents.replace(sources, download_instructions + '\n' + sources)
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))

        error_pattern = common_error_pattern + ", please follow the download instructions above"
        self.mock_stderr(True)
        self.mock_stdout(True)
        self.assertErrorRegex(EasyBuildError, error_pattern, eb.fetch_step)
        stderr = self.get_stderr().strip()
        stdout = self.get_stdout().strip()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertEqual(stderr, "Download instructions:\n\nManual download from example.com required")
        self.assertEqual(stdout, '')

        # create dummy source file
        write_file(os.path.join(os.path.dirname(self.eb_file), 'software_with_missing_sources-0.0.tar.gz'), '')

        # now downloading of sources for extension should fail
        # top-level download instructions are printed (because there's nothing else)
        error_pattern = "^Couldn't find file ext_with_missing_sources-0.0.tar.gz anywhere"
        self.mock_stderr(True)
        self.mock_stdout(True)
        self.assertErrorRegex(EasyBuildError, error_pattern, eb.fetch_step)
        stderr = self.get_stderr().strip()
        stdout = self.get_stdout().strip()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertEqual(stderr, "Download instructions:\n\nManual download from example.com required")
        self.assertEqual(stdout, '')

        # wipe top-level download instructions, try again
        self.contents = self.contents.replace(download_instructions, '')
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))

        # no download instructions printed anymore now
        self.mock_stderr(True)
        self.mock_stdout(True)
        self.assertErrorRegex(EasyBuildError, error_pattern, eb.fetch_step)
        stderr = self.get_stderr().strip()
        stdout = self.get_stdout().strip()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertEqual(stdout, '')

        # inject download instructions for extension
        download_instructions = ' ' * 8 + "'download_instructions': "
        download_instructions += "'Extension sources must be downloaded via example.com',"
        sources = "'sources': [SOURCE_TAR_GZ],"
        self.contents = self.contents.replace(sources, sources + '\n' + download_instructions)
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))

        self.mock_stderr(True)
        self.mock_stdout(True)
        self.assertErrorRegex(EasyBuildError, error_pattern, eb.fetch_step)
        stderr = self.get_stderr().strip()
        stdout = self.get_stdout().strip()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertEqual(stderr, "Download instructions:\n\nExtension sources must be downloaded via example.com")
        self.assertEqual(stdout, '')

        # download instructions should also be printed if 'source_tmpl' is used to specify extension sources
        self.contents = self.contents.replace(sources, "'source_tmpl': SOURCE_TAR_GZ,")
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))

        self.mock_stderr(True)
        self.mock_stdout(True)
        self.assertErrorRegex(EasyBuildError, error_pattern, eb.fetch_step)
        stderr = self.get_stderr().strip()
        stdout = self.get_stdout().strip()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertEqual(stderr, "Download instructions:\n\nExtension sources must be downloaded via example.com")
        self.assertEqual(stdout, '')

        # create dummy source file for extension
        write_file(os.path.join(os.path.dirname(self.eb_file), 'ext_with_missing_sources-0.0.tar.gz'), '')

        # no more errors, all source files found (so no download instructions printed either)
        self.mock_stderr(True)
        self.mock_stdout(True)
        eb.fetch_step()
        stderr = self.get_stderr().strip()
        stdout = self.get_stdout().strip()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertEqual(stderr, '')
        self.assertEqual(stdout, '')

    def test_fetch_patches(self):
        """Test fetch_patches method."""
        testdir = os.path.abspath(os.path.dirname(__file__))
        ec = process_easyconfig(os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb'))[0]
        eb = get_easyblock_instance(ec)

        toy_patch = 'toy-0.0_fix-silly-typo-in-printf-statement.patch'
        eb.fetch_patches()
        self.assertEqual(len(eb.patches), 2)
        self.assertEqual(eb.patches[0]['name'], toy_patch)
        self.assertNotIn('level', eb.patches[0])

        # reset
        eb.patches = []

        patches = [
            (toy_patch, 0),  # should also be level 0 (not None or something else)
            (toy_patch, 4),   # should be level 4
            (toy_patch, 'foobar'),  # sourcepath should be set to 'foobar'
            ('toy-0.0.tar.gz', 'some/path'),  # copy mode (not a .patch file)
            {'name': toy_patch, 'level': 0, 'alt_location': 'alt_toy'},
        ]
        # check if patch levels are parsed correctly
        eb.fetch_patches(patch_specs=patches)

        self.assertEqual(len(eb.patches), 5)
        self.assertEqual(eb.patches[0]['name'], toy_patch)
        self.assertEqual(eb.patches[0]['level'], 0)
        self.assertEqual(eb.patches[1]['name'], toy_patch)
        self.assertEqual(eb.patches[1]['level'], 4)
        self.assertEqual(eb.patches[2]['name'], toy_patch)
        self.assertEqual(eb.patches[2]['sourcepath'], 'foobar')
        self.assertEqual(eb.patches[3]['name'], 'toy-0.0.tar.gz'),
        self.assertEqual(eb.patches[3]['copy'], 'some/path')
        self.assertEqual(eb.patches[4]['name'], toy_patch)
        self.assertEqual(eb.patches[4]['level'], 0)
        testdir = os.path.abspath(os.path.dirname(__file__))
        sandbox_sources = os.path.join(testdir, 'sandbox', 'sources')
        self.assertEqual(eb.patches[4]['path'], os.path.join(sandbox_sources, 'alt_toy', toy_patch))

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
        alt_toy_tarball_path = os.path.join(sandbox_sources, 'alt_toy', toy_tarball)
        tmpdir = tempfile.mkdtemp()
        tmpdir_subdir = os.path.join(tmpdir, 'testing')
        mkdir(tmpdir_subdir, parents=True)
        del os.environ['EASYBUILD_SOURCEPATH']  # defined by setUp

        toy_ec = os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        test_ec = os.path.join(tmpdir, 'ecs', 'test.eb')
        copy_file(toy_ec, test_ec)

        ec = process_easyconfig(test_ec)[0]
        eb = EasyBlock(ec['ec'])

        # 'downloading' a file to (first) sourcepath works
        init_config(args=["--sourcepath=%s:/no/such/dir:%s" % (tmpdir, testdir)])
        shutil.copy2(toy_tarball_path, tmpdir_subdir)
        res = eb.obtain_file(toy_tarball, urls=['file://%s' % tmpdir_subdir])
        self.assertEqual(res, os.path.join(tmpdir, 't', 'toy', toy_tarball))

        # test no_download option
        urls = ['file://%s' % tmpdir_subdir]
        error_pattern = "Couldn't find file toy-0.0.tar.gz anywhere, and downloading it is disabled"
        self.assertErrorRegex(EasyBuildError, error_pattern, eb.obtain_file,
                              toy_tarball, urls=urls, alt_location='alt_toy', no_download=True)

        # 'downloading' a file to (first) alternative sourcepath works
        res = eb.obtain_file(toy_tarball, urls=urls, alt_location='alt_toy')
        self.assertEqual(res, os.path.join(tmpdir, 'a', 'alt_toy', toy_tarball))

        # make sure that directory in which easyconfig file is located is *ignored* when alt_location is used
        dummy_toy_tar_gz = os.path.join(os.path.dirname(test_ec), 'toy-0.0.tar.gz')
        write_file(dummy_toy_tar_gz, '')
        res = eb.obtain_file(toy_tarball, urls=['file://%s' % tmpdir_subdir])
        self.assertEqual(res, dummy_toy_tar_gz)
        res = eb.obtain_file(toy_tarball, urls=['file://%s' % tmpdir_subdir], alt_location='alt_toy')
        self.assertEqual(res, os.path.join(tmpdir, 'a', 'alt_toy', toy_tarball))
        remove_file(dummy_toy_tar_gz)

        # finding a file in sourcepath works
        init_config(args=["--sourcepath=%s:/no/such/dir:%s" % (sandbox_sources, tmpdir)])
        res = eb.obtain_file(toy_tarball)
        self.assertEqual(res, toy_tarball_path)

        # finding a file in the alternate location works
        res = eb.obtain_file(toy_tarball, alt_location='alt_toy')
        self.assertEqual(res, alt_toy_tarball_path)

        # sourcepath has preference over downloading
        res = eb.obtain_file(toy_tarball, urls=['file://%s' % tmpdir_subdir])
        self.assertEqual(res, toy_tarball_path)
        res = eb.obtain_file(toy_tarball, urls=['file://%s' % tmpdir_subdir], alt_location='alt_toy')
        self.assertEqual(res, alt_toy_tarball_path)

        init_config(args=["--sourcepath=%s:%s" % (tmpdir, sandbox_sources)])

        # clean up toy tarballs in tmpdir, so the one in sourcepath is found
        remove_file(os.path.join(tmpdir, toy_tarball))
        remove_file(os.path.join(tmpdir, 't', 'toy', toy_tarball))
        remove_file(os.path.join(tmpdir, 'a', 'alt_toy', toy_tarball))

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
        self.assertExists(os.path.join(tmpdir, 't', 'toy', toy_tarball))

        # obtain_file yields error for non-existing files
        fn = 'thisisclearlyanonexistingfile'
        error_regex = "Couldn't find file %s anywhere, and downloading it didn't work either" % fn
        self.assertErrorRegex(EasyBuildError, error_regex, eb.obtain_file, fn, urls=['file://%s' % tmpdir_subdir])

        # also test triggering error when downloading from a URL that includes URL-encoded characters
        # cfr. https://github.com/easybuilders/easybuild-framework/pull/4005
        url = 'file://%s' % os.path.dirname(tmpdir_subdir)
        url += '%2F' + os.path.basename(tmpdir_subdir)
        self.assertErrorRegex(EasyBuildError, error_regex, eb.obtain_file, fn, urls=[url])

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
            except EasyBuildError as err:
                # if this fails, it should be because there's no online access
                download_fail_regex = re.compile('socket error')
                self.assertTrue(download_fail_regex.search(str(err)))

            # result may be None during offline testing
            if res is not None:
                loc = os.path.join(tmpdir, 't', 'toy', fn)
                self.assertEqual(res, loc)
                self.assertExists(loc)
                txt = read_file(loc)
                eb_regex = re.compile("EasyBuild: building software with ease")
                self.assertTrue(eb_regex.search(txt), "Pattern '%s' found in: %s" % (eb_regex.pattern, txt))
            else:
                print("ignoring failure to download %s in test_obtain_file, testing offline?" % file_url)

        shutil.rmtree(tmpdir)

    def test_fallback_source_url(self):
        """Check whether downloading from fallback source URL https://sources.easybuild.io works."""
        # cfr. https://github.com/easybuilders/easybuild-easyconfigs/issues/11951

        init_config(args=["--sourcepath=%s" % self.test_prefix])

        udunits_ec = os.path.join(self.test_prefix, 'UDUNITS.eb')
        udunits_ec_txt = '\n'.join([
            "easyblock = 'ConfigureMake'",
            "name = 'UDUNITS'",
            "version = '2.2.26'",
            "homepage = 'https://www.unidata.ucar.edu/software/udunits'",
            "description = 'UDUNITS'",
            "toolchain = {'name': 'GCC', 'version': '4.8.2'}",
            "source_urls = ['https://broken.source.urls/nosuchdirectory']",
            "sources = [SOURCELOWER_TAR_GZ]",
            "checksums = ['368f4869c9c7d50d2920fa8c58654124e9ed0d8d2a8c714a9d7fdadc08c7356d']",
        ])
        write_file(udunits_ec, udunits_ec_txt)

        ec = process_easyconfig(udunits_ec)[0]
        eb = EasyBlock(ec['ec'])

        eb.fetch_step()

        expected_path = os.path.join(self.test_prefix, 'u', 'UDUNITS', 'udunits-2.2.26.tar.gz')
        self.assertTrue(os.path.samefile(eb.src[0]['path'], expected_path))

        self.assertTrue(verify_checksum(expected_path, eb.cfg['checksums'][0]))

    def test_collect_exts_file_info(self):
        """Test collect_exts_file_info method."""
        testdir = os.path.abspath(os.path.dirname(__file__))
        toy_sources = os.path.join(testdir, 'sandbox', 'sources', 'toy')
        toy_ext_sources = os.path.join(toy_sources, 'extensions')
        toy_ec_file = os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-gompi-2018a-test.eb')
        toy_ec = process_easyconfig(toy_ec_file)[0]
        toy_eb = EasyBlock(toy_ec['ec'])

        exts_file_info = toy_eb.collect_exts_file_info()

        self.assertIsInstance(exts_file_info, list)
        self.assertEqual(len(exts_file_info), 4)

        self.assertEqual(exts_file_info[0], {'name': 'ulimit'})

        self.assertEqual(exts_file_info[1]['name'], 'bar')
        self.assertEqual(exts_file_info[1]['src'], os.path.join(toy_ext_sources, 'bar-0.0.tar.gz'))
        bar_patch1 = 'bar-0.0_fix-silly-typo-in-printf-statement.patch'
        self.assertEqual(exts_file_info[1]['patches'][0]['name'], bar_patch1)
        self.assertEqual(exts_file_info[1]['patches'][0]['path'], os.path.join(toy_ext_sources, bar_patch1))
        bar_patch2 = 'bar-0.0_fix-very-silly-typo-in-printf-statement.patch'
        self.assertEqual(exts_file_info[1]['patches'][1]['name'], bar_patch2)
        self.assertEqual(exts_file_info[1]['patches'][1]['path'], os.path.join(toy_ext_sources, bar_patch2))

        self.assertEqual(exts_file_info[2]['name'], 'barbar')
        self.assertEqual(exts_file_info[2]['src'], os.path.join(toy_ext_sources, 'barbar-1.2.tar.gz'))
        self.assertNotIn('patches', exts_file_info[2])

        self.assertEqual(exts_file_info[3]['name'], 'toy')
        self.assertEqual(exts_file_info[3]['src'], os.path.join(toy_sources, 'toy-0.0.tar.gz'))
        self.assertNotIn('patches', exts_file_info[3])

        # location of files is missing when fetch_files is set to False
        exts_file_info = toy_eb.collect_exts_file_info(fetch_files=False, verify_checksums=False)

        self.assertIsInstance(exts_file_info, list)
        self.assertEqual(len(exts_file_info), 4)

        self.assertEqual(exts_file_info[0], {'name': 'ulimit'})

        self.assertEqual(exts_file_info[1]['name'], 'bar')
        self.assertNotIn('src', exts_file_info[1])
        self.assertEqual(exts_file_info[1]['patches'][0]['name'], bar_patch1)
        self.assertNotIn('path', exts_file_info[1]['patches'][0])
        self.assertEqual(exts_file_info[1]['patches'][1]['name'], bar_patch2)
        self.assertNotIn('path', exts_file_info[1]['patches'][1])

        self.assertEqual(exts_file_info[2]['name'], 'barbar')
        self.assertNotIn('src', exts_file_info[2])
        self.assertNotIn('patches', exts_file_info[2])

        self.assertEqual(exts_file_info[3]['name'], 'toy')
        self.assertNotIn('src', exts_file_info[3])
        self.assertNotIn('patches', exts_file_info[3])

        error_msg = "Can't verify checksums for extension files if they are not being fetched"
        self.assertErrorRegex(EasyBuildError, error_msg, toy_eb.collect_exts_file_info, fetch_files=False)

    def test_obtain_file_extension(self):
        """Test use of obtain_file method on an extension."""

        testdir = os.path.abspath(os.path.dirname(__file__))
        toy_ec_file = os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-gompi-2018a-test.eb')
        toy_ec = process_easyconfig(toy_ec_file)[0]
        toy_eb = EasyBlock(toy_ec['ec'])

        toy_eb.fetch_step()

        test_ext = toy_eb.exts[-1]
        test_ext_src_fn = os.path.basename(test_ext['src'])

        ext = ExtensionEasyBlock(toy_eb, test_ext)
        ext_src_path = ext.obtain_file(test_ext_src_fn)
        self.assertEqual(os.path.basename(ext_src_path), 'toy-0.0.tar.gz')
        self.assertExists(ext_src_path)

    def test_check_readiness(self):
        """Test check_readiness method."""
        init_config(build_options={'validate': False, 'silent': True})

        # check that check_readiness step works (adding dependencies, etc.)
        ec_file = 'OpenMPI-2.1.2-GCC-6.4.0-2.28.eb'
        topdir = os.path.dirname(os.path.abspath(__file__))
        ec_path = os.path.join(topdir, 'easyconfigs', 'test_ecs', 'o', 'OpenMPI', ec_file)
        ec = EasyConfig(ec_path)
        eb = EasyBlock(ec)
        eb.check_readiness_step()

        # a proper error should be thrown for dependencies that can't be resolved (module should be there)
        tmpdir = tempfile.mkdtemp()
        shutil.copy2(ec_path, tmpdir)
        ec_path = os.path.join(tmpdir, ec_file)
        write_file(ec_path, "\ndependencies += [('nosuchsoftware', '1.2.3')]\n", append=True)
        ec = EasyConfig(ec_path)
        eb = EasyBlock(ec)
        try:
            eb.check_readiness_step()
        except EasyBuildError as err:
            err_regex = re.compile("Missing modules dependencies .*: nosuchsoftware/1.2.3-GCC-6.4.0-2.28")
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

        intel_ver = '2016.1.150-GCC-4.9.3-2.25'
        impi_modfile_path = os.path.join('Compiler', 'intel', intel_ver, 'impi', '5.1.2.150')
        imkl_modfile_path = os.path.join('MPI', 'intel', intel_ver, 'impi', '5.1.2.150', 'imkl', '11.3.1.150')
        if get_module_syntax() == 'Lua':
            impi_modfile_path += '.lua'
            imkl_modfile_path += '.lua'

        # example: for imkl on top of iimpi toolchain with HierarchicalMNS, no module load statements should be included
        # not for the toolchain or any of the toolchain components,
        # since both icc/ifort and impi form the path to the top of the module tree
        iccifort_mods = ['icc', 'ifort', 'iccifort']
        tests = [
            ('i/impi/impi-5.1.2.150-iccifort-2016.1.150-GCC-4.9.3-2.25.eb', impi_modfile_path, iccifort_mods),
            ('i/imkl/imkl-11.3.1.150-iimpi-2016.01.eb', imkl_modfile_path, iccifort_mods + ['iimpi', 'impi']),
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
                    self.fail("Unknown module syntax: %s" % get_module_syntax())

        # modpath_extensions_for should spit out correct result, even if modules are loaded
        icc_mod = 'icc/%s' % intel_ver
        impi_mod = 'impi/5.1.2.150'
        self.modtool.load([icc_mod])
        self.assertIn(impi_modfile_path, self.modtool.show(impi_mod))
        self.modtool.load([impi_mod])
        expected = {
            icc_mod: [os.path.join(modpath, 'Compiler', 'intel', intel_ver)],
            impi_mod: [os.path.join(modpath, 'MPI', 'intel', intel_ver, 'impi', '5.1.2.150')],
        }
        self.assertEqual(self.modtool.modpath_extensions_for([icc_mod, impi_mod]), expected)

    def test_patch_step(self):
        """Test patch step."""
        test_easyconfigs = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        ec = process_easyconfig(os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb'))[0]
        orig_sources = ec['ec']['sources'][:]

        toy_patches = [
            'toy-0.0_fix-silly-typo-in-printf-statement.patch',  # test for applying patch
            ('toy-extra.txt', 'toy-0.0'),  # test for patch-by-copy
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
        self.assertEqual(sorted(os.listdir(toydir)), ['toy-extra.txt', 'toy.source'])
        self.assertIn("and very proud of it", read_file(os.path.join(toydir, 'toy.source')))
        self.assertEqual(read_file(os.path.join(toydir, 'toy-extra.txt')), 'moar!\n')

        # check again with backup of patched files enabled
        update_build_option('backup_patched_files', True)
        eb = EasyBlock(ec['ec'])
        eb.fetch_step()
        eb.extract_step()
        eb.patch_step()
        # verify that patches were applied
        toydir = os.path.join(eb.builddir, 'toy-0.0')
        self.assertEqual(sorted(os.listdir(toydir)), ['toy-extra.txt', 'toy.source', 'toy.source.orig'])
        self.assertIn("and very proud of it", read_file(os.path.join(toydir, 'toy.source')))
        self.assertNotIn("and very proud of it", read_file(os.path.join(toydir, 'toy.source.orig')))
        self.assertEqual(read_file(os.path.join(toydir, 'toy-extra.txt')), 'moar!\n')

    def test_extensions_sanity_check(self):
        """Test sanity check aspect of extensions."""
        init_config(build_options={'silent': True})

        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec_fn = os.path.join(test_ecs_dir, 't', 'toy', 'toy-0.0-gompi-2018a-test.eb')

        # Do this before loading the easyblock to check the non-translated output below
        os.environ['LC_ALL'] = 'C'
        os.environ['LANG'] = 'C'

        # this import only works here, since EB_toy is a test easyblock
        from easybuild.easyblocks.toy import EB_toy

        # purposely inject failing custom extension filter for last extension
        toy_ec = EasyConfig(toy_ec_fn)
        with toy_ec.disable_templating():
            exts_list = toy_ec['exts_list']
            exts_list[-1][2]['exts_filter'] = ("thisshouldfail", '')
            toy_ec['exts_list'] = exts_list

        eb = EB_toy(toy_ec)
        eb.silent = True
        error_pattern = r"Sanity check failed: extensions sanity check failed for 1 extensions: toy\n"
        error_pattern += r"failing sanity check for 'toy' extension: "
        error_pattern += r'command "thisshouldfail" failed; output:\n/bin/bash:.* thisshouldfail: command not found'
        self.assertErrorRegex(EasyBuildError, error_pattern, eb.run_all_steps, True)

        # purposely put sanity check command in place that breaks the build,
        # to check whether sanity check is only run once;
        # sanity check commands are checked after checking sanity check paths, so this should work
        toy_ec = EasyConfig(toy_ec_fn)
        toy_ec.update('sanity_check_commands', [("%(installdir)s/bin/toy && rm %(installdir)s/bin/toy", '')])
        eb = EB_toy(toy_ec)
        eb.silent = True
        eb.run_all_steps(True)

    def test_parallel(self):
        """Test defining of parallelism."""
        topdir = os.path.abspath(os.path.dirname(__file__))
        toy_ec = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        toytxt = read_file(toy_ec)

        handle, toy_ec1 = tempfile.mkstemp(prefix='easyblock_test_file_', suffix='.eb')
        os.close(handle)
        write_file(toy_ec1, toytxt + "\nparallel = 123")

        handle, toy_ec2 = tempfile.mkstemp(prefix='easyblock_test_file_', suffix='.eb')
        os.close(handle)
        write_file(toy_ec2, toytxt + "\nparallel = 123\nmaxparallel = 67")

        handle, toy_ec3 = tempfile.mkstemp(prefix='easyblock_test_file_', suffix='.eb')
        os.close(handle)
        write_file(toy_ec3, toytxt + "\nparallel = False")

        # default: parallelism is derived from # available cores + ulimit
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

        # make sure 'parallel = False' is not overriden (no 'parallel' build option)
        test_eb = EasyBlock(EasyConfig(toy_ec3))
        test_eb.check_readiness_step()
        self.assertEqual(test_eb.cfg['parallel'], False)

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

        # make sure 'parallel = False' is not overriden (with 'parallel' build option)
        test_eb = EasyBlock(EasyConfig(toy_ec3))
        test_eb.check_readiness_step()
        self.assertEqual(test_eb.cfg['parallel'], 0)

    def test_guess_start_dir(self):
        """Test guessing the start dir."""
        test_easyconfigs = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        ec = process_easyconfig(os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb'))[0]

        cwd = os.getcwd()
        self.assertExists(cwd)

        def check_start_dir(expected_start_dir):
            """Check start dir."""
            # make sure we're in an existing directory at the start
            change_dir(cwd)
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

    def test_extension_set_start_dir(self):
        """Test start dir with extensions."""
        test_easyconfigs = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        ec = process_easyconfig(os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb'))[0]

        cwd = os.getcwd()
        self.assertExists(cwd)

        def check_ext_start_dir(expected_start_dir, unpack_src=True):
            """Check start dir."""
            # make sure we're in an existing directory at the start
            change_dir(cwd)
            eb = EasyBlock(ec['ec'])
            eb.extensions_step(fetch=True, install=False)
            # extract sources of the extension
            ext = eb.ext_instances[-1]
            ext.run(unpack_src=unpack_src)

            if expected_start_dir is None:
                self.assertIsNone(ext.start_dir)
            else:
                self.assertTrue(os.path.isabs(ext.start_dir))
                if ext.start_dir != os.sep:
                    self.assertFalse(ext.start_dir.endswith(os.sep))
                if os.path.isabs(expected_start_dir):
                    abs_expected_start_dir = expected_start_dir
                else:
                    abs_expected_start_dir = os.path.join(eb.builddir, expected_start_dir)
                self.assertEqual(ext.start_dir, abs_expected_start_dir)
                if not os.path.exists(eb.builddir):
                    eb.make_builddir()  # Required to exist for samefile
                self.assertTrue(os.path.samefile(ext.start_dir, abs_expected_start_dir))
            if unpack_src:
                self.assertTrue(os.path.samefile(os.getcwd(), abs_expected_start_dir))
            else:
                # When not unpacking we don't change the CWD
                self.assertEqual(os.getcwd(), cwd)
            remove_dir(eb.builddir)

        ec['ec']['exts_defaultclass'] = 'DummyExtension'

        # default (no start_dir specified): use unpacked dir as start dir
        ec['ec']['exts_list'] = [
            ('barbar', '0.0', {}),
        ]
        with self.mocked_stdout_stderr():
            check_ext_start_dir('barbar/barbar-0.0')
            check_ext_start_dir(None, unpack_src=False)
            self.assertFalse(self.get_stderr())

        # use start dir defined in extension
        ec['ec']['exts_list'] = [
            ('barbar', '0.0', {
                'start_dir': 'src'}),
        ]
        with self.mocked_stdout_stderr():
            check_ext_start_dir('barbar/barbar-0.0/src')
            self.assertFalse(self.get_stderr())

        # clean error when specified start dir does not exist
        ec['ec']['exts_list'] = [
            ('barbar', '0.0', {
                'start_dir': 'nonexistingdir'}),
        ]
        with self.mocked_stdout_stderr():
            err_pattern = "Failed to change from .*barbar/barbar-0.0 to nonexistingdir.*"
            self.assertErrorRegex(EasyBuildError, err_pattern, check_ext_start_dir, 'whatever')
            stderr = self.get_stderr()
        warning_pattern = "WARNING: Provided start dir (nonexistingdir) for extension barbar does not exist"
        self.assertIn(warning_pattern, stderr)

        # No error when using relative path in non-extracted source for some reason
        ec['ec']['exts_list'] = [
            ('barbar', '0.0', {
                'start_dir': '.'}),  # The build directory which does exist
        ]
        with self.mocked_stdout_stderr():
            check_ext_start_dir('.', unpack_src=False)
            self.assertFalse(self.get_stderr())

        # Keep absolute path in start_dir
        assert os.path.isabs(self.test_prefix)
        ec['ec']['exts_list'] = [
            ('barbar', '0.0', {
                'start_dir': self.test_prefix}),
        ]
        with self.mocked_stdout_stderr():
            check_ext_start_dir(self.test_prefix, unpack_src=False)
            self.assertFalse(self.get_stderr())

        # Support / (absolute path) if explicitely requested
        ec['ec']['exts_list'] = [
            ('barbar', '0.0', {
                'start_dir': os.sep}),
        ]
        with self.mocked_stdout_stderr():
            check_ext_start_dir(os.sep, unpack_src=False)
            self.assertFalse(self.get_stderr())

    def test_prepare_step(self):
        """Test prepare step (setting up build environment)."""
        test_easyconfigs = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        ec = process_easyconfig(os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb'))[0]

        mkdir(os.path.join(self.test_buildpath, 'toy', '0.0', 'system-system'), parents=True)
        eb = EasyBlock(ec['ec'])
        eb.silent = True
        eb.prepare_step()
        self.assertEqual(self.modtool.list(), [])

        os.environ['THIS_IS_AN_UNWANTED_ENV_VAR'] = 'foo'
        eb.cfg['unwanted_env_vars'] = ['THIS_IS_AN_UNWANTED_ENV_VAR']

        eb.cfg['allow_system_deps'] = [('Python', '1.2.3')]

        init_config(build_options={'extra_modules': ['GCC/6.4.0-2.28']})

        eb.prepare_step()

        self.assertEqual(os.environ.get('THIS_IS_AN_UNWANTED_ENV_VAR'), None)
        self.assertEqual(os.environ.get('EBROOTPYTHON'), 'Python')
        self.assertEqual(os.environ.get('EBVERSIONPYTHON'), '1.2.3')
        self.assertEqual(len(self.modtool.list()), 1)
        self.assertEqual(self.modtool.list()[0]['mod_name'], 'GCC/6.4.0-2.28')

    def test_prepare_step_load_tc_deps_modules(self):
        """Test disabling loading of toolchain + dependencies in build environment."""

        init_config(build_options={'robot_path': os.environ['EASYBUILD_ROBOT_PATHS']})

        test_easyconfigs = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        ompi_ec_file = os.path.join(test_easyconfigs, 'o', 'OpenMPI', 'OpenMPI-2.1.2-GCC-6.4.0-2.28.eb')
        ec = process_easyconfig(ompi_ec_file, validate=False)[0]

        mkdir(os.path.join(self.test_buildpath, 'OpenMPI', '2.1.2', 'GCC-6.4.0-2.28'), parents=True)
        eb = EasyBlock(ec['ec'])
        eb.silent = True

        # $EBROOTGCC and $EBROOTHWLOC must be set to set up build environment
        os.environ['EBROOTGCC'] = self.test_prefix
        os.environ['EBROOTHWLOC'] = self.test_prefix

        # loaded of modules for toolchain + dependencies can be disabled via load_tc_deps_modules=False
        eb.prepare_step(load_tc_deps_modules=False)
        self.assertEqual(self.modtool.list(), [])

        del os.environ['EBROOTGCC']
        del os.environ['EBROOTHWLOC']

        # modules for toolchain + dependencies are still loaded by default
        eb.prepare_step()
        loaded_modules = self.modtool.list()
        self.assertEqual(len(loaded_modules), 2)
        self.assertEqual(loaded_modules[0]['mod_name'], 'GCC/6.4.0-2.28')
        self.assertTrue(os.environ['EBROOTGCC'])
        self.assertEqual(loaded_modules[1]['mod_name'], 'hwloc/1.11.8-GCC-6.4.0-2.28')
        self.assertTrue(os.environ['EBROOTHWLOC'])

    def test_prepare_step_hmns(self):
        """
        Check whether loading of already existing dependencies during prepare step works when HierarchicalMNS is used.
        """
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')

        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = 'HierarchicalMNS'
        init_config(build_options={'robot_path': [test_ecs]})

        # set up hierarchical modules, but reset $MODULEPATH to empty
        # the expectation is that EasyBuild set's up the $MODULEPATH such that pre-installed dependencies can be loaded
        # see also https://github.com/easybuilders/easybuild-framework/issues/2186
        self.setup_hierarchical_modules()

        self.assertIn('GCC/6.4.0-2.28', self.modtool.available())

        self.reset_modulepath([])
        self.assertEqual(os.environ.get('MODULEPATH'), None)

        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')

        test_ec = os.path.join(self.test_prefix, 'test.eb')
        regex = re.compile('^toolchain = .*', re.M)
        test_ectxt = regex.sub("toolchain = SYSTEM", read_file(toy_ec))
        test_ectxt += "\ndependencies = [('GCC', '6.4.0', '-2.28')]"
        write_file(test_ec, test_ectxt)

        test_ec = process_easyconfig(test_ec)[0]
        eb = EasyBlock(test_ec['ec'])

        mkdir(os.path.join(self.test_buildpath, 'toy', '0.0', 'system-system'), parents=True)
        eb.prepare_step()

        loaded_modules = self.modtool.list()
        self.assertEqual(len(loaded_modules), 1)
        self.assertEqual(loaded_modules[0]['mod_name'], 'GCC/6.4.0-2.28')

    def test_prepare_step_cuda_cache(self):
        """Test handling cuda-cache-* options."""

        init_config(build_options={'cuda_cache_maxsize': None})  # Automatic mode

        test_ecs = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')
        ec = process_easyconfig(toy_ec)[0]
        eb = EasyBlock(ec['ec'])
        eb.silent = True
        eb.make_builddir()

        eb.prepare_step(start_dir=False)
        logtxt = read_file(eb.logfile)
        self.assertNotIn('Disabling CUDA PTX cache', logtxt)
        self.assertNotIn('Enabling CUDA PTX cache', logtxt)

        # Now with CUDA
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        test_ectxt = re.sub('^toolchain = .*', "toolchain = {'name': 'gcccuda', 'version': '2018a'}",
                            read_file(toy_ec), flags=re.M)
        write_file(test_ec, test_ectxt)
        ec = process_easyconfig(test_ec)[0]
        eb = EasyBlock(ec['ec'])
        eb.silent = True
        eb.make_builddir()

        write_file(eb.logfile, '')
        eb.prepare_step(start_dir=False)
        logtxt = read_file(eb.logfile)
        self.assertNotIn('Disabling CUDA PTX cache', logtxt)
        self.assertIn('Enabling CUDA PTX cache', logtxt)
        self.assertEqual(os.environ['CUDA_CACHE_DISABLE'], '0')

        init_config(build_options={'cuda_cache_maxsize': 0})  # Disable
        write_file(eb.logfile, '')
        eb.prepare_step(start_dir=False)
        logtxt = read_file(eb.logfile)
        self.assertIn('Disabling CUDA PTX cache', logtxt)
        self.assertNotIn('Enabling CUDA PTX cache', logtxt)
        self.assertEqual(os.environ['CUDA_CACHE_DISABLE'], '1')

        # Specified size and location
        cuda_cache_dir = os.path.join(self.test_prefix, 'custom-cuda-cache')
        init_config(build_options={'cuda_cache_maxsize': 1234, 'cuda_cache_dir': cuda_cache_dir})
        write_file(eb.logfile, '')
        eb.prepare_step(start_dir=False)
        logtxt = read_file(eb.logfile)
        self.assertNotIn('Disabling CUDA PTX cache', logtxt)
        self.assertIn('Enabling CUDA PTX cache', logtxt)
        self.assertEqual(os.environ['CUDA_CACHE_DISABLE'], '0')
        self.assertEqual(os.environ['CUDA_CACHE_MAXSIZE'], str(1234 * 1024 * 1024))
        self.assertEqual(os.environ['CUDA_CACHE_PATH'], cuda_cache_dir)

    def test_checksum_step(self):
        """Test checksum step"""
        testdir = os.path.abspath(os.path.dirname(__file__))
        toy_ec = os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-gompi-2018a-test.eb')

        ec = process_easyconfig(toy_ec)[0]
        eb = get_easyblock_instance(ec)
        eb.fetch_sources()
        eb.checksum_step()

        with self.mocked_stdout_stderr() as (stdout, stderr):

            # using checksum-less test easyconfig in location that does not provide checksums.json
            test_ec = os.path.join(self.test_prefix, 'test-no-checksums.eb')
            copy_file(toy_ec, test_ec)
            write_file(test_ec, 'checksums = []', append=True)
            ec = process_easyconfig(test_ec)[0]

            # enable logging to screen, so we can check whether error is logged when checksums.json is not found
            fancylogger.logToScreen(enable=True, stdout=True)

            eb = get_easyblock_instance(ec)
            eb.fetch_sources()
            eb.checksum_step()

            fancylogger.logToScreen(enable=False, stdout=True)
            stdout = self.get_stdout()

            # make sure there's no error logged for not finding checksums.json,
            # see also https://github.com/easybuilders/easybuild-framework/issues/4301
            regex = re.compile("ERROR .*Couldn't find file checksums.json anywhere", re.M)
            self.assertFalse(regex.search(stdout), "Pattern '%s' should not be found in log" % regex.pattern)

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
        error_msg = "Checksum verification for .*/toy-0.0.tar.gz using .* failed"
        self.assertErrorRegex(EasyBuildError, error_msg, eb.checksum_step)

        # also check verification of checksums for extensions, which is part of collect_exts_file_info
        error_msg = "Checksum verification for extension source bar-0.0.tar.gz failed"
        self.assertErrorRegex(EasyBuildError, error_msg, eb.collect_exts_file_info)

        # also check with deprecated fetch_extension_sources method
        self.allow_deprecated_behaviour()
        self.mock_stderr(True)
        self.assertErrorRegex(EasyBuildError, error_msg, eb.fetch_extension_sources)
        self.mock_stderr(False)
        self.disallow_deprecated_behaviour()

        # create test easyconfig from which checksums have been stripped
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        ectxt = read_file(toy_ec)
        regex = re.compile(r"'?checksums'?\s*[=:]\s*\[[^]]+\].*", re.M)
        ectxt = regex.sub('', ectxt)
        write_file(test_ec, ectxt)

        ec_json = process_easyconfig(test_ec)[0]

        # make sure that test easyconfig file indeed doesn't contain any checksums (either top-level or for extensions)
        self.assertEqual(ec_json['ec']['checksums'], [])
        for ext in ec_json['ec']['exts_list']:
            if isinstance(ext, string_type):
                continue
            elif isinstance(ext, tuple):
                self.assertEqual(ext[2].get('checksums', []), [])
            else:
                self.fail("Incorrect extension type: %s" % type(ext))

        # put checksums.json in place next to easyconfig file being used for the tests
        toy_checksums_json = os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'checksums.json')
        copy_file(toy_checksums_json, os.path.join(self.test_prefix, 'checksums.json'))

        # test without checksums, it should work since they are in checksums.json
        eb_json = get_easyblock_instance(ec_json)
        eb_json.fetch_sources()
        eb_json.checksum_step()

        # if we look only at checksums in Json, it should succeed
        eb = get_easyblock_instance(ec)
        build_options = {
            'checksum_priority': config.CHECKSUM_PRIORITY_JSON
        }
        init_config(build_options=build_options)
        eb.fetch_sources()
        eb.checksum_step()

        # if we look only at (incorrect) checksums in easyconfig, it should fail
        eb = get_easyblock_instance(ec)
        build_options = {
            'checksum_priority': config.CHECKSUM_PRIORITY_EASYCONFIG
        }
        init_config(build_options=build_options)
        eb.fetch_sources()
        error_msg = "Checksum verification for .*/toy-0.0.tar.gz using .* failed"
        self.assertErrorRegex(EasyBuildError, error_msg, eb.checksum_step)

        # also check verification of checksums for extensions, which is part of fetch_extension_sources
        error_msg = "Checksum verification for extension source bar-0.0.tar.gz failed"
        self.assertErrorRegex(EasyBuildError, error_msg, eb.collect_exts_file_info)

        # also check with deprecated fetch_extension_sources method
        self.allow_deprecated_behaviour()
        self.mock_stderr(True)
        self.assertErrorRegex(EasyBuildError, error_msg, eb.fetch_extension_sources)
        self.mock_stderr(False)
        self.disallow_deprecated_behaviour()

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
        eb.collect_exts_file_info()
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertEqual(stdout, '')
        self.assertEqual(stderr.strip(), "WARNING: Ignoring failing checksum verification for bar-0.0.tar.gz")

        # also check with deprecated fetch_extension_sources method
        self.allow_deprecated_behaviour()
        self.mock_stderr(True)
        self.mock_stdout(True)
        eb.fetch_extension_sources()
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertEqual(stdout, '')
        self.assertTrue(stderr.strip().endswith("WARNING: Ignoring failing checksum verification for bar-0.0.tar.gz"))
        self.disallow_deprecated_behaviour()

    def test_check_checksums(self):
        """Test for check_checksums_for and check_checksums methods."""
        testdir = os.path.abspath(os.path.dirname(__file__))
        toy_ec = os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0-gompi-2018a-test.eb')

        ec = process_easyconfig(toy_ec)[0]
        eb = get_easyblock_instance(ec)

        def run_checks():
            expected = "Checksums missing for one or more sources/patches in toy-0.0-gompi-2018a-test.eb: "
            expected += "found 1 sources + 1 patches vs 1 checksums"
            self.assertEqual(res[0], expected)
            self.assertTrue(res[1].startswith("Non-SHA256 checksum(s) found for toy-0.0.tar.gz:"))

        # check for main sources/patches should reveal two issues with checksums
        res = eb.check_checksums_for(eb.cfg)
        self.assertEqual(len(res), 2)
        run_checks()

        # full check also catches checksum issues with extensions
        res = eb.check_checksums()
        self.assertEqual(len(res), 4)
        run_checks()

        idx = 2
        for ext in ['bar', 'barbar']:
            expected = "Checksums missing for one or more sources/patches of extension %s in " % ext
            self.assertTrue(res[idx].startswith(expected))
            idx += 1

        # check whether tuple of alternative SHA256 checksums is correctly recognized
        toy_ec = os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        ec = process_easyconfig(toy_ec)[0]
        eb = get_easyblock_instance(ec)

        # single SHA256 checksum per source/patch: OK
        eb.cfg['checksums'] = [
            '44332000aa33b99ad1e00cbd1a7da769220d74647060a10e807b916d73ea27bc',  # toy-0.0.tar.gz
            '81a3accc894592152f81814fbf133d39afad52885ab52c25018722c7bda92487',  # toy-*.patch
            '4196b56771140d8e2468fb77f0240bc48ddbf5dabafe0713d612df7fafb1e458',  # toy-extra.txt]
        ]
        # no checksum issues
        self.assertEqual(eb.check_checksums(), [])

        # SHA256 checksum with type specifier: OK
        eb.cfg['checksums'] = [
            ('sha256', '44332000aa33b99ad1e00cbd1a7da769220d74647060a10e807b916d73ea27bc'),  # toy-0.0.tar.gz
            '81a3accc894592152f81814fbf133d39afad52885ab52c25018722c7bda92487',  # toy-*.patch
            ('sha256', '4196b56771140d8e2468fb77f0240bc48ddbf5dabafe0713d612df7fafb1e458'),  # toy-extra.txt]
        ]
        # no checksum issues
        self.assertEqual(eb.check_checksums(), [])

        # tuple of two alternate SHA256 checksums: OK
        eb.cfg['checksums'] = [
            (
                # two alternate checksums for toy-0.0.tar.gz
                'a2848f34fcd5d6cf47def00461fcb528a0484d8edef8208d6d2e2909dc61d9cd',
                '44332000aa33b99ad1e00cbd1a7da769220d74647060a10e807b916d73ea27bc',
            ),
            '81a3accc894592152f81814fbf133d39afad52885ab52c25018722c7bda92487',  # toy-*.patch
            '4196b56771140d8e2468fb77f0240bc48ddbf5dabafe0713d612df7fafb1e458',  # toy-extra.txt
        ]
        # no checksum issues
        self.assertEqual(eb.check_checksums(), [])

        # checksums as dict for some files
        eb.cfg['checksums'] = [
            {
                'toy-0.0.tar.gz': '44332000aa33b99ad1e00cbd1a7da769220d74647060a10e807b916d73ea27bc',
                'toy-0.1.tar.gz': '123456789abcdef123456789abcdef123456789abcdef123456789abcdef1234',
            },
            '81a3accc894592152f81814fbf133d39afad52885ab52c25018722c7bda92487',  # toy-*.patch
            '4196b56771140d8e2468fb77f0240bc48ddbf5dabafe0713d612df7fafb1e458',  # toy-extra.txt
        ]
        self.assertEqual(eb.check_checksums(), [])

        # sources can also have dict entries
        eb.cfg['sources'] = [{'filename': 'toy-0.0.tar.gz', 'download_fileame': 'toy.tar.gz'}]
        self.assertEqual(eb.check_checksums(), [])
        # Same in extensions: Single source as dict, checksum as string
        eb.cfg['exts_list'] = [(
            'toy-ext', '42',
            {
                'sources': {'filename': 'toy-ext.tar.gz'},
                'checksums': '81a3accc894592152f81814fbf133d39afad52885ab52c25018722c7bda92487',
            }
        )]
        self.assertEqual(eb.check_checksums(), [])

        # no checksums in easyconfig, then picked up from checksums.json next to easyconfig file
        test_ec = os.path.join(self.test_prefix, 'test.eb')
        copy_file(toy_ec, test_ec)
        ec = process_easyconfig(test_ec)[0]
        eb = get_easyblock_instance(ec)
        eb.cfg['checksums'] = []
        res = eb.check_checksums()
        self.assertEqual(len(res), 1)
        expected = "Checksums missing for one or more sources/patches in test.eb: "
        expected += "found 1 sources + 2 patches vs 0 checksums"
        self.assertEqual(res[0], expected)

        # all is fine is checksums.json is also copied
        copy_file(os.path.join(os.path.dirname(toy_ec), 'checksums.json'), self.test_prefix)
        eb.json_checksums = None
        self.assertEqual(eb.check_checksums(), [])

    def test_this_is_easybuild(self):
        """Test 'this_is_easybuild' function (and get_git_revision function used by it)."""
        # make sure both return a non-Unicode string
        self.assertIsInstance(get_git_revision(), str)
        self.assertIsInstance(this_is_easybuild(), str)

    def test_stale_module_caches(self):
        """Test whether module caches are reset between builds."""

        ec1 = os.path.join(self.test_prefix, 'one.eb')
        ec1_txt = '\n'.join([
            "easyblock = 'Toolchain'",
            "name = 'one'",
            "version = '1.0.2'",
            "homepage = 'https://example.com'",
            "description = '1st test easyconfig'",
            "toolchain = SYSTEM",
        ])
        write_file(ec1, ec1_txt)

        # key aspect here is that two/2.0 depends on one/1.0 (which is an alias for one/1.0.2)
        ec2 = os.path.join(self.test_prefix, 'two.eb')
        ec2_txt = '\n'.join([
            "easyblock = 'Toolchain'",
            "name = 'two'",
            "version = '2.0'",
            "toolchain = SYSTEM",
            "homepage = 'https://example.com'",
            "description = '2nd test easyconfig'",
            "dependencies = [('one', '1.0')]",
        ])
        write_file(ec2, ec2_txt)

        # populate modules avail/show cache with result for "show one/1.0" when it doesn't exist yet
        # need to make sure we use same $MODULEPATH value as the one that is in place during build
        moddir = os.path.join(self.test_installpath, 'modules', 'all')
        self.modtool.use(moddir)
        self.assertFalse(self.modtool.exist(['one/1.0'])[0])

        # add .modulerc to install version alias one/1.0 for one/1.0.2
        # this makes cached result for "show one/1.0" incorrect as soon as one/1.0.2 is installed via one.eb
        modgen = module_generator(None)
        module_version_spec = {'modname': 'one/1.0.2', 'sym_version': '1.0', 'version': '1.0.2'}
        modulerc_txt = modgen.modulerc(module_version=module_version_spec)
        one_moddir = os.path.join(self.test_installpath, 'modules', 'all', 'one')

        write_file(os.path.join(one_moddir, modgen.DOT_MODULERC), modulerc_txt)

        # check again, this just grabs the cached results for 'avail one/1.0' & 'show one/1.0'
        self.assertFalse(self.modtool.exist(['one/1.0'])[0])

        # one/1.0 still doesn't exist yet (because underlying one/1.0.2 doesn't exist yet), even after clearing cache
        reset_module_caches()
        self.assertFalse(self.modtool.exist(['one/1.0'])[0])

        # installing both one.eb and two.eb in one go should work
        # this verifies whether the "module show" cache is cleared in between builds,
        # since one/1.0 is required for ec2, and the underlying one/1.0.2 is installed via ec1 in the same session
        self.eb_main([ec1, ec2], raise_error=True, do_build=True, verbose=True)

    def test_avail_easyblocks(self):
        """Test avail_easyblocks function."""
        easyblocks = avail_easyblocks()

        self.assertTrue(all(key.startswith('easybuild.easyblocks') for key in easyblocks))

        for modname in ['foo', 'generic.bar', 'toy', 'gcc', 'hpl']:
            self.assertIn('easybuild.easyblocks.%s' % modname, easyblocks)

        foo = easyblocks['easybuild.easyblocks.foo']
        self.assertEqual(foo['class'], 'EB_foo')
        self.assertTrue(foo['loc'].endswith('sandbox/easybuild/easyblocks/f/foo.py'))

        bar = easyblocks['easybuild.easyblocks.generic.bar']
        self.assertEqual(bar['class'], 'bar')
        self.assertTrue(bar['loc'].endswith('sandbox/easybuild/easyblocks/generic/bar.py'))

        toy = easyblocks['easybuild.easyblocks.toy']
        self.assertEqual(toy['class'], 'EB_toy')
        self.assertTrue(toy['loc'].endswith('sandbox/easybuild/easyblocks/t/toy.py'))

        gcc = easyblocks['easybuild.easyblocks.gcc']
        self.assertEqual(gcc['class'], 'EB_GCC')
        self.assertTrue(gcc['loc'].endswith('sandbox/easybuild/easyblocks/g/gcc.py'))

        hpl = easyblocks['easybuild.easyblocks.hpl']
        self.assertEqual(hpl['class'], 'EB_HPL')
        self.assertTrue(hpl['loc'].endswith('sandbox/easybuild/easyblocks/h/hpl.py'))

    def test_arch_specific_sanity_check(self):
        """Tests that the correct version is chosen for this architecture"""

        my_arch = st.get_cpu_architecture()

        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "test"',
            'version = "0.2"',
            'homepage = "https://example.com"',
            'description = "test"',
            'toolchain = SYSTEM',
            'sanity_check_paths = {',
            "  'files': [{'arch=%s': 'correct.a'}, 'default.a']," % my_arch,
            "  'dirs': [{'arch=%s': ('correct', 'alternative')}, {'arch=no-arch': 'not-used'}]," % my_arch,
            '}',
        ])
        self.writeEC()
        ec = EasyConfig(self.eb_file)
        eb = EasyBlock(ec)
        paths, _, _ = eb._sanity_check_step_common(None, None)

        self.assertEqual(set(paths.keys()), set(('files', 'dirs')))
        self.assertEqual(paths['files'], ['correct.a', 'default.a'])
        self.assertEqual(paths['dirs'], [('correct', 'alternative')])

    def test_sanity_check_paths_verification(self):
        """Test verification of sanity_check_paths w.r.t. keys & values."""

        testdir = os.path.abspath(os.path.dirname(__file__))
        toy_ec = os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        eb = EasyBlock(EasyConfig(toy_ec))
        eb.dry_run = True

        error_pattern = r"Incorrect format for sanity_check_paths: "
        error_pattern += r"should \(only\) have 'dirs', 'files' keys, "
        error_pattern += r"values should be lists \(at least one non-empty\)."

        def run_sanity_check_step(sanity_check_paths, enhance_sanity_check):
            """Helper function to run sanity check step, and do trivial check on generated output."""
            self.mock_stderr(True)
            self.mock_stdout(True)
            eb.cfg['sanity_check_paths'] = sanity_check_paths
            eb.cfg['enhance_sanity_check'] = enhance_sanity_check
            eb.sanity_check_step()
            stderr, stdout = self.get_stderr(), self.get_stdout()
            self.mock_stderr(False)
            self.mock_stdout(False)
            self.assertFalse(stderr)
            self.assertTrue(stdout.startswith("Sanity check paths"))

        # partial sanity_check_paths, only allowed when using enhance_sanity_check
        test_cases = [
            {'dirs': ['foo']},
            {'files': ['bar']},
            {'dirs': []},
            {'files': []},
            {'files': [], 'dirs': []},
        ]
        for test_case in test_cases:
            # without enhanced sanity check, these are all invalid sanity_check_paths values
            self.assertErrorRegex(EasyBuildError, error_pattern, run_sanity_check_step, test_case, False)

            # if enhance_sanity_check is enabled, these are acceptable sanity_check_step values
            run_sanity_check_step(test_case, True)

        # some inputs are always invalid, regardless of enhance_sanity_check, due to wrong keys/values
        test_cases = [
            {'foo': ['bar']},
            {'files': ['foo'], 'dirs': [], 'libs': ['libfoo.a']},
            {'files': ['foo'], 'libs': ['libfoo.a']},
            {'dirs': [], 'libs': ['libfoo.a']},
        ]
        for test_case in test_cases:
            self.assertErrorRegex(EasyBuildError, error_pattern, run_sanity_check_step, test_case, False)
            self.assertErrorRegex(EasyBuildError, error_pattern, run_sanity_check_step, test_case, True)

        # non-list values yield different errors with/without enhance_sanity_check
        error_pattern_bis = r"Incorrect value type in sanity_check_paths, should be a list: .*"
        test_cases = [
            {'files': 123, 'dirs': []},
            {'files': [], 'dirs': 123},
            {'files': 'foo', 'dirs': []},
            {'files': [], 'dirs': 'foo'},
        ]
        for test_case in test_cases:
            self.assertErrorRegex(EasyBuildError, error_pattern, run_sanity_check_step, test_case, False)
            self.assertErrorRegex(EasyBuildError, error_pattern_bis, run_sanity_check_step, test_case, True)

        # empty sanity_check_paths is always OK, since then the fallback to default bin + lib/lib64 kicks in
        run_sanity_check_step({}, False)
        run_sanity_check_step({}, True)


def suite():
    """ return all the tests in this file """
    return TestLoaderFiltered().loadTestsFromTestCase(EasyBlockTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
