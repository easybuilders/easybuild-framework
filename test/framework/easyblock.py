##
# Copyright 2012-2014 Ghent University
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
import copy
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
from easybuild.tools.filetools import mkdir, write_file
from easybuild.tools.module_generator import det_full_module_name


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

        self.orig_tmp_logdir = os.environ.get('EASYBUILD_TMP_LOGDIR', None)
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
            # EasyBuild v1.x
            self.assertTrue(isinstance(extra_options, list))
            for extra_option in extra_options:
                self.assertTrue(isinstance(extra_option, tuple))
                self.assertEqual(len(extra_option), 2)
                self.assertTrue(isinstance(extra_option[0], basestring))
                self.assertTrue(isinstance(extra_option[1], list))
                self.assertEqual(len(extra_option[1]), 3)
            # EasyBuild v2.0 (breaks backward compatibility compared to v1.x)
            #self.assertTrue(isinstance(extra_options, dict))
            #for key in extra_options:
            #    self.assertTrue(isinstance(extra_options[key], list))
            #    self.assertTrue(len(extra_options[key]), 3)

        name = "pi"
        version = "3.14"
        self.contents =  '\n'.join([
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

        # test extensioneasyblock, as extension
        exeb1 = ExtensionEasyBlock(eb, {'name': 'foo', 'version': '0.0'})
        self.assertEqual(exeb1.cfg['name'], 'foo')
        extra_options = exeb1.extra_options()
        check_extra_options_format(extra_options)
        self.assertTrue('options' in [key for (key, _) in extra_options])

        # test extensioneasyblock, as easyblock
        exeb2 = ExtensionEasyBlock(ec)
        self.assertEqual(exeb2.cfg['name'], 'pi')
        self.assertEqual(exeb2.cfg['version'], '3.14')
        extra_options = exeb2.extra_options()
        check_extra_options_format(extra_options)
        self.assertTrue('options' in [key for (key, _) in extra_options])

        class TestExtension(ExtensionEasyBlock):
            @staticmethod
            def extra_options():
                return ExtensionEasyBlock.extra_options([('extra_param', [None, "help", CUSTOM])])
        texeb = TestExtension(eb, {'name': 'bar'})
        self.assertEqual(texeb.cfg['name'], 'bar')
        extra_options = texeb.extra_options()
        check_extra_options_format(extra_options)
        self.assertTrue('options' in [key for (key, _) in extra_options])
        self.assertEqual([val for (key, val) in extra_options if key == 'extra_param'][0], [None, "help", CUSTOM])

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

    def test_fake_module_load(self):
        """Testcase for fake module load"""
        self.contents = '\n'.join([
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

        self.assertTrue(re.search("^prepend-path\s+CLASSPATH\s+\$root/bla.jar$", guess, re.M))
        self.assertTrue(re.search("^prepend-path\s+CLASSPATH\s+\$root/foo.jar$", guess, re.M))
        self.assertTrue(re.search("^prepend-path\s+MANPATH\s+\$root/share/man$", guess, re.M))
        self.assertTrue(re.search("^prepend-path\s+PATH\s+\$root/bin$", guess, re.M))
        self.assertFalse(re.search("^prepend-path\s+CPATH\s+.*$", guess, re.M))

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

    def test_extensions_step(self):
        """Test the extensions_step"""
        self.contents = '\n'.join([
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
        self.assertRaises(EasyBuildError, eb.extensions_step)
        self.assertErrorRegex(EasyBuildError, "No default extension class set", eb.extensions_step)

        # test if everything works fine if set
        self.contents += "\nexts_defaultclass = ['easybuild.framework.extension', 'Extension']"
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.builddir = config.build_path()
        eb.installdir = config.install_path()
        eb.extensions_step()

        # test for proper error message when skip is set, but no exts_filter is set
        self.assertRaises(EasyBuildError, eb.skip_extensions)
        self.assertErrorRegex(EasyBuildError, "no exts_filter set", eb.skip_extensions)

        # cleanup
        eb.close_log()
        os.remove(eb.logfile)

    def test_skip_extensions_step(self):
        """Test the skip_extensions_step"""
        self.contents = '\n'.join([
            'name = "pi"',
            'version = "3.14"',
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            'toolchain = {"name": "dummy", "version": "dummy"}',
            'exts_list = ["ext1", "ext2"]',
            'exts_filter = ("if [ %(name)s == \'ext2\' ]; then exit 0; else exit 1; fi", "")',
            'exts_defaultclass = ["easybuild.framework.extension", "Extension"]',
        ])
        # check if skip skips correct extensions
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        #self.assertTrue('ext1' in eb.exts.keys() and 'ext2' in eb.exts.keys())
        eb.builddir = config.build_path()
        eb.installdir = config.install_path()
        eb.skip = True
        eb.extensions_step()
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
        modextravars = {'PI': '3.1415', 'FOO': 'bar'}
        modextrapaths = {'PATH': 'pibin', 'CPATH': 'pi/include'}
        self.contents = '\n'.join([
            'name = "%s"' % name,
            'version = "%s"' % version,
            'homepage = "http://example.com"',
            'description = "test easyconfig"',
            "toolchain = {'name': 'dummy', 'version': 'dummy'}",
            "dependencies = [('foo', '1.2.3')]",
            "builddependencies = [('bar', '9.8.7')]",
            "modextravars = %s" % str(modextravars),
            "modextrapaths = %s" % str(modextrapaths),
        ])

        # test if module is generated correctly
        self.writeEC()
        eb = EasyBlock(EasyConfig(self.eb_file))
        eb.installdir = os.path.join(config.install_path(), 'pi', '3.14')

        modpath = os.path.join(eb.make_module_step(), name, version)
        self.assertTrue(os.path.exists(modpath))

        # verify contents of module
        f = open(modpath, 'r')
        txt = f.read()
        f.close()
        self.assertTrue(re.search("^#%Module", txt.split('\n')[0]))
        self.assertTrue(re.search("^conflict\s+%s$" % name, txt, re.M))
        self.assertTrue(re.search("^set\s+root\s+%s$" % eb.installdir, txt, re.M))
        self.assertTrue(re.search('^setenv\s+EBROOT%s\s+".root"\s*$' % name.upper(), txt, re.M))
        self.assertTrue(re.search('^setenv\s+EBVERSION%s\s+"%s"$' % (name.upper(), version), txt, re.M))
        for (key, val) in modextravars.items():
            self.assertTrue(re.search('^setenv\s+%s\s+"%s"$' % (key, val), txt, re.M))
        for (key, val) in modextrapaths.items():
            self.assertTrue(re.search('^prepend-path\s+%s\s+\$root/%s$' % (key, val), txt, re.M))

    def test_gen_dirs(self):
        """Test methods that generate/set build/install directory names."""
        self.contents = '\n'.join([
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
        eb.mod_name = det_full_module_name(eb.cfg)  # required by gen_installdir()
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
        if not eb_blocks_path in sys.path:
            sys.path.append(eb_blocks_path)
            easybuild = reload(easybuild)

        import easybuild.easyblocks
        reload(easybuild.easyblocks)

        from easybuild.easyblocks.toy import EB_toy
        ec = process_easyconfig(os.path.join(testdir, 'easyconfigs', 'toy-0.0.eb'))[0]
        eb = get_easyblock_instance(ec)
        self.assertTrue(isinstance(eb, EB_toy))

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
        res = eb.obtain_file(toy_tarball, urls=[os.path.join('file://', tmpdir_subdir)])
        self.assertEqual(res, os.path.join(tmpdir, 't', 'toy', toy_tarball))

        # finding a file in sourcepath works
        init_config(args=["--sourcepath=%s:/no/such/dir:%s" % (sandbox_sources, tmpdir)])
        res = eb.obtain_file(toy_tarball)
        self.assertEqual(res, toy_tarball_path)

        # sourcepath has preference over downloading
        res = eb.obtain_file(toy_tarball, urls=[os.path.join('file://', tmpdir_subdir)])
        self.assertEqual(res, toy_tarball_path)

        # obtain_file yields error for non-existing files
        fn = 'thisisclearlyanonexistingfile'
        try:
            eb.obtain_file(fn, urls=[os.path.join('file://', tmpdir_subdir)])
        except EasyBuildError, err:
            fail_regex = re.compile("Couldn't find file %s anywhere, and downloading it didn't work either" % fn)
            self.assertTrue(fail_regex.search(str(err)))

        # file specifications via URL also work, are downloaded to (first) sourcepath
        init_config(args=["--sourcepath=%s:/no/such/dir:%s" % (tmpdir, sandbox_sources)])
        file_url = "http://hpcugent.github.io/easybuild/index.html"
        fn = os.path.basename(file_url)
        try:
            res = eb.obtain_file(file_url)
            loc = os.path.join(tmpdir, 't', 'toy', fn)
            self.assertEqual(res, loc)
            self.assertTrue(os.path.exists(loc), "%s file is found at %s" % (fn, loc))
            txt = open(loc, 'r').read()
            eb_regex = re.compile("EasyBuild: building software with ease")
            self.assertTrue(eb_regex.search(txt))
        except EasyBuildError, err:
            # if this fails, it should be because there's no online access
            download_fail_regex = re.compile('socket error')
            self.assertTrue(download_fail_regex.search(str(err)))

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

    def tearDown(self):
        """ make sure to remove the temporary file """
        super(EasyBlockTest, self).tearDown()

        os.remove(self.eb_file)
        if self.orig_tmp_logdir is not None:
            os.environ['EASYBUILD_TMP_LOGDIR'] = self.orig_tmp_logdir


def suite():
    """ return all the tests in this file """
    return TestLoader().loadTestsFromTestCase(EasyBlockTest)

if __name__ == '__main__':
    main()
