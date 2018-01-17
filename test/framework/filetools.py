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
Unit tests for filetools.py

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
@author: Ward Poelmans (Ghent University)
"""
import datetime
import glob
import os
import re
import shutil
import stat
import sys
import tempfile
import urllib2
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner
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
            ('test.bz2', "bunzip2 -c test.bz2 > test"),
            ('/some/path/test.bz2', "bunzip2 -c /some/path/test.bz2 > test"),
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

    def test_find_extension(self):
        """Test find_extension function."""
        tests = [
            ('test.zip', '.zip'),
            ('/some/path/test.tar', '.tar'),
            ('test.tar.gz', '.tar.gz'),
            ('test.TAR.GZ', '.TAR.GZ'),
            ('test.tgz', '.tgz'),
            ('test.gtgz', '.gtgz'),
            ('test.bz2', '.bz2'),
            ('/some/path/test.bz2', '.bz2'),
            ('test.tbz', '.tbz'),
            ('test.tbz2', '.tbz2'),
            ('test.tb2', '.tb2'),
            ('test.tar.bz2', '.tar.bz2'),
            ('test.gz', '.gz'),
            ('untar.gz', '.gz'),
            ("/some/path/test.gz", '.gz'),
            ('test.xz', '.xz'),
            ('test.tar.xz', '.tar.xz'),
            ('test.txz', '.txz'),
            ('test.iso', '.iso'),
            ('test.tar.Z', '.tar.Z'),
        ]
        for (fn, expected_ext) in tests:
            cmd = ft.find_extension(fn)
            self.assertEqual(expected_ext, cmd)

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

        os.environ['PATH'] = '%s:%s' % (self.test_prefix, os.environ['PATH'])
        # put a directory 'foo' in place (should be ignored by 'which')
        foo = os.path.join(self.test_prefix, 'foo')
        ft.mkdir(foo)
        ft.adjust_permissions(foo, stat.S_IRUSR|stat.S_IXUSR)
        # put executable file 'bar' in place
        bar = os.path.join(self.test_prefix, 'bar')
        ft.write_file(bar, '#!/bin/bash')
        ft.adjust_permissions(bar, stat.S_IRUSR|stat.S_IXUSR)
        self.assertEqual(ft.which('foo'), None)
        self.assertTrue(os.path.samefile(ft.which('bar'), bar))

        # add another location to 'bar', which should only return the first location by default
        barbis = os.path.join(self.test_prefix, 'more', 'bar')
        ft.write_file(barbis, '#!/bin/bash')
        ft.adjust_permissions(barbis, stat.S_IRUSR|stat.S_IXUSR)
        os.environ['PATH'] = '%s:%s' % (os.environ['PATH'], os.path.dirname(barbis))
        self.assertTrue(os.path.samefile(ft.which('bar'), bar))

        # test getting *all* locations to specified command
        res = ft.which('bar', retain_all=True)
        self.assertEqual(len(res), 2)
        self.assertTrue(os.path.samefile(res[0], bar))
        self.assertTrue(os.path.samefile(res[1], barbis))

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
            'sha256': '1c49562c4b404f3120a3fa0926c8d09c99ef80e470f7de03ffdfa14047960ea5',
            'sha512': '7610f6ce5e91e56e350d25c917490e4815f7986469fafa41056698aec256733eb7297da8b547d5e74b851d7c4e475900cec4744df0f887ae5c05bf1757c224b4',
        }

        # make sure checksums computation/verification is correct
        for checksum_type, checksum in known_checksums.items():
            self.assertEqual(ft.compute_checksum(fp, checksum_type=checksum_type), checksum)
            self.assertTrue(ft.verify_checksum(fp, (checksum_type, checksum)))

        # default checksum type is MD5
        self.assertEqual(ft.compute_checksum(fp), known_checksums['md5'])

        # both MD5 and SHA256 checksums can be verified without specifying type
        self.assertTrue(ft.verify_checksum(fp, known_checksums['md5']))
        self.assertTrue(ft.verify_checksum(fp, known_checksums['sha256']))

        # checksum of length 32 is assumed to be MD5, length 64 to be SHA256, other lengths not allowed
        # providing non-matching MD5 and SHA256 checksums results in failed verification
        self.assertFalse(ft.verify_checksum(fp, '1c49562c4b404f3120a3fa0926c8d09c'))
        self.assertFalse(ft.verify_checksum(fp, '7167b64b1ca062b9674ffef46f9325db7167b64b1ca062b9674ffef46f9325db'))
        # checksum of length other than 32/64 yields an error
        error_pattern = "Length of checksum '.*' \(\d+\) does not match with either MD5 \(32\) or SHA256 \(64\)"
        for checksum in ['tooshort', 'inbetween32and64charactersisnotgoodeither', known_checksums['sha256'] + 'foo']:
            self.assertErrorRegex(EasyBuildError, error_pattern, ft.verify_checksum, fp, checksum)

        # make sure faulty checksums are reported
        broken_checksums = dict([(typ, val[:-3] + 'foo') for (typ, val) in known_checksums.items()])
        for checksum_type, checksum in broken_checksums.items():
            self.assertFalse(ft.compute_checksum(fp, checksum_type=checksum_type) == checksum)
            self.assertFalse(ft.verify_checksum(fp, (checksum_type, checksum)))
        # md5 is default
        self.assertFalse(ft.compute_checksum(fp) == broken_checksums['md5'])
        self.assertFalse(ft.verify_checksum(fp, broken_checksums['md5']))
        self.assertFalse(ft.verify_checksum(fp, broken_checksums['sha256']))

        # check whether missing checksums are enforced
        build_options = {
            'enforce_checksums': True,
        }
        init_config(build_options=build_options)

        self.assertErrorRegex(EasyBuildError, "Missing checksum for", ft.verify_checksum, fp, None)
        self.assertTrue(ft.verify_checksum(fp, known_checksums['md5']))
        self.assertTrue(ft.verify_checksum(fp, known_checksums['sha256']))

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
        toy_source_dir = os.path.join(test_dir, 'sandbox', 'sources', 'toy')
        source_url = 'file://%s/%s' % (toy_source_dir, fn)
        res = ft.download_file(fn, source_url, target_location)
        self.assertEqual(res, target_location, "'download' of local file works")
        downloads = glob.glob(target_location + '*')
        self.assertEqual(len(downloads), 1)

        # non-existing files result in None return value
        self.assertEqual(ft.download_file(fn, 'file://%s/nosuchfile' % test_dir, target_location), None)

        # install broken proxy handler for opening local files
        # this should make urllib2.urlopen use this broken proxy for downloading from a file:// URL
        proxy_handler = urllib2.ProxyHandler({'file': 'file://%s/nosuchfile' % test_dir})
        urllib2.install_opener(urllib2.build_opener(proxy_handler))

        # downloading over a broken proxy results in None return value (failed download)
        # this tests whether proxies are taken into account by download_file
        self.assertEqual(ft.download_file(fn, source_url, target_location), None, "download over broken proxy fails")

        # modify existing download so we can verify re-download
        ft.write_file(target_location, '')

        # restore a working file handler, and retest download of local file
        urllib2.install_opener(urllib2.build_opener(urllib2.FileHandler()))
        res = ft.download_file(fn, source_url, target_location)
        self.assertEqual(res, target_location, "'download' of local file works after removing broken proxy")

        # existing file was re-downloaded, so a backup should have been created of the existing file
        downloads = glob.glob(target_location + '*')
        self.assertEqual(len(downloads), 2)
        backup = [d for d in downloads if os.path.basename(d) != fn][0]
        self.assertEqual(ft.read_file(backup), '')
        self.assertEqual(ft.compute_checksum(target_location), ft.compute_checksum(os.path.join(toy_source_dir, fn)))

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

        # also test behaviour of download_file under --dry-run
        build_options = {
            'extended_dry_run': True,
            'silent': False,
        }
        init_config(build_options=build_options)

        target_location = os.path.join(self.test_prefix, 'foo')
        if os.path.exists(target_location):
            shutil.rmtree(target_location)

        self.mock_stdout(True)
        path = ft.download_file(fn, source_url, target_location)
        txt = self.get_stdout()
        self.mock_stdout(False)

        self.assertEqual(path, target_location)
        self.assertFalse(os.path.exists(target_location))
        self.assertTrue(re.match("^file written: .*/foo$", txt))

        ft.download_file(fn, source_url, target_location, forced=True)
        self.assertTrue(os.path.exists(target_location))
        self.assertTrue(os.path.samefile(path, target_location))

    def test_mkdir(self):
        """Test mkdir function."""

        def check_mkdir(path, error=None, **kwargs):
            """Create specified directory with mkdir, and check for correctness."""
            if error is None:
                ft.mkdir(path, **kwargs)
                self.assertTrue(os.path.exists(path) and os.path.isdir(path), "Directory %s exists" % path)
            else:
                self.assertErrorRegex(EasyBuildError, error, ft.mkdir, path, **kwargs)

        foodir = os.path.join(self.test_prefix, 'foo')
        barfoodir = os.path.join(self.test_prefix, 'bar', 'foo')
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

    def test_path_matches(self):
        """Test path_matches function."""
        # set up temporary directories
        path1 = os.path.join(self.test_prefix, 'path1')
        ft.mkdir(path1)
        path2 = os.path.join(self.test_prefix, 'path2')
        ft.mkdir(path1)
        symlink = os.path.join(self.test_prefix, 'symlink')
        os.symlink(path1, symlink)
        missing = os.path.join(self.test_prefix, 'missing')

        self.assertFalse(ft.path_matches(missing, [path1, path2]))
        self.assertFalse(ft.path_matches(path1, [missing]))
        self.assertFalse(ft.path_matches(path1, [missing, path2]))
        self.assertFalse(ft.path_matches(path2, [missing, symlink]))
        self.assertTrue(ft.path_matches(path1, [missing, symlink]))

    def test_is_readable(self):
        """Test is_readable"""
        test_file = os.path.join(self.test_prefix, 'test.txt')

        self.assertFalse(ft.is_readable(test_file))

        ft.write_file(test_file, 'test')
        self.assertTrue(ft.is_readable(test_file))

        os.chmod(test_file, 0)
        self.assertFalse(ft.is_readable(test_file))

    def test_symlink_resolve_path(self):
        """Test symlink and resolve_path function"""

        # write_file and read_file tests are elsewhere. so not getting their states
        test_dir = os.path.join(os.path.realpath(self.test_prefix), 'test')
        ft.mkdir(test_dir)

        link_dir = os.path.join(self.test_prefix, 'linkdir')
        ft.symlink(test_dir, link_dir)
        self.assertTrue(os.path.islink(link_dir))
        self.assertTrue(os.path.exists(link_dir))

        test_file = os.path.join(link_dir, 'test.txt')
        ft.write_file(test_file, "test123")

        # creating the link file
        link = os.path.join(self.test_prefix, 'test.link')
        ft.symlink(test_file, link)

        # checking if file is symlink
        self.assertTrue(os.path.islink(link))
        self.assertTrue(os.path.exists(link_dir))

        self.assertTrue(os.path.samefile(os.path.join(self.test_prefix, 'test', 'test.txt'), link))

        # test resolve_path
        self.assertEqual(test_dir, ft.resolve_path(link_dir))
        self.assertEqual(os.path.join(os.path.realpath(self.test_prefix), 'test', 'test.txt'), ft.resolve_path(link))
        self.assertEqual(ft.read_file(link), "test123")
        self.assertErrorRegex(EasyBuildError, "Resolving path .* failed", ft.resolve_path, None)

    def test_remove_symlinks(self):
        """Test remove valid and invalid symlinks"""

        # creating test file
        fp = os.path.join(self.test_prefix, 'test.txt')
        txt = "test_my_link_file"
        ft.write_file(fp, txt)

        # creating the symlink
        link = os.path.join(self.test_prefix, 'test.link')
        ft.symlink(fp, link) # test if is symlink is valid is done elsewhere

        # Attempting to remove a valid symlink
        ft.remove_file(link)
        self.assertFalse(os.path.islink(link))
        self.assertFalse(os.path.exists(link))

        # Testing the removal of invalid symlinks
        # Restoring the symlink and removing the file, this way the symlink is invalid
        ft.symlink(fp, link)
        ft.remove_file(fp)
        # attempting to remove the invalid symlink
        ft.remove_file(link)
        self.assertFalse(os.path.islink(link))
        self.assertFalse(os.path.exists(link))

    def test_read_write_file(self):
        """Test reading/writing files."""

        fp = os.path.join(self.test_prefix, 'test.txt')
        txt = "test123"
        ft.write_file(fp, txt)
        self.assertEqual(ft.read_file(fp), txt)

        txt2 = '\n'.join(['test', '123'])
        ft.write_file(fp, txt2, append=True)
        self.assertEqual(ft.read_file(fp), txt+txt2)

        # test backing up of existing file
        ft.write_file(fp, 'foo', backup=True)
        self.assertEqual(ft.read_file(fp), 'foo')

        test_files = glob.glob(fp + '*')
        self.assertEqual(len(test_files), 2)
        backup1 = [x for x in test_files if os.path.basename(x) != 'test.txt'][0]
        self.assertEqual(ft.read_file(backup1), txt + txt2)

        ft.write_file(fp, 'bar', append=True, backup=True)
        self.assertEqual(ft.read_file(fp), 'foobar')

        test_files = glob.glob(fp + '*')
        self.assertEqual(len(test_files), 3)
        backup2 = [x for x in test_files if x != backup1 and os.path.basename(x) != 'test.txt'][0]
        self.assertEqual(ft.read_file(backup1), txt + txt2)
        self.assertEqual(ft.read_file(backup2), 'foo')

        # also test behaviour of write_file under --dry-run
        build_options = {
            'extended_dry_run': True,
            'silent': False,
        }
        init_config(build_options=build_options)

        foo = os.path.join(self.test_prefix, 'foo.txt')

        self.mock_stdout(True)
        ft.write_file(foo, 'bar')
        txt = self.get_stdout()
        self.mock_stdout(False)

        self.assertFalse(os.path.exists(foo))
        self.assertTrue(re.match("^file written: .*/foo.txt$", txt))

        ft.write_file(foo, 'bar', forced=True)
        self.assertTrue(os.path.exists(foo))
        self.assertEqual(ft.read_file(foo), 'bar')


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

    def test_back_up_file(self):
        """Test back_up_file function."""
        fp = os.path.join(self.test_prefix, 'sandbox', 'test.txt')
        txt = 'foobar'
        ft.write_file(fp, txt)

        known_files = ['test.txt']
        self.assertEqual(sorted(os.listdir(os.path.dirname(fp))), known_files)

        # Test simple file backup
        ft.back_up_file(fp)
        test_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(len(test_files), 2)
        new_file = [x for x in test_files if x not in known_files][0]
        self.assertTrue(new_file.startswith('test.txt.bak_'))
        first_normal_backup = os.path.join(os.path.dirname(fp), new_file)
        known_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(ft.read_file(os.path.join(os.path.dirname(fp), new_file)), txt)
        self.assertEqual(ft.read_file(fp), txt)

        # Test hidden simple file backup
        ft.back_up_file(fp, hidden=True)
        test_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(len(test_files), 3)
        new_file = [x for x in test_files if x not in known_files][0]
        self.assertTrue(new_file.startswith('.test.txt.bak_'))
        first_hidden_backup = os.path.join(os.path.dirname(fp), new_file)
        known_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(ft.read_file(os.path.join(os.path.dirname(fp), new_file)), txt)
        self.assertEqual(ft.read_file(fp), txt)

        # Test simple file backup with empty extension
        ft.back_up_file(fp, backup_extension='')
        test_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(len(test_files), 4)
        new_file = [x for x in test_files if x not in known_files][0]
        self.assertTrue(new_file.startswith('test.txt_'))
        first_normal_backup = os.path.join(os.path.dirname(fp), new_file)
        known_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(ft.read_file(os.path.join(os.path.dirname(fp), new_file)), txt)
        self.assertEqual(ft.read_file(fp), txt)

        # Test hidden simple file backup
        ft.back_up_file(fp, hidden=True, backup_extension=None)
        test_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(len(test_files), 5)
        new_file = [x for x in test_files if x not in known_files][0]
        self.assertTrue(new_file.startswith('.test.txt_'))
        first_hidden_backup = os.path.join(os.path.dirname(fp), new_file)
        known_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(ft.read_file(os.path.join(os.path.dirname(fp), new_file)), txt)
        self.assertEqual(ft.read_file(fp), txt)

        # Test simple file backup with custom extension
        ft.back_up_file(fp, backup_extension='foobar')
        test_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(len(test_files), 6)
        new_file = [x for x in test_files if x not in known_files][0]
        self.assertTrue(new_file.startswith('test.txt.foobar_'))
        first_bck_backup = os.path.join(os.path.dirname(fp), new_file)
        known_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(ft.read_file(os.path.join(os.path.dirname(fp), new_file)), txt)
        self.assertEqual(ft.read_file(fp), txt)

        # Test hidden simple file backup with custom extension
        ft.back_up_file(fp, backup_extension='bck', hidden=True)
        test_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(len(test_files), 7)
        new_file = [x for x in test_files if x not in known_files][0]
        self.assertTrue(new_file.startswith('.test.txt.bck_'))
        first_hidden_bck_backup = os.path.join(os.path.dirname(fp), new_file)
        known_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(ft.read_file(os.path.join(os.path.dirname(fp), new_file)), txt)
        self.assertEqual(ft.read_file(fp), txt)

        new_txt = 'barfoo'
        ft.write_file(fp, new_txt)
        self.assertEqual(len(os.listdir(os.path.dirname(fp))), 7)

        # Test file backup with existing backup
        ft.back_up_file(fp)
        test_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(len(test_files), 8)
        new_file = [x for x in test_files if x not in known_files][0]
        self.assertTrue(new_file.startswith('test.txt.bak_'))
        known_files = os.listdir(os.path.dirname(fp))
        self.assertTrue(ft.read_file(first_normal_backup), txt)
        self.assertEqual(ft.read_file(os.path.join(os.path.dirname(fp), new_file)), new_txt)
        self.assertEqual(ft.read_file(fp), new_txt)

        # Test hidden file backup with existing backup
        ft.back_up_file(fp, hidden=True, backup_extension=None)
        test_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(len(test_files), 9)
        new_file = [x for x in test_files if x not in known_files][0]
        self.assertTrue(new_file.startswith('.test.txt_'))
        known_files = os.listdir(os.path.dirname(fp))
        self.assertTrue(ft.read_file(first_hidden_backup), txt)
        self.assertEqual(ft.read_file(os.path.join(os.path.dirname(fp), new_file)), new_txt)
        self.assertEqual(ft.read_file(fp), new_txt)

        # Test file backup with extension and existing backup
        ft.back_up_file(fp, backup_extension='bck')
        test_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(len(test_files), 10)
        new_file = [x for x in test_files if x not in known_files][0]
        self.assertTrue(new_file.startswith('test.txt.bck_'))
        known_files = os.listdir(os.path.dirname(fp))
        self.assertTrue(ft.read_file(first_bck_backup), txt)
        self.assertEqual(ft.read_file(os.path.join(os.path.dirname(fp), new_file)), new_txt)
        self.assertEqual(ft.read_file(fp), new_txt)

        # Test hidden file backup with extension and existing backup
        ft.back_up_file(fp, backup_extension='foobar', hidden=True)
        test_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(len(test_files), 11)
        new_file = [x for x in test_files if x not in known_files][0]
        self.assertTrue(new_file.startswith('.test.txt.foobar_'))
        known_files = os.listdir(os.path.dirname(fp))
        self.assertTrue(ft.read_file(first_hidden_bck_backup), txt)
        self.assertEqual(ft.read_file(os.path.join(os.path.dirname(fp), new_file)), new_txt)
        self.assertEqual(ft.read_file(fp), new_txt)

    def test_move_logs(self):
        """Test move_logs function."""
        fp = os.path.join(self.test_prefix, 'test.txt')

        ft.write_file(fp, 'foobar')
        ft.write_file(fp + '.1', 'moarfoobar')
        ft.move_logs(fp, os.path.join(self.test_prefix, 'foo.log'))

        self.assertEqual(ft.read_file(os.path.join(self.test_prefix, 'foo.log')), 'foobar')
        self.assertEqual(ft.read_file(os.path.join(self.test_prefix, 'foo.log.1')), 'moarfoobar')

        ft.write_file(os.path.join(self.test_prefix, 'bar.log'), 'bar')
        ft.write_file(os.path.join(self.test_prefix, 'bar.log_1'), 'barbar')

        fp = os.path.join(self.test_prefix, 'test2.txt')
        ft.write_file(fp, 'moarbar')
        ft.write_file(fp + '.1', 'evenmoarbar')
        ft.move_logs(fp, os.path.join(self.test_prefix, 'bar.log'))

        logs = sorted([f for f in os.listdir(self.test_prefix) if 'log' in f])
        self.assertEqual(len(logs), 7)
        self.assertEqual(len([x for x in logs if x.startswith('eb-test-')]), 1)
        self.assertEqual(len([x for x in logs if x.startswith('foo')]), 2)
        self.assertEqual(len([x for x in logs if x.startswith('bar')]), 4)
        self.assertEqual(ft.read_file(os.path.join(self.test_prefix, 'bar.log_1')), 'barbar')
        self.assertEqual(ft.read_file(os.path.join(self.test_prefix, 'bar.log')), 'moarbar')
        self.assertEqual(ft.read_file(os.path.join(self.test_prefix, 'bar.log.1')), 'evenmoarbar')
        # one more 'bar' log, the rotated copy of bar.log
        other_bar = [x for x in logs if x.startswith('bar') and x not in ['bar.log', 'bar.log.1', 'bar.log_1']][0]
        self.assertEqual(ft.read_file(os.path.join(self.test_prefix, other_bar)), 'bar')

    def test_multidiff(self):
        """Test multidiff function."""
        test_easyconfigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        other_toy_ecs = [
            os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0-deps.eb'),
            os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0-gompi-1.3.12-test.eb'),
        ]

        # default (colored)
        toy_ec = os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb')
        lines = multidiff(toy_ec, other_toy_ecs).split('\n')
        expected = "Comparing \x1b[0;35mtoy-0.0.eb\x1b[0m with toy-0.0-deps.eb, toy-0.0-gompi-1.3.12-test.eb"

        red = "\x1b[0;41m"
        green = "\x1b[0;42m"
        endcol = "\x1b[0m"

        self.assertEqual(lines[0], expected)
        self.assertEqual(lines[1], "=====")

        # different versionsuffix
        self.assertTrue(lines[2].startswith("3 %s- versionsuffix = '-test'%s (1/2) toy-0.0-" % (red, endcol)))
        self.assertTrue(lines[3].startswith("3 %s- versionsuffix = '-deps'%s (1/2) toy-0.0-" % (red, endcol)))

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
        expected = "29 %s+ postinstallcmds = " % green
        self.assertTrue(any([line.startswith(expected) for line in lines]))
        expected = "30 %s+%s (1/2) toy-0.0" % (green, endcol)
        self.assertTrue(any(l.startswith(expected) for l in lines), "Found '%s' in: %s" % (expected, lines))
        self.assertEqual(lines[-1], "=====")

        lines = multidiff(toy_ec, other_toy_ecs, colored=False).split('\n')
        self.assertEqual(lines[0], "Comparing toy-0.0.eb with toy-0.0-deps.eb, toy-0.0-gompi-1.3.12-test.eb")
        self.assertEqual(lines[1], "=====")

        # different versionsuffix
        self.assertTrue(lines[2].startswith("3 - versionsuffix = '-test' (1/2) toy-0.0-"))
        self.assertTrue(lines[3].startswith("3 - versionsuffix = '-deps' (1/2) toy-0.0-"))

        # different toolchain in toy-0.0-gompi-1.3.12-test: '+' line with squigly line underneath to mark removed chars
        expected = "7 - toolchain = {'name': 'gompi', 'version': '1.3.12'} (1/2) toy"
        self.assertTrue(lines[7].startswith(expected))
        expected = "  ?                       ^^ ^^ "
        self.assertTrue(lines[8].startswith(expected))
        # different toolchain in toy-0.0-gompi-1.3.12-test: '-' line with squigly line underneath to mark added chars
        expected = "7 + toolchain = {'name': 'dummy', 'version': 'dummy'} (1/2) toy"
        self.assertTrue(lines[9].startswith(expected))
        expected = "  ?                       ^^ ^^ "
        self.assertTrue(lines[10].startswith(expected))

        # no postinstallcmds in toy-0.0-deps.eb
        expected = "29 + postinstallcmds = "
        self.assertTrue(any(l.startswith(expected) for l in lines), "Found '%s' in: %s" % (expected, lines))
        expected = "30 + (1/2) toy-0.0-"
        self.assertTrue(any(l.startswith(expected) for l in lines), "Found '%s' in: %s" % (expected, lines))

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

    def test_expand_glob_paths(self):
        """Test expand_glob_paths function."""
        for dirname in ['empty_dir', 'test_dir']:
            ft.mkdir(os.path.join(self.test_prefix, dirname), parents=True)
        for filename in ['file1.txt', 'test_dir/file2.txt', 'test_dir/file3.txt', 'test_dir2/file4.dat']:
            ft.write_file(os.path.join(self.test_prefix, filename), 'gibberish')

        globs = [os.path.join(self.test_prefix, '*.txt'), os.path.join(self.test_prefix, '*', '*')]
        expected = [
            os.path.join(self.test_prefix, 'file1.txt'),
            os.path.join(self.test_prefix, 'test_dir', 'file2.txt'),
            os.path.join(self.test_prefix, 'test_dir', 'file3.txt'),
            os.path.join(self.test_prefix, 'test_dir2', 'file4.dat'),
        ]
        self.assertEqual(sorted(ft.expand_glob_paths(globs)), sorted(expected))

        # passing non-glob patterns is fine too
        file2 = os.path.join(self.test_prefix, 'test_dir', 'file2.txt')
        self.assertEqual(ft.expand_glob_paths([file2]), [file2])

        # test expanding of '~' into $HOME value
        # hard overwrite $HOME in environment (used by os.path.expanduser) so we can reliably test this
        new_home = os.path.join(self.test_prefix, 'home')
        ft.mkdir(new_home, parents=True)
        ft.write_file(os.path.join(new_home, 'test.txt'), 'test')
        os.environ['HOME'] = new_home
        self.assertEqual(ft.expand_glob_paths(['~/*.txt']), [os.path.join(new_home, 'test.txt')])

        # check behaviour if glob that has no (file) matches is passed
        glob_pat = os.path.join(self.test_prefix, 'test_*')
        self.assertErrorRegex(EasyBuildError, "No files found using glob pattern", ft.expand_glob_paths, [glob_pat])

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

    def test_adjust_permissions_max_fail_ratio(self):
        """Test ratio of allowed failures when adjusting permissions"""
        # set up symlinks in test directory that can be broken to test allowed failure ratio of adjust_permissions
        testdir = os.path.join(self.test_prefix, 'test123')
        test_files = []
        for idx in range(0, 3):
            test_files.append(os.path.join(testdir, 'tmp%s' % idx))
            ft.write_file(test_files[-1], '')
            ft.symlink(test_files[-1], os.path.join(testdir, 'symlink%s' % idx))

        # by default, 50% of failures are allowed (to be robust against broken symlinks)
        perms = stat.S_IRUSR|stat.S_IWUSR|stat.S_IXUSR

        # one file remove, 1 dir + 2 files + 3 symlinks (of which 1 broken) left => 1/6 (16%) fail ratio is OK
        ft.remove_file(test_files[0])
        ft.adjust_permissions(testdir, perms, recursive=True, skip_symlinks=False, ignore_errors=True)
        # 2 files removed, 1 dir + 1 file + 3 symlinks (of which 2 broken) left => 2/5 (40%) fail ratio is OK
        ft.remove_file(test_files[1])
        ft.adjust_permissions(testdir, perms, recursive=True, skip_symlinks=False, ignore_errors=True)
        # 3 files removed, 1 dir + 3 broken symlinks => 75% fail ratio is too high, so error is raised
        ft.remove_file(test_files[2])
        error_pattern = r"75.00% of permissions/owner operations failed \(more than 50.00%\), something must be wrong"
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.adjust_permissions, testdir, perms,
                              recursive=True, skip_symlinks=False, ignore_errors=True)

        # reconfigure EasyBuild to allow even higher fail ratio (80%)
        build_options = {
            'max_fail_ratio_adjust_permissions': 0.8,
        }
        init_config(build_options=build_options)

        # 75% < 80%, so OK
        ft.adjust_permissions(testdir, perms, recursive=True, skip_symlinks=False, ignore_errors=True)

        # reconfigure to allow less failures (10%)
        build_options = {
            'max_fail_ratio_adjust_permissions': 0.1,
        }
        init_config(build_options=build_options)

        # way too many failures with 3 broken symlinks
        error_pattern = r"75.00% of permissions/owner operations failed \(more than 10.00%\), something must be wrong"
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.adjust_permissions, testdir, perms,
                              recursive=True, skip_symlinks=False, ignore_errors=True)

        # one broken symlink is still too much with max fail ratio of 10%
        ft.write_file(test_files[0], '')
        ft.write_file(test_files[1], '')
        error_pattern = r"16.67% of permissions/owner operations failed \(more than 10.00%\), something must be wrong"
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.adjust_permissions, testdir, perms,
                              recursive=True, skip_symlinks=False, ignore_errors=True)

        # all files restored, no more broken symlinks, so OK
        ft.write_file(test_files[2], '')
        ft.adjust_permissions(testdir, perms, recursive=True, skip_symlinks=False, ignore_errors=True)

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

        # passing empty list of substitions is a no-op
        ft.write_file(testfile, testtxt)
        ft.apply_regex_substitutions(testfile, [])
        new_testtxt = ft.read_file(testfile)
        self.assertEqual(new_testtxt, testtxt)

        # clean error on non-existing file
        error_pat = "Failed to patch .*/nosuchfile.txt: .*No such file or directory"
        path = os.path.join(self.test_prefix, 'nosuchfile.txt')
        self.assertErrorRegex(EasyBuildError, error_pat, ft.apply_regex_substitutions, path, regex_subs)

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

        # duplicates are filtered out, order is maintained
        os.environ['LM_LICENSE_FILE'] = ':'.join([lic_file1, lic_server, self.test_prefix, lic_file2, lic_file1])
        self.assertEqual(ft.find_flexlm_license(), ([lic_file1, lic_server, lic_file2], 'LM_LICENSE_FILE'))

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

    def test_is_patch_file(self):
        """Test for is_patch_file() function."""
        testdir = os.path.dirname(os.path.abspath(__file__))
        self.assertFalse(ft.is_patch_file(os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')))
        self.assertTrue(ft.is_patch_file(os.path.join(testdir, 'sandbox', 'sources', 'toy', 'toy-0.0_typo.patch')))

    def test_is_alt_pypi_url(self):
        """Test is_alt_pypi_url() function."""
        url = 'https://pypi.python.org/packages/source/e/easybuild/easybuild-2.7.0.tar.gz'
        self.assertFalse(ft.is_alt_pypi_url(url))

        url = url.replace('source/e/easybuild', '5b/03/e135b19fadeb9b1ccb45eac9f60ca2dc3afe72d099f6bd84e03cb131f9bf')
        self.assertTrue(ft.is_alt_pypi_url(url))

    def test_pypi_source_urls(self):
        """Test pypi_source_urls() function."""
        res = ft.pypi_source_urls('easybuild')
        eb340_url = 'https://pypi.python.org/packages/'
        eb340_url += '93/41/574d01f352671fbc8589a436167e15a7f3e27ac0aa635d208eb29ee8fd4e/'
        eb340_url += 'easybuild-3.4.0.tar.gz#md5=267a056a77a8f77fccfbf56354364045'
        self.assertTrue(eb340_url, res)
        pattern = '^https://pypi.python.org/packages/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{60}/'
        pattern += 'easybuild-[0-9rc.]+.tar.gz#md5=[a-f0-9]{32}$'
        regex = re.compile(pattern)
        for url in res:
            self.assertTrue(regex.match(url), "Pattern '%s' matches for '%s'" % (regex.pattern, url))
        # more than 50 releases at time of writing test, which always stay there
        self.assertTrue(len(res) > 50)

    def test_derive_alt_pypi_url(self):
        """Test derive_alt_pypi_url() function."""
        url = 'https://pypi.python.org/packages/source/e/easybuild/easybuild-2.7.0.tar.gz'
        alturl = url.replace('source/e/easybuild', '5b/03/e135b19fadeb9b1ccb45eac9f60ca2dc3afe72d099f6bd84e03cb131f9bf')
        self.assertEqual(ft.derive_alt_pypi_url(url), alturl)

        # test case to ensure that '.' characters in filename are escaped using '\.'
        # if not, the alternative URL for tornado-4.5b1.tar.gz is found...
        url = 'https://pypi.python.org/packages/source/t/tornado/tornado-4.5.1.tar.gz'
        alturl = url.replace('source/t/tornado', 'df/42/a180ee540e12e2ec1007ac82a42b09dd92e5461e09c98bf465e98646d187')
        self.assertEqual(ft.derive_alt_pypi_url(url), alturl)

        # no crash on non-existing version
        url = 'https://pypi.python.org/packages/source/e/easybuild/easybuild-0.0.0.tar.gz'
        self.assertEqual(ft.derive_alt_pypi_url(url), None)

        # no crash on non-existing package
        url = 'https://pypi.python.org/packages/source/n/nosuchpackageonpypiever/nosuchpackageonpypiever-0.0.0.tar.gz'
        self.assertEqual(ft.derive_alt_pypi_url(url), None)

    def test_apply_patch(self):
        """ Test apply_patch """
        testdir = os.path.dirname(os.path.abspath(__file__))
        tmpdir = self.test_prefix
        path = ft.extract_file(os.path.join(testdir, 'sandbox', 'sources', 'toy', 'toy-0.0.tar.gz'), tmpdir)
        toy_patch = os.path.join(testdir, 'sandbox', 'sources', 'toy', 'toy-0.0_typo.patch')

        self.assertTrue(ft.apply_patch(toy_patch, path))
        patched = ft.read_file(os.path.join(path, 'toy-0.0', 'toy.source'))
        pattern = "I'm a toy, and very proud of it"
        self.assertTrue(pattern in patched)

        # This patch is dependent on the previous one
        toy_patch_gz = os.path.join(testdir, 'sandbox', 'sources', 'toy', 'toy-0.0_gzip.patch.gz')
        self.assertTrue(ft.apply_patch(toy_patch_gz, path))
        patched_gz = ft.read_file(os.path.join(path, 'toy-0.0', 'toy.source'))
        pattern = "I'm a toy, and very very proud of it"
        self.assertTrue(pattern in patched_gz)

        # trying the patch again should fail
        self.assertErrorRegex(EasyBuildError, "Couldn't apply patch file", ft.apply_patch, toy_patch, path)

    def test_copy_file(self):
        """ Test copy_file """
        testdir = os.path.dirname(os.path.abspath(__file__))
        to_copy = os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        target_path = os.path.join(self.test_prefix, 'toy.eb')
        ft.copy_file(to_copy, target_path)
        self.assertTrue(os.path.exists(target_path))
        self.assertTrue(ft.read_file(to_copy) == ft.read_file(target_path))

        # clean error when trying to copy a directory with copy_file
        src, target = os.path.dirname(to_copy), os.path.join(self.test_prefix, 'toy')
        self.assertErrorRegex(EasyBuildError, "Failed to copy file.*Is a directory", ft.copy_file, src, target)

        # also test behaviour of copy_file under --dry-run
        build_options = {
            'extended_dry_run': True,
            'silent': False,
        }
        init_config(build_options=build_options)

        # remove target file, it shouldn't get copied under dry run
        os.remove(target_path)

        self.mock_stdout(True)
        ft.copy_file(to_copy, target_path)
        txt = self.get_stdout()
        self.mock_stdout(False)

        self.assertFalse(os.path.exists(target_path))
        self.assertTrue(re.search("^copied file .*/toy-0.0.eb to .*/toy.eb", txt))

        # forced copy, even in dry run mode
        self.mock_stdout(True)
        ft.copy_file(to_copy, target_path, force_in_dry_run=True)
        txt = self.get_stdout()
        self.mock_stdout(False)

        self.assertTrue(os.path.exists(target_path))
        self.assertTrue(ft.read_file(to_copy) == ft.read_file(target_path))
        self.assertEqual(txt, '')

    def test_copy_dir(self):
        """Test copy_file"""
        testdir = os.path.dirname(os.path.abspath(__file__))
        to_copy = os.path.join(testdir, 'easyconfigs', 'test_ecs', 'g', 'GCC')

        target_dir = os.path.join(self.test_prefix, 'GCC')
        self.assertFalse(os.path.exists(target_dir))

        self.assertTrue(os.path.exists(os.path.join(to_copy, 'GCC-4.7.2.eb')))

        ft.copy_dir(to_copy, target_dir, ignore=lambda src, names: [x for x in names if '4.7.2' in x])
        self.assertTrue(os.path.exists(target_dir))
        expected = ['GCC-4.6.3.eb', 'GCC-4.6.4.eb', 'GCC-4.8.2.eb', 'GCC-4.8.3.eb', 'GCC-4.9.2.eb', 'GCC-4.9.3-2.25.eb']
        self.assertEqual(sorted(os.listdir(target_dir)), expected)
        # GCC-4.7.2.eb should not get copied, since it's specified as file too ignore
        self.assertFalse(os.path.exists(os.path.join(target_dir, 'GCC-4.7.2.eb')))

        # clean error when trying to copy a file with copy_dir
        src, target = os.path.join(to_copy, 'GCC-4.6.3.eb'), os.path.join(self.test_prefix, 'GCC-4.6.3.eb')
        self.assertErrorRegex(EasyBuildError, "Failed to copy directory.*Not a directory", ft.copy_dir, src, target)

        # if directory already exists, we expect a clean error
        testdir = os.path.join(self.test_prefix, 'thisdirexists')
        ft.mkdir(testdir)
        self.assertErrorRegex(EasyBuildError, "Target location .* already exists", ft.copy_dir, to_copy, testdir)

        # also test behaviour of copy_file under --dry-run
        build_options = {
            'extended_dry_run': True,
            'silent': False,
        }
        init_config(build_options=build_options)

        shutil.rmtree(target_dir)
        self.assertFalse(os.path.exists(target_dir))

        # no actual copying in dry run mode, unless forced
        self.mock_stdout(True)
        ft.copy_dir(to_copy, target_dir)
        txt = self.get_stdout()
        self.mock_stdout(False)

        self.assertFalse(os.path.exists(target_dir))
        self.assertTrue(re.search("^copied directory .*/GCC to .*/GCC", txt))

        # forced copy, even in dry run mode
        self.mock_stdout(True)
        ft.copy_dir(to_copy, target_dir, force_in_dry_run=True)
        txt = self.get_stdout()
        self.mock_stdout(False)

        self.assertTrue(os.path.exists(target_dir))
        self.assertTrue(sorted(os.listdir(to_copy)) == sorted(os.listdir(target_dir)))
        self.assertEqual(txt, '')

    def test_copy(self):
        """Test copy function."""
        testdir = os.path.dirname(os.path.abspath(__file__))

        toy_file = os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        toy_patch = os.path.join(testdir, 'sandbox', 'sources', 'toy', 'toy-0.0_typo.patch')
        gcc_dir = os.path.join(testdir, 'easyconfigs', 'test_ecs', 'g', 'GCC')

        ft.copy([toy_file, gcc_dir, toy_patch], self.test_prefix)

        self.assertTrue(os.path.isdir(os.path.join(self.test_prefix, 'GCC')))
        for filepath in ['GCC/GCC-4.6.3.eb', 'GCC/GCC-4.9.2.eb', 'toy-0.0.eb', 'toy-0.0_typo.patch']:
            self.assertTrue(os.path.isfile(os.path.join(self.test_prefix, filepath)))

        # test copying of a single file, to a non-existing directory
        ft.copy(toy_file, os.path.join(self.test_prefix, 'foo'))
        self.assertTrue(os.path.isfile(os.path.join(self.test_prefix, 'foo', 'toy-0.0.eb')))

        # also test behaviour of copy under --dry-run
        build_options = {
            'extended_dry_run': True,
            'silent': False,
        }
        init_config(build_options=build_options)

        # no actual copying in dry run mode, unless forced
        self.mock_stdout(True)
        to_copy = [os.path.dirname(toy_file), os.path.join(gcc_dir, 'GCC-4.6.3.eb')]
        ft.copy(to_copy, self.test_prefix)
        txt = self.get_stdout()
        self.mock_stdout(False)

        self.assertFalse(os.path.exists(os.path.join(self.test_prefix, 'toy')))
        self.assertFalse(os.path.exists(os.path.join(self.test_prefix, 'GCC-4.6.3.eb')))
        self.assertTrue(re.search("^copied directory .*/toy to .*/toy", txt, re.M))
        self.assertTrue(re.search("^copied file .*/GCC-4.6.3.eb to .*/GCC-4.6.3.eb", txt, re.M))

        # forced copy, even in dry run mode
        self.mock_stdout(True)
        ft.copy(to_copy, self.test_prefix, force_in_dry_run=True)
        txt = self.get_stdout()
        self.mock_stdout(False)

        self.assertTrue(os.path.isdir(os.path.join(self.test_prefix, 'toy')))
        self.assertTrue(os.path.isfile(os.path.join(self.test_prefix, 'toy', 'toy-0.0.eb')))
        self.assertTrue(os.path.isfile(os.path.join(self.test_prefix, 'GCC-4.6.3.eb')))
        self.assertEqual(txt, '')

    def test_change_dir(self):
        """Test change_dir"""

        prev_dir = ft.change_dir(self.test_prefix)
        self.assertTrue(os.path.samefile(os.getcwd(), self.test_prefix))
        self.assertNotEqual(prev_dir, None)

        # prepare another directory to play around with
        test_path = os.path.join(self.test_prefix, 'anotherdir')
        ft.mkdir(test_path)

        # check return value (previous location)
        prev_dir = ft.change_dir(test_path)
        self.assertTrue(os.path.samefile(os.getcwd(), test_path))
        self.assertTrue(os.path.samefile(prev_dir, self.test_prefix))

        # check behaviour when current working directory does not exist anymore
        shutil.rmtree(test_path)
        prev_dir = ft.change_dir(self.test_prefix)
        self.assertTrue(os.path.samefile(os.getcwd(), self.test_prefix))
        self.assertEqual(prev_dir, None)

        foo = os.path.join(self.test_prefix, 'foo')
        self.assertErrorRegex(EasyBuildError, "Failed to change from .* to %s" % foo, ft.change_dir, foo)

    def test_extract_file(self):
        """Test extract_file"""
        testdir = os.path.dirname(os.path.abspath(__file__))
        toy_tarball = os.path.join(testdir, 'sandbox', 'sources', 'toy', 'toy-0.0.tar.gz')

        self.assertFalse(os.path.exists(os.path.join(self.test_prefix, 'toy-0.0', 'toy.source')))
        path = ft.extract_file(toy_tarball, self.test_prefix)
        self.assertTrue(os.path.exists(os.path.join(self.test_prefix, 'toy-0.0', 'toy.source')))
        self.assertTrue(os.path.samefile(path, self.test_prefix))
        shutil.rmtree(os.path.join(path, 'toy-0.0'))

        toy_tarball_renamed = os.path.join(self.test_prefix, 'toy_tarball')
        shutil.copyfile(toy_tarball, toy_tarball_renamed)

        path = ft.extract_file(toy_tarball_renamed, self.test_prefix, cmd="tar xfvz %s")
        self.assertTrue(os.path.exists(os.path.join(self.test_prefix, 'toy-0.0', 'toy.source')))
        self.assertTrue(os.path.samefile(path, self.test_prefix))
        shutil.rmtree(os.path.join(path, 'toy-0.0'))

        # also test behaviour of extract_file under --dry-run
        build_options = {
            'extended_dry_run': True,
            'silent': False,
        }
        init_config(build_options=build_options)

        self.mock_stdout(True)
        path = ft.extract_file(toy_tarball, self.test_prefix)
        txt = self.get_stdout()
        self.mock_stdout(False)

        self.assertTrue(os.path.samefile(path, self.test_prefix))
        self.assertFalse(os.path.exists(os.path.join(self.test_prefix, 'toy-0.0')))
        self.assertTrue(re.search('running command "tar xzf .*/toy-0.0.tar.gz"', txt))

        path = ft.extract_file(toy_tarball, self.test_prefix, forced=True)
        self.assertTrue(os.path.exists(os.path.join(self.test_prefix, 'toy-0.0', 'toy.source')))
        self.assertTrue(os.path.samefile(path, self.test_prefix))

    def test_remove_file(self):
        """Test remove_file"""
        testfile = os.path.join(self.test_prefix, 'foo')
        ft.write_file(testfile, 'bar')

        self.assertTrue(os.path.exists(testfile))
        ft.remove_file(testfile)

        ft.write_file(testfile, 'bar')
        ft.adjust_permissions(self.test_prefix, stat.S_IWUSR|stat.S_IWGRP|stat.S_IWOTH, add=False)
        self.assertErrorRegex(EasyBuildError, "Failed to remove", ft.remove_file, testfile)

        # also test behaviour of remove_file under --dry-run
        build_options = {
            'extended_dry_run': True,
            'silent': False,
        }
        init_config(build_options=build_options)
        self.mock_stdout(True)
        ft.remove_file(testfile)
        txt = self.get_stdout()
        self.mock_stdout(False)

        regex = re.compile("^file [^ ]* removed$")
        self.assertTrue(regex.match(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))

    def test_search_file(self):
        """Test search_file function."""
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')

        # check for default semantics, test case-insensitivity
        var_defs, hits = ft.search_file([test_ecs], 'HWLOC', silent=True)
        self.assertEqual(var_defs, [])
        self.assertEqual(len(hits), 2)
        self.assertTrue(all(os.path.exists(p) for p in hits))
        self.assertTrue(hits[0].endswith('/hwloc-1.6.2-GCC-4.6.4.eb'))
        self.assertTrue(hits[1].endswith('/hwloc-1.6.2-GCC-4.7.2.eb'))

        # check filename-only mode
        var_defs, hits = ft.search_file([test_ecs], 'HWLOC', silent=True, filename_only=True)
        self.assertEqual(var_defs, [])
        self.assertEqual(hits, ['hwloc-1.6.2-GCC-4.6.4.eb', 'hwloc-1.6.2-GCC-4.7.2.eb'])

        # check specifying of ignored dirs
        var_defs, hits = ft.search_file([test_ecs], 'HWLOC', silent=True, ignore_dirs=['hwloc'])
        self.assertEqual(var_defs + hits, [])

        # check short mode
        var_defs, hits = ft.search_file([test_ecs], 'HWLOC', silent=True, short=True)
        self.assertEqual(var_defs, [('CFGS1', os.path.join(test_ecs, 'h', 'hwloc'))])
        self.assertEqual(hits, ['$CFGS1/hwloc-1.6.2-GCC-4.6.4.eb', '$CFGS1/hwloc-1.6.2-GCC-4.7.2.eb'])

        # check terse mode (implies 'silent', overrides 'short')
        var_defs, hits = ft.search_file([test_ecs], 'HWLOC', terse=True, short=True)
        self.assertEqual(var_defs, [])
        expected = [
            os.path.join(test_ecs, 'h', 'hwloc', 'hwloc-1.6.2-GCC-4.6.4.eb'),
            os.path.join(test_ecs, 'h', 'hwloc', 'hwloc-1.6.2-GCC-4.7.2.eb'),
        ]
        self.assertEqual(hits, expected)

        # check combo of terse and filename-only
        var_defs, hits = ft.search_file([test_ecs], 'HWLOC', terse=True, filename_only=True)
        self.assertEqual(var_defs, [])
        self.assertEqual(hits, ['hwloc-1.6.2-GCC-4.6.4.eb', 'hwloc-1.6.2-GCC-4.7.2.eb'])

    def test_find_eb_script(self):
        """Test find_eb_script function."""
        self.assertTrue(os.path.exists(ft.find_eb_script('rpath_args.py')))
        self.assertTrue(os.path.exists(ft.find_eb_script('rpath_wrapper_template.sh.in')))
        self.assertErrorRegex(EasyBuildError, "Script 'no_such_script' not found", ft.find_eb_script, 'no_such_script')

        # put test script in place relative to location of 'eb'
        ft.write_file(os.path.join(self.test_prefix, 'bin', 'eb'), '#!/bin/bash\necho "fake eb"')
        ft.adjust_permissions(os.path.join(self.test_prefix, 'bin', 'eb'), stat.S_IXUSR)
        os.environ['PATH'] = '%s:%s' % (os.path.join(self.test_prefix, 'bin'), os.getenv('PATH', ''))

        justatest = os.path.join(self.test_prefix, 'easybuild', 'scripts', 'justatest.sh')
        ft.write_file(justatest, '#!/bin/bash')

        self.assertTrue(os.path.samefile(ft.find_eb_script('justatest.sh'), justatest))

    def test_move_file(self):
        """Test move_file function"""
        test_file = os.path.join(self.test_prefix, 'test.txt')
        ft.write_file(test_file, 'test123')

        new_test_file = os.path.join(self.test_prefix, 'subdir', 'new_test.txt')
        ft.move_file(test_file, new_test_file)

        self.assertFalse(os.path.exists(test_file))
        self.assertTrue(os.path.exists(new_test_file))
        self.assertEqual(ft.read_file(new_test_file), 'test123')

        # test moving to an existing file
        ft.write_file(test_file, 'gibberish')
        ft.move_file(new_test_file, test_file)

        self.assertTrue(os.path.exists(test_file))
        self.assertEqual(ft.read_file(test_file), 'test123')
        self.assertFalse(os.path.exists(new_test_file))

        # also test behaviour of move_file under --dry-run
        build_options = {
            'extended_dry_run': True,
            'silent': False,
        }
        init_config(build_options=build_options)

        self.mock_stdout(True)
        self.mock_stderr(True)
        ft.move_file(test_file, new_test_file)
        stdout = self.get_stdout()
        stderr = self.get_stderr()
        self.mock_stdout(False)
        self.mock_stderr(False)

        # informative message printed, but file was not actually moved
        regex = re.compile("^moved file .*/test\.txt to .*/new_test\.txt$")
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))
        self.assertEqual(stderr, '')

        self.assertTrue(os.path.exists(test_file))
        self.assertEqual(ft.read_file(test_file), 'test123')
        self.assertFalse(os.path.exists(new_test_file))

    def test_find_backup_name_candidate(self):
        """Test find_backup_name_candidate"""
        test_file = os.path.join(self.test_prefix, 'test.txt')
        ft.write_file(test_file, 'foo')

        # timestamp should be exactly 14 digits (year, month, day, hours, minutes, seconds)
        regex = re.compile('^test\.txt_[0-9]{14}$')

        res = ft.find_backup_name_candidate(test_file)
        self.assertTrue(os.path.samefile(os.path.dirname(res), self.test_prefix))
        fn = os.path.basename(res)
        self.assertTrue(regex.match(fn), "'%s' matches pattern '%s'" % (fn, regex.pattern))

        # create expected next backup location to (try and) see if it's handled well
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        ft.write_file(os.path.join(self.test_prefix, 'test.txt_%s' % timestamp), '')

        res = ft.find_backup_name_candidate(test_file)
        self.assertTrue(os.path.samefile(os.path.dirname(res), self.test_prefix))
        fn = os.path.basename(res)
        self.assertTrue(regex.match(fn), "'%s' matches pattern '%s'" % (fn, regex.pattern))

    def test_diff_files(self):
        """Test for diff_files function"""
        foo = os.path.join(self.test_prefix, 'foo')
        ft.write_file(foo, '\n'.join([
            'one',
            'two',
            'three',
            'four',
            'five',
        ]))
        bar = os.path.join(self.test_prefix, 'bar')
        ft.write_file(bar, '\n'.join([
            'zero',
            '1',
            'two',
            'tree',
            'four',
            'five',
        ]))
        expected = '\n'.join([
            "@@ -1,5 +1,6 @@",
            "-one",
            "+zero",
            "+1",
            " two",
            "-three",
            "+tree",
            " four",
            " five",
            '',
        ])
        res = ft.diff_files(foo, bar)
        self.assertTrue(res.endswith(expected), "%s ends with %s" % (res, expected))
        regex = re.compile('^--- .*/foo\s*\n\+\+\+ .*/bar\s*$', re.M)
        self.assertTrue(regex.search(res), "Pattern '%s' found in: %s" % (regex.pattern, res))


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(FileToolsTest, sys.argv[1:])

if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
