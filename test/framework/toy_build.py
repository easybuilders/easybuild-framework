# #
# Copyright 2013-2014 Ghent University
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
Toy build unit test

@author: Kenneth Hoste (Ghent University)
"""
import glob
import grp
import os
import re
import shutil
import stat
import sys
import tempfile
from test.framework.utilities import EnhancedTestCase
from unittest import TestLoader
from unittest import main as unittestmain
from vsc.utils.fancylogger import setLogLevelDebug, logToScreen

import easybuild.tools.module_naming_scheme  # required to dynamically load test module naming scheme(s)
from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import mkdir, read_file, write_file
from easybuild.tools.modules import modules_tool


class ToyBuildTest(EnhancedTestCase):
    """Toy build unit test."""

    def setUp(self):
        """Test setup."""
        super(ToyBuildTest, self).setUp()

        fd, self.dummylogfn = tempfile.mkstemp(prefix='easybuild-dummy', suffix='.log')
        os.close(fd)

        # adjust PYTHONPATH such that test easyblocks are found
        import easybuild
        eb_blocks_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'sandbox'))
        if not eb_blocks_path in sys.path:
            sys.path.append(eb_blocks_path)
            easybuild = reload(easybuild)

        import easybuild.easyblocks
        reload(easybuild.easyblocks)
        reload(easybuild.tools.module_naming_scheme)

        # clear log
        write_file(self.logfile, '')

    def tearDown(self):
        """Cleanup."""
        super(ToyBuildTest, self).tearDown()
        # remove logs
        if os.path.exists(self.dummylogfn):
            os.remove(self.dummylogfn)

    def check_toy(self, installpath, outtxt, version='0.0', versionprefix='', versionsuffix=''):
        """Check whether toy build succeeded."""

        full_version = ''.join([versionprefix, version, versionsuffix])

        # check for success
        success = re.compile("COMPLETED: Installation ended successfully")
        self.assertTrue(success.search(outtxt), "COMPLETED message found in '%s" % outtxt)

        # if the module exists, it should be fine
        toy_module = os.path.join(installpath, 'modules', 'all', 'toy', full_version)
        msg = "module for toy build toy/%s found (path %s)" % (full_version, toy_module)
        self.assertTrue(os.path.exists(toy_module), msg)

        # module file is symlinked according to moduleclass
        toy_module_symlink = os.path.join(installpath, 'modules', 'tools', 'toy', full_version)
        self.assertTrue(os.path.islink(toy_module_symlink))
        self.assertTrue(os.path.exists(toy_module_symlink))

        # make sure installation log file and easyconfig file are copied to install dir
        software_path = os.path.join(installpath, 'software', 'toy', full_version)
        install_log_path_pattern = os.path.join(software_path, 'easybuild', 'easybuild-toy-%s*.log' % version)
        self.assertTrue(len(glob.glob(install_log_path_pattern)) == 1, "Found 1 file at %s" % install_log_path_pattern)

        # make sure test report is available
        test_report_path_pattern = os.path.join(software_path, 'easybuild', 'easybuild-toy-%s*test_report.md' % version)
        self.assertTrue(len(glob.glob(test_report_path_pattern)) == 1, "Found 1 file at %s" % test_report_path_pattern)

        ec_file_path = os.path.join(software_path, 'easybuild', 'toy-%s.eb' % full_version)
        self.assertTrue(os.path.exists(ec_file_path))

        devel_module_path = os.path.join(software_path, 'easybuild', 'toy-%s-easybuild-devel' % full_version)
        self.assertTrue(os.path.exists(devel_module_path))

    def test_toy_build(self, extra_args=None, ec_file=None, tmpdir=None, verify=True, fails=False, verbose=True,
                       raise_error=False, test_report=None, versionsuffix=''):
        """Perform a toy build."""
        if extra_args is None:
            extra_args = []
        test_readme = False
        if ec_file is None:
            ec_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb')
            test_readme = True
        full_ver = '0.0%s' % versionsuffix
        args = [
            ec_file,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--debug',
            '--unittest-file=%s' % self.logfile,
            '--force',
            '--robot=%s' % os.pathsep.join([self.test_buildpath, os.path.dirname(__file__)]),
        ]
        if tmpdir is not None:
            args.append('--tmpdir=%s' % tmpdir)
        if test_report is not None:
            args.append('--dump-test-report=%s' % test_report)
        args.extend(extra_args)
        myerr = None
        try:
            outtxt = self.eb_main(args, logfile=self.dummylogfn, do_build=True, verbose=verbose,
                                  raise_error=raise_error)
        except Exception, err:
            myerr = err
            if raise_error:
                raise myerr

        if verify:
            self.check_toy(self.test_installpath, outtxt, versionsuffix=versionsuffix)

        if test_readme:
            # make sure postinstallcmds were used
            toy_install_path = os.path.join(self.test_installpath, 'software', 'toy', full_ver)
            self.assertEqual(read_file(os.path.join(toy_install_path, 'README')), "TOY\n")

        # make sure full test report was dumped, and contains sensible information
        if test_report is not None:
            self.assertTrue(os.path.exists(test_report))
            if fails:
                test_result = 'FAIL'
            else:
                test_result = 'SUCCESS'
            regex_patterns = [
                r"Test result[\S\s]*Build succeeded for %d out of 1" % (not fails),
                r"Overview of tested easyconfig[\S\s]*%s[\S\s]*%s" % (test_result, os.path.basename(ec_file)),
                r"Time info[\S\s]*start:[\S\s]*end:",
                r"EasyBuild info[\S\s]*framework version:[\S\s]*easyblocks ver[\S\s]*command line[\S\s]*configuration",
                r"System info[\S\s]*cpu model[\S\s]*os name[\S\s]*os version[\S\s]*python version",
                r"List of loaded modules",
                r"Environment",
            ]
            test_report_txt = read_file(test_report)
            for regex_pattern in regex_patterns:
                regex = re.compile(regex_pattern, re.M)
                msg = "Pattern %s found in full test report: %s" % (regex.pattern, test_report_txt)
                self.assertTrue(regex.search(test_report_txt), msg)

        return outtxt

    def test_toy_broken(self):
        """Test deliberately broken toy build."""
        tmpdir = tempfile.mkdtemp()
        broken_toy_ec = os.path.join(tmpdir, "toy-broken.eb")
        toy_ec_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb')
        broken_toy_ec_txt = read_file(toy_ec_file)
        broken_toy_ec_txt += "checksums = ['clearywrongchecksum']"
        write_file(broken_toy_ec, broken_toy_ec_txt)
        error_regex = "Checksum verification .* failed"
        self.assertErrorRegex(EasyBuildError, error_regex, self.test_toy_build, ec_file=broken_toy_ec, tmpdir=tmpdir,
                              verify=False, fails=True, verbose=False, raise_error=True)

        # make sure log file is retained, also for failed build
        log_path_pattern = os.path.join(tmpdir, 'easybuild-*', 'easybuild-toy-0.0*.log')
        self.assertTrue(len(glob.glob(log_path_pattern)) == 1, "Log file found at %s" % log_path_pattern)

        # make sure individual test report is retained, also for failed build
        test_report_fp_pattern = os.path.join(tmpdir, 'easybuild-*', 'easybuild-toy-0.0*test_report.md')
        self.assertTrue(len(glob.glob(test_report_fp_pattern)) == 1, "Test report %s found" % test_report_fp_pattern)

        # test dumping full test report (doesn't raise an exception)
        test_report_fp = os.path.join(self.test_buildpath, 'full_test_report.md')
        self.test_toy_build(ec_file=broken_toy_ec, tmpdir=tmpdir, verify=False, fails=True, verbose=False,
                            raise_error=True, test_report=test_report_fp)

        # cleanup
        shutil.rmtree(tmpdir)

    def test_toy_tweaked(self):
        """Test toy build with tweaked easyconfig, for testing extra easyconfig parameters."""
        test_ecs_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'easyconfigs')
        ec_file = os.path.join(self.test_buildpath, 'toy-0.0-tweaked.eb')
        shutil.copy2(os.path.join(test_ecs_dir, 'toy-0.0.eb'), ec_file)

        # tweak easyconfig by appending to it
        ec_extra = '\n'.join([
            "versionsuffix = '-tweaked'",
            "modextrapaths = {'SOMEPATH': ['foo/bar', 'baz']}",
            "modextravars = {'FOO': 'bar'}",
            "modloadmsg =  'THANKS FOR LOADING ME, I AM %(name)s v%(version)s'",
            "modtclfooter = 'puts stderr \"oh hai!\"'",
        ])
        write_file(ec_file, ec_extra, append=True)

        args = [
            ec_file,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--debug',
            '--force',
        ]
        outtxt = self.eb_main(args, do_build=True, verbose=True, raise_error=True)
        self.check_toy(self.test_installpath, outtxt, versionsuffix='-tweaked')
        toy_module = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '0.0-tweaked')
        toy_module_txt = read_file(toy_module)

        self.assertTrue(re.search('setenv\s*FOO\s*"bar"', toy_module_txt))
        self.assertTrue(re.search('prepend-path\s*SOMEPATH\s*\$root/foo/bar', toy_module_txt))
        self.assertTrue(re.search('prepend-path\s*SOMEPATH\s*\$root/baz', toy_module_txt))
        self.assertTrue(re.search('module-info mode load.*\n\s*puts stderr\s*.*I AM toy v0.0', toy_module_txt))
        self.assertTrue(re.search('puts stderr "oh hai!"', toy_module_txt))

    def test_toy_buggy_easyblock(self):
        """Test build using a buggy/broken easyblock, make sure a traceback is reported."""
        ec_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb')
        kwargs = {
            'ec_file': ec_file,
            'extra_args': ['--easyblock=EB_toy_buggy'],
            'raise_error': True,
            'verify': False,
            'verbose': False,
        }
        err_regex = r"crashed with an error.*Traceback[\S\s]*toy_buggy.py.*build_step[\S\s]*global name 'run_cmd'"
        self.assertErrorRegex(EasyBuildError, err_regex, self.test_toy_build, **kwargs)

    def test_toy_build_formatv2(self):
        """Perform a toy build (format v2)."""
        # set $MODULEPATH such that modules for specified dependencies are found
        modulepath = os.environ.get('MODULEPATH')
        os.environ['MODULEPATH'] = os.path.abspath(os.path.join(os.path.dirname(__file__), 'modules'))

        args = [
            os.path.join(os.path.dirname(__file__), 'easyconfigs', 'v2.0', 'toy.eb'),
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--debug',
            '--unittest-file=%s' % self.logfile,
            '--force',
            '--robot=%s' % os.pathsep.join([self.test_buildpath, os.path.dirname(__file__)]),
            '--software-version=0.0',
            '--toolchain=dummy,dummy',
            '--experimental',
        ]
        outtxt = self.eb_main(args, logfile=self.dummylogfn, do_build=True, verbose=True)

        self.check_toy(self.test_installpath, outtxt)

        # restore
        if modulepath is not None:
            os.environ['MODULEPATH'] = modulepath
        else:
            del os.environ['MODULEPATH']

    def test_toy_build_with_blocks(self):
        """Test a toy build with multiple blocks."""
        orig_sys_path = sys.path[:]
        # add directory in which easyconfig file can be found to Python search path, since we're not specifying it full path below
        tmpdir = tempfile.mkdtemp()
        # note get_paths_for expects easybuild/easyconfigs subdir
        ecs_path = os.path.join(tmpdir, "easybuild", "easyconfigs")
        os.makedirs(ecs_path)
        shutil.copy2(os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0-multiple.eb'), ecs_path)
        sys.path.append(tmpdir)

        args = [
                'toy-0.0-multiple.eb',
                '--sourcepath=%s' % self.test_sourcepath,
                '--buildpath=%s' % self.test_buildpath,
                '--installpath=%s' % self.test_installpath,
                '--debug',
                '--unittest-file=%s' % self.logfile,
                '--force',
               ]
        outtxt = self.eb_main(args, logfile=self.dummylogfn, do_build=True, verbose=True)

        for toy_prefix, toy_version, toy_suffix in [
            ('', '0.0', '-somesuffix'),
            ('someprefix-', '0.0', '-somesuffix')
        ]:
            self.check_toy(self.test_installpath, outtxt, version=toy_version,
                           versionprefix=toy_prefix, versionsuffix=toy_suffix)

        # cleanup
        shutil.rmtree(tmpdir)
        sys.path = orig_sys_path

    def test_toy_build_formatv2_sections(self):
        """Perform a toy build (format v2, using sections)."""
        versions = {
            '0.0': {'versionprefix': '', 'versionsuffix': ''},
            '1.0': {'versionprefix': '', 'versionsuffix': ''},
            '1.1': {'versionprefix': 'stable-', 'versionsuffix': ''},
            '1.5': {'versionprefix': 'stable-', 'versionsuffix': '-early'},
            '1.6': {'versionprefix': 'stable-', 'versionsuffix': '-early'},
            '2.0': {'versionprefix': 'stable-', 'versionsuffix': '-early'},
            '3.0': {'versionprefix': 'stable-', 'versionsuffix': '-mature'},
        }

        for version, specs in versions.items():
            args = [
                os.path.join(os.path.dirname(__file__), 'easyconfigs', 'v2.0', 'toy-with-sections.eb'),
                '--sourcepath=%s' % self.test_sourcepath,
                '--buildpath=%s' % self.test_buildpath,
                '--installpath=%s' % self.test_installpath,
                '--debug',
                '--unittest-file=%s' % self.logfile,
                '--force',
                '--robot=%s' % os.pathsep.join([self.test_buildpath, os.path.dirname(__file__)]),
                '--software-version=%s' % version,
                '--toolchain=dummy,dummy',
                '--experimental',
            ]
            outtxt = self.eb_main(args, logfile=self.dummylogfn, do_build=True, verbose=True)

            specs['version'] = version

            self.check_toy(self.test_installpath, outtxt, **specs)

    def test_toy_download_sources(self):
        """Test toy build with sources that still need to be 'downloaded'."""
        tmpdir = tempfile.mkdtemp()
        # copy toy easyconfig file, and append source_urls to it
        shutil.copy2(os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb'), tmpdir)
        source_url = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'sandbox', 'sources', 'toy')
        ec_file = os.path.join(tmpdir, 'toy-0.0.eb')
        write_file(ec_file, '\nsource_urls = ["file://%s"]\n' % source_url, append=True)

        # unset $EASYBUILD_XPATH env vars, to make sure --prefix is picked up
        for cfg_opt in ['build', 'install', 'source']:
            del os.environ['EASYBUILD_%sPATH' % cfg_opt.upper()]
        sourcepath = os.path.join(tmpdir, 'mysources')
        args = [
            ec_file,
            '--prefix=%s' % tmpdir,
            '--sourcepath=%s' % ':'.join([sourcepath, '/bar']),  # include senseless path which should be ignored
            '--debug',
            '--unittest-file=%s' % self.logfile,
            '--force',
        ]
        outtxt = self.eb_main(args, logfile=self.dummylogfn, do_build=True, verbose=True)

        self.check_toy(tmpdir, outtxt)

        self.assertTrue(os.path.exists(os.path.join(sourcepath, 't', 'toy', 'toy-0.0.tar.gz')))

        shutil.rmtree(tmpdir)

    def test_toy_permissions(self):
        """Test toy build with custom umask settings."""
        toy_ec_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb')
        args = [
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--debug',
            '--unittest-file=%s' % self.logfile,
            '--force',
        ]

        # set umask hard to verify default reliably
        orig_umask = os.umask(0022)

        # test specifying a non-existing group
        allargs = [toy_ec_file] + args + ['--group=thisgroupdoesnotexist']
        outtxt, err = self.eb_main(allargs, logfile=self.dummylogfn, do_build=True, return_error=True)
        err_regex = re.compile("Failed to get group ID .* group does not exist")
        self.assertTrue(err_regex.search(outtxt), "Pattern '%s' found in '%s'" % (err_regex.pattern, outtxt))

        # determine current group name (at least we can use that)
        gid = os.getgid()
        curr_grp = grp.getgrgid(gid).gr_name

        for umask, cfg_group, ec_group, dir_perms, fil_perms, bin_perms in [
            (None, None, None, 0755, 0644, 0755),  # default: inherit session umask
            (None, None, curr_grp, 0750, 0640, 0750),  # default umask, but with specified group in ec
            (None, curr_grp, None, 0750, 0640, 0750),  # default umask, but with specified group in cfg
            (None, 'notagrp', curr_grp, 0750, 0640, 0750),  # default umask, but with specified group in both cfg and ec
            ('000', None, None, 0777, 0666, 0777),  # stupid empty umask
            ('032', None, None, 0745, 0644, 0745),  # no write/execute for group, no write for other
            ('030', None, curr_grp, 0740, 0640, 0740),  # no write for group, with specified group
            ('077', None, None, 0700, 0600, 0700),  # no access for other/group
        ]:
            if cfg_group is None and ec_group is None:
                allargs = [toy_ec_file]
            elif ec_group is not None:
                shutil.copy2(toy_ec_file, self.test_buildpath)
                tmp_ec_file = os.path.join(self.test_buildpath, os.path.basename(toy_ec_file))
                write_file(tmp_ec_file, "\ngroup = '%s'" % ec_group, append=True)
                allargs = [tmp_ec_file]
            allargs.extend(args)
            if umask is not None:
                allargs.append("--umask=%s" % umask)
            if cfg_group is not None:
                allargs.append("--group=%s" % cfg_group)
            outtxt = self.eb_main(allargs, logfile=self.dummylogfn, do_build=True, verbose=True)

            # verify that installation was correct
            self.check_toy(self.test_installpath, outtxt)

            # group specified in easyconfig overrules configured group
            group = cfg_group
            if ec_group is not None:
                group = ec_group

            # verify permissions
            paths_perms = [
                # no write permissions for group/other, regardless of umask
                (('software', 'toy', '0.0'), dir_perms & ~ 0022),
                (('software', 'toy', '0.0', 'bin'), dir_perms & ~ 0022),
                (('software', 'toy', '0.0', 'bin', 'toy'), bin_perms & ~ 0022),
            ]
            # only software subdirs are chmod'ed for 'protected' installs, so don't check those if a group is specified
            if group is None:
                paths_perms.extend([
                    (('software', ), dir_perms),
                    (('software', 'toy'), dir_perms),
                    (('software', 'toy', '0.0', 'easybuild', '*.log'), fil_perms),
                    (('modules', ), dir_perms),
                    (('modules', 'all'), dir_perms),
                    (('modules', 'all', 'toy'), dir_perms),
                    (('modules', 'all', 'toy', '0.0'), fil_perms),
                ])
            for path, correct_perms in paths_perms:
                fullpath = glob.glob(os.path.join(self.test_installpath, *path))[0]
                perms = os.stat(fullpath).st_mode & 0777
                msg = "Path %s has %s permissions: %s" % (fullpath, oct(correct_perms), oct(perms))
                self.assertEqual(perms, correct_perms, msg)
                if group is not None:
                    path_gid = os.stat(fullpath).st_gid
                    self.assertEqual(path_gid, grp.getgrnam(group).gr_gid)

            # cleanup for next iteration
            shutil.rmtree(self.test_installpath)

        # restore original umask
        os.umask(orig_umask)

    def test_toy_gid_sticky_bits(self):
        """Test setting gid and sticky bits."""
        subdirs = [
            (('',), False),
            (('software',), False),
            (('software', 'toy'), False),
            (('software', 'toy', '0.0'), True),
            (('modules', 'all'), False),
            (('modules', 'all', 'toy'), False),
        ]
        # no gid/sticky bits by default
        self.test_toy_build()
        for subdir, _ in subdirs:
            fullpath = os.path.join(self.test_installpath, *subdir)
            perms = os.stat(fullpath).st_mode
            self.assertFalse(perms & stat.S_ISGID, "no gid bit on %s" % fullpath)
            self.assertFalse(perms & stat.S_ISVTX, "no sticky bit on %s" % fullpath)

        # git/sticky bits are set, but only on (re)created directories
        self.test_toy_build(extra_args=['--set-gid-bit', '--sticky-bit'])
        for subdir, bits_set in subdirs:
            fullpath = os.path.join(self.test_installpath, *subdir)
            perms = os.stat(fullpath).st_mode
            if bits_set:
                self.assertTrue(perms & stat.S_ISGID, "gid bit set on %s" % fullpath)
                self.assertTrue(perms & stat.S_ISVTX, "sticky bit set on %s" % fullpath)
            else:
                self.assertFalse(perms & stat.S_ISGID, "no gid bit on %s" % fullpath)
                self.assertFalse(perms & stat.S_ISVTX, "no sticky bit on %s" % fullpath)

        # start with a clean slate, now gid/sticky bits should be set on everything
        shutil.rmtree(self.test_installpath)
        self.test_toy_build(extra_args=['--set-gid-bit', '--sticky-bit'])
        for subdir, _ in subdirs:
            fullpath = os.path.join(self.test_installpath, *subdir)
            perms = os.stat(fullpath).st_mode
            self.assertTrue(perms & stat.S_ISGID, "gid bit set on %s" % fullpath)
            self.assertTrue(perms & stat.S_ISVTX, "sticky bit set on %s" % fullpath)

    def test_allow_system_deps(self):
        """Test allow_system_deps easyconfig parameter."""
        tmpdir = tempfile.mkdtemp()
        # copy toy easyconfig file, and append source_urls to it
        shutil.copy2(os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb'), tmpdir)
        ec_file = os.path.join(tmpdir, 'toy-0.0.eb')
        write_file(ec_file, "\nallow_system_deps = [('Python', SYS_PYTHON_VERSION)]\n", append=True)
        self.test_toy_build(ec_file=ec_file)
        shutil.rmtree(tmpdir)

    def test_toy_hierarchical(self):
        """Test toy build under example hierarchical module naming scheme."""

        self.setup_hierarchical_modules()
        mod_prefix = os.path.join(self.test_installpath, 'modules', 'all')

        args = [
            os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb'),
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--debug',
            '--unittest-file=%s' % self.logfile,
            '--force',
            '--robot=%s' % os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs'),
            '--module-naming-scheme=HierarchicalMNS',
        ]

        # test module paths/contents with gompi build
        extra_args = [
            '--try-toolchain=goolf,1.4.10',
        ]
        self.eb_main(args + extra_args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)

        # make sure module file is installed in correct path
        toy_module_path = os.path.join(mod_prefix, 'MPI', 'GCC', '4.7.2', 'OpenMPI', '1.6.4', 'toy', '0.0')
        self.assertTrue(os.path.exists(toy_module_path))

        # check that toolchain load is expanded to loads for toolchain dependencies,
        # except for the ones that extend $MODULEPATH to make the toy module available
        modtxt = read_file(toy_module_path)
        for dep in ['goolf', 'GCC', 'OpenMPI']:
            load_regex = re.compile("load %s" % dep)
            self.assertFalse(load_regex.search(modtxt), "Pattern '%s' not found in %s" % (load_regex.pattern, modtxt))
        for dep in ['OpenBLAS', 'FFTW', 'ScaLAPACK']:
            load_regex = re.compile("load %s" % dep)
            self.assertTrue(load_regex.search(modtxt), "Pattern '%s' found in %s" % (load_regex.pattern, modtxt))

        os.remove(toy_module_path)

        # test module path with GCC/4.7.2 build
        extra_args = [
            '--try-toolchain=GCC,4.7.2',
        ]
        self.eb_main(args + extra_args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)

        # make sure module file is installed in correct path
        toy_module_path = os.path.join(mod_prefix, 'Compiler', 'GCC', '4.7.2', 'toy', '0.0')
        self.assertTrue(os.path.exists(toy_module_path))

        # no dependencies or toolchain => no module load statements in module file
        modtxt = read_file(toy_module_path)
        self.assertFalse(re.search("module load", modtxt))
        os.remove(toy_module_path)

        # test module path with GCC/4.7.2 build, pretend to be an MPI lib by setting moduleclass
        extra_args = [
            '--try-toolchain=GCC,4.7.2',
            '--try-amend=moduleclass=mpi',
        ]
        self.eb_main(args + extra_args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)

        # make sure module file is installed in correct path
        toy_module_path = os.path.join(mod_prefix, 'Compiler', 'GCC', '4.7.2', 'toy', '0.0')
        self.assertTrue(os.path.exists(toy_module_path))

        # 'module use' statements to extend $MODULEPATH are present
        modtxt = read_file(toy_module_path)
        modpath_extension = os.path.join(mod_prefix, 'MPI', 'GCC', '4.7.2', 'toy', '0.0')
        self.assertTrue(re.search("^module\s*use\s*%s" % modpath_extension, modtxt, re.M))
        os.remove(toy_module_path)

        # ... unless they shouldn't be
        extra_args.append('--try-amend=include_modpath_extensions=')  # pass empty string as equivalent to False
        self.eb_main(args + extra_args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)
        modtxt = read_file(toy_module_path)
        modpath_extension = os.path.join(mod_prefix, 'MPI', 'GCC', '4.7.2', 'toy', '0.0')
        self.assertFalse(re.search("^module\s*use\s*%s" % modpath_extension, modtxt, re.M))
        os.remove(toy_module_path)

        # test module path with dummy/dummy build
        extra_args = [
            '--try-toolchain=dummy,dummy',
        ]
        self.eb_main(args + extra_args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)

        # make sure module file is installed in correct path
        toy_module_path = os.path.join(mod_prefix, 'Core', 'toy', '0.0')
        self.assertTrue(os.path.exists(toy_module_path))

        # no dependencies or toolchain => no module load statements in module file
        modtxt = read_file(toy_module_path)
        self.assertFalse(re.search("module load", modtxt))
        os.remove(toy_module_path)

        # test module path with dummy/dummy build, pretend to be a compiler by setting moduleclass
        extra_args = [
            '--try-toolchain=dummy,dummy',
            '--try-amend=moduleclass=compiler',
        ]
        self.eb_main(args + extra_args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)

        # make sure module file is installed in correct path
        toy_module_path = os.path.join(mod_prefix, 'Core', 'toy', '0.0')
        self.assertTrue(os.path.exists(toy_module_path))

        # no dependencies or toolchain => no module load statements in module file
        modtxt = read_file(toy_module_path)
        modpath_extension = os.path.join(mod_prefix, 'Compiler', 'toy', '0.0')
        self.assertTrue(re.search("^module\s*use\s*%s" % modpath_extension, modtxt, re.M))
        os.remove(toy_module_path)

        # building a toolchain module should also work
        args = ['gompi-1.4.10.eb'] + args[1:]
        modules_tool().purge()
        self.eb_main(args, logfile=self.dummylogfn, do_build=True, verbose=True, raise_error=True)

    def test_toy_advanced(self):
        """Test toy build with extensions and non-dummy toolchain."""
        test_dir = os.path.abspath(os.path.dirname(__file__))
        os.environ['MODULEPATH'] = os.path.join(test_dir, 'modules')
        test_ec = os.path.join(test_dir, 'easyconfigs', 'toy-0.0-gompi-1.3.12.eb')
        self.test_toy_build(ec_file=test_ec, versionsuffix='-gompi-1.3.12')

    def test_toy_hidden(self):
        """Test installing a hidden module."""
        ec_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'toy-0.0.eb')
        self.test_toy_build(ec_file=ec_file, extra_args=['--hidden'], verify=False)
        # module file is hidden
        toy_module = os.path.join(self.test_installpath, 'modules', 'all', 'toy', '.0.0')
        self.assertTrue(os.path.exists(toy_module), 'Found hidden module %s' % toy_module)
        # installed software is not hidden
        toybin = os.path.join(self.test_installpath, 'software', 'toy', '0.0', 'bin', 'toy')
        self.assertTrue(os.path.exists(toybin))

    def test_module_filepath_tweaking(self):
        """Test using --suffix-modules-path."""
        # install test module naming scheme dynamically
        test_mns_parent_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox')
        sys.path.append(test_mns_parent_dir)
        reload(easybuild)
        reload(easybuild.tools)
        reload(easybuild.tools.module_naming_scheme)
        mns_path = "easybuild.tools.module_naming_scheme.test_module_naming_scheme"
        __import__(mns_path, globals(), locals(), [''])

        eb_file = os.path.join(os.path.dirname(__file__), 'easyconfigs', 'toy-0.0.eb')
        args = [
            eb_file,
            '--sourcepath=%s' % self.test_sourcepath,
            '--buildpath=%s' % self.test_buildpath,
            '--installpath=%s' % self.test_installpath,
            '--force',
            '--debug',
            '--suffix-modules-path=foobarbaz',
            '--module-naming-scheme=TestModuleNamingScheme',
        ]
        self.eb_main(args, do_build=True, verbose=True)
        mod_file_prefix = os.path.join(self.test_installpath, 'modules')
        self.assertTrue(os.path.exists(os.path.join(mod_file_prefix, 'foobarbaz', 'toy', '0.0')))
        self.assertTrue(os.path.exists(os.path.join(mod_file_prefix, 'TOOLS', 'toy', '0.0')))
        self.assertTrue(os.path.islink(os.path.join(mod_file_prefix, 'TOOLS', 'toy', '0.0')))
        self.assertTrue(os.path.exists(os.path.join(mod_file_prefix, 't', 'toy', '0.0')))
        self.assertTrue(os.path.islink(os.path.join(mod_file_prefix, 't', 'toy', '0.0')))

    def test_toy_archived_easyconfig(self):
        """Test archived easyconfig for a succesful build."""
        repositorypath = os.path.join(self.test_installpath, 'easyconfigs_archive')
        extra_args = [
            '--repository=FileRepository',
            '--repositorypath=%s' % repositorypath,
        ]
        self.test_toy_build(raise_error=True, extra_args=extra_args)

        archived_ec = os.path.join(repositorypath, 'toy', 'toy-0.0.eb')
        self.assertTrue(os.path.exists(archived_ec))
        ec = EasyConfig(archived_ec)
        self.assertEqual(ec.name, 'toy')
        self.assertEqual(ec.version, '0.0')

def suite():
    """ return all the tests in this file """
    return TestLoader().loadTestsFromTestCase(ToyBuildTest)

if __name__ == '__main__':
    #logToScreen(enable=True)
    #setLogLevelDebug()
    unittestmain()
