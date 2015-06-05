##
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
from test.framework.utilities import EnhancedTestCase, init_config
from unittest import TestLoader, main

from easybuild.framework.easyblock import EasyBlock, get_easyblock_instance
from easybuild.framework.easyconfig import CUSTOM
from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.framework.easyconfig.tools import process_easyconfig
from easybuild.framework.extensioneasyblock import ExtensionEasyBlock
from easybuild.tools import config
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import get_module_syntax
from easybuild.tools.filetools import mkdir, read_file, write_file
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

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

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
        deps = [('GCC', '4.6.4')]
        hiddendeps = [('toy', '0.0-deps')]
        alldeps = deps + hiddendeps  # hidden deps must be included in list of deps
        modextravars = {'PI': '3.1415', 'FOO': 'bar'}
        modextrapaths = {'PATH': 'pibin', 'CPATH': 'pi/include'}
        self.contents = '\n'.join([
            'easyblock = "ConfigureMake"',
            'name = "%s"' % name,
            'version = "%s"' % version,
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            "toolchain = {'name': 'dummy', 'version': 'dummy'}",
            "dependencies = %s" % str(alldeps),
            "hiddendependencies = %s" % str(hiddendeps),
            "builddependencies = [('OpenMPI', '1.6.4-GCC-4.6.4')]",
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

        for (name, ver) in deps:
            if get_module_syntax() == 'Tcl':
                regex = re.compile(r'^\s*module load %s\s*$' % os.path.join(name, ver), re.M)
            elif get_module_syntax() == 'Lua':
                regex = re.compile(r'^\s*load\("%s"\)$' % os.path.join(name, ver), re.M)
            else:
                self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())
            self.assertTrue(regex.search(txt), "Pattern %s found in %s" % (regex.pattern, txt))

        for (name, ver) in hiddendeps:
            if get_module_syntax() == 'Tcl':
                regex = re.compile(r'^\s*module load %s/.%s\s*$' % (name, ver), re.M)
            elif get_module_syntax() == 'Lua':
                regex = re.compile(r'^\s*load\("%s/.%s"\)$' % (name, ver), re.M)
            else:
                self.assertTrue(False, "Unknown module syntax: %s" % get_module_syntax())
            self.assertTrue(regex.search(txt), "Pattern %s found in %s" % (regex.pattern, txt))

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
        # adjust PYTHONPATH such that test easyblocks are found
        testdir = os.path.abspath(os.path.dirname(__file__))
        import easybuild
        eb_blocks_path = os.path.join(testdir, 'sandbox')
        if eb_blocks_path not in sys.path:
            sys.path.append(eb_blocks_path)
            easybuild = reload(easybuild)

        import easybuild.easyblocks
        reload(easybuild.easyblocks)

        from easybuild.easyblocks.toy import EB_toy
        ec = process_easyconfig(os.path.join(testdir, 'easyconfigs', 'toy-0.0.eb'))[0]
        eb = get_easyblock_instance(ec)
        self.assertTrue(isinstance(eb, EB_toy))

        # check whether 'This is easyblock' log message is there
        tup = ('EB_toy', 'easybuild.easyblocks.toy', '.*test/framework/sandbox/easybuild/easyblocks/toy.pyc*')
        eb_log_msg_re = re.compile(r"INFO This is easyblock %s from module %s (%s)" % tup, re.M)
        logtxt = read_file(eb.logfile)
        self.assertTrue(eb_log_msg_re.search(logtxt), "Pattern '%s' found in: %s" % (eb_log_msg_re.pattern, logtxt))

    def test_fetch_patches(self):
        """Test fetch_patches method."""
        # adjust PYTHONPATH such that test easyblocks are found
        testdir = os.path.abspath(os.path.dirname(__file__))
        ec = process_easyconfig(os.path.join(testdir, 'easyconfigs', 'toy-0.0.eb'))[0]
        eb = get_easyblock_instance(ec)

        eb.fetch_patches()
        self.assertEqual(len(eb.patches), 1)
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

        ec = process_easyconfig(os.path.join(testdir, 'easyconfigs', 'toy-0.0.eb'))[0]
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

        # obtain_file yields error for non-existing files
        fn = 'thisisclearlyanonexistingfile'
        error_regex = "Couldn't find file %s anywhere, and downloading it didn't work either" % fn
        self.assertErrorRegex(EasyBuildError, error_regex, eb.obtain_file, fn, urls=['file://%s' % tmpdir_subdir])

        # file specifications via URL also work, are downloaded to (first) sourcepath
        init_config(args=["--sourcepath=%s:/no/such/dir:%s" % (tmpdir, sandbox_sources)])
        file_url = "http://hpcugent.github.io/easybuild/index.html"
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
            self.assertTrue(eb_regex.search(txt))
        else:
            print "ignoring failure to download %s in test_obtain_file, testing offline?" % file_url

        shutil.rmtree(tmpdir)

    def test_check_readiness(self):
        """Test check_readiness method."""
        init_config(build_options={'validate': False})

        # check that check_readiness step works (adding dependencies, etc.)
        ec_file = 'OpenMPI-1.6.4-GCC-4.6.4.eb'
        ec_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', ec_file)
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
            err_regex = re.compile("no module 'nosuchsoftware/1.2.3-GCC-4.6.4' found for dependency .*")
            self.assertTrue(err_regex.search(str(err)), "Pattern '%s' found in '%s'" % (err_regex.pattern, err))

        shutil.rmtree(tmpdir)

    def test_exclude_path_to_top_of_module_tree(self):
        """
        Make sure that modules under the HierarchicalMNS are correct,
        w.r.t. not including any load statements for modules that build up the path to the top of the module tree.
        """
        self.orig_module_naming_scheme = config.get_module_naming_scheme()
        test_ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
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

        modfile_prefix = os.path.join(self.test_installpath, 'modules', 'all')
        mkdir(os.path.join(modfile_prefix, 'Compiler', 'GCC', '4.8.3'), parents=True)
        mkdir(os.path.join(modfile_prefix, 'MPI', 'intel', '2013.5.192-GCC-4.8.3', 'impi', '4.1.3.049'), parents=True)

        impi_modfile_path = os.path.join('Compiler', 'intel', '2013.5.192-GCC-4.8.3', 'impi', '4.1.3.049')
        imkl_modfile_path = os.path.join('MPI', 'intel', '2013.5.192-GCC-4.8.3', 'impi', '4.1.3.049', 'imkl', '11.1.2.144')
        if get_module_syntax() == 'Lua':
            impi_modfile_path += '.lua'
            imkl_modfile_path += '.lua'

        # example: for imkl on top of iimpi toolchain with HierarchicalMNS, no module load statements should be included
        # not for the toolchain or any of the toolchain components,
        # since both icc/ifort and impi form the path to the top of the module tree
        tests = [
            ('impi-4.1.3.049-iccifort-2013.5.192-GCC-4.8.3.eb', impi_modfile_path, ['icc', 'ifort', 'iccifort']),
            ('imkl-11.1.2.144-iimpi-5.5.3-GCC-4.8.3.eb', imkl_modfile_path, ['icc', 'ifort', 'impi', 'iccifort', 'iimpi']),
        ]
        for ec_file, modfile_path, excluded_deps in tests:
            ec = EasyConfig(os.path.join(test_ecs_path, ec_file))
            eb = EasyBlock(ec)
            eb.toolchain.prepare()
            modpath = eb.make_module_step()
            modfile_path = os.path.join(modpath, modfile_path)
            modtxt = read_file(modfile_path)

            for imkl_dep in excluded_deps:
                tup = (imkl_dep, modfile_path, modtxt)
                failmsg = "No 'module load' statement found for '%s' not found in module %s: %s" % tup
                self.assertFalse(re.search("module load %s" % imkl_dep, modtxt), failmsg)

        os.environ['EASYBUILD_MODULE_NAMING_SCHEME'] = self.orig_module_naming_scheme
        init_config(build_options=build_options)

    def test_patch_step(self):
        """Test patch step."""
        ec = process_easyconfig(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs', 'toy-0.0.eb'))[0]
        orig_sources = ec['ec']['sources'][:]

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


def suite():
    """ return all the tests in this file """
    return TestLoader().loadTestsFromTestCase(EasyBlockTest)

if __name__ == '__main__':
    main()
