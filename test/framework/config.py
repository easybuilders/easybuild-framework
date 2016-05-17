# #
# Copyright 2013-2016 Ghent University
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
Unit tests for EasyBuild configuration.

@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""
import os
import shutil
import sys
import tempfile
from test.framework.utilities import EnhancedTestCase, init_config
from unittest import TestLoader
from unittest import main as unittestmain
from vsc.utils.fancylogger import setLogLevelDebug, logToScreen

import easybuild.tools.options as eboptions
from easybuild.tools import run
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option, build_path, source_paths, install_path, get_repositorypath
from easybuild.tools.config import BuildOptions, ConfigurationVariables
from easybuild.tools.config import get_build_log_path, DEFAULT_PATH_SUBDIRS, init_build_options
from easybuild.tools.environment import modify_env
from easybuild.tools.filetools import mkdir, write_file
from easybuild.tools.options import CONFIG_ENV_VAR_PREFIX


class EasyBuildConfigTest(EnhancedTestCase):
    """Test cases for EasyBuild configuration."""

    tmpdir = None

    def setUp(self):
        """Prepare for running a config test."""
        reload(eboptions)
        super(EasyBuildConfigTest, self).setUp()
        self.tmpdir = tempfile.mkdtemp()

    def purge_environment(self):
        """Remove any leftover easybuild variables"""
        for var in os.environ.keys():
            # retain $EASYBUILD_IGNORECONFIGFILES, to make sure the test is isolated from system-wide config files!
            if var.startswith('EASYBUILD_') and var != 'EASYBUILD_IGNORECONFIGFILES':
                del os.environ[var]

    def tearDown(self):
        """Clean up after a config test."""
        super(EasyBuildConfigTest, self).tearDown()

        try:
            shutil.rmtree(self.tmpdir)
        except OSError:
            pass
        tempfile.tempdir = None

    def configure(self, args=None):
        """(re)Configure and return configfile"""
        options = init_config(args=args)
        return options.config

    def test_default_config(self):
        """Test default configuration."""
        self.purge_environment()

        eb_go = eboptions.parse_options(args=[])
        config_options = eb_go.get_options_by_section('config')

        # check default subdirs
        self.assertEqual(DEFAULT_PATH_SUBDIRS['buildpath'], 'build')
        self.assertEqual(DEFAULT_PATH_SUBDIRS['installpath'], '')
        self.assertEqual(DEFAULT_PATH_SUBDIRS['subdir_modules'], 'modules')
        self.assertEqual(DEFAULT_PATH_SUBDIRS['repositorypath'], 'ebfiles_repo')
        self.assertEqual(DEFAULT_PATH_SUBDIRS['sourcepath'], 'sources')
        self.assertEqual(DEFAULT_PATH_SUBDIRS['subdir_software'], 'software')

        # check whether defaults are honored, use hardcoded paths/subdirs
        eb_homedir = os.path.join(os.path.expanduser('~'), '.local', 'easybuild')
        self.assertEqual(config_options['buildpath'], os.path.join(eb_homedir, 'build'))
        self.assertEqual(config_options['sourcepath'], os.path.join(eb_homedir, 'sources'))
        self.assertEqual(config_options['installpath'], eb_homedir)
        self.assertEqual(config_options['subdir_software'], 'software')
        self.assertEqual(config_options['subdir_modules'], 'modules')
        self.assertEqual(config_options['repository'], 'FileRepository')
        self.assertEqual(config_options['repositorypath'], [os.path.join(eb_homedir, 'ebfiles_repo')])
        self.assertEqual(config_options['logfile_format'][0], 'easybuild')
        self.assertEqual(config_options['logfile_format'][1], "easybuild-%(name)s-%(version)s-%(date)s.%(time)s.log")
        self.assertEqual(config_options['tmpdir'], None)
        self.assertEqual(config_options['tmp_logdir'], None)

    def test_generaloption_config(self):
        """Test new-style configuration (based on generaloption)."""
        self.purge_environment()

        # check whether configuration via environment variables works as expected
        prefix = os.path.join(self.tmpdir, 'testprefix')
        buildpath_env_var = os.path.join(self.tmpdir, 'envvar', 'build', 'path')
        os.environ['EASYBUILD_PREFIX'] = prefix
        os.environ['EASYBUILD_BUILDPATH'] = buildpath_env_var
        options = init_config(args=[])
        self.assertEqual(build_path(), buildpath_env_var)
        self.assertEqual(install_path(), os.path.join(prefix, 'software'))
        self.assertEqual(get_repositorypath(), [os.path.join(prefix, 'ebfiles_repo')])

        del os.environ['EASYBUILD_PREFIX']
        del os.environ['EASYBUILD_BUILDPATH']

        # check whether configuration via command line arguments works
        prefix = os.path.join(self.tmpdir, 'test1')
        install = os.path.join(self.tmpdir, 'test2', 'install')
        repopath = os.path.join(self.tmpdir, 'test2', 'repo')
        config_file = os.path.join(self.tmpdir, 'nooldconfig.py')

        write_file(config_file, '')

        args = [
            '--configfiles', config_file,  # force empty config file
            '--prefix', prefix,
            '--installpath', install,
            '--repositorypath', repopath,
            '--subdir-software', 'APPS',
        ]

        options = init_config(args=args)

        self.assertEqual(build_path(), os.path.join(prefix, 'build'))
        self.assertEqual(install_path(), os.path.join(install, 'APPS'))
        self.assertEqual(install_path(typ='mod'), os.path.join(install, 'modules'))

        self.assertEqual(options.installpath, install)
        self.assertTrue(config_file in options.configfiles)

        # check mixed command line/env var configuration
        prefix = os.path.join(self.tmpdir, 'test3')
        install = os.path.join(self.tmpdir, 'test4', 'install')
        subdir_software = 'eb-soft'
        args = [
            '--configfiles', config_file,  # force empty config file
            '--installpath', install,
        ]

        os.environ['EASYBUILD_PREFIX'] = prefix
        os.environ['EASYBUILD_SUBDIR_SOFTWARE'] = subdir_software
        installpath_modules = tempfile.mkdtemp(prefix='installpath-modules')
        os.environ['EASYBUILD_INSTALLPATH_MODULES'] = installpath_modules

        options = init_config(args=args)

        self.assertEqual(build_path(), os.path.join(prefix, 'build'))
        self.assertEqual(install_path(), os.path.join(install, subdir_software))
        self.assertEqual(install_path('mod'), installpath_modules)

        # subdir options *must* be relative (to --installpath)
        installpath_software = tempfile.mkdtemp(prefix='installpath-software')
        os.environ['EASYBUILD_SUBDIR_SOFTWARE'] = installpath_software
        error_regex = r"Found problems validating the options.*'subdir_software' must specify a \*relative\* path"
        self.assertErrorRegex(EasyBuildError, error_regex, init_config)

        del os.environ['EASYBUILD_PREFIX']
        del os.environ['EASYBUILD_SUBDIR_SOFTWARE']

    def test_error_env_var_typo(self):
        """Test error reporting on use of known $EASYBUILD-prefixed env vars."""
        # all is well
        init_config()

        os.environ['EASYBUILD_FOO'] = 'foo'
        os.environ['EASYBUILD_THERESNOSUCHCONFIGURATIONOPTION'] = 'whatever'

        error = r"Found 2 environment variable\(s\) that are prefixed with %s " % CONFIG_ENV_VAR_PREFIX
        error += "but do not match valid option\(s\): "
        error += ','.join(['EASYBUILD_FOO', 'EASYBUILD_THERESNOSUCHCONFIGURATIONOPTION'])
        self.assertErrorRegex(EasyBuildError, error, init_config)

        del os.environ['EASYBUILD_THERESNOSUCHCONFIGURATIONOPTION']
        del os.environ['EASYBUILD_FOO']

    def test_install_path(self):
        """Test install_path function."""
        # defaults
        self.assertEqual(install_path(), os.path.join(self.test_installpath, 'software'))
        self.assertEqual(install_path('software'), os.path.join(self.test_installpath, 'software'))
        self.assertEqual(install_path(typ='mod'), os.path.join(self.test_installpath, 'modules'))
        self.assertEqual(install_path('modules'), os.path.join(self.test_installpath, 'modules'))

        self.assertErrorRegex(EasyBuildError, "Unknown type specified", install_path, typ='foo')

        args = [
            '--subdir-software', 'SOFT',
            '--installpath', '/foo',
        ]
        os.environ['EASYBUILD_SUBDIR_MODULES'] = 'MOD'
        init_config(args=args)
        self.assertEqual(install_path(), os.path.join('/foo', 'SOFT'))
        self.assertEqual(install_path(typ='mod'), os.path.join('/foo', 'MOD'))
        del os.environ['EASYBUILD_SUBDIR_MODULES']

        args = [
            '--installpath', '/prefix',
            '--installpath-modules', '/foo',
        ]
        os.environ['EASYBUILD_INSTALLPATH_SOFTWARE'] = '/bar/baz'
        init_config(args=args)
        self.assertEqual(install_path(), os.path.join('/bar', 'baz'))
        self.assertEqual(install_path(typ='mod'), '/foo')

        del os.environ['EASYBUILD_INSTALLPATH_SOFTWARE']
        init_config(args=args)
        self.assertEqual(install_path(), os.path.join('/prefix', 'software'))
        self.assertEqual(install_path(typ='mod'), '/foo')

    def test_generaloption_config_file(self):
        """Test use of new-style configuration file."""
        self.purge_environment()

        config_file = os.path.join(self.tmpdir, 'testconfig.cfg')

        testpath1 = os.path.join(self.tmpdir, 'test1')
        testpath2 = os.path.join(self.tmpdir, 'testtwo')

        # test with config file passed via command line
        cfgtxt = '\n'.join([
            '[config]',
            'installpath = %s' % testpath2,
        ])
        write_file(config_file, cfgtxt)

        installpath_software = tempfile.mkdtemp(prefix='installpath-software')
        args = [
            '--configfiles', config_file,
            '--debug',
            '--buildpath', testpath1,
            '--installpath-software', installpath_software,
        ]
        options = init_config(args=args)

        self.assertEqual(build_path(), testpath1)  # via command line
        self.assertEqual(source_paths(), [os.path.join(os.getenv('HOME'), '.local', 'easybuild', 'sources')])  # default
        self.assertEqual(install_path(), installpath_software)  # via cmdline arg
        self.assertEqual(install_path('mod'), os.path.join(testpath2, 'modules'))  # via config file

        # copy test easyconfigs to easybuild/easyconfigs subdirectory of temp directory
        # to check whether easyconfigs install path is auto-included in robot path
        tmpdir = tempfile.mkdtemp(prefix='easybuild-easyconfigs-pkg-install-path')
        mkdir(os.path.join(tmpdir, 'easybuild'), parents=True)

        test_ecs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        shutil.copytree(test_ecs_dir, os.path.join(tmpdir, 'easybuild', 'easyconfigs'))

        orig_sys_path = sys.path[:]
        sys.path.insert(0, tmpdir)  # prepend to give it preference over possible other installed easyconfigs pkgs

        # test with config file passed via environment variable
        installpath_modules = tempfile.mkdtemp(prefix='installpath-modules')
        cfgtxt = '\n'.join([
            '[config]',
            'buildpath = %s' % testpath1,
            'sourcepath = %(DEFAULT_REPOSITORYPATH)s',
            'repositorypath = %(DEFAULT_REPOSITORYPATH)s,somesubdir',
            'robot-paths=/tmp/foo:%(sourcepath)s:%(DEFAULT_ROBOT_PATHS)s',
            'installpath-modules=%s' % installpath_modules,
        ])
        write_file(config_file, cfgtxt)

        os.environ['EASYBUILD_CONFIGFILES'] = config_file
        args = [
            '--debug',
            '--sourcepath', testpath2,
        ]
        options = init_config(args=args)

        topdir = os.path.join(os.getenv('HOME'), '.local', 'easybuild')
        self.assertEqual(install_path(), os.path.join(topdir, 'software'))  # default
        self.assertEqual(install_path('mod'), installpath_modules),  # via config file
        self.assertEqual(source_paths(), [testpath2])  # via command line
        self.assertEqual(build_path(), testpath1)  # via config file
        self.assertEqual(get_repositorypath(), [os.path.join(topdir, 'ebfiles_repo'), 'somesubdir'])  # via config file
        robot_paths = [
            '/tmp/foo',
            os.path.join(os.getenv('HOME'), '.local', 'easybuild', 'ebfiles_repo'),
            os.path.join(tmpdir, 'easybuild', 'easyconfigs'),
        ]
        self.assertEqual(options.robot_paths[:3], robot_paths)

        testpath3 = os.path.join(self.tmpdir, 'testTHREE')
        os.environ['EASYBUILD_SOURCEPATH'] = testpath2
        args = [
            '--debug',
            '--installpath', testpath3,
        ]
        options = init_config(args=args)

        self.assertEqual(source_paths(), [testpath2])  # via environment variable $EASYBUILD_SOURCEPATHS
        self.assertEqual(install_path(), os.path.join(testpath3, 'software'))  # via command line
        self.assertEqual(install_path('mod'), installpath_modules),  # via config file
        self.assertEqual(build_path(), testpath1)  # via config file

        del os.environ['EASYBUILD_CONFIGFILES']
        sys.path[:] = orig_sys_path

    def test_configuration_variables(self):
        """Test usage of ConfigurationVariables."""
        # delete instance of ConfigurationVariables
        ConfigurationVariables.__metaclass__._instances.pop(ConfigurationVariables, None)

        # make sure ConfigurationVariables is a singleton class (only one available instance)
        cv1 = ConfigurationVariables()
        cv2 = ConfigurationVariables()
        cv3 = ConfigurationVariables({'foo': 'bar'})  # note: argument is ignored, an instance is already available
        self.assertTrue(cv1 is cv2)
        self.assertTrue(cv1 is cv3)

    def test_build_options(self):
        """Test usage of BuildOptions."""
        # delete instance of BuildOptions
        BuildOptions.__metaclass__._instances.pop(BuildOptions, None)

        # make sure BuildOptions is a singleton class
        bo1 = BuildOptions()
        bo2 = BuildOptions()
        bo3 = BuildOptions({'foo': 'bar'})  # note: argument is ignored, an instance is already available
        self.assertTrue(bo1 is bo2)
        self.assertTrue(bo1 is bo3)

        # test basic functionality
        BuildOptions.__metaclass__._instances.pop(BuildOptions, None)
        bo = BuildOptions({
            'debug': False,
            'force': True
        })
        self.assertTrue(not bo['debug'])
        self.assertTrue(bo['force'])

        # updating is impossible (methods are not even available)
        self.assertErrorRegex(TypeError, '.*item assignment.*', lambda x: bo.update(x), {'debug': True})
        self.assertErrorRegex(AttributeError, '.*no attribute.*', lambda x: bo.__setitem__(*x), ('debug', True))

        # only valid keys can be set
        BuildOptions.__metaclass__._instances.pop(BuildOptions, None)
        msg = "Encountered unknown keys .* \(known keys: .*"
        self.assertErrorRegex(KeyError, msg, BuildOptions, {'thisisclearlynotavalidbuildoption': 'FAIL'})

        # test init_build_options and build_option functions
        self.assertErrorRegex(KeyError, msg, init_build_options, {'thisisclearlynotavalidbuildoption': 'FAIL'})
        bo = init_build_options({
            'robot_path': '/some/robot/path',
            'stop': 'configure',
        })

        # specific build options should be set
        self.assertEqual(bo['robot_path'], '/some/robot/path')
        self.assertEqual(bo['stop'], 'configure')

        # all possible build options should be set (defaults are used where needed)
        self.assertEqual(sorted(bo.keys()), sorted(BuildOptions.KNOWN_KEYS))

        # there should be only one BuildOptions instance
        bo2 = BuildOptions()
        self.assertTrue(bo is bo2)

    def test_XDG_CONFIG_env_vars(self):
        """Test effect of XDG_CONFIG* environment variables on default configuration."""
        self.purge_environment()

        xdg_config_home = os.environ.get('XDG_CONFIG_HOME')
        xdg_config_dirs = os.environ.get('XDG_CONFIG_DIRS')

        cfg_template = '\n'.join([
            '[config]',
            'prefix=%s',
        ])

        homedir = os.path.join(self.test_prefix, 'homedir', '.config')
        mkdir(os.path.join(homedir, 'easybuild'), parents=True)
        write_file(os.path.join(homedir, 'easybuild', 'config.cfg'), cfg_template % '/home')

        dir1 = os.path.join(self.test_prefix, 'dir1')
        mkdir(os.path.join(dir1, 'easybuild.d'), parents=True)
        write_file(os.path.join(dir1, 'easybuild.d', 'foo.cfg'), cfg_template % '/foo')
        write_file(os.path.join(dir1, 'easybuild.d', 'bar.cfg'), cfg_template % '/bar')

        dir2 = os.path.join(self.test_prefix, 'dir2')  # empty on purpose
        mkdir(os.path.join(dir2, 'easybuild.d'), parents=True)

        dir3 = os.path.join(self.test_prefix, 'dir3')
        mkdir(os.path.join(dir3, 'easybuild.d'), parents=True)
        write_file(os.path.join(dir3, 'easybuild.d', 'foobarbaz.cfg'), cfg_template % '/foobarbaz')

        # set $XDG_CONFIG_DIRS to non-existing dir to isolate ourselves from possible system-wide config files
        os.environ['XDG_CONFIG_DIRS'] = '/there/should/be/no/such/directory/we/hope'

        # only $XDG_CONFIG_HOME set (to existing path)
        os.environ['XDG_CONFIG_HOME'] = homedir
        cfg_files = [os.path.join(homedir, 'easybuild', 'config.cfg')]
        reload(eboptions)
        eb_go = eboptions.parse_options(args=[])
        self.assertEqual(eb_go.options.configfiles, cfg_files)
        self.assertEqual(eb_go.options.prefix, '/home')

        # $XDG_CONFIG_HOME set, one directory listed in $XDG_CONFIG_DIRS
        os.environ['XDG_CONFIG_DIRS'] = dir1
        cfg_files = [
            os.path.join(dir1, 'easybuild.d', 'bar.cfg'),
            os.path.join(dir1, 'easybuild.d', 'foo.cfg'),
            os.path.join(homedir, 'easybuild', 'config.cfg'),  # $XDG_CONFIG_HOME goes last
        ]
        reload(eboptions)
        eb_go = eboptions.parse_options(args=[])
        self.assertEqual(eb_go.options.configfiles, cfg_files)
        self.assertEqual(eb_go.options.prefix, '/home')  # last cfgfile wins

        # $XDG_CONFIG_HOME not set, multiple directories listed in $XDG_CONFIG_DIRS
        del os.environ['XDG_CONFIG_HOME']  # unset, so should become default
        os.environ['XDG_CONFIG_DIRS'] = os.pathsep.join([dir1, dir2, dir3])
        cfg_files = [
            os.path.join(dir1, 'easybuild.d', 'bar.cfg'),
            os.path.join(dir1, 'easybuild.d', 'foo.cfg'),
            os.path.join(dir3, 'easybuild.d', 'foobarbaz.cfg'),
        ]
        reload(eboptions)
        eb_go = eboptions.parse_options(args=[])
        # note: there may be a config file in $HOME too, so don't use a strict comparison
        self.assertEqual(cfg_files, eb_go.options.configfiles[:3])

        # $XDG_CONFIG_HOME set to non-existing directory, multiple directories listed in $XDG_CONFIG_DIRS
        os.environ['XDG_CONFIG_HOME'] = os.path.join(self.test_prefix, 'nosuchdir')
        cfg_files = [
            os.path.join(dir1, 'easybuild.d', 'bar.cfg'),
            os.path.join(dir1, 'easybuild.d', 'foo.cfg'),
            os.path.join(dir3, 'easybuild.d', 'foobarbaz.cfg'),
        ]
        reload(eboptions)
        eb_go = eboptions.parse_options(args=[])
        self.assertEqual(eb_go.options.configfiles, cfg_files)
        self.assertEqual(eb_go.options.prefix, '/foobarbaz')  # last cfgfile wins

        # restore $XDG_CONFIG env vars to original state
        if xdg_config_home is None:
            del os.environ['XDG_CONFIG_HOME']
        else:
            os.environ['XDG_CONFIG_HOME'] = xdg_config_home

        if xdg_config_dirs is None:
            del os.environ['XDG_CONFIG_DIRS']
        else:
            os.environ['XDG_CONFIG_DIRS'] = xdg_config_dirs
        reload(eboptions)

    def test_flex_robot_paths(self):
        """Test prepend/appending to default robot search path via --robot-paths."""
        # unset $EASYBUILD_ROBOT_PATHS that was defined in setUp
        del os.environ['EASYBUILD_ROBOT_PATHS']

        # copy test easyconfigs to easybuild/easyconfigs subdirectory of temp directory
        # to check whether easyconfigs install path is auto-included in robot path
        tmpdir = tempfile.mkdtemp(prefix='easybuild-easyconfigs-pkg-install-path')
        mkdir(os.path.join(tmpdir, 'easybuild'), parents=True)
        test_ecs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs')
        tmp_ecs_dir = os.path.join(tmpdir, 'easybuild', 'easyconfigs')
        shutil.copytree(test_ecs_path, tmp_ecs_dir)

        # prepend path to test easyconfigs into Python search path, so it gets picked up as --robot-paths default
        orig_sys_path = sys.path[:]
        sys.path = [tmpdir] + [p for p in sys.path if not os.path.exists(os.path.join(p, 'easybuild', 'easyconfigs'))]

        # default: only pick up installed easyconfigs via sys.path
        eb_go = eboptions.parse_options(args=[])
        self.assertEqual(eb_go.options.robot_paths, [tmp_ecs_dir])

        # prepend to default robot path
        eb_go = eboptions.parse_options(args=['--robot-paths=/foo:'])
        self.assertEqual(eb_go.options.robot_paths, ['/foo', tmp_ecs_dir])
        eb_go = eboptions.parse_options(args=['--robot-paths=/foo:/bar/baz/:'])
        self.assertEqual(eb_go.options.robot_paths, ['/foo', '/bar/baz/', tmp_ecs_dir])

        # append to default robot path
        eb_go = eboptions.parse_options(args=['--robot-paths=:/bar/baz'])
        self.assertEqual(eb_go.options.robot_paths, [tmp_ecs_dir, '/bar/baz'])
        # append to default robot path
        eb_go = eboptions.parse_options(args=['--robot-paths=:/bar/baz:/foo'])
        self.assertEqual(eb_go.options.robot_paths, [tmp_ecs_dir, '/bar/baz', '/foo'])

        # prepend and append to default robot path
        eb_go = eboptions.parse_options(args=['--robot-paths=/foo/bar::/baz'])
        self.assertEqual(eb_go.options.robot_paths, ['/foo/bar', tmp_ecs_dir, '/baz'])
        eb_go = eboptions.parse_options(args=['--robot-paths=/foo/bar::/baz:/trala'])
        self.assertEqual(eb_go.options.robot_paths, ['/foo/bar', tmp_ecs_dir, '/baz', '/trala'])
        eb_go = eboptions.parse_options(args=['--robot-paths=/foo/bar:/trala::/baz'])
        self.assertEqual(eb_go.options.robot_paths, ['/foo/bar', '/trala', tmp_ecs_dir, '/baz'])

        # also via $EASYBUILD_ROBOT_PATHS
        os.environ['EASYBUILD_ROBOT_PATHS'] = '/foo::/bar/baz'
        eb_go = eboptions.parse_options(args=[])
        self.assertEqual(eb_go.options.robot_paths, ['/foo', tmp_ecs_dir, '/bar/baz'])

        # --robot-paths overrides $EASYBUILD_ROBOT_PATHS
        os.environ['EASYBUILD_ROBOT_PATHS'] = '/foobar::/barbar/baz/baz'
        eb_go = eboptions.parse_options(args=['--robot-paths=/one::/last'])
        self.assertEqual(eb_go.options.robot_paths, ['/one', tmp_ecs_dir, '/last'])

        del os.environ['EASYBUILD_ROBOT_PATHS']

        # also works with a cfgfile in the mix
        config_file = os.path.join(self.tmpdir, 'testconfig.cfg')
        cfgtxt = '\n'.join([
            '[config]',
            'robot-paths=/cfgfirst::/cfglast',
        ])
        write_file(config_file, cfgtxt)
        eb_go = eboptions.parse_options(args=['--configfiles=%s' % config_file])
        self.assertEqual(eb_go.options.robot_paths, ['/cfgfirst', tmp_ecs_dir, '/cfglast'])

        # cfgfile entry is lost when env var and/or cmdline options are used
        os.environ['EASYBUILD_ROBOT_PATHS'] = '/envfirst::/envend'
        eb_go = eboptions.parse_options(args=['--configfiles=%s' % config_file])
        self.assertEqual(eb_go.options.robot_paths, ['/envfirst', tmp_ecs_dir, '/envend'])

        del os.environ['EASYBUILD_ROBOT_PATHS']
        eb_go = eboptions.parse_options(args=['--robot-paths=/veryfirst:', '--configfiles=%s' % config_file])
        self.assertEqual(eb_go.options.robot_paths, ['/veryfirst', tmp_ecs_dir])

        os.environ['EASYBUILD_ROBOT_PATHS'] = ':/envend'
        eb_go = eboptions.parse_options(args=['--robot-paths=/veryfirst:', '--configfiles=%s' % config_file])
        self.assertEqual(eb_go.options.robot_paths, ['/veryfirst', tmp_ecs_dir])

        del os.environ['EASYBUILD_ROBOT_PATHS']

        # override default robot path
        eb_go = eboptions.parse_options(args=['--robot-paths=/foo:/bar/baz'])
        self.assertEqual(eb_go.options.robot_paths, ['/foo', '/bar/baz'])

        # paths specified via --robot still get preference
        eb_go = eboptions.parse_options(args=['--robot-paths=/foo/bar::/baz', '--robot=/first'])
        self.assertEqual(eb_go.options.robot_paths, ['/first', '/foo/bar', tmp_ecs_dir, '/baz'])

        sys.path[:] = orig_sys_path

    def test_strict(self):
        """Test use of --strict."""
        # check default
        self.assertEqual(build_option('strict'), run.WARN)

        for strict_str, strict_val in [('error', run.ERROR), ('ignore', run.IGNORE), ('warn', run.WARN)]:
            options = init_config(args=['--strict=%s' % strict_str])
            init_config(build_options={'strict': options.strict})
            self.assertEqual(build_option('strict'), strict_val)


def suite():
    return TestLoader().loadTestsFromTestCase(EasyBuildConfigTest)

if __name__ == '__main__':
    #logToScreen(enable=True)
    #setLogLevelDebug()
    unittestmain()
