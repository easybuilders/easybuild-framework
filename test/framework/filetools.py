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
Unit tests for filetools.py

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
@author: Ward Poelmans (Ghent University)
@author: Maxime Boissonneault (Compute Canada, Universite Laval)
"""
import datetime
import glob
import os
import re
import shutil
import stat
import sys
import tempfile
import time
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered, init_config
from unittest import TextTestRunner
from easybuild.tools import run
import easybuild.tools.filetools as ft
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import IGNORE, ERROR
from easybuild.tools.multidiff import multidiff
from easybuild.tools.py2vs3 import std_urllib


class FileToolsTest(EnhancedTestCase):
    """ Testcase for filetools module """

    class_names = [
        ('GCC', 'EB_GCC'),
        ('7zip', 'EB_7zip'),
        ('Charm++', 'EB_Charm_plus__plus_'),
        ('DL_POLY_Classic', 'EB_DL_underscore_POLY_underscore_Classic'),
        ('0_foo+0x0x#-$__', 'EB_0_underscore_foo_plus_0x0x_hash__minus__dollar__underscore__underscore_'),
    ]

    def setUp(self):
        """Test setup."""
        super(FileToolsTest, self).setUp()

        self.orig_filetools_std_urllib_urlopen = ft.std_urllib.urlopen

    def tearDown(self):
        """Cleanup."""
        super(FileToolsTest, self).tearDown()

        ft.std_urllib.urlopen = self.orig_filetools_std_urllib_urlopen

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
            ('test.tar.xz', "unset TAPE; unxz test.tar.xz --stdout | tar x"),
            ('test.txz', "unset TAPE; unxz test.txz --stdout | tar x"),
            ('test.iso', "7z x test.iso"),
            ('test.tar.Z', "tar xzf test.tar.Z"),
            ('test.foo.bar.sh', "cp -a test.foo.bar.sh ."),
            # check whether extension is stripped correct to determine name of target file
            # cfr. https://github.com/easybuilders/easybuild-framework/pull/3705
            ('testbz2.bz2', "bunzip2 -c testbz2.bz2 > testbz2"),
            ('testgz.gz', "gunzip -c testgz.gz > testgz"),
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
            ('test.foo.bar.sh', '.sh'),
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

    def test_find_glob_pattern(self):
        """test find_glob_pattern function"""
        tmpdir = tempfile.mkdtemp()
        os.mkdir(os.path.join(tmpdir, 'python2.7'))
        os.mkdir(os.path.join(tmpdir, 'python2.7', 'include'))
        os.mkdir(os.path.join(tmpdir, 'python3.5m'))
        os.mkdir(os.path.join(tmpdir, 'python3.5m', 'include'))

        self.assertEqual(ft.find_glob_pattern(os.path.join(tmpdir, 'python2.7*')),
                         os.path.join(tmpdir, 'python2.7'))
        self.assertEqual(ft.find_glob_pattern(os.path.join(tmpdir, 'python2.7*', 'include')),
                         os.path.join(tmpdir, 'python2.7', 'include'))
        self.assertEqual(ft.find_glob_pattern(os.path.join(tmpdir, 'python3.5*')),
                         os.path.join(tmpdir, 'python3.5m'))
        self.assertEqual(ft.find_glob_pattern(os.path.join(tmpdir, 'python3.5*', 'include')),
                         os.path.join(tmpdir, 'python3.5m', 'include'))
        self.assertEqual(ft.find_glob_pattern(os.path.join(tmpdir, 'python3.6*'), False), None)
        self.assertErrorRegex(EasyBuildError, "Was expecting exactly", ft.find_glob_pattern,
                              os.path.join(tmpdir, 'python3.6*'))
        self.assertErrorRegex(EasyBuildError, "Was expecting exactly", ft.find_glob_pattern,
                              os.path.join(tmpdir, 'python*'))

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

        invalid_cmd = 'i_really_do_not_expect_a_command_with_a_name_like_this_to_be_available'
        path = ft.which(invalid_cmd)
        self.assertTrue(path is None)
        path = ft.which(invalid_cmd, on_error=IGNORE)
        self.assertTrue(path is None)
        error_msg = "Could not find command '%s'" % invalid_cmd
        self.assertErrorRegex(EasyBuildError, error_msg, ft.which, invalid_cmd, on_error=ERROR)

        os.environ['PATH'] = '%s:%s' % (self.test_prefix, os.environ['PATH'])
        # put a directory 'foo' in place (should be ignored by 'which')
        foo = os.path.join(self.test_prefix, 'foo')
        ft.mkdir(foo)
        ft.adjust_permissions(foo, stat.S_IRUSR | stat.S_IXUSR)
        # put executable file 'bar' in place
        bar = os.path.join(self.test_prefix, 'bar')
        ft.write_file(bar, '#!/bin/bash')
        ft.adjust_permissions(bar, stat.S_IRUSR | stat.S_IXUSR)
        self.assertEqual(ft.which('foo'), None)
        self.assertTrue(os.path.samefile(ft.which('bar'), bar))

        # add another location to 'bar', which should only return the first location by default
        barbis = os.path.join(self.test_prefix, 'more', 'bar')
        ft.write_file(barbis, '#!/bin/bash')
        ft.adjust_permissions(barbis, stat.S_IRUSR | stat.S_IXUSR)
        os.environ['PATH'] = '%s:%s' % (os.environ['PATH'], os.path.dirname(barbis))
        self.assertTrue(os.path.samefile(ft.which('bar'), bar))

        # test getting *all* locations to specified command
        res = ft.which('bar', retain_all=True)
        self.assertEqual(len(res), 2)
        self.assertTrue(os.path.samefile(res[0], bar))
        self.assertTrue(os.path.samefile(res[1], barbis))

        # both read/exec permissions must be available
        # if read permissions are removed for first hit, second hit is found instead
        ft.adjust_permissions(bar, stat.S_IRUSR, add=False)
        self.assertTrue(os.path.samefile(ft.which('bar'), barbis))

        # likewise for read permissions
        ft.adjust_permissions(bar, stat.S_IRUSR, add=True)
        self.assertTrue(os.path.samefile(ft.which('bar'), bar))

        ft.adjust_permissions(bar, stat.S_IXUSR, add=False)
        self.assertTrue(os.path.samefile(ft.which('bar'), barbis))

        # if read permission on other 'bar' are also removed, nothing is found anymore
        ft.adjust_permissions(barbis, stat.S_IRUSR, add=False)
        self.assertEqual(ft.which('bar'), None)

        # checking of read/exec permissions can be disabled via 'check_perms'
        self.assertTrue(os.path.samefile(ft.which('bar', check_perms=False), bar))

    def test_checksums(self):
        """Test checksum functionality."""

        fp = os.path.join(self.test_prefix, 'test.txt')
        ft.write_file(fp, "easybuild\n")

        known_checksums = {
            'adler32': '0x379257805',
            'crc32': '0x1457143216',
            'md5': '7167b64b1ca062b9674ffef46f9325db',
            'sha1': 'db05b79e09a4cc67e9dd30b313b5488813db3190',
            'sha256': '1c49562c4b404f3120a3fa0926c8d09c99ef80e470f7de03ffdfa14047960ea5',
            'sha512': '7610f6ce5e91e56e350d25c917490e4815f7986469fafa41056698aec256733e'
                      'b7297da8b547d5e74b851d7c4e475900cec4744df0f887ae5c05bf1757c224b4',
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

        # providing non-matching MD5 and SHA256 checksums results in failed verification
        self.assertFalse(ft.verify_checksum(fp, '1c49562c4b404f3120a3fa0926c8d09c'))
        self.assertFalse(ft.verify_checksum(fp, '7167b64b1ca062b9674ffef46f9325db7167b64b1ca062b9674ffef46f9325db'))

        # checksum of length 32 is assumed to be MD5, length 64 to be SHA256, other lengths not allowed
        # checksum of length other than 32/64 yields an error
        error_pattern = r"Length of checksum '.*' \(\d+\) does not match with either MD5 \(32\) or SHA256 \(64\)"
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

        # test specify alternative checksums
        alt_checksums = ('7167b64b1ca062b9674ffef46f9325db7167b64b1ca062b9674ffef46f9325db', known_checksums['sha256'])
        self.assertTrue(ft.verify_checksum(fp, alt_checksums))

        alt_checksums = ('fecf50db81148786647312bbd3b5c740', '2c829facaba19c0fcd81f9ce96bef712',
                         '840078aeb4b5d69506e7c8edae1e1b89', known_checksums['md5'])
        self.assertTrue(ft.verify_checksum(fp, alt_checksums))

        alt_checksums = ('840078aeb4b5d69506e7c8edae1e1b89', known_checksums['md5'], '2c829facaba19c0fcd81f9ce96bef712')
        self.assertTrue(ft.verify_checksum(fp, alt_checksums))

        alt_checksums = (known_checksums['md5'], '840078aeb4b5d69506e7c8edae1e1b89', '2c829facaba19c0fcd81f9ce96bef712')
        self.assertTrue(ft.verify_checksum(fp, alt_checksums))

        alt_checksums = (known_checksums['sha256'],)
        self.assertTrue(ft.verify_checksum(fp, alt_checksums))

        # check whether missing checksums are enforced
        build_options = {
            'enforce_checksums': True,
        }
        init_config(build_options=build_options)

        self.assertErrorRegex(EasyBuildError, "Missing checksum for", ft.verify_checksum, fp, None)
        self.assertTrue(ft.verify_checksum(fp, known_checksums['md5']))
        self.assertTrue(ft.verify_checksum(fp, known_checksums['sha256']))

        # Test dictionary-type checksums
        for checksum in [known_checksums[x] for x in ('md5', 'sha256')]:
            dict_checksum = {os.path.basename(fp): checksum, 'foo': 'baa'}
            self.assertTrue(ft.verify_checksum(fp, dict_checksum))

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

    def test_normalize_path(self):
        """Test normalize_path"""
        self.assertEqual(ft.normalize_path(''), '')
        self.assertEqual(ft.normalize_path('/'), '/')
        self.assertEqual(ft.normalize_path('//'), '//')
        self.assertEqual(ft.normalize_path('///'), '/')
        self.assertEqual(ft.normalize_path('/foo/bar/baz'), '/foo/bar/baz')
        self.assertEqual(ft.normalize_path('/foo//bar/././baz/'), '/foo/bar/baz')
        self.assertEqual(ft.normalize_path('foo//bar/././baz/'), 'foo/bar/baz')
        self.assertEqual(ft.normalize_path('//foo//bar/././baz/'), '//foo/bar/baz')
        self.assertEqual(ft.normalize_path('///foo//bar/././baz/'), '/foo/bar/baz')
        self.assertEqual(ft.normalize_path('////foo//bar/././baz/'), '/foo/bar/baz')
        self.assertEqual(ft.normalize_path('/././foo//bar/././baz/'), '/foo/bar/baz')
        self.assertEqual(ft.normalize_path('//././foo//bar/././baz/'), '//foo/bar/baz')

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
        # this should make urlopen use this broken proxy for downloading from a file:// URL
        proxy_handler = std_urllib.ProxyHandler({'file': 'file://%s/nosuchfile' % test_dir})
        std_urllib.install_opener(std_urllib.build_opener(proxy_handler))

        # downloading over a broken proxy results in None return value (failed download)
        # this tests whether proxies are taken into account by download_file
        self.assertEqual(ft.download_file(fn, source_url, target_location), None, "download over broken proxy fails")

        # modify existing download so we can verify re-download
        ft.write_file(target_location, '')

        # restore a working file handler, and retest download of local file
        std_urllib.install_opener(std_urllib.build_opener(std_urllib.FileHandler()))
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
        url = 'https://raw.githubusercontent.com/easybuilders/easybuild-framework/master/README.rst'
        try:
            std_urllib.urlopen(url)
            res = ft.download_file(fn, url, target_location)
            self.assertEqual(res, target_location, "download with specified timeout works")
        except std_urllib.URLError:
            print("Skipping timeout test in test_download_file (working offline)")

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

    def test_download_file_requests_fallback(self):
        """Test fallback to requests in download_file function."""
        url = 'https://raw.githubusercontent.com/easybuilders/easybuild-framework/master/README.rst'
        fn = 'README.rst'
        target = os.path.join(self.test_prefix, fn)

        # replaceurlopen with function that raises SSL error
        def fake_urllib_open(*args, **kwargs):
            error_msg = "<urlopen error [Errno 1] _ssl.c:510: error:12345:"
            error_msg += "SSL routines:SSL23_GET_SERVER_HELLO:sslv3 alert handshake failure>"
            raise IOError(error_msg)

        ft.std_urllib.urlopen = fake_urllib_open

        # if requests is available, file is downloaded
        if ft.HAVE_REQUESTS:
            res = ft.download_file(fn, url, target)
            self.assertTrue(res and os.path.exists(res))
            self.assertTrue("https://easybuilders.github.io/easybuild" in ft.read_file(res))

        # without requests being available, error is raised
        ft.HAVE_REQUESTS = False
        self.assertErrorRegex(EasyBuildError, "SSL issues with urllib2", ft.download_file, fn, url, target)

        # replaceurlopen with function that raises HTTP error 403
        def fake_urllib_open(*args, **kwargs):
            from easybuild.tools.py2vs3 import StringIO
            raise ft.std_urllib.HTTPError(url, 403, "Forbidden", "", StringIO())

        ft.std_urllib.urlopen = fake_urllib_open

        # if requests is available, file is downloaded
        if ft.HAVE_REQUESTS:
            res = ft.download_file(fn, url, target)
            self.assertTrue(res and os.path.exists(res))
            self.assertTrue("https://easybuilders.github.io/easybuild" in ft.read_file(res))

        # without requests being available, error is raised
        ft.HAVE_REQUESTS = False
        self.assertErrorRegex(EasyBuildError, "SSL issues with urllib2", ft.download_file, fn, url, target)

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

        # test symlink when it already exists and points to the same path
        ft.symlink(test_file, link)

        # test symlink when it already exists but points to a different path
        test_file2 = os.path.join(link_dir, 'test2.txt')
        ft.write_file(test_file, "test123")
        self.assertErrorRegex(EasyBuildError,
                              "Trying to symlink %s to %s, but the symlink already exists and points to %s." %
                              (test_file2, link, test_file),
                              ft.symlink, test_file2, link)

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
        ft.symlink(fp, link)  # test if is symlink is valid is done elsewhere

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

        # Test different "encodings"
        ascii_file = os.path.join(self.test_prefix, 'ascii.txt')
        txt = 'Hello World\nFoo bar'
        ft.write_file(ascii_file, txt)
        self.assertEqual(ft.read_file(ascii_file), txt)

        binary_file = os.path.join(self.test_prefix, 'binary.txt')
        txt = b'Hello World\x12\x00\x01\x02\x03\nFoo bar'
        ft.write_file(binary_file, txt)
        self.assertEqual(ft.read_file(binary_file, mode='rb'), txt)

        utf8_file = os.path.join(self.test_prefix, 'utf8.txt')
        txt = b'Hyphen: \xe2\x80\x93\nEuro sign: \xe2\x82\xac\na with dots: \xc3\xa4'
        if sys.version_info[0] == 3:
            txt_decoded = txt.decode('utf-8')
        else:
            txt_decoded = txt
        # Must work as binary and string
        ft.write_file(utf8_file, txt)
        self.assertEqual(ft.read_file(utf8_file), txt_decoded)
        ft.write_file(utf8_file, txt_decoded)
        self.assertEqual(ft.read_file(utf8_file), txt_decoded)

        # Test append
        fp = os.path.join(self.test_prefix, 'test.txt')
        txt = "test123"
        ft.write_file(fp, txt)
        self.assertEqual(ft.read_file(fp), txt)
        txt2 = '\n'.join(['test', '123'])
        ft.write_file(fp, txt2, append=True)
        self.assertEqual(ft.read_file(fp), txt + txt2)

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

        # tese use of 'verbose' to make write_file print location of backed up file
        self.mock_stdout(True)
        ft.write_file(fp, 'foo', backup=True, verbose=True)
        stdout = self.get_stdout()
        self.mock_stdout(False)
        regex = re.compile("^== Backup of .*/test.txt created at .*/test.txt.bak_[0-9]*")
        self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

        # by default, write_file will just blindly overwrite an already existing file
        self.assertTrue(os.path.exists(fp))
        ft.write_file(fp, 'blah')
        self.assertEqual(ft.read_file(fp), 'blah')

        # blind overwriting can be disabled via 'overwrite'
        error = "File exists, not overwriting it without --force: %s" % fp
        self.assertErrorRegex(EasyBuildError, error, ft.write_file, fp, 'blah', always_overwrite=False)
        self.assertErrorRegex(EasyBuildError, error, ft.write_file, fp, 'blah', always_overwrite=False, backup=True)

        # use of --force ensuring that file gets written regardless of whether or not it exists already
        build_options = {'force': True}
        init_config(build_options=build_options)

        ft.write_file(fp, 'overwrittenbyforce', always_overwrite=False)
        self.assertEqual(ft.read_file(fp), 'overwrittenbyforce')

        ft.write_file(fp, 'overwrittenbyforcewithbackup', always_overwrite=False, backup=True)
        self.assertEqual(ft.read_file(fp), 'overwrittenbyforcewithbackup')

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

        # test use of 'mode' in read_file
        self.assertEqual(ft.read_file(foo, mode='rb'), b'bar')

    def test_write_file_obj(self):
        """Test writing from a file-like object directly"""
        # Write a text file
        fp = os.path.join(self.test_prefix, 'test.txt')
        fp_out = os.path.join(self.test_prefix, 'test_out.txt')
        ft.write_file(fp, b'Hyphen: \xe2\x80\x93\nEuro sign: \xe2\x82\xac\na with dots: \xc3\xa4')

        with ft.open_file(fp, 'rb') as fh:
            ft.write_file(fp_out, fh)
        self.assertEqual(ft.read_file(fp_out), ft.read_file(fp))

        # Write a binary file
        fp = os.path.join(self.test_prefix, 'test.bin')
        fp_out = os.path.join(self.test_prefix, 'test_out.bin')
        ft.write_file(fp, b'\x00\x01'+os.urandom(42)+b'\x02\x03')

        with ft.open_file(fp, 'rb') as fh:
            ft.write_file(fp_out, fh)
        self.assertEqual(ft.read_file(fp_out, mode='rb'), ft.read_file(fp, mode='rb'))

    def test_is_binary(self):
        """Test is_binary function."""

        for test in ['foo', '', b'foo', b'', "This is just a test", b"This is just a test", b"\xa0"]:
            self.assertFalse(ft.is_binary(test))

        self.assertTrue(ft.is_binary(b'\00'))
        self.assertTrue(ft.is_binary(b"File is binary when it includes \00 somewhere"))
        self.assertTrue(ft.is_binary(ft.read_file('/bin/ls', mode='rb')))

    def test_det_patched_files(self):
        """Test det_patched_files function."""
        toy_patch_fn = 'toy-0.0_fix-silly-typo-in-printf-statement.patch'
        pf = os.path.join(os.path.dirname(__file__), 'sandbox', 'sources', 'toy', toy_patch_fn)
        self.assertEqual(ft.det_patched_files(pf), ['b/toy-0.0/toy.source'])
        self.assertEqual(ft.det_patched_files(pf, omit_ab_prefix=True), ['toy-0.0/toy.source'])

        # create a patch file with a non-UTF8 character in it, should not result in problems
        # (see https://github.com/easybuilders/easybuild-framework/issues/3190)
        test_patch = os.path.join(self.test_prefix, 'test.patch')
        patch_txt = b'\n'.join([
            b"--- foo",
            b"+++ foo",
            b"- test line",
            b"+ test line with non-UTF8 char: '\xa0'",
        ])
        ft.write_file(test_patch, patch_txt)
        self.assertEqual(ft.det_patched_files(test_patch), ['foo'])

    def test_guess_patch_level(self):
        "Test guess_patch_level."""
        # create dummy toy.source file so guess_patch_level can work
        ft.write_file(os.path.join(self.test_buildpath, 'toy.source'), "This is toy.source")

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
        res = ft.back_up_file(fp)
        test_files = os.listdir(os.path.dirname(fp))
        self.assertEqual(len(test_files), 2)
        new_file = [x for x in test_files if x not in known_files][0]
        self.assertTrue(os.path.samefile(res, os.path.join(self.test_prefix, 'sandbox', new_file)))
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

        # check whether strip_fn works as expected
        fp2 = fp + 'a.lua'
        ft.copy_file(fp, fp2)
        res = ft.back_up_file(fp2)
        self.assertTrue(fp2.endswith('.lua'))
        self.assertTrue('.lua' in os.path.basename(res))

        res = ft.back_up_file(fp2, strip_fn='.lua')
        self.assertFalse('.lua' in os.path.basename(res))
        # strip_fn should not remove the first a in 'a.lua'
        expected = os.path.basename(fp) + 'a.bak_'
        res_fn = os.path.basename(res)
        self.assertTrue(res_fn.startswith(expected), "'%s' should start with with '%s'" % (res_fn, expected))

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

        logs = sorted([f for f in os.listdir(self.test_prefix) if '.log' in f])
        self.assertEqual(len(logs), 7, "Found exactly 7 log files: %d (%s)" % (len(logs), logs))
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
            os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0-gompi-2018a-test.eb'),
        ]

        # default (colored)
        toy_ec = os.path.join(test_easyconfigs, 't', 'toy', 'toy-0.0.eb')
        lines = multidiff(toy_ec, other_toy_ecs).split('\n')
        expected = "Comparing \x1b[0;35mtoy-0.0.eb\x1b[0m with toy-0.0-deps.eb, toy-0.0-gompi-2018a-test.eb"

        red = "\x1b[0;41m"
        green = "\x1b[0;42m"
        endcol = "\x1b[0m"

        self.assertEqual(lines[0], expected)
        self.assertEqual(lines[1], "=====")

        # different versionsuffix
        self.assertTrue(lines[2].startswith("3 %s- versionsuffix = '-deps'%s (1/2) toy-0.0-" % (red, endcol)))
        self.assertTrue(lines[3].startswith("3 %s- versionsuffix = '-test'%s (1/2) toy-0.0-" % (red, endcol)))

        # different toolchain in toy-0.0-gompi-1.3.12-test: '+' line (added line in green)
        expected = "7 %(green)s+ toolchain = SYSTEM%(endcol)s"
        expected = expected % {'endcol': endcol, 'green': green, 'red': red}
        self.assertTrue(lines[7].startswith(expected))
        # different toolchain in toy-0.0-gompi-1.3.12-test: '-' line (removed line in red)
        expected = "8 %(red)s- toolchain = {'name': 'gompi', 'version': '2018a'}%(endcol)s"
        expected = expected % {'endcol': endcol, 'green': green, 'red': red}
        self.assertTrue(lines[8].startswith(expected))

        # no postinstallcmds in toy-0.0-deps.eb
        expected = "29 %s+ postinstallcmds = " % green
        self.assertTrue(any(line.startswith(expected) for line in lines))
        expected = "30 %s+%s (1/2) toy-0.0" % (green, endcol)
        self.assertTrue(any(line.startswith(expected) for line in lines), "Found '%s' in: %s" % (expected, lines))
        self.assertEqual(lines[-1], "=====")

        lines = multidiff(toy_ec, other_toy_ecs, colored=False).split('\n')
        self.assertEqual(lines[0], "Comparing toy-0.0.eb with toy-0.0-deps.eb, toy-0.0-gompi-2018a-test.eb")
        self.assertEqual(lines[1], "=====")

        # different versionsuffix
        self.assertTrue(lines[2].startswith("3 - versionsuffix = '-deps' (1/2) toy-0.0-"))
        self.assertTrue(lines[3].startswith("3 - versionsuffix = '-test' (1/2) toy-0.0-"))

        # different toolchain in toy-0.0-gompi-2018a-test: '+' added line, '-' removed line
        expected = "7 + toolchain = SYSTEM (1/2) toy"
        self.assertTrue(lines[7].startswith(expected))
        expected = "8 - toolchain = {'name': 'gompi', 'version': '2018a'} (1/2) toy"
        self.assertTrue(lines[8].startswith(expected))

        # no postinstallcmds in toy-0.0-deps.eb
        expected = "29 + postinstallcmds = "
        self.assertTrue(any(line.startswith(expected) for line in lines), "Found '%s' in: %s" % (expected, lines))
        expected = "30 + (1/2) toy-0.0-"
        self.assertTrue(any(line.startswith(expected) for line in lines), "Found '%s' in: %s" % (expected, lines))

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
        orig_umask = os.umask(0o022)

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
        ft.adjust_permissions(self.test_prefix, stat.S_IXUSR | stat.S_IWGRP)

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

        # check error reporting when changing permissions fails
        nosuchdir = os.path.join(self.test_prefix, 'nosuchdir')
        err_msg = "Failed to chmod/chown several paths.*No such file or directory"
        self.assertErrorRegex(EasyBuildError, err_msg, ft.adjust_permissions, nosuchdir, stat.S_IWOTH)
        nosuchfile = os.path.join(self.test_prefix, 'nosuchfile')
        self.assertErrorRegex(EasyBuildError, err_msg, ft.adjust_permissions, nosuchfile, stat.S_IWUSR, recursive=False)

        # try using adjust_permissions on a file not owned by current user,
        # using permissions that are actually already correct;
        # actual chmod should be skipped, otherwise it fails (you need to own a file to change permissions on it)

        # use /bin/ls, which should always be there, has read/exec permissions for anyone (755), and is owned by root
        ls_path = '/bin/ls'

        # try adding read/exec permissions for current user (which is already there)
        ft.adjust_permissions(ls_path, stat.S_IRUSR | stat.S_IXUSR, add=True)

        # try removing write permissions for others (which are not set already)
        ft.adjust_permissions(ls_path, stat.S_IWOTH, add=False)

        # try hard setting permissions using current permissions
        current_ls_perms = os.stat(ls_path)[stat.ST_MODE]
        ft.adjust_permissions(ls_path, current_ls_perms, relative=False)

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

        # by default, 50% of failures are allowed (to be robust against failures to change permissions)
        perms = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR

        ft.adjust_permissions(testdir, perms, recursive=True, ignore_errors=True)

        # introducing a broken symlinks doesn't cause problems
        ft.remove_file(test_files[0])
        ft.adjust_permissions(testdir, perms, recursive=True, ignore_errors=True)

        # multiple/all broken symlinks is no problem either, since symlinks are never followed
        ft.remove_file(test_files[1])
        ft.remove_file(test_files[2])
        ft.adjust_permissions(testdir, perms, recursive=True, ignore_errors=True)

        # reconfigure EasyBuild to allow even higher fail ratio (80%)
        build_options = {
            'max_fail_ratio_adjust_permissions': 0.8,
        }
        init_config(build_options=build_options)

        # 75% < 80%, so OK
        ft.adjust_permissions(testdir, perms, recursive=True, ignore_errors=True)

        # reconfigure to allow less failures (10%)
        build_options = {
            'max_fail_ratio_adjust_permissions': 0.1,
        }
        init_config(build_options=build_options)

        ft.adjust_permissions(testdir, perms, recursive=True, ignore_errors=True)

        ft.write_file(test_files[0], '')
        ft.write_file(test_files[1], '')
        ft.write_file(test_files[2], '')
        ft.adjust_permissions(testdir, perms, recursive=True, ignore_errors=True)

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
        regex_subs_copy = regex_subs[:]
        ft.apply_regex_substitutions(testfile, regex_subs)

        expected_testtxt = '\n'.join([
            "CC = ${CC}",
            "CFLAGS = -O2",
            "FC = ${FC}",
            "FFLAGS = -O2 -ffixed-form",
        ])
        new_testtxt = ft.read_file(testfile)
        self.assertEqual(new_testtxt, expected_testtxt)
        # Must not have touched the list
        self.assertEqual(regex_subs_copy, regex_subs)

        # backup file is created by default
        backup = testfile + '.orig.eb'
        self.assertTrue(os.path.exists(backup))
        self.assertEqual(ft.read_file(backup), testtxt)

        # cleanup
        ft.remove_file(backup)
        ft.write_file(testfile, testtxt)

        # extension of backed up file can be controlled
        ft.apply_regex_substitutions(testfile, regex_subs, backup='.backup')

        new_testtxt = ft.read_file(testfile)
        self.assertEqual(new_testtxt, expected_testtxt)

        backup = testfile + '.backup'
        self.assertTrue(os.path.exists(backup))
        self.assertEqual(ft.read_file(backup), testtxt)

        # cleanup
        ft.remove_file(backup)
        ft.write_file(testfile, testtxt)

        # creation of backup can be avoided
        ft.apply_regex_substitutions(testfile, regex_subs, backup=False)
        new_testtxt = ft.read_file(testfile)
        self.assertEqual(new_testtxt, expected_testtxt)
        self.assertFalse(os.path.exists(backup))

        # passing empty list of substitions is a no-op
        ft.write_file(testfile, testtxt)
        ft.apply_regex_substitutions(testfile, [], on_missing_match=run.IGNORE)
        new_testtxt = ft.read_file(testfile)
        self.assertEqual(new_testtxt, testtxt)

        # Check handling of on_missing_match
        ft.write_file(testfile, testtxt)
        regex_subs_no_match = [('Not there', 'Not used')]
        error_pat = 'Nothing found to replace in %s' % testfile
        # Error
        self.assertErrorRegex(EasyBuildError, error_pat, ft.apply_regex_substitutions, testfile, regex_subs_no_match,
                              on_missing_match=run.ERROR)

        # Warn
        with self.log_to_testlogfile():
            ft.apply_regex_substitutions(testfile, regex_subs_no_match, on_missing_match=run.WARN)
        logtxt = ft.read_file(self.logfile)
        self.assertTrue('WARNING ' + error_pat in logtxt)

        # Ignore
        with self.log_to_testlogfile():
            ft.apply_regex_substitutions(testfile, regex_subs_no_match, on_missing_match=run.IGNORE)
        logtxt = ft.read_file(self.logfile)
        self.assertTrue('INFO ' + error_pat in logtxt)

        # clean error on non-existing file
        error_pat = "Failed to patch .*/nosuchfile.txt: .*No such file or directory"
        path = os.path.join(self.test_prefix, 'nosuchfile.txt')
        self.assertErrorRegex(EasyBuildError, error_pat, ft.apply_regex_substitutions, path, regex_subs)

        # make sure apply_regex_substitutions can patch files that include UTF-8 characters
        testtxt = b"foo \xe2\x80\x93 bar"  # This is an UTF-8 "-"
        ft.write_file(testfile, testtxt)
        ft.apply_regex_substitutions(testfile, [('foo', 'FOO')])
        txt = ft.read_file(testfile)
        if sys.version_info[0] == 3:
            testtxt = testtxt.decode('utf-8')
        self.assertEqual(txt, testtxt.replace('foo', 'FOO'))

        # make sure apply_regex_substitutions can patch files that include non-UTF-8 characters
        testtxt = b"foo \xe2 bar"
        ft.write_file(testfile, testtxt)
        ft.apply_regex_substitutions(testfile, [('foo', 'FOO')])
        txt = ft.read_file(testfile)
        # avoid checking problematic character itself, since it's treated differently in Python 2 vs 3
        self.assertTrue(txt.startswith('FOO '))
        self.assertTrue(txt.endswith(' bar'))

        # also test apply_regex_substitutions with a *list* of paths
        # cfr. https://github.com/easybuilders/easybuild-framework/issues/3493
        test_dir = os.path.join(self.test_prefix, 'test_dir')
        test_file1 = os.path.join(test_dir, 'one.txt')
        test_file2 = os.path.join(test_dir, 'two.txt')
        ft.write_file(test_file1, "Donald is an elephant")
        ft.write_file(test_file2, "2 + 2 = 5")
        regexs = [
            ('Donald', 'Dumbo'),
            ('= 5', '= 4'),
        ]
        ft.apply_regex_substitutions([test_file1, test_file2], regexs)

        # also check dry run mode
        init_config(build_options={'extended_dry_run': True})
        self.mock_stderr(True)
        self.mock_stdout(True)
        ft.apply_regex_substitutions([test_file1, test_file2], regexs)
        stderr, stdout = self.get_stderr(), self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        self.assertFalse(stderr)
        regex = re.compile('\n'.join([
            r"applying regex substitutions to file\(s\): .*/test_dir/one.txt, .*/test_dir/two.txt",
            r"  \* regex pattern 'Donald', replacement string 'Dumbo'",
            r"  \* regex pattern '= 5', replacement string '= 4'",
            '',
        ]))
        self.assertTrue(regex.search(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

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
        toy_patch_fn = 'toy-0.0_fix-silly-typo-in-printf-statement.patch'
        self.assertTrue(ft.is_patch_file(os.path.join(testdir, 'sandbox', 'sources', 'toy', toy_patch_fn)))

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
        pattern_md5 = pattern + 'easybuild-[0-9a-z.]+.tar.gz#md5=[a-f0-9]{32}$'
        pattern_sha256 = pattern + 'easybuild-[0-9a-z.]+.tar.gz#sha256=[a-f0-9]{64}$'
        regex_md5 = re.compile(pattern_md5)
        regex_sha256 = re.compile(pattern_sha256)
        for url in res:
            error_msg = "Pattern '%s' or '%s' matches for '%s'" % (regex_md5.pattern, regex_sha256.pattern, url)
            self.assertTrue(regex_md5.match(url) or regex_sha256.match(url), error_msg)

        # more than 50 releases at time of writing test, which always stay there
        self.assertTrue(len(res) > 50)

        # check for Python package that has yanked releases,
        # see https://github.com/easybuilders/easybuild-framework/issues/3301
        res = ft.pypi_source_urls('ipython')
        self.assertTrue(isinstance(res, list) and res)
        prefix = 'https://pypi.python.org/packages'
        for entry in res:
            self.assertTrue(entry.startswith(prefix), "'%s' should start with '%s'" % (entry, prefix))
            self.assertTrue('ipython' in entry, "Pattern 'ipython' should be found in '%s'" % entry)

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
        toy_tar_gz = os.path.join(testdir, 'sandbox', 'sources', 'toy', 'toy-0.0.tar.gz')
        path = ft.extract_file(toy_tar_gz, self.test_prefix, change_into_dir=False)
        toy_patch_fn = 'toy-0.0_fix-silly-typo-in-printf-statement.patch'
        toy_patch = os.path.join(testdir, 'sandbox', 'sources', 'toy', toy_patch_fn)

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

        # test copying of files, both to an existing directory and a non-existing location
        test_file = os.path.join(self.test_prefix, 'foo.txt')
        ft.write_file(test_file, '123')
        target_dir = os.path.join(self.test_prefix, 'target_dir')
        ft.mkdir(target_dir)

        # copy to existing dir
        ft.apply_patch(test_file, target_dir, copy=True)
        self.assertEqual(ft.read_file(os.path.join(target_dir, 'foo.txt')), '123')

        # copy to existing file
        ft.write_file(os.path.join(target_dir, 'foo.txt'), '')
        ft.apply_patch(test_file, target_dir, copy=True)
        self.assertEqual(ft.read_file(os.path.join(target_dir, 'foo.txt')), '123')

        # copy to new file in existing dir
        ft.apply_patch(test_file, os.path.join(target_dir, 'target.txt'), copy=True)
        self.assertEqual(ft.read_file(os.path.join(target_dir, 'target.txt')), '123')

        # copy to non-existing subdir
        ft.apply_patch(test_file, os.path.join(target_dir, 'subdir', 'target.txt'), copy=True)
        self.assertEqual(ft.read_file(os.path.join(target_dir, 'subdir', 'target.txt')), '123')

        # cleanup and re-extract toy source tarball
        ft.remove_dir(self.test_prefix)
        ft.mkdir(self.test_prefix)
        ft.change_dir(self.test_prefix)
        path = ft.extract_file(toy_tar_gz, self.test_prefix, change_into_dir=False)

        # test applying of patch with git
        toy_source_path = os.path.join(self.test_prefix, 'toy-0.0', 'toy.source')
        self.assertFalse("I'm a toy, and very proud of it" in ft.read_file(toy_source_path))

        ft.apply_patch(toy_patch, self.test_prefix, use_git=True)
        self.assertTrue("I'm a toy, and very proud of it" in ft.read_file(toy_source_path))

        # construct patch that only adds a new file,
        # this shouldn't break applying a patch with git even when no level is specified
        new_file_patch = os.path.join(self.test_prefix, 'toy_new_file.patch')
        new_file_patch_txt = '\n'.join([
            "new file mode 100755",
            "--- /dev/null\t1970-01-01 01:00:00.000000000 +0100",
            "+++ b/toy-0.0/new_file.txt\t2020-08-18 12:31:57.000000000 +0200",
            "@@ -0,0 +1 @@",
            "+This is a new file\n",
        ])
        ft.write_file(new_file_patch, new_file_patch_txt)
        ft.apply_patch(new_file_patch, self.test_prefix, use_git=True)
        new_file_path = os.path.join(self.test_prefix, 'toy-0.0', 'new_file.txt')
        self.assertEqual(ft.read_file(new_file_path), "This is a new file\n")

        # cleanup & restore
        ft.remove_dir(path)
        path = ft.extract_file(toy_tar_gz, self.test_prefix, change_into_dir=False)

        self.assertFalse("I'm a toy, and very proud of it" in ft.read_file(toy_source_path))

        # mock stderr to catch deprecation warning caused by setting 'use_git_am'
        self.allow_deprecated_behaviour()
        self.mock_stderr(True)
        ft.apply_patch(toy_patch, self.test_prefix, use_git_am=True)
        stderr = self.get_stderr()
        self.mock_stderr(False)
        self.assertTrue("I'm a toy, and very proud of it" in ft.read_file(toy_source_path))
        self.assertTrue("'use_git_am' named argument in apply_patch function has been renamed to 'use_git'" in stderr)

    def test_copy_file(self):
        """Test copy_file function."""
        testdir = os.path.dirname(os.path.abspath(__file__))
        to_copy = os.path.join(testdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')
        target_path = os.path.join(self.test_prefix, 'toy.eb')
        ft.copy_file(to_copy, target_path)
        self.assertTrue(os.path.exists(target_path))
        self.assertTrue(ft.read_file(to_copy) == ft.read_file(target_path))

        # clean error when trying to copy a directory with copy_file
        src, target = os.path.dirname(to_copy), os.path.join(self.test_prefix, 'toy')
        self.assertErrorRegex(EasyBuildError, "Failed to copy file.*Is a directory", ft.copy_file, src, target)

        # test overwriting of existing file owned by someone else,
        # which should make copy_file use shutil.copyfile rather than shutil.copy2
        test_file_contents = "This is just a test, 1, 2, 3, check"
        test_file_to_copy = os.path.join(self.test_prefix, 'test123.txt')
        ft.write_file(test_file_to_copy, test_file_contents)

        # this test file must be created before, we can't create a file owned by another account
        test_file_to_overwrite = os.path.join('/tmp', 'file_to_overwrite_for_easybuild_test_copy_file.txt')
        if os.path.exists(test_file_to_overwrite):
            # make sure target file is owned by another user (we don't really care who)
            self.assertTrue(os.stat(test_file_to_overwrite).st_uid != os.getuid())
            # make sure the target file is writeable by current user (otherwise the copy will definitely fail)
            self.assertTrue(os.access(test_file_to_overwrite, os.W_OK))

            ft.copy_file(test_file_to_copy, test_file_to_overwrite)
            self.assertEqual(ft.read_file(test_file_to_overwrite), test_file_contents)
        else:
            # printing this message will make test suite fail in Travis/GitHub CI,
            # since we check for unexpected output produced by the tests
            print("Skipping overwrite-file-owned-by-other-user copy_file test (%s is missing)" % test_file_to_overwrite)

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

    def test_copy_files(self):
        """Test copy_files function."""
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')
        toy_ec_txt = ft.read_file(toy_ec)
        bzip2_ec = os.path.join(test_ecs, 'b', 'bzip2', 'bzip2-1.0.6-GCC-4.9.2.eb')
        bzip2_ec_txt = ft.read_file(bzip2_ec)

        # copying a single file to a non-existing directory
        target_dir = os.path.join(self.test_prefix, 'target_dir1')
        ft.copy_files([toy_ec], target_dir)
        copied_toy_ec = os.path.join(target_dir, 'toy-0.0.eb')
        self.assertTrue(os.path.exists(copied_toy_ec))
        self.assertEqual(ft.read_file(copied_toy_ec), toy_ec_txt)

        # copying a single file to an existing directory
        ft.copy_files([bzip2_ec], target_dir)
        copied_bzip2_ec = os.path.join(target_dir, 'bzip2-1.0.6-GCC-4.9.2.eb')
        self.assertTrue(os.path.exists(copied_bzip2_ec))
        self.assertEqual(ft.read_file(copied_bzip2_ec), bzip2_ec_txt)

        # copying multiple files to a non-existing directory
        target_dir = os.path.join(self.test_prefix, 'target_dir_multiple')
        ft.copy_files([toy_ec, bzip2_ec], target_dir)
        copied_toy_ec = os.path.join(target_dir, 'toy-0.0.eb')
        self.assertTrue(os.path.exists(copied_toy_ec))
        self.assertEqual(ft.read_file(copied_toy_ec), toy_ec_txt)
        copied_bzip2_ec = os.path.join(target_dir, 'bzip2-1.0.6-GCC-4.9.2.eb')
        self.assertTrue(os.path.exists(copied_bzip2_ec))
        self.assertEqual(ft.read_file(copied_bzip2_ec), bzip2_ec_txt)

        # copying files to an existing target that is not a directory results in an error
        self.assertTrue(os.path.isfile(copied_toy_ec))
        error_pattern = "/toy-0.0.eb exists but is not a directory"
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.copy_files, [bzip2_ec], copied_toy_ec)

        # by default copy_files allows empty input list, but if allow_empty=False then an error is raised
        ft.copy_files([], self.test_prefix)
        error_pattern = 'One or more files to copy should be specified!'
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.copy_files, [], self.test_prefix, allow_empty=False)

        # test special case: copying a single file to a file target via target_single_file=True
        target = os.path.join(self.test_prefix, 'target')
        self.assertFalse(os.path.exists(target))
        ft.copy_files([toy_ec], target, target_single_file=True)
        self.assertTrue(os.path.exists(target))
        self.assertTrue(os.path.isfile(target))
        self.assertEqual(toy_ec_txt, ft.read_file(target))

        ft.remove_file(target)

        # also test target_single_file=True with path including a missing subdirectory
        target = os.path.join(self.test_prefix, 'target_parent', 'target_subdir', 'target.txt')
        self.assertFalse(os.path.exists(target))
        self.assertFalse(os.path.exists(os.path.dirname(target)))
        ft.copy_files([toy_ec], target, target_single_file=True)
        self.assertTrue(os.path.exists(target))
        self.assertTrue(os.path.isfile(target))
        self.assertEqual(toy_ec_txt, ft.read_file(target))

        ft.remove_file(target)

        # default behaviour is to copy single file list to target *directory*
        self.assertFalse(os.path.exists(target))
        ft.copy_files([toy_ec], target)
        self.assertTrue(os.path.exists(target))
        self.assertTrue(os.path.isdir(target))
        copied_toy_ec = os.path.join(target, 'toy-0.0.eb')
        self.assertTrue(os.path.exists(copied_toy_ec))
        self.assertEqual(toy_ec_txt, ft.read_file(copied_toy_ec))

        ft.remove_dir(target)

        # test enabling verbose mode
        self.mock_stderr(True)
        self.mock_stdout(True)
        ft.copy_files([toy_ec], target, verbose=True)
        stderr, stdout = self.get_stderr(), self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertEqual(stderr, '')
        regex = re.compile(r"^1 file\(s\) copied to .*/target")
        self.assertTrue(regex.match(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

        ft.remove_dir(target)

        self.mock_stderr(True)
        self.mock_stdout(True)
        ft.copy_files([toy_ec], target, target_single_file=True, verbose=True)
        stderr, stdout = self.get_stderr(), self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertEqual(stderr, '')
        regex = re.compile(r"/.*/toy-0\.0\.eb copied to .*/target")
        self.assertTrue(regex.match(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

        ft.remove_file(target)

        # check behaviour under -x: only printing, no actual copying
        init_config(build_options={'extended_dry_run': True})
        self.assertFalse(os.path.exists(os.path.join(target, 'test.eb')))

        self.mock_stderr(True)
        self.mock_stdout(True)
        ft.copy_files(['test.eb'], target)
        stderr, stdout = self.get_stderr(), self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        self.assertFalse(os.path.exists(os.path.join(target, 'test.eb')))
        self.assertEqual(stderr, '')

        regex = re.compile("^copied test.eb to .*/target")
        self.assertTrue(regex.match(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

        self.mock_stderr(True)
        self.mock_stdout(True)
        ft.copy_files(['bar.eb', 'foo.eb'], target)
        stderr, stdout = self.get_stderr(), self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        self.assertFalse(os.path.exists(os.path.join(target, 'bar.eb')))
        self.assertFalse(os.path.exists(os.path.join(target, 'foo.eb')))
        self.assertEqual(stderr, '')

        regex = re.compile("^copied 2 files to .*/target")
        self.assertTrue(regex.match(stdout), "Pattern '%s' should be found in: %s" % (regex.pattern, stdout))

    def test_has_recursive_symlinks(self):
        """Test has_recursive_symlinks function"""
        test_folder = tempfile.mkdtemp()
        self.assertFalse(ft.has_recursive_symlinks(test_folder))
        # Clasic Loop: Symlink to .
        os.symlink('.', os.path.join(test_folder, 'self_link_dot'))
        self.assertTrue(ft.has_recursive_symlinks(test_folder))
        # Symlink to self
        test_folder = tempfile.mkdtemp()
        os.symlink('self_link', os.path.join(test_folder, 'self_link'))
        self.assertTrue(ft.has_recursive_symlinks(test_folder))
        # Symlink from 2 folders up
        test_folder = tempfile.mkdtemp()
        sub_folder = os.path.join(test_folder, 'sub1', 'sub2')
        os.makedirs(sub_folder)
        os.symlink(os.path.join('..', '..'), os.path.join(sub_folder, 'uplink'))
        self.assertTrue(ft.has_recursive_symlinks(test_folder))
        # Non-issue: Symlink to sibling folders
        test_folder = tempfile.mkdtemp()
        sub_folder = os.path.join(test_folder, 'sub1', 'sub2')
        os.makedirs(sub_folder)
        sibling_folder = os.path.join(test_folder, 'sub1', 'sibling')
        os.mkdir(sibling_folder)
        os.symlink('sibling', os.path.join(test_folder, 'sub1', 'sibling_link'))
        os.symlink(os.path.join('..', 'sibling'), os.path.join(test_folder, sub_folder, 'sibling_link'))
        self.assertFalse(ft.has_recursive_symlinks(test_folder))
        # Tricky case: Sibling symlink to folder starting with the same name
        os.mkdir(os.path.join(test_folder, 'sub11'))
        os.symlink(os.path.join('..', 'sub11'), os.path.join(test_folder, 'sub1', 'trick_link'))
        self.assertFalse(ft.has_recursive_symlinks(test_folder))
        # Symlink cycle: sub1/cycle_2 -> sub2, sub2/cycle_1 -> sub1, ...
        test_folder = tempfile.mkdtemp()
        sub_folder1 = os.path.join(test_folder, 'sub1')
        sub_folder2 = sub_folder = os.path.join(test_folder, 'sub2')
        os.mkdir(sub_folder1)
        os.mkdir(sub_folder2)
        os.symlink(os.path.join('..', 'sub2'), os.path.join(sub_folder1, 'cycle_1'))
        os.symlink(os.path.join('..', 'sub1'), os.path.join(sub_folder2, 'cycle_2'))
        self.assertTrue(ft.has_recursive_symlinks(test_folder))

    def test_copy_dir(self):
        """Test copy_dir function."""
        testdir = os.path.dirname(os.path.abspath(__file__))
        to_copy = os.path.join(testdir, 'easyconfigs', 'test_ecs', 'g', 'GCC')

        target_dir = os.path.join(self.test_prefix, 'GCC')
        self.assertFalse(os.path.exists(target_dir))

        self.assertTrue(os.path.exists(os.path.join(to_copy, 'GCC-6.4.0-2.28.eb')))

        ft.copy_dir(to_copy, target_dir, ignore=lambda src, names: [x for x in names if '6.4.0-2.28' in x])
        self.assertTrue(os.path.exists(target_dir))
        expected = ['GCC-4.6.3.eb', 'GCC-4.6.4.eb', 'GCC-4.8.2.eb', 'GCC-4.8.3.eb', 'GCC-4.9.2.eb', 'GCC-4.9.3-2.25.eb',
                    'GCC-4.9.3-2.26.eb', 'GCC-7.3.0-2.30.eb']
        self.assertEqual(sorted(os.listdir(target_dir)), expected)
        # GCC-6.4.0-2.28.eb should not get copied, since it's specified as file too ignore
        self.assertFalse(os.path.exists(os.path.join(target_dir, 'GCC-6.4.0-2.28.eb')))

        # clean error when trying to copy a file with copy_dir
        src, target = os.path.join(to_copy, 'GCC-4.6.3.eb'), os.path.join(self.test_prefix, 'GCC-4.6.3.eb')
        self.assertErrorRegex(EasyBuildError, "Failed to copy directory.*Not a directory", ft.copy_dir, src, target)

        # if directory already exists, we expect a clean error
        testdir = os.path.join(self.test_prefix, 'thisdirexists')
        ft.mkdir(testdir)
        self.assertErrorRegex(EasyBuildError, "Target location .* already exists", ft.copy_dir, to_copy, testdir)

        # if the directory already exists and 'dirs_exist_ok' is True, copy_dir should succeed
        ft.copy_dir(to_copy, testdir, dirs_exist_ok=True)
        self.assertTrue(sorted(os.listdir(to_copy)) == sorted(os.listdir(testdir)))

        # check whether use of 'ignore' works if target path already exists and 'dirs_exist_ok' is enabled
        def ignore_func(_, names):
            return [x for x in names if '6.4.0-2.28' in x]

        shutil.rmtree(testdir)
        ft.mkdir(testdir)
        ft.copy_dir(to_copy, testdir, dirs_exist_ok=True, ignore=ignore_func)
        self.assertEqual(sorted(os.listdir(testdir)), expected)
        self.assertFalse(os.path.exists(os.path.join(testdir, 'GCC-6.4.0-2.28.eb')))

        # test copy_dir when broken symlinks are involved
        srcdir = os.path.join(self.test_prefix, 'topdir_to_copy')
        ft.mkdir(srcdir)
        ft.write_file(os.path.join(srcdir, 'test.txt'), '123')
        subdir = os.path.join(srcdir, 'subdir')
        # introduce broken file symlink
        foo_txt = os.path.join(subdir, 'foo.txt')
        ft.write_file(foo_txt, 'bar')
        ft.symlink(foo_txt, os.path.join(subdir, 'bar.txt'))
        ft.remove_file(foo_txt)
        # introduce broken dir symlink
        subdir_tmp = os.path.join(srcdir, 'subdir_tmp')
        ft.mkdir(subdir_tmp)
        ft.symlink(subdir_tmp, os.path.join(srcdir, 'subdir_link'))
        ft.remove_dir(subdir_tmp)

        target_dir = os.path.join(self.test_prefix, 'target_to_copy_to')

        # trying this without symlinks=True ends in tears, because bar.txt points to a non-existing file
        self.assertErrorRegex(EasyBuildError, "Failed to copy directory", ft.copy_dir, srcdir, target_dir)
        ft.remove_dir(target_dir)

        ft.copy_dir(srcdir, target_dir, symlinks=True)

        # copying directory with broken symlinks should also work if target directory already exists
        ft.remove_dir(target_dir)
        ft.mkdir(target_dir)
        ft.mkdir(subdir)
        ft.copy_dir(srcdir, target_dir, symlinks=True, dirs_exist_ok=True)

        # Detect recursive symlinks by default instead of infinite loop during copy
        ft.remove_dir(target_dir)
        os.symlink('.', os.path.join(subdir, 'recursive_link'))
        self.assertErrorRegex(EasyBuildError, 'Recursive symlinks detected', ft.copy_dir, srcdir, target_dir)
        self.assertFalse(os.path.exists(target_dir))
        # Ok for symlinks=True
        ft.copy_dir(srcdir, target_dir, symlinks=True)
        self.assertTrue(os.path.exists(target_dir))

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
        self.assertTrue(re.search("^copied directory .*/GCC to .*/%s" % os.path.basename(target_dir), txt))

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
        toy_patch_fn = 'toy-0.0_fix-silly-typo-in-printf-statement.patch'
        toy_patch = os.path.join(testdir, 'sandbox', 'sources', 'toy', toy_patch_fn)
        gcc_dir = os.path.join(testdir, 'easyconfigs', 'test_ecs', 'g', 'GCC')

        ft.copy([toy_file, gcc_dir, toy_patch], self.test_prefix)

        self.assertTrue(os.path.isdir(os.path.join(self.test_prefix, 'GCC')))
        for filepath in ['GCC/GCC-4.6.3.eb', 'GCC/GCC-4.9.2.eb', 'toy-0.0.eb', toy_patch_fn]:
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
        cwd = os.getcwd()

        testdir = os.path.dirname(os.path.abspath(__file__))
        toy_tarball = os.path.join(testdir, 'sandbox', 'sources', 'toy', 'toy-0.0.tar.gz')

        self.assertFalse(os.path.exists(os.path.join(self.test_prefix, 'toy-0.0', 'toy.source')))
        path = ft.extract_file(toy_tarball, self.test_prefix, change_into_dir=False)
        self.assertTrue(os.path.exists(os.path.join(self.test_prefix, 'toy-0.0', 'toy.source')))
        self.assertTrue(os.path.samefile(path, self.test_prefix))
        # still in same directory as before if change_into_dir is set to False
        self.assertTrue(os.path.samefile(os.getcwd(), cwd))
        shutil.rmtree(os.path.join(path, 'toy-0.0'))

        toy_tarball_renamed = os.path.join(self.test_prefix, 'toy_tarball')
        shutil.copyfile(toy_tarball, toy_tarball_renamed)

        path = ft.extract_file(toy_tarball_renamed, self.test_prefix, cmd="tar xfvz %s", change_into_dir=False)
        self.assertTrue(os.path.samefile(os.getcwd(), cwd))
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
        path = ft.extract_file(toy_tarball, self.test_prefix, change_into_dir=False)
        txt = self.get_stdout()
        self.mock_stdout(False)
        self.assertTrue(os.path.samefile(os.getcwd(), cwd))

        self.assertTrue(os.path.samefile(path, self.test_prefix))
        self.assertFalse(os.path.exists(os.path.join(self.test_prefix, 'toy-0.0')))
        self.assertTrue(re.search('running command "tar xzf .*/toy-0.0.tar.gz"', txt))

        path = ft.extract_file(toy_tarball, self.test_prefix, forced=True, change_into_dir=False)
        self.assertTrue(os.path.exists(os.path.join(self.test_prefix, 'toy-0.0', 'toy.source')))
        self.assertTrue(os.path.samefile(path, self.test_prefix))
        self.assertTrue(os.path.samefile(os.getcwd(), cwd))

        build_options['extended_dry_run'] = False
        init_config(build_options=build_options)

        ft.remove_dir(os.path.join(self.test_prefix, 'toy-0.0'))

        # a deprecation warning is printed (which is an error in this context)
        # if the 'change_into_dir' named argument was left unspecified
        error_pattern = "extract_file function was called without specifying value for change_into_dir"
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.extract_file, toy_tarball, self.test_prefix)
        self.allow_deprecated_behaviour()

        # make sure we're not in self.test_prefix now (checks below assumes so)
        self.assertFalse(os.path.samefile(os.getcwd(), self.test_prefix))

        # by default, extract_file changes to directory in which source file was unpacked
        self.mock_stderr(True)
        path = ft.extract_file(toy_tarball, self.test_prefix)
        stderr = self.get_stderr().strip()
        self.mock_stderr(False)
        self.assertTrue(os.path.samefile(path, self.test_prefix))
        self.assertTrue(os.path.samefile(os.getcwd(), self.test_prefix))
        regex = re.compile("^WARNING: .*extract_file function was called without specifying value for change_into_dir")
        self.assertTrue(regex.search(stderr), "Pattern '%s' found in: %s" % (regex.pattern, stderr))

        ft.change_dir(cwd)
        self.assertFalse(os.path.samefile(os.getcwd(), self.test_prefix))

        # no deprecation warning when change_into_dir is set to True
        self.mock_stderr(True)
        path = ft.extract_file(toy_tarball, self.test_prefix, change_into_dir=True)
        stderr = self.get_stderr().strip()
        self.mock_stderr(False)

        self.assertTrue(os.path.samefile(path, self.test_prefix))
        self.assertTrue(os.path.samefile(os.getcwd(), self.test_prefix))
        self.assertFalse(stderr)

    def test_remove(self):
        """Test remove_file, remove_dir and join remove functions."""
        testfile = os.path.join(self.test_prefix, 'foo')
        test_dir = os.path.join(self.test_prefix, 'test123')

        for remove_file_function in (ft.remove_file, ft.remove):
            ft.write_file(testfile, 'bar')
            self.assertTrue(os.path.exists(testfile))
            remove_file_function(testfile)
            self.assertFalse(os.path.exists(testfile))

        for remove_dir_function in (ft.remove_dir, ft.remove):
            ft.mkdir(test_dir)
            self.assertTrue(os.path.exists(test_dir) and os.path.isdir(test_dir))
            remove_dir_function(test_dir)
            self.assertFalse(os.path.exists(test_dir) or os.path.isdir(test_dir))

        # remove also takes a list of paths
        ft.write_file(testfile, 'bar')
        ft.mkdir(test_dir)
        self.assertTrue(os.path.exists(testfile))
        self.assertTrue(os.path.exists(test_dir) and os.path.isdir(test_dir))
        ft.remove([testfile, test_dir])
        self.assertFalse(os.path.exists(testfile))
        self.assertFalse(os.path.exists(test_dir) or os.path.isdir(test_dir))

        # check error handling (after creating a permission problem with removing files/dirs)
        ft.write_file(testfile, 'bar')
        ft.mkdir(test_dir)
        ft.adjust_permissions(self.test_prefix, stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH, add=False)
        self.assertErrorRegex(EasyBuildError, "Failed to remove", ft.remove_file, testfile)
        self.assertErrorRegex(EasyBuildError, "Failed to remove", ft.remove, testfile)
        self.assertErrorRegex(EasyBuildError, "Failed to remove", ft.remove_dir, test_dir)
        self.assertErrorRegex(EasyBuildError, "Failed to remove", ft.remove, test_dir)

        # also test behaviour under --dry-run
        build_options = {
            'extended_dry_run': True,
            'silent': False,
        }
        init_config(build_options=build_options)

        for remove_file_function in (ft.remove_file, ft.remove):
            self.mock_stdout(True)
            remove_file_function(testfile)
            txt = self.get_stdout()
            self.mock_stdout(False)

            regex = re.compile("^file [^ ]* removed$")
            self.assertTrue(regex.match(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))

        for remove_dir_function in (ft.remove_dir, ft.remove):
            self.mock_stdout(True)
            remove_dir_function(test_dir)
            txt = self.get_stdout()
            self.mock_stdout(False)

            regex = re.compile("^directory [^ ]* removed$")
            self.assertTrue(regex.match(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))

        ft.adjust_permissions(self.test_prefix, stat.S_IWUSR, add=True)

    def test_index_functions(self):
        """Test *_index functions."""

        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')

        # create_index checks whether specified path is an existing directory
        doesnotexist = os.path.join(self.test_prefix, 'doesnotexist')
        self.assertErrorRegex(EasyBuildError, "Specified path does not exist", ft.create_index, doesnotexist)

        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')
        self.assertErrorRegex(EasyBuildError, "Specified path is not a directory", ft.create_index, toy_ec)

        # load_index just returns None if there is no index in specified directory
        self.assertEqual(ft.load_index(self.test_prefix), None)

        # create index for test easyconfigs;
        # test with specified path with and without trailing '/'s
        for path in [test_ecs, test_ecs + '/', test_ecs + '//']:
            index = ft.create_index(path)
            self.assertEqual(len(index), 89)

            expected = [
                os.path.join('b', 'bzip2', 'bzip2-1.0.6-GCC-4.9.2.eb'),
                os.path.join('t', 'toy', 'toy-0.0.eb'),
                os.path.join('s', 'ScaLAPACK', 'ScaLAPACK-2.0.2-gompi-2018a-OpenBLAS-0.2.20.eb'),
            ]
            for fn in expected:
                self.assertTrue(fn in index)

            for fp in index:
                self.assertTrue(fp.endswith('.eb'))

        # set up some files to create actual index file for
        ft.copy_dir(os.path.join(test_ecs, 'g'), os.path.join(self.test_prefix, 'g'))

        # test dump_index function
        index_fp = ft.dump_index(self.test_prefix)
        self.assertTrue(os.path.exists(index_fp))
        self.assertTrue(os.path.samefile(self.test_prefix, os.path.dirname(index_fp)))

        datestamp_pattern = r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+"
        expected_header = [
            "# created at: " + datestamp_pattern,
            "# valid until: " + datestamp_pattern,
        ]
        expected = [
            os.path.join('g', 'gzip', 'gzip-1.4.eb'),
            os.path.join('g', 'GCC', 'GCC-7.3.0-2.30.eb'),
            os.path.join('g', 'gompic', 'gompic-2018a.eb'),
        ]
        index_txt = ft.read_file(index_fp)
        for fn in expected_header + expected:
            regex = re.compile('^%s$' % fn, re.M)
            self.assertTrue(regex.search(index_txt), "Pattern '%s' found in: %s" % (regex.pattern, index_txt))

        # test load_index function
        self.mock_stderr(True)
        self.mock_stdout(True)
        index = ft.load_index(self.test_prefix)
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        self.assertFalse(stderr)
        regex = re.compile(r"^== found valid index for %s, so using it\.\.\.$" % self.test_prefix)
        self.assertTrue(regex.match(stdout.strip()), "Pattern '%s' matches with: %s" % (regex.pattern, stdout))

        self.assertEqual(len(index), 26)
        for fn in expected:
            self.assertTrue(fn in index, "%s should be found in %s" % (fn, sorted(index)))

        # dump_index will not overwrite existing index without force
        error_pattern = "File exists, not overwriting it without --force"
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.dump_index, self.test_prefix)

        ft.remove_file(index_fp)

        # test creating index file that's infinitely valid
        index_fp = ft.dump_index(self.test_prefix, max_age_sec=0)
        index_txt = ft.read_file(index_fp)
        expected_header[1] = r"# valid until: 9999-12-31 23:59:59\.9+"
        for fn in expected_header + expected:
            regex = re.compile('^%s$' % fn, re.M)
            self.assertTrue(regex.search(index_txt), "Pattern '%s' found in: %s" % (regex.pattern, index_txt))

        self.mock_stderr(True)
        self.mock_stdout(True)
        index = ft.load_index(self.test_prefix)
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        self.assertFalse(stderr)
        regex = re.compile(r"^== found valid index for %s, so using it\.\.\.$" % self.test_prefix)
        self.assertTrue(regex.match(stdout.strip()), "Pattern '%s' matches with: %s" % (regex.pattern, stdout))

        self.assertEqual(len(index), 26)
        for fn in expected:
            self.assertTrue(fn in index, "%s should be found in %s" % (fn, sorted(index)))

        ft.remove_file(index_fp)

        # test creating index file that's only valid for a (very) short amount of time
        index_fp = ft.dump_index(self.test_prefix, max_age_sec=1)
        time.sleep(3)
        self.mock_stderr(True)
        self.mock_stdout(True)
        index = ft.load_index(self.test_prefix)
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)
        self.assertTrue(index is None)
        self.assertFalse(stdout)
        regex = re.compile(r"WARNING: Index for %s is no longer valid \(too old\), so ignoring it" % self.test_prefix)
        self.assertTrue(regex.search(stderr), "Pattern '%s' found in: %s" % (regex.pattern, stderr))

        # check whether load_index takes into account --ignore-index
        init_config(build_options={'ignore_index': True})
        self.assertEqual(ft.load_index(self.test_prefix), None)

    def test_search_file(self):
        """Test search_file function."""
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')

        # check for default semantics, test case-insensitivity
        var_defs, hits = ft.search_file([test_ecs], 'HWLOC', silent=True)
        self.assertEqual(var_defs, [])
        self.assertEqual(len(hits), 5)
        self.assertTrue(all(os.path.exists(p) for p in hits))
        self.assertTrue(hits[0].endswith('/hwloc-1.6.2-GCC-4.9.3-2.26.eb'))
        self.assertTrue(hits[1].endswith('/hwloc-1.8-gcccuda-2018a.eb'))
        self.assertTrue(hits[2].endswith('/hwloc-1.11.8-GCC-4.6.4.eb'))
        self.assertTrue(hits[3].endswith('/hwloc-1.11.8-GCC-6.4.0-2.28.eb'))
        self.assertTrue(hits[4].endswith('/hwloc-1.11.8-GCC-7.3.0-2.30.eb'))

        # also test case-sensitive searching
        var_defs, hits_bis = ft.search_file([test_ecs], 'HWLOC', silent=True, case_sensitive=True)
        self.assertEqual(var_defs, [])
        self.assertEqual(hits_bis, [])

        var_defs, hits_bis = ft.search_file([test_ecs], 'hwloc', silent=True, case_sensitive=True)
        self.assertEqual(var_defs, [])
        self.assertEqual(hits_bis, hits)

        # check filename-only mode
        var_defs, hits = ft.search_file([test_ecs], 'HWLOC', silent=True, filename_only=True)
        self.assertEqual(var_defs, [])
        self.assertEqual(hits, ['hwloc-1.6.2-GCC-4.9.3-2.26.eb',
                                'hwloc-1.8-gcccuda-2018a.eb',
                                'hwloc-1.11.8-GCC-4.6.4.eb',
                                'hwloc-1.11.8-GCC-6.4.0-2.28.eb',
                                'hwloc-1.11.8-GCC-7.3.0-2.30.eb',
                                ])

        # check specifying of ignored dirs
        var_defs, hits = ft.search_file([test_ecs], 'HWLOC', silent=True, ignore_dirs=['hwloc'])
        self.assertEqual(var_defs + hits, [])

        # check short mode
        var_defs, hits = ft.search_file([test_ecs], 'HWLOC', silent=True, short=True)
        self.assertEqual(var_defs, [('CFGS1', os.path.join(test_ecs, 'h', 'hwloc'))])
        self.assertEqual(hits, ['$CFGS1/hwloc-1.6.2-GCC-4.9.3-2.26.eb',
                                '$CFGS1/hwloc-1.8-gcccuda-2018a.eb',
                                '$CFGS1/hwloc-1.11.8-GCC-4.6.4.eb',
                                '$CFGS1/hwloc-1.11.8-GCC-6.4.0-2.28.eb',
                                '$CFGS1/hwloc-1.11.8-GCC-7.3.0-2.30.eb'
                                ])

        # check terse mode (implies 'silent', overrides 'short')
        var_defs, hits = ft.search_file([test_ecs], 'HWLOC', terse=True, short=True)
        self.assertEqual(var_defs, [])
        expected = [
            os.path.join(test_ecs, 'h', 'hwloc', 'hwloc-1.6.2-GCC-4.9.3-2.26.eb'),
            os.path.join(test_ecs, 'h', 'hwloc', 'hwloc-1.8-gcccuda-2018a.eb'),
            os.path.join(test_ecs, 'h', 'hwloc', 'hwloc-1.11.8-GCC-4.6.4.eb'),
            os.path.join(test_ecs, 'h', 'hwloc', 'hwloc-1.11.8-GCC-6.4.0-2.28.eb'),
            os.path.join(test_ecs, 'h', 'hwloc', 'hwloc-1.11.8-GCC-7.3.0-2.30.eb'),
        ]
        self.assertEqual(hits, expected)

        # check combo of terse and filename-only
        var_defs, hits = ft.search_file([test_ecs], 'HWLOC', terse=True, filename_only=True)
        self.assertEqual(var_defs, [])
        self.assertEqual(hits, ['hwloc-1.6.2-GCC-4.9.3-2.26.eb',
                                'hwloc-1.8-gcccuda-2018a.eb',
                                'hwloc-1.11.8-GCC-4.6.4.eb',
                                'hwloc-1.11.8-GCC-6.4.0-2.28.eb',
                                'hwloc-1.11.8-GCC-7.3.0-2.30.eb',
                                ])

        # patterns that include special characters + (or ++) shouldn't cause trouble
        # cfr. https://github.com/easybuilders/easybuild-framework/issues/2966
        for pattern in ['netCDF-C++', 'foo.*bar', 'foo|bar']:
            var_defs, hits = ft.search_file([test_ecs], pattern, terse=True, filename_only=True)
            self.assertEqual(var_defs, [])
            # no hits for any of these in test easyconfigs
            self.assertEqual(hits, [])

        # create hit for netCDF-C++ search
        test_ec = os.path.join(self.test_prefix, 'netCDF-C++-4.2-foss-2019a.eb')
        ft.write_file(test_ec, '')
        for pattern in ['netCDF-C++', 'CDF', 'C++', '^netCDF']:
            var_defs, hits = ft.search_file([self.test_prefix], pattern, terse=True, filename_only=True)
            self.assertEqual(var_defs, [])
            self.assertEqual(hits, ['netCDF-C++-4.2-foss-2019a.eb'])

        # check how simply invalid queries are handled
        for pattern in ['*foo', '(foo', ')foo', 'foo)', 'foo(']:
            self.assertErrorRegex(EasyBuildError, "Invalid search query", ft.search_file, [test_ecs], pattern)

    def test_dir_contains_files(self):
        def makedirs_in_test(*paths):
            """Make dir specified by paths and return top-level folder"""
            os.makedirs(os.path.join(self.test_prefix, *paths))
            return os.path.join(self.test_prefix, paths[0])

        empty_dir = makedirs_in_test('empty_dir')
        self.assertFalse(ft.dir_contains_files(empty_dir))
        self.assertFalse(ft.dir_contains_files(empty_dir, recursive=False))

        dir_w_subdir = makedirs_in_test('dir_w_subdir', 'sub_dir')
        self.assertFalse(ft.dir_contains_files(dir_w_subdir))
        self.assertFalse(ft.dir_contains_files(dir_w_subdir, recursive=False))

        dir_subdir_file = makedirs_in_test('dir_subdir_file', 'sub_dir_w_file')
        ft.write_file(os.path.join(dir_subdir_file, 'sub_dir_w_file', 'file.h'), '')
        self.assertTrue(ft.dir_contains_files(dir_subdir_file))
        self.assertFalse(ft.dir_contains_files(dir_subdir_file, recursive=False))

        dir_w_file = makedirs_in_test('dir_w_file')
        ft.write_file(os.path.join(dir_w_file, 'file.h'), '')
        self.assertTrue(ft.dir_contains_files(dir_w_file))
        self.assertTrue(ft.dir_contains_files(dir_w_file, recursive=False))

        dir_w_dir_and_file = makedirs_in_test('dir_w_dir_and_file', 'sub_dir')
        ft.write_file(os.path.join(dir_w_dir_and_file, 'file.h'), '')
        self.assertTrue(ft.dir_contains_files(dir_w_dir_and_file))
        self.assertTrue(ft.dir_contains_files(dir_w_dir_and_file, recursive=False))

    def test_find_eb_script(self):
        """Test find_eb_script function."""

        # make sure $EB_SCRIPT_PATH is not set already (used as fallback mechanism in find_eb_script)
        if 'EB_SCRIPT_PATH' in os.environ:
            del os.environ['EB_SCRIPT_PATH']

        self.assertTrue(os.path.exists(ft.find_eb_script('rpath_args.py')))
        self.assertTrue(os.path.exists(ft.find_eb_script('rpath_wrapper_template.sh.in')))
        self.assertErrorRegex(EasyBuildError, "Script 'no_such_script' not found", ft.find_eb_script, 'no_such_script')

        # put test script in place relative to location of 'eb'
        fake_eb = os.path.join(self.test_prefix, 'bin', 'eb')
        ft.write_file(fake_eb, '#!/bin/bash\necho "fake eb"')
        ft.adjust_permissions(fake_eb, stat.S_IXUSR)
        os.environ['PATH'] = '%s:%s' % (os.path.dirname(fake_eb), os.getenv('PATH', ''))

        justatest = os.path.join(self.test_prefix, 'easybuild', 'scripts', 'thisisjustatestscript.sh')
        ft.write_file(justatest, '#!/bin/bash')

        self.assertTrue(os.path.samefile(ft.find_eb_script('thisisjustatestscript.sh'), justatest))

        # $EB_SCRIPT_PATH can also be used (overrules 'eb' found via $PATH)
        ft.remove_file(fake_eb)
        os.environ['EB_SCRIPT_PATH'] = os.path.join(self.test_prefix, 'easybuild', 'scripts')
        self.assertTrue(os.path.samefile(ft.find_eb_script('thisisjustatestscript.sh'), justatest))

        # if script can't be found via either $EB_SCRIPT_PATH or location of 'eb', we get a clean error
        del os.environ['EB_SCRIPT_PATH']
        error_pattern = "Script 'thisisjustatestscript.sh' not found at expected location"
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.find_eb_script, 'thisisjustatestscript.sh')

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
        regex = re.compile(r"^moved file .*/test\.txt to .*/new_test\.txt$")
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
        regex = re.compile(r'^test\.txt_[0-9]{14}_[0-9]+$')

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
        regex = re.compile(r'^--- .*/foo\s*\n\+\+\+ .*/bar\s*$', re.M)
        self.assertTrue(regex.search(res), "Pattern '%s' found in: %s" % (regex.pattern, res))

    def test_get_source_tarball_from_git(self):
        """Test get_source_tarball_from_git function."""

        target_dir = os.path.join(self.test_prefix, 'target')

        # only test in dry run mode, i.e. check which commands would be executed without actually running them
        build_options = {
            'extended_dry_run': True,
            'silent': False,
        }
        init_config(build_options=build_options)

        def run_check():
            """Helper function to run get_source_tarball_from_git & check dry run output"""
            with self.mocked_stdout_stderr():
                res = ft.get_source_tarball_from_git('test.tar.gz', target_dir, git_config)
                stdout = self.get_stdout()
                stderr = self.get_stderr()
            self.assertEqual(stderr, '')
            regex = re.compile(expected)
            self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

            self.assertEqual(os.path.dirname(res), target_dir)
            self.assertEqual(os.path.basename(res), 'test.tar.gz')

        git_config = {
            'repo_name': 'testrepository',
            'url': 'git@github.com:easybuilders',
            'tag': 'tag_for_tests',
        }
        git_repo = {'git_repo': 'git@github.com:easybuilders/testrepository.git'}  # Just to make the below shorter
        expected = '\n'.join([
            r'  running command "git clone --depth 1 --branch tag_for_tests %(git_repo)s"',
            r"  \(in .*/tmp.*\)",
            r'  running command "tar cfvz .*/target/test.tar.gz --exclude .git testrepository"',
            r"  \(in .*/tmp.*\)",
        ]) % git_repo
        run_check()

        git_config['recursive'] = True
        expected = '\n'.join([
            r'  running command "git clone --depth 1 --branch tag_for_tests --recursive %(git_repo)s"',
            r"  \(in .*/tmp.*\)",
            r'  running command "tar cfvz .*/target/test.tar.gz --exclude .git testrepository"',
            r"  \(in .*/tmp.*\)",
        ]) % git_repo
        run_check()

        git_config['keep_git_dir'] = True
        expected = '\n'.join([
            r'  running command "git clone --branch tag_for_tests --recursive %(git_repo)s"',
            r"  \(in .*/tmp.*\)",
            r'  running command "tar cfvz .*/target/test.tar.gz testrepository"',
            r"  \(in .*/tmp.*\)",
        ]) % git_repo
        run_check()
        del git_config['keep_git_dir']

        del git_config['tag']
        git_config['commit'] = '8456f86'
        expected = '\n'.join([
            r'  running command "git clone --depth 1 --no-checkout %(git_repo)s"',
            r"  \(in .*/tmp.*\)",
            r'  running command "git checkout 8456f86 && git submodule update --init --recursive"',
            r"  \(in testrepository\)",
            r'  running command "tar cfvz .*/target/test.tar.gz --exclude .git testrepository"',
            r"  \(in .*/tmp.*\)",
        ]) % git_repo
        run_check()

        del git_config['recursive']
        expected = '\n'.join([
            r'  running command "git clone --depth 1 --no-checkout %(git_repo)s"',
            r"  \(in .*/tmp.*\)",
            r'  running command "git checkout 8456f86"',
            r"  \(in testrepository\)",
            r'  running command "tar cfvz .*/target/test.tar.gz --exclude .git testrepository"',
            r"  \(in .*/tmp.*\)",
        ]) % git_repo
        run_check()

        # Test with real data.
        init_config()
        git_config = {
            'repo_name': 'testrepository',
            'url': 'https://github.com/easybuilders',
            'tag': 'branch_tag_for_test',
        }

        try:
            res = ft.get_source_tarball_from_git('test.tar.gz', target_dir, git_config)
            # (only) tarball is created in specified target dir
            test_file = os.path.join(target_dir, 'test.tar.gz')
            self.assertEqual(res, test_file)
            self.assertTrue(os.path.isfile(test_file))
            self.assertEqual(os.listdir(target_dir), ['test.tar.gz'])
            # Check that we indeed downloaded the right tag
            extracted_dir = tempfile.mkdtemp(prefix='extracted_dir')
            extracted_repo_dir = ft.extract_file(test_file, extracted_dir, change_into_dir=False)
            self.assertTrue(os.path.isfile(os.path.join(extracted_repo_dir, 'this-is-a-branch.txt')))
            os.remove(test_file)

            # use a tag that clashes with a branch name and make sure this is handled correctly
            git_config['tag'] = 'tag_for_tests'
            with self.mocked_stdout_stderr():
                res = ft.get_source_tarball_from_git('test.tar.gz', target_dir, git_config)
                stderr = self.get_stderr()
            self.assertIn('Tag tag_for_tests was not downloaded in the first try', stderr)
            self.assertEqual(res, test_file)
            self.assertTrue(os.path.isfile(test_file))
            # Check that we indeed downloaded the tag and not the branch
            extracted_dir = tempfile.mkdtemp(prefix='extracted_dir')
            extracted_repo_dir = ft.extract_file(test_file, extracted_dir, change_into_dir=False)
            self.assertTrue(os.path.isfile(os.path.join(extracted_repo_dir, 'this-is-a-tag.txt')))

            del git_config['tag']
            git_config['commit'] = '8456f86'
            res = ft.get_source_tarball_from_git('test2.tar.gz', target_dir, git_config)
            test_file = os.path.join(target_dir, 'test2.tar.gz')
            self.assertEqual(res, test_file)
            self.assertTrue(os.path.isfile(test_file))
            self.assertEqual(sorted(os.listdir(target_dir)), ['test.tar.gz', 'test2.tar.gz'])

        except EasyBuildError as err:
            if "Network is down" in str(err):
                print("Ignoring download error in test_get_source_tarball_from_git, working offline?")
            else:
                raise err

        git_config = {
            'repo_name': 'testrepository',
            'url': 'git@github.com:easybuilders',
            'tag': 'tag_for_tests',
        }
        args = ['test.tar.gz', self.test_prefix, git_config]

        for key in ['repo_name', 'url', 'tag']:
            orig_value = git_config.pop(key)
            if key == 'tag':
                error_pattern = "Neither tag nor commit found in git_config parameter"
            else:
                error_pattern = "%s not specified in git_config parameter" % key
            self.assertErrorRegex(EasyBuildError, error_pattern, ft.get_source_tarball_from_git, *args)
            git_config[key] = orig_value

        git_config['commit'] = '8456f86'
        error_pattern = "Tag and commit are mutually exclusive in git_config parameter"
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.get_source_tarball_from_git, *args)
        del git_config['commit']

        git_config['unknown'] = 'foobar'
        error_pattern = "Found one or more unexpected keys in 'git_config' specification"
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.get_source_tarball_from_git, *args)
        del git_config['unknown']

        args[0] = 'test.txt'
        error_pattern = "git_config currently only supports filename ending in .tar.gz"
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.get_source_tarball_from_git, *args)
        args[0] = 'test.tar.gz'

    def test_is_sha256_checksum(self):
        """Test for is_sha256_checksum function."""
        a_sha256_checksum = '44332000aa33b99ad1e00cbd1a7da769220d74647060a10e807b916d73ea27bc'
        self.assertTrue(ft.is_sha256_checksum(a_sha256_checksum))

        for not_a_sha256_checksum in [
            'be662daa971a640e40be5c804d9d7d10',  # MD5 != SHA256
            [a_sha256_checksum],  # False for a list of whatever, even with only a single SHA256 in it
            True,
            12345,
            '',
            (a_sha256_checksum,),
            [],
        ]:
            self.assertFalse(ft.is_sha256_checksum(not_a_sha256_checksum))

    def test_fake_vsc(self):
        """Test whether importing from 'vsc.*' namespace results in an error after calling install_fake_vsc."""

        ft.install_fake_vsc()

        self.mock_stderr(True)
        self.mock_stdout(True)
        try:
            import vsc  # noqa
            self.assertTrue(False, "'import vsc' results in an error")
        except SystemExit:
            pass

        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        self.assertEqual(stdout, '')

        error_pattern = r"Detected import from 'vsc' namespace in .*test/framework/filetools.py \(line [0-9]+\)"
        regex = re.compile(r"^\nERROR: %s" % error_pattern)
        self.assertTrue(regex.search(stderr), "Pattern '%s' found in: %s" % (regex.pattern, stderr))

        # also test with import from another module
        test_python_mod = os.path.join(self.test_prefix, 'test_fake_vsc', 'import_vsc.py')
        ft.write_file(os.path.join(os.path.dirname(test_python_mod), '__init__.py'), '')
        ft.write_file(test_python_mod, 'import vsc')

        sys.path.insert(0, self.test_prefix)

        self.mock_stderr(True)
        self.mock_stdout(True)
        try:
            from test_fake_vsc import import_vsc  # noqa
            self.assertTrue(False, "'import vsc' results in an error")
        except SystemExit:
            pass
        stderr = self.get_stderr()
        stdout = self.get_stdout()
        self.mock_stderr(False)
        self.mock_stdout(False)

        self.assertEqual(stdout, '')
        error_pattern = r"Detected import from 'vsc' namespace in .*/test_fake_vsc/import_vsc.py \(line 1\)"
        regex = re.compile(r"^\nERROR: %s" % error_pattern)
        self.assertTrue(regex.search(stderr), "Pattern '%s' found in: %s" % (regex.pattern, stderr))

        # no error if import was detected from pkgutil.py or pkg_resources/__init__.py,
        # since that may be triggered by a system-wide vsc-base installation
        # (even though no code is doing 'import vsc'...)
        ft.move_file(test_python_mod, os.path.join(os.path.dirname(test_python_mod), 'pkgutil.py'))

        from test_fake_vsc import pkgutil
        self.assertTrue(pkgutil.__file__.endswith('/test_fake_vsc/pkgutil.py'))

        pkg_resources_init = os.path.join(os.path.dirname(test_python_mod), 'pkg_resources', '__init__.py')
        ft.write_file(pkg_resources_init, 'import vsc')

        # cleanup to force new import of 'vsc', avoid using cached import from previous attempt
        del sys.modules['vsc']

        from test_fake_vsc import pkg_resources
        self.assertTrue(pkg_resources.__file__.endswith('/test_fake_vsc/pkg_resources/__init__.py'))

    def test_is_generic_easyblock(self):
        """Test for is_generic_easyblock function."""

        for name in ['Binary', 'ConfigureMake', 'CMakeMake', 'PythonPackage', 'JAR']:
            self.assertTrue(ft.is_generic_easyblock(name))

        for name in ['EB_bzip2', 'EB_DL_underscore_POLY_underscore_Classic', 'EB_GCC', 'EB_WRF_minus_Fire']:
            self.assertFalse(ft.is_generic_easyblock(name))

    def test_get_easyblock_class_name(self):
        """Test for get_easyblock_class_name function."""

        topdir = os.path.dirname(os.path.abspath(__file__))
        test_ebs = os.path.join(topdir, 'sandbox', 'easybuild', 'easyblocks')

        configuremake = os.path.join(test_ebs, 'generic', 'configuremake.py')
        self.assertEqual(ft.get_easyblock_class_name(configuremake), 'ConfigureMake')

        gcc_eb = os.path.join(test_ebs, 'g', 'gcc.py')
        self.assertEqual(ft.get_easyblock_class_name(gcc_eb), 'EB_GCC')

        toy_eb = os.path.join(test_ebs, 't', 'toy.py')
        self.assertEqual(ft.get_easyblock_class_name(toy_eb), 'EB_toy')

    def test_copy_easyblocks(self):
        """Test for copy_easyblocks function."""

        topdir = os.path.dirname(os.path.abspath(__file__))
        test_ebs = os.path.join(topdir, 'sandbox', 'easybuild', 'easyblocks')

        # easybuild/easyblocks subdirectory must exist in target directory
        error_pattern = "Could not find easybuild/easyblocks subdir in .*"
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.copy_easyblocks, [], self.test_prefix)

        easyblocks_dir = os.path.join(self.test_prefix, 'easybuild', 'easyblocks')

        # passing empty list works fine
        ft.mkdir(easyblocks_dir, parents=True)
        res = ft.copy_easyblocks([], self.test_prefix)
        self.assertEqual(os.listdir(easyblocks_dir), [])
        self.assertEqual(res, {'eb_names': [], 'new': [], 'paths_in_repo': []})

        # check with different types of easyblocks
        configuremake = os.path.join(test_ebs, 'generic', 'configuremake.py')
        gcc_eb = os.path.join(test_ebs, 'g', 'gcc.py')
        toy_eb = os.path.join(test_ebs, 't', 'toy.py')
        test_ebs = [gcc_eb, configuremake, toy_eb]

        # copy them straight into tmpdir first, to check whether correct subdir is derived correctly
        ft.copy_files(test_ebs, self.test_prefix)

        # touch empty toy.py easyblock, to check whether 'new' aspect is determined correctly
        ft.write_file(os.path.join(easyblocks_dir, 't', 'toy.py'), '')

        # check whether easyblocks were copied as expected, and returned dict is correct
        test_ebs = [os.path.join(self.test_prefix, os.path.basename(e)) for e in test_ebs]
        res = ft.copy_easyblocks(test_ebs, self.test_prefix)

        self.assertEqual(sorted(res.keys()), ['eb_names', 'new', 'paths_in_repo'])
        self.assertEqual(res['eb_names'], ['gcc', 'configuremake', 'toy'])
        self.assertEqual(res['new'], [True, True, False])  # toy.py is not new

        self.assertEqual(sorted(os.listdir(easyblocks_dir)), ['g', 'generic', 't'])

        g_dir = os.path.join(easyblocks_dir, 'g')
        self.assertEqual(sorted(os.listdir(g_dir)), ['gcc.py'])
        copied_gcc_eb = os.path.join(g_dir, 'gcc.py')
        self.assertEqual(ft.read_file(copied_gcc_eb), ft.read_file(gcc_eb))
        self.assertTrue(os.path.samefile(res['paths_in_repo'][0], copied_gcc_eb))

        gen_dir = os.path.join(easyblocks_dir, 'generic')
        self.assertEqual(sorted(os.listdir(gen_dir)), ['configuremake.py'])
        copied_configuremake = os.path.join(gen_dir, 'configuremake.py')
        self.assertEqual(ft.read_file(copied_configuremake), ft.read_file(configuremake))
        self.assertTrue(os.path.samefile(res['paths_in_repo'][1], copied_configuremake))

        t_dir = os.path.join(easyblocks_dir, 't')
        self.assertEqual(sorted(os.listdir(t_dir)), ['toy.py'])
        copied_toy_eb = os.path.join(t_dir, 'toy.py')
        self.assertEqual(ft.read_file(copied_toy_eb), ft.read_file(toy_eb))
        self.assertTrue(os.path.samefile(res['paths_in_repo'][2], copied_toy_eb))

    def test_copy_framework_files(self):
        """Test for copy_framework_files function."""

        target_dir = os.path.join(self.test_prefix, 'target')
        ft.mkdir(target_dir)

        res = ft.copy_framework_files([], target_dir)

        self.assertEqual(os.listdir(target_dir), [])
        self.assertEqual(res, {'paths_in_repo': [], 'new': []})

        foo_py = os.path.join(self.test_prefix, 'foo.py')
        ft.write_file(foo_py, '')

        error_pattern = "Specified path '.*/foo.py' does not include a 'easybuild-framework' directory!"
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.copy_framework_files, [foo_py], self.test_prefix)

        # create empty test/framework/modules.py, to check whether 'new' is set correctly in result
        ft.write_file(os.path.join(target_dir, 'test', 'framework', 'modules.py'), '')

        topdir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        test_files = [
            os.path.join('easybuild', 'tools', 'filetools.py'),
            os.path.join('test', 'framework', 'modules.py'),
            os.path.join('test', 'framework', 'sandbox', 'sources', 'toy', 'toy-0.0.tar.gz'),
        ]
        expected_entries = ['easybuild', 'test']
        # test/framework/modules.py is not new
        expected_new = [True, False, True]

        # we include setup.py conditionally because it may not be there,
        # for example when running the tests on an actual easybuild-framework instalation,
        # as opposed to when running from a repository checkout...
        # setup.py is an important test case, since it has no parent directory
        # (it's straight in the easybuild-framework directory)
        setup_py = 'setup.py'
        if os.path.exists(os.path.join(topdir, setup_py)):
            test_files.append(os.path.join(setup_py))
            expected_entries.append(setup_py)
            expected_new.append(True)

        # files being copied are expected to be in a directory named 'easybuild-framework',
        # so we need to make sure that's the case here as well (may not be in workspace dir on Travis from example)
        framework_dir = os.path.join(self.test_prefix, 'easybuild-framework')
        for test_file in test_files:
            ft.copy_file(os.path.join(topdir, test_file), os.path.join(framework_dir, test_file))

        test_paths = [os.path.join(framework_dir, f) for f in test_files]

        res = ft.copy_framework_files(test_paths, target_dir)

        self.assertEqual(sorted(os.listdir(target_dir)), sorted(expected_entries))

        self.assertEqual(sorted(res.keys()), ['new', 'paths_in_repo'])

        for idx, test_file in enumerate(test_files):
            orig_path = os.path.join(topdir, test_file)
            copied_path = os.path.join(target_dir, test_file)

            self.assertTrue(os.path.exists(copied_path))
            self.assertEqual(ft.read_file(orig_path, mode='rb'), ft.read_file(copied_path, mode='rb'))

            self.assertTrue(os.path.samefile(copied_path, res['paths_in_repo'][idx]))

        self.assertEqual(res['new'], expected_new)

    def test_locks(self):
        """Tests for lock-related functions."""

        init_config(build_options={'silent': True})

        # make sure that global list of locks is empty when we start off
        self.assertFalse(ft.global_lock_names)

        # use a realistic lock name (cfr. EasyBlock.run_all_steps)
        installdir = os.path.join(self.test_installpath, 'software', 'test', '1.2.3-foss-2019b-Python-3.7.4')
        lock_name = installdir.replace('/', '_')

        # det_lock_path returns full path to lock with specified name
        # (used internally by create_lock, check_lock, remove_lock)
        lock_path = ft.det_lock_path(lock_name)
        self.assertFalse(os.path.exists(lock_path))

        locks_dir = os.path.dirname(lock_path)
        self.assertFalse(os.path.exists(locks_dir))

        # if lock doesn't exist yet, check_lock just returns
        ft.check_lock(lock_name)

        # create lock, and check whether it actually was created
        ft.create_lock(lock_name)
        self.assertTrue(os.path.exists(lock_path))

        # can't use os.path.samefile until locks_dir actually exists
        self.assertTrue(os.path.samefile(locks_dir, os.path.join(self.test_installpath, 'software', '.locks')))

        self.assertEqual(os.listdir(locks_dir), [lock_name + '.lock'])

        # if lock exists, then check_lock raises an error
        self.assertErrorRegex(EasyBuildError, "Lock .* already exists", ft.check_lock, lock_name)

        # remove_lock should... remove the lock
        ft.remove_lock(lock_name)
        self.assertFalse(os.path.exists(lock_path))
        self.assertEqual(os.listdir(locks_dir), [])

        # no harm done if remove_lock is called if lock is already gone
        ft.remove_lock(lock_name)

        # check_lock just returns again after lock is removed
        ft.check_lock(lock_name)

        # global list of locks should be empty at this point
        self.assertFalse(ft.global_lock_names)

        # calling clean_up_locks when there are no locks should not cause trouble
        ft.clean_up_locks()

        ft.create_lock(lock_name)
        self.assertEqual(ft.global_lock_names, set([lock_name]))
        self.assertEqual(os.listdir(locks_dir), [lock_name + '.lock'])

        ft.clean_up_locks()
        self.assertFalse(ft.global_lock_names)
        self.assertFalse(os.path.exists(lock_path))
        self.assertEqual(os.listdir(locks_dir), [])

        # no problem with multiple locks
        lock_names = [lock_name, 'test123', 'foo@bar%baz']
        lock_paths = [os.path.join(locks_dir, x + '.lock') for x in lock_names]
        for ln in lock_names:
            ft.create_lock(ln)
        for lp in lock_paths:
            self.assertTrue(os.path.exists(lp), "Path %s should exist" % lp)

        self.assertEqual(ft.global_lock_names, set(lock_names))
        expected_locks = sorted(ln + '.lock' for ln in lock_names)
        self.assertEqual(sorted(os.listdir(locks_dir)), expected_locks)

        ft.clean_up_locks()
        for lp in lock_paths:
            self.assertFalse(os.path.exists(lp), "Path %s should not exist" % lp)
        self.assertFalse(ft.global_lock_names)
        self.assertEqual(os.listdir(locks_dir), [])

        # also test signal handler that is supposed to clean up locks
        ft.create_lock(lock_name)
        self.assertTrue(ft.global_lock_names)
        self.assertTrue(os.path.exists(lock_path))
        self.assertEqual(os.listdir(locks_dir), [lock_name + '.lock'])

        # clean_up_locks_signal_handler causes sys.exit with specified exit code
        self.assertErrorRegex(SystemExit, '15', ft.clean_up_locks_signal_handler, 15, None)
        self.assertFalse(ft.global_lock_names)
        self.assertFalse(os.path.exists(lock_path))
        self.assertEqual(os.listdir(locks_dir), [])

    def test_locate_files(self):
        """Test locate_files function."""

        # create some files to find
        one = os.path.join(self.test_prefix, '1.txt')
        ft.write_file(one, 'one')
        two = os.path.join(self.test_prefix, 'subdirA', '2.txt')
        ft.write_file(two, 'two')
        three = os.path.join(self.test_prefix, 'subdirB', '3.txt')
        ft.write_file(three, 'three')
        ft.mkdir(os.path.join(self.test_prefix, 'empty_subdir'))

        # empty list of files yields empty result
        self.assertEqual(ft.locate_files([], []), [])
        self.assertEqual(ft.locate_files([], [self.test_prefix]), [])

        # error is raised if files could not be found
        error_pattern = r"One or more files not found: nosuchfile.txt \(search paths: \)"
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.locate_files, ['nosuchfile.txt'], [])

        # files specified via absolute path don't have to be found
        res = ft.locate_files([one], [])
        self.assertTrue(len(res) == 1)
        self.assertTrue(os.path.samefile(res[0], one))

        # note: don't compare file paths directly but use os.path.samefile instead,
        # which is required to avoid failing tests in case temporary directory is a symbolic link (e.g. on macOS)
        res = ft.locate_files(['1.txt'], [self.test_prefix])
        self.assertEqual(len(res), 1)
        self.assertTrue(os.path.samefile(res[0], one))

        res = ft.locate_files(['2.txt'], [self.test_prefix])
        self.assertEqual(len(res), 1)
        self.assertTrue(os.path.samefile(res[0], two))

        res = ft.locate_files(['1.txt', '3.txt'], [self.test_prefix])
        self.assertEqual(len(res), 2)
        self.assertTrue(os.path.samefile(res[0], one))
        self.assertTrue(os.path.samefile(res[1], three))

        # search in multiple paths
        files = ['2.txt', '3.txt']
        paths = [os.path.dirname(three), os.path.dirname(two)]
        res = ft.locate_files(files, paths)
        self.assertEqual(len(res), 2)
        self.assertTrue(os.path.samefile(res[0], two))
        self.assertTrue(os.path.samefile(res[1], three))

        # same file specified multiple times works fine
        files = ['1.txt', '2.txt', '1.txt', '3.txt', '2.txt']
        res = ft.locate_files(files, [self.test_prefix])
        self.assertEqual(len(res), 5)
        for idx, expected in enumerate([one, two, one, three, two]):
            self.assertTrue(os.path.samefile(res[idx], expected))

        # only some files found yields correct warning
        files = ['2.txt', '3.txt', '1.txt']
        error_pattern = r"One or more files not found: 3\.txt, 1.txt \(search paths: .*/subdirA\)"
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.locate_files, files, [os.path.dirname(two)])

        # check that relative paths are found in current working dir
        ft.change_dir(self.test_prefix)
        rel_paths = ['subdirA/2.txt', '1.txt']
        # result is still absolute paths to those files
        res = ft.locate_files(rel_paths, [])
        self.assertEqual(len(res), 2)
        self.assertTrue(os.path.samefile(res[0], two))
        self.assertTrue(os.path.samefile(res[1], one))

        # no recursive search in current working dir (which would potentially be way too expensive)
        error_pattern = r"One or more files not found: 2\.txt \(search paths: \)"
        self.assertErrorRegex(EasyBuildError, error_pattern, ft.locate_files, ['2.txt'], [])

    def test_set_gid_sticky_bits(self):
        """Test for set_gid_sticky_bits function."""
        test_dir = os.path.join(self.test_prefix, 'test_dir')
        test_subdir = os.path.join(test_dir, 'subdir')

        ft.mkdir(test_subdir, parents=True)
        dir_perms = os.lstat(test_dir)[stat.ST_MODE]
        self.assertEqual(dir_perms & stat.S_ISGID, 0)
        self.assertEqual(dir_perms & stat.S_ISVTX, 0)
        dir_perms = os.lstat(test_subdir)[stat.ST_MODE]
        self.assertEqual(dir_perms & stat.S_ISGID, 0)
        self.assertEqual(dir_perms & stat.S_ISVTX, 0)

        # by default, GID & sticky bits are not set
        ft.set_gid_sticky_bits(test_dir)
        dir_perms = os.lstat(test_dir)[stat.ST_MODE]
        self.assertEqual(dir_perms & stat.S_ISGID, 0)
        self.assertEqual(dir_perms & stat.S_ISVTX, 0)

        ft.set_gid_sticky_bits(test_dir, set_gid=True)
        dir_perms = os.lstat(test_dir)[stat.ST_MODE]
        self.assertEqual(dir_perms & stat.S_ISGID, stat.S_ISGID)
        self.assertEqual(dir_perms & stat.S_ISVTX, 0)
        ft.remove_dir(test_dir)
        ft.mkdir(test_subdir, parents=True)

        ft.set_gid_sticky_bits(test_dir, sticky=True)
        dir_perms = os.lstat(test_dir)[stat.ST_MODE]
        self.assertEqual(dir_perms & stat.S_ISGID, 0)
        self.assertEqual(dir_perms & stat.S_ISVTX, stat.S_ISVTX)
        ft.remove_dir(test_dir)
        ft.mkdir(test_subdir, parents=True)

        ft.set_gid_sticky_bits(test_dir, set_gid=True, sticky=True)
        dir_perms = os.lstat(test_dir)[stat.ST_MODE]
        self.assertEqual(dir_perms & stat.S_ISGID, stat.S_ISGID)
        self.assertEqual(dir_perms & stat.S_ISVTX, stat.S_ISVTX)
        # no recursion by default
        dir_perms = os.lstat(test_subdir)[stat.ST_MODE]
        self.assertEqual(dir_perms & stat.S_ISGID, 0)
        self.assertEqual(dir_perms & stat.S_ISVTX, 0)

        ft.remove_dir(test_dir)
        ft.mkdir(test_subdir, parents=True)

        ft.set_gid_sticky_bits(test_dir, set_gid=True, sticky=True, recursive=True)
        dir_perms = os.lstat(test_dir)[stat.ST_MODE]
        self.assertEqual(dir_perms & stat.S_ISGID, stat.S_ISGID)
        self.assertEqual(dir_perms & stat.S_ISVTX, stat.S_ISVTX)
        dir_perms = os.lstat(test_subdir)[stat.ST_MODE]
        self.assertEqual(dir_perms & stat.S_ISGID, stat.S_ISGID)
        self.assertEqual(dir_perms & stat.S_ISVTX, stat.S_ISVTX)

        ft.remove_dir(test_dir)
        ft.mkdir(test_subdir, parents=True)

        # set_gid_sticky_bits honors relevant build options
        init_config(build_options={'set_gid_bit': True, 'sticky_bit': True})
        ft.set_gid_sticky_bits(test_dir, recursive=True)
        dir_perms = os.lstat(test_dir)[stat.ST_MODE]
        self.assertEqual(dir_perms & stat.S_ISGID, stat.S_ISGID)
        self.assertEqual(dir_perms & stat.S_ISVTX, stat.S_ISVTX)
        dir_perms = os.lstat(test_subdir)[stat.ST_MODE]
        self.assertEqual(dir_perms & stat.S_ISGID, stat.S_ISGID)
        self.assertEqual(dir_perms & stat.S_ISVTX, stat.S_ISVTX)

    def test_create_unused_dir(self):
        """Test create_unused_dir function."""
        path = ft.create_unused_dir(self.test_prefix, 'folder')
        self.assertEqual(path, os.path.join(self.test_prefix, 'folder'))
        self.assertTrue(os.path.exists(path))

        # Repeat with existing folder(s) should create new ones
        for i in range(10):
            path = ft.create_unused_dir(self.test_prefix, 'folder')
            self.assertEqual(path, os.path.join(self.test_prefix, 'folder_%s' % i))
            self.assertTrue(os.path.exists(path))

        # Not influenced by similar folder
        path = ft.create_unused_dir(self.test_prefix, 'folder2')
        self.assertEqual(path, os.path.join(self.test_prefix, 'folder2'))
        self.assertTrue(os.path.exists(path))
        for i in range(10):
            path = ft.create_unused_dir(self.test_prefix, 'folder2')
            self.assertEqual(path, os.path.join(self.test_prefix, 'folder2_%s' % i))
            self.assertTrue(os.path.exists(path))

        # Fail cleanly if passed a readonly folder
        readonly_dir = os.path.join(self.test_prefix, 'ro_folder')
        ft.mkdir(readonly_dir)
        old_perms = os.lstat(readonly_dir)[stat.ST_MODE]
        ft.adjust_permissions(readonly_dir, stat.S_IREAD | stat.S_IEXEC, relative=False)
        try:
            self.assertErrorRegex(EasyBuildError, 'Failed to create directory',
                                  ft.create_unused_dir, readonly_dir, 'new_folder')
        finally:
            ft.adjust_permissions(readonly_dir, old_perms, relative=False)

        # Ignore files same as folders. So first just create a file with no contents
        ft.write_file(os.path.join(self.test_prefix, 'file'), '')
        path = ft.create_unused_dir(self.test_prefix, 'file')
        self.assertEqual(path, os.path.join(self.test_prefix, 'file_0'))
        self.assertTrue(os.path.exists(path))


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(FileToolsTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
