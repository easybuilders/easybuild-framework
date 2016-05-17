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
Unit tests for filetools.py

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
@author: Ward Poelmans (Ghent University)
"""
import os
import shutil
import stat
import tempfile
import urllib2
from test.framework.utilities import EnhancedTestCase, init_config
from unittest import TestLoader, main
from urllib2 import URLError

import easybuild.tools.filetools as ft
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.multidiff import multidiff


class FileToolsTest(EnhancedTestCase):
    """ Testcase for filetools module """

    class_names = [
        ('GCC', 'EB_GCC'),
        ('7zip', 'EB_7zip'),
        ('Charm++', 'EB_Charm_plus__plus_'),
        ('DL_POLY_Classic', 'EB_DL_underscore_POLY_underscore_Classic'),
        ('0_foo+0x0x#-$__', 'EB_0_underscore_foo_plus_0x0x_hash__minus__dollar__underscore__underscore_'),
    ]

    def test_extract_cmd(self):
        """Test various extract commands."""
        tests = [
            ('test.zip', "unzip -qq test.zip"),
            ('/some/path/test.tar', "tar xf /some/path/test.tar"),
            ('test.tar.gz', "tar xzf test.tar.gz"),
            ('test.TAR.GZ', "tar xzf test.TAR.GZ"),
            ('test.tgz', "tar xzf test.tgz"),
            ('test.gtgz', "tar xzf test.gtgz"),
            ('test.bz2', "bunzip2 test.bz2"),
            ('test.tbz', "tar xjf test.tbz"),
            ('test.tbz2', "tar xjf test.tbz2"),
            ('test.tb2', "tar xjf test.tb2"),
            ('test.tar.bz2', "tar xjf test.tar.bz2"),
            ('test.gz', "gunzip -c test.gz > test"),
            ('untar.gz', "gunzip -c untar.gz > untar"),
            ("/some/path/test.gz", "gunzip -c /some/path/test.gz > test"),
            ('test.xz', "unxz test.xz"),
            ('test.tar.xz', "unxz test.tar.xz --stdout | tar x"),
            ('test.txz', "unxz test.txz --stdout | tar x"),
            ('test.iso', "7z x test.iso"),
            ('test.tar.Z', "tar xZf test.tar.Z"),
        ]
        for (fn, expected_cmd) in tests:
            cmd = ft.extract_cmd(fn)
            self.assertEqual(expected_cmd, cmd)

        self.assertEqual("unzip -qq -o test.zip", ft.extract_cmd('test.zip', True))

    def test_convert_name(self):
        """Test convert_name function."""
        name = ft.convert_name("test+test-test.mpi")
        self.assertEqual(name, "testplustestmintestmpi")
        name = ft.convert_name("test+test-test.mpi", True)
        self.assertEqual(name, "TESTPLUSTESTMINTESTMPI")

    def test_find_base_dir(self):
        """test if we find the correct base dir"""
        tmpdir = tempfile.mkdtemp()

        foodir = os.path.join(tmpdir, 'foo')
        os.mkdir(foodir)
        os.mkdir(os.path.join(tmpdir, '.bar'))
        os.mkdir(os.path.join(tmpdir, 'easybuild'))

        os.chdir(tmpdir)
        self.assertTrue(os.path.samefile(foodir, ft.find_base_dir()))

    def test_encode_class_name(self):
        """Test encoding of class names."""
        for (class_name, encoded_class_name) in self.class_names:
            self.assertEqual(ft.encode_class_name(class_name), encoded_class_name)
            self.assertEqual(ft.encode_class_name(ft.decode_class_name(encoded_class_name)), encoded_class_name)

    def test_decode_class_name(self):
        """Test decoding of class names."""
        for (class_name, encoded_class_name) in self.class_names:
            self.assertEqual(ft.decode_class_name(encoded_class_name), class_name)
            self.assertEqual(ft.decode_class_name(ft.encode_class_name(class_name)), class_name)

    def test_patch_perl_script_autoflush(self):
        """Test patching Perl script for autoflush."""

        fh, fp = tempfile.mkstemp()
        os.close(fh)
        perl_lines = [
            "$!/usr/bin/perl",
            "use strict;",
            "print hello",
            "",
            "print hello again",
        ]
        perltxt = '\n'.join(perl_lines)
        ft.write_file(fp, perltxt)
        ft.patch_perl_script_autoflush(fp)
        txt = ft.read_file(fp)
        self.assertTrue(len(txt.split('\n')) == len(perl_lines) + 4)
        self.assertTrue(txt.startswith(perl_lines[0] + "\n\nuse IO::Handle qw();\nSTDOUT->autoflush(1);"))
        for line in perl_lines[1:]:
            self.assertTrue(line in txt)
        os.remove(fp)
        os.remove("%s.eb.orig" % fp)

    def test_which(self):
        """Test which function for locating commands."""
        python = ft.which('python')
        self.assertTrue(python and os.path.exists(python) and os.path.isabs(python))

        path = ft.which('i_really_do_not_expect_a_command_with_a_name_like_this_to_be_available')
        self.assertTrue(path is None)


    def test_checksums(self):
        """Test checksum functionality."""
        fh, fp = tempfile.mkstemp()
        os.close(fh)
        ft.write_file(fp, "easybuild\n")
        known_checksums = {
            'adler32': '0x379257805',
            'crc32': '0x1457143216',
            'md5': '7167b64b1ca062b9674ffef46f9325db',
            'sha1': 'db05b79e09a4cc67e9dd30b313b5488813db3190',
        }

        # make sure checksums computation/verification is correct
        for checksum_type, checksum in known_checksums.items():
            self.assertEqual(ft.compute_checksum(fp, checksum_type=checksum_type), checksum)
            self.assertTrue(ft.verify_checksum(fp, (checksum_type, checksum)))
        # md5 is default
        self.assertEqual(ft.compute_checksum(fp), known_checksums['md5'])
        self.assertTrue(ft.verify_checksum(fp, known_checksums['md5']))

        # make sure faulty checksums are reported
        broken_checksums = dict([(typ, val + 'foo') for (typ, val) in known_checksums.items()])
        for checksum_type, checksum in broken_checksums.items():
            self.assertFalse(ft.compute_checksum(fp, checksum_type=checksum_type) == checksum)
            self.assertFalse(ft.verify_checksum(fp, (checksum_type, checksum)))
        # md5 is default
        self.assertFalse(ft.compute_checksum(fp) == broken_checksums['md5'])
        self.assertFalse(ft.verify_checksum(fp, broken_checksums['md5']))

        # cleanup
        os.remove(fp)

    def test_common_path_prefix(self):
        """Test get common path prefix for a list of paths."""
        self.assertEqual(ft.det_common_path_prefix(['/foo/bar/foo', '/foo/bar/baz', '/foo/bar/bar']), '/foo/bar')
        self.assertEqual(ft.det_common_path_prefix(['/foo/bar/', '/foo/bar/baz', '/foo/bar']), '/foo/bar')
        self.assertEqual(ft.det_common_path_prefix(['/foo/bar', '/foo']), '/foo')
        self.assertEqual(ft.det_common_path_prefix(['/foo/bar/']), '/foo/bar')
        self.assertEqual(ft.det_common_path_prefix(['/foo/bar', '/bar', '/foo']), None)
        self.assertEqual(ft.det_common_path_prefix(['foo', 'bar']), None)
        self.assertEqual(ft.det_common_path_prefix(['foo']), None)
        self.assertEqual(ft.det_common_path_prefix([]), None)

    def test_download_file(self):
        """Test download_file function."""
        fn = 'toy-0.0.tar.gz'
        target_location = os.path.join(self.test_buildpath, 'some', 'subdir', fn)
        # provide local file path as source URL
        test_dir = os.path.abspath(os.path.dirname(__file__))
        source_url = 'file://%s/sandbox/sources/toy/%s' % (test_dir, fn)
        res = ft.download_file(fn, source_url, target_location)
        self.assertEqual(res, target_location, "'download' of local file works")

        # non-existing files result in None return value
        self.assertEqual(ft.download_file(fn, 'file://%s/nosuchfile' % test_dir, target_location), None)

        # install broken proxy handler for opening local files
        # this should make urllib2.urlopen use this broken proxy for downloading from a file:// URL
        proxy_handler = urllib2.ProxyHandler({'file': 'file://%s/nosuchfile' % test_dir})
        urllib2.install_opener(urllib2.build_opener(proxy_handler))

        # downloading over a broken proxy results in None return value (failed download)
        # this tests whether proxies are taken into account by download_file
        self.assertEqual(ft.download_file(fn, source_url, target_location), None, "download over broken proxy fails")

        # restore a working file handler, and retest download of local file
        urllib2.install_opener(urllib2.build_opener(urllib2.FileHandler()))
        res = ft.download_file(fn, source_url, target_location)
        self.assertEqual(res, target_location, "'download' of local file works after removing broken proxy")

        # make sure specified timeout is parsed correctly (as a float, not a string)
        opts = init_config(args=['--download-timeout=5.3'])
        init_config(build_options={'download_timeout': opts.download_timeout})
        target_location = os.path.join(self.test_prefix, 'jenkins_robots.txt')
        url = 'https://jenkins1.ugent.be/robots.txt'
        try:
            urllib2.urlopen(url)
            res = ft.download_file(fn, url, target_location)
            self.assertEqual(res, target_location, "download with specified timeout works")
        except urllib2.URLError:
            print "Skipping timeout test in test_download_file (working offline)"

    def test_mkdir(self):
        """Test mkdir function."""
        tmpdir = tempfile.mkdtemp()

        def check_mkdir(path, error=None, **kwargs):
            """Create specified directory with mkdir, and check for correctness."""
            if error is None:
                ft.mkdir(path, **kwargs)
                self.assertTrue(os.path.exists(path) and os.path.isdir(path), "Directory %s exists" % path)
            else:
                self.assertErrorRegex(EasyBuildError, error, ft.mkdir, path, **kwargs)

        foodir = os.path.join(tmpdir, 'foo')
        barfoodir = os.path.join(tmpdir, 'bar', 'foo')
        check_mkdir(foodir)
        # no error on existing paths
        check_mkdir(foodir)
        # no recursion by defaults, requires parents=True
        check_mkdir(barfoodir, error="Failed.*No such file or directory")
        check_mkdir(barfoodir, parents=True)
        check_mkdir(os.path.join(barfoodir, 'bar', 'foo', 'trolololol'), parents=True)
        # group ID and sticky bits are disabled by default
        self.assertFalse(os.stat(foodir).st_mode & (stat.S_ISGID | stat.S_ISVTX), "no gid/sticky bit %s" % foodir)
        self.assertFalse(os.stat(barfoodir).st_mode & (stat.S_ISGID | stat.S_ISVTX), "no gid/sticky bit %s" % barfoodir)
        # setting group ID bit works
        giddir = os.path.join(foodir, 'gid')
        check_mkdir(giddir, set_gid=True)
        self.assertTrue(os.stat(giddir).st_mode & stat.S_ISGID, "gid bit set %s" % giddir)
        self.assertFalse(os.stat(giddir).st_mode & stat.S_ISVTX, "no sticky bit %s" % giddir)
        # setting stciky bit works
        stickydir = os.path.join(barfoodir, 'sticky')
        check_mkdir(stickydir, sticky=True)
        self.assertFalse(os.stat(stickydir).st_mode & stat.S_ISGID, "no gid bit %s" % stickydir)
        self.assertTrue(os.stat(stickydir).st_mode & stat.S_ISVTX, "sticky bit set %s" % stickydir)
        # setting both works, bits are set for all new subdirectories
        stickygiddirs = [os.path.join(foodir, 'new')]
        stickygiddirs.append(os.path.join(stickygiddirs[-1], 'sticky'))
        stickygiddirs.append(os.path.join(stickygiddirs[-1], 'and'))
        stickygiddirs.append(os.path.join(stickygiddirs[-1], 'gid'))
        check_mkdir(stickygiddirs[-1], parents=True, set_gid=True, sticky=True)
        for subdir in stickygiddirs:
            gid_or_sticky = stat.S_ISGID | stat.S_ISVTX
            self.assertEqual(os.stat(subdir).st_mode & gid_or_sticky, gid_or_sticky, "gid bit set %s" % subdir)
        # existing parent dirs are untouched, no sticky/group ID bits set
        self.assertFalse(os.stat(foodir).st_mode & (stat.S_ISGID | stat.S_ISVTX), "no gid/sticky bit %s" % foodir)
        self.assertFalse(os.stat(barfoodir).st_mode & (stat.S_ISGID | stat.S_ISVTX), "no gid/sticky bit %s" % barfoodir)

        shutil.rmtree(tmpdir)

    def test_path_matches(self):
        # set up temporary directories
        tmpdir = tempfile.mkdtemp()
        path1 = os.path.join(tmpdir, 'path1')
        ft.mkdir(path1)
        path2 = os.path.join(tmpdir, 'path2')
        ft.mkdir(path1)
        symlink = os.path.join(tmpdir, 'symlink')
        os.symlink(path1, symlink)
        missing = os.path.join(tmpdir, 'missing')

        self.assertFalse(ft.path_matches(missing, [path1, path2]))
        self.assertFalse(ft.path_matches(path1, [missing]))
        self.assertFalse(ft.path_matches(path1, [missing, path2]))
        self.assertFalse(ft.path_matches(path2, [missing, symlink]))
        self.assertTrue(ft.path_matches(path1, [missing, symlink]))

        # cleanup
        shutil.rmtree(tmpdir)

    def test_read_write_file(self):
        """Test reading/writing files."""
        tmpdir = tempfile.mkdtemp()

        fp = os.path.join(tmpdir, 'test.txt')
        txt = "test123"
        ft.write_file(fp, txt)
        self.assertEqual(ft.read_file(fp), txt)

        txt2 = '\n'.join(['test', '123'])
        ft.write_file(fp, txt2, append=True)
        self.assertEqual(ft.read_file(fp), txt+txt2)

        shutil.rmtree(tmpdir)

    def test_det_patched_files(self):
        """Test det_patched_files function."""
        pf = os.path.join(os.path.dirname(__file__), 'sandbox', 'sources', 'toy', 'toy-0.0_typo.patch')
        self.assertEqual(ft.det_patched_files(pf), ['b/toy-0.0/toy.source'])
        self.assertEqual(ft.det_patched_files(pf, omit_ab_prefix=True), ['toy-0.0/toy.source'])

    def test_guess_patch_level(self):
        "Test guess_patch_level."""
        # create dummy toy.source file so guess_patch_level can work
        f = open(os.path.join(self.test_buildpath, 'toy.source'), 'w')
        f.write("This is toy.source")
        f.close()

        for patched_file, correct_patch_level in [
            ('toy.source', 0),
            ('b/toy.source', 1),  # b/ prefix is used in +++ line in git diff patches
            ('a/toy.source', 1),  # a/ prefix is used in --- line in git diff patches
            ('c/toy.source', 1),
            ('toy-0.0/toy.source', 1),
            ('b/toy-0.0/toy.source', 2),
        ]:
            self.assertEqual(ft.guess_patch_level([patched_file], self.test_buildpath), correct_patch_level)

    def test_move_logs(self):
        """Test move_logs function."""
        fh, fp = tempfile.mkstemp()
        os.close(fh)
        ft.write_file(fp, 'foobar')
        ft.write_file(fp + '.1', 'moarfoobar')
        ft.move_logs(fp, os.path.join(self.test_prefix, 'foo.log'))

        self.assertEqual(ft.read_file(os.path.join(self.test_prefix, 'foo.log')), 'foobar')
        self.assertEqual(ft.read_file(os.path.join(self.test_prefix, 'foo.log.1')), 'moarfoobar')

        ft.write_file(os.path.join(self.test_prefix, 'bar.log'), 'bar')
        ft.write_file(os.path.join(self.test_prefix, 'bar.log_1'), 'barbar')

        fh, fp = tempfile.mkstemp()
        os.close(fh)
        ft.write_file(fp, 'moarbar')
        ft.write_file(fp + '.1', 'evenmoarbar')
        ft.move_logs(fp, os.path.join(self.test_prefix, 'bar.log'))

        logs = ['bar.log', 'bar.log.1', 'bar.log_0', 'bar.log_1',
                os.path.basename(self.logfile),
                'foo.log', 'foo.log.1']
        self.assertEqual(sorted([f for f in os.listdir(self.test_prefix) if 'log' in f]), logs)
        self.assertEqual(ft.read_file(os.path.join(self.test_prefix, 'bar.log_0')), 'bar')
        self.assertEqual(ft.read_file(os.path.join(self.test_prefix, 'bar.log_1')), 'barbar')
        self.assertEqual(ft.read_file(os.path.join(self.test_prefix, 'bar.log')), 'moarbar')
        self.assertEqual(ft.read_file(os.path.join(self.test_prefix, 'bar.log.1')), 'evenmoarbar')

    def test_multidiff(self):
        """Test multidiff function."""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        other_toy_ecs = [
            os.path.join(test_easyconfigs, 'toy-0.0-deps.eb'),
            os.path.join(test_easyconfigs, 'toy-0.0-gompi-1.3.12-test.eb'),
        ]

        # default (colored)
        lines = multidiff(os.path.join(test_easyconfigs, 'toy-0.0.eb'), other_toy_ecs).split('\n')
        expected = "Comparing \x1b[0;35mtoy-0.0.eb\x1b[0m with toy-0.0-deps.eb, toy-0.0-gompi-1.3.12-test.eb"

        red = "\x1b[0;41m"
        green = "\x1b[0;42m"
        endcol = "\x1b[0m"

        self.assertEqual(lines[0], expected)
        self.assertEqual(lines[1], "=====")

        # different versionsuffix
        self.assertEqual(lines[2], "3 %s- versionsuffix = '-test'%s (1/2) toy-0.0-gompi-1.3.12-test.eb" % (red, endcol))
        self.assertEqual(lines[3], "3 %s- versionsuffix = '-deps'%s (1/2) toy-0.0-deps.eb" % (red, endcol))

        # different toolchain in toy-0.0-gompi-1.3.12-test: '+' line (removed chars in toolchain name/version, in red)
        expected = "7 %(endcol)s-%(endcol)s toolchain = {"
        expected += "'name': '%(endcol)s%(red)sgo%(endcol)sm\x1b[0m%(red)spi%(endcol)s', "
        expected = expected % {'endcol': endcol, 'green': green, 'red': red}
        self.assertTrue(lines[7].startswith(expected))
        # different toolchain in toy-0.0-gompi-1.3.12-test: '+' line (added chars in toolchain name/version, in green)
        expected = "7 %(endcol)s+%(endcol)s toolchain = {"
        expected += "'name': '%(endcol)s%(green)sdu%(endcol)sm\x1b[0m%(green)smy%(endcol)s', "
        expected = expected % {'endcol': endcol, 'green': green, 'red': red}
        self.assertTrue(lines[8].startswith(expected))

        # no postinstallcmds in toy-0.0-deps.eb
        expected = "28 %s+ postinstallcmds = " % green
        self.assertTrue(any([line.startswith(expected) for line in lines]))
        self.assertTrue("29 %s+%s (1/2) toy-0.0-deps.eb" % (green, endcol) in lines)
        self.assertEqual(lines[-1], "=====")

        lines = multidiff(os.path.join(test_easyconfigs, 'toy-0.0.eb'), other_toy_ecs, colored=False).split('\n')
        self.assertEqual(lines[0], "Comparing toy-0.0.eb with toy-0.0-deps.eb, toy-0.0-gompi-1.3.12-test.eb")
        self.assertEqual(lines[1], "=====")

        # different versionsuffix
        self.assertEqual(lines[2], "3 - versionsuffix = '-test' (1/2) toy-0.0-gompi-1.3.12-test.eb")
        self.assertEqual(lines[3], "3 - versionsuffix = '-deps' (1/2) toy-0.0-deps.eb")

        # different toolchain in toy-0.0-gompi-1.3.12-test: '+' line with squigly line underneath to mark removed chars
        expected = "7 - toolchain = {'name': 'gompi', 'version': '1.3.12'} (1/2) toy"
        self.assertTrue(lines[7].startswith(expected))
        expected = "  ?                       ^^ ^^               ^^^^^^"
        self.assertEqual(lines[8], expected)
        # different toolchain in toy-0.0-gompi-1.3.12-test: '-' line with squigly line underneath to mark added chars
        expected = "7 + toolchain = {'name': 'dummy', 'version': 'dummy'} (1/2) toy"
        self.assertTrue(lines[9].startswith(expected))
        expected = "  ?                       ^^ ^^               ^^^^^"
        self.assertEqual(lines[10], expected)

        # no postinstallcmds in toy-0.0-deps.eb
        expected = "28 + postinstallcmds = "
        self.assertTrue(any([line.startswith(expected) for line in lines]))
        self.assertTrue("29 + (1/2) toy-0.0-deps.eb" in lines)

        self.assertEqual(lines[-1], "=====")

    def test_weld_paths(self):
        """Test weld_paths."""
        # works like os.path.join is there's no overlap
        self.assertEqual(ft.weld_paths('/foo/bar', 'foobar/baz'), '/foo/bar/foobar/baz/')
        self.assertEqual(ft.weld_paths('foo', 'bar/'), 'foo/bar/')
        self.assertEqual(ft.weld_paths('foo/', '/bar'), '/bar/')
        self.assertEqual(ft.weld_paths('/foo/', '/bar'), '/bar/')

        # overlap is taken into account
        self.assertEqual(ft.weld_paths('foo/bar', 'bar/baz'), 'foo/bar/baz/')
        self.assertEqual(ft.weld_paths('foo/bar/baz', 'bar/baz'), 'foo/bar/baz/')
        self.assertEqual(ft.weld_paths('foo/bar', 'foo/bar/baz'), 'foo/bar/baz/')
        self.assertEqual(ft.weld_paths('foo/bar', 'foo/bar'), 'foo/bar/')
        self.assertEqual(ft.weld_paths('/foo/bar', 'foo/bar'), '/foo/bar/')
        self.assertEqual(ft.weld_paths('/foo/bar', '/foo/bar'), '/foo/bar/')
        self.assertEqual(ft.weld_paths('/foo', '/foo/bar/baz'), '/foo/bar/baz/')


    def test_adjust_permissions(self):
        """Test adjust_permissions"""
        # set umask hard to run test reliably
        orig_umask = os.umask(0022)

        # prep files/dirs/(broken) symlinks is test dir

        # file: rw-r--r--
        ft.write_file(os.path.join(self.test_prefix, 'foo'), 'foo')
        foo_perms = os.stat(os.path.join(self.test_prefix, 'foo'))[stat.ST_MODE]
        for bit in [stat.S_IRUSR, stat.S_IWUSR, stat.S_IRGRP, stat.S_IROTH]:
            self.assertTrue(foo_perms & bit)
        for bit in [stat.S_IXUSR, stat.S_IWGRP, stat.S_IXGRP, stat.S_IWOTH, stat.S_IXOTH]:
            self.assertFalse(foo_perms & bit)

        # dir: rwxr-xr-x
        ft.mkdir(os.path.join(self.test_prefix, 'bar'))
        bar_perms = os.stat(os.path.join(self.test_prefix, 'bar'))[stat.ST_MODE]
        for bit in [stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR, stat.S_IRGRP, stat.S_IXGRP, stat.S_IROTH, stat.S_IXOTH]:
            self.assertTrue(bar_perms & bit)
        for bit in [stat.S_IWGRP, stat.S_IWOTH]:
            self.assertFalse(bar_perms & bit)

        # file in dir: rw-r--r--
        foobar_path = os.path.join(self.test_prefix, 'bar', 'foobar')
        ft.write_file(foobar_path, 'foobar')
        foobar_perms = os.stat(foobar_path)[stat.ST_MODE]
        for bit in [stat.S_IRUSR, stat.S_IWUSR, stat.S_IRGRP, stat.S_IROTH]:
            self.assertTrue(foobar_perms & bit)
        for bit in [stat.S_IXUSR, stat.S_IWGRP, stat.S_IXGRP, stat.S_IWOTH, stat.S_IXOTH]:
            self.assertFalse(foobar_perms & bit)

        # include symlink
        os.symlink(foobar_path, os.path.join(self.test_prefix, 'foobar_symlink'))

        # include broken symlink (symlinks are skipped, so this shouldn't cause problems)
        tmpfile = os.path.join(self.test_prefix, 'thiswontbetherelong')
        ft.write_file(tmpfile, 'poof!')
        os.symlink(tmpfile, os.path.join(self.test_prefix, 'broken_symlink'))
        os.remove(tmpfile)

        # test default behaviour:
        # recursive, add permissions, relative to existing permissions, both files and dirs, skip symlinks
        # add user execution, group write permissions
        ft.adjust_permissions(self.test_prefix, stat.S_IXUSR|stat.S_IWGRP)

        # foo file: rwxrw-r--
        foo_perms = os.stat(os.path.join(self.test_prefix, 'foo'))[stat.ST_MODE]
        for bit in [stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR, stat.S_IRGRP, stat.S_IWGRP, stat.S_IROTH]:
            self.assertTrue(foo_perms & bit)
        for bit in [stat.S_IXGRP, stat.S_IWOTH, stat.S_IXOTH]:
            self.assertFalse(foo_perms & bit)

        # bar dir: rwxrwxr-x
        bar_perms = os.stat(os.path.join(self.test_prefix, 'bar'))[stat.ST_MODE]
        for bit in [stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR, stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP,
                    stat.S_IROTH, stat.S_IXOTH]:
            self.assertTrue(bar_perms & bit)
        self.assertFalse(bar_perms & stat.S_IWOTH)

        # foo/foobar file: rwxrw-r--
        for path in [os.path.join(self.test_prefix, 'bar', 'foobar'), os.path.join(self.test_prefix, 'foobar_symlink')]:
            perms = os.stat(path)[stat.ST_MODE]
            for bit in [stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR, stat.S_IRGRP, stat.S_IWGRP, stat.S_IROTH]:
                self.assertTrue(perms & bit)
            for bit in [stat.S_IXGRP, stat.S_IWOTH, stat.S_IXOTH]:
                self.assertFalse(perms & bit)

        # broken symlinks are trouble if symlinks are not skipped
        self.assertErrorRegex(EasyBuildError, "No such file or directory", ft.adjust_permissions, self.test_prefix,
                              stat.S_IXUSR, skip_symlinks=False)

        # restore original umask
        os.umask(orig_umask)

    def test_apply_regex_substitutions(self):
        """Test apply_regex_substitutions function."""
        testfile = os.path.join(self.test_prefix, 'test.txt')
        testtxt = '\n'.join([
            "CC = gcc",
            "CFLAGS = -O3 -g",
            "FC = gfortran",
            "FFLAGS = -O3 -g -ffixed-form",
        ])
        ft.write_file(testfile, testtxt)

        regex_subs = [
            (r"^(CC)\s*=\s*.*$", r"\1 = ${CC}"),
            (r"^(FC\s*=\s*).*$", r"\1${FC}"),
            (r"^(.FLAGS)\s*=\s*-O3\s-g(.*)$", r"\1 = -O2\2"),
        ]
        ft.apply_regex_substitutions(testfile, regex_subs)

        expected_testtxt = '\n'.join([
            "CC = ${CC}",
            "CFLAGS = -O2",
            "FC = ${FC}",
            "FFLAGS = -O2 -ffixed-form",
        ])
        new_testtxt = ft.read_file(testfile)
        self.assertEqual(new_testtxt, expected_testtxt)

    def test_find_flexlm_license(self):
        """Test find_flexlm_license function."""
        lic_file1 = os.path.join(self.test_prefix, 'one.lic')
        ft.write_file(lic_file1, "This is a license file (no, really!)")

        lic_file2 = os.path.join(self.test_prefix, 'two.dat')
        ft.write_file(lic_file2, "This is another license file (sure it is!)")

        lic_server = '1234@example.license.server'

        # make test robust against environment in which $LM_LICENSE_FILE is defined
        if 'LM_LICENSE_FILE' in os.environ:
            del os.environ['LM_LICENSE_FILE']

        # default return value
        self.assertEqual(ft.find_flexlm_license(), ([], None))

        # provided license spec
        self.assertEqual(ft.find_flexlm_license(lic_specs=[lic_file1]), ([lic_file1], None))
        self.assertEqual(ft.find_flexlm_license(lic_specs=[lic_server, lic_file2]), ([lic_server, lic_file2], None))

        # non-existing license file
        os.environ['LM_LICENSE_FILE'] = '/no/such/file/unless/you/aim/to/break/this/check'
        self.assertEqual(ft.find_flexlm_license(), ([], None))

        # existing license file
        os.environ['LM_LICENSE_FILE'] = lic_file2
        self.assertEqual(ft.find_flexlm_license(), ([lic_file2], 'LM_LICENSE_FILE'))

        # directory with existing license files
        os.environ['LM_LICENSE_FILE'] = self.test_prefix
        self.assertEqual(ft.find_flexlm_license(), ([lic_file1, lic_file2], 'LM_LICENSE_FILE'))

        # server spec
        os.environ['LM_LICENSE_FILE'] = lic_server
        self.assertEqual(ft.find_flexlm_license(), ([lic_server], 'LM_LICENSE_FILE'))

        # invalid server spec (missing port)
        os.environ['LM_LICENSE_FILE'] = 'test.license.server'
        self.assertEqual(ft.find_flexlm_license(), ([], None))

        # env var wins of provided lic spec
        os.environ['LM_LICENSE_FILE'] = lic_file2
        self.assertEqual(ft.find_flexlm_license(lic_specs=[lic_server]), ([lic_file2], 'LM_LICENSE_FILE'))

        # custom env var wins over $LM_LICENSE_FILE
        os.environ['INTEL_LICENSE_FILE'] = lic_file1
        expected = ([lic_file1], 'INTEL_LICENSE_FILE')
        self.assertEqual(ft.find_flexlm_license(custom_env_vars='INTEL_LICENSE_FILE'), expected)
        self.assertEqual(ft.find_flexlm_license(custom_env_vars=['INTEL_LICENSE_FILE']), expected)
        self.assertEqual(ft.find_flexlm_license(custom_env_vars=['NOSUCHENVVAR', 'INTEL_LICENSE_FILE']), expected)

        # $LM_LICENSE_FILE is always considered
        os.environ['LM_LICENSE_FILE'] = lic_server
        os.environ['INTEL_LICENSE_FILE'] = '/no/such/file/unless/you/aim/to/break/this/check'
        expected = ([lic_server], 'LM_LICENSE_FILE')
        self.assertEqual(ft.find_flexlm_license(custom_env_vars=['INTEL_LICENSE_FILE']), expected)

        # license server *and* file spec; order is preserved
        os.environ['LM_LICENSE_FILE'] = ':'.join([lic_file2, lic_server, lic_file1])
        self.assertEqual(ft.find_flexlm_license(), ([lic_file2, lic_server, lic_file1], 'LM_LICENSE_FILE'))

        # typical usage
        os.environ['LM_LICENSE_FILE'] = lic_server
        os.environ['INTEL_LICENSE_FILE'] = '/not/a/valid/license/path:%s:/another/bogus/license/file' % lic_file2
        expected = ([lic_file2], 'INTEL_LICENSE_FILE')
        self.assertEqual(ft.find_flexlm_license(custom_env_vars='INTEL_LICENSE_FILE'), expected)

        os.environ['INTEL_LICENSE_FILE'] = '1234@lic1.test:4567@lic2.test:7890@lic3.test'
        expected = (['1234@lic1.test', '4567@lic2.test', '7890@lic3.test'], 'INTEL_LICENSE_FILE')
        self.assertEqual(ft.find_flexlm_license(custom_env_vars=['INTEL_LICENSE_FILE']), expected)

        # make sure find_flexlm_license is robust against None input;
        # this occurs if license_file is left unspecified
        del os.environ['INTEL_LICENSE_FILE']
        del os.environ['LM_LICENSE_FILE']
        self.assertEqual(ft.find_flexlm_license(lic_specs=[None]), ([], None))

    def test_is_alt_pypi_url(self):
        """Test is_alt_pypi_url() function."""
        url = 'https://pypi.python.org/packages/source/e/easybuild/easybuild-2.7.0.tar.gz'
        self.assertFalse(ft.is_alt_pypi_url(url))

        url = url.replace('source/e/easybuild', '5b/03/e135b19fadeb9b1ccb45eac9f60ca2dc3afe72d099f6bd84e03cb131f9bf')
        self.assertTrue(ft.is_alt_pypi_url(url))

    def test_derive_alt_pypi_url(self):
        """Test derive_alt_pypi_url() function."""
        url = 'https://pypi.python.org/packages/source/e/easybuild/easybuild-2.7.0.tar.gz'
        alturl = url.replace('source/e/easybuild', '5b/03/e135b19fadeb9b1ccb45eac9f60ca2dc3afe72d099f6bd84e03cb131f9bf')
        self.assertEqual(ft.derive_alt_pypi_url(url), alturl)

        # no crash on non-existing version
        url = 'https://pypi.python.org/packages/source/e/easybuild/easybuild-0.0.0.tar.gz'
        self.assertEqual(ft.derive_alt_pypi_url(url), None)

        # no crash on non-existing package
        url = 'https://pypi.python.org/packages/source/n/nosuchpackageonpypiever/nosuchpackageonpypiever-0.0.0.tar.gz'
        self.assertEqual(ft.derive_alt_pypi_url(url), None)


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(FileToolsTest)

if __name__ == '__main__':
    main()
