# #
# Copyright 2013 Ghent University
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
Unit tests for EasyBuild configuration.

@author: Kenneth Hoste (Ghent University)
@author: Stijn De Weirdt (Ghent University)
"""
import os
import shutil
import tempfile
from unittest import TestCase, TestLoader
from unittest import main as unittestmain

import easybuild.tools.config as config
import easybuild.tools.options as eboptions
from easybuild.main import main
from easybuild.tools.config import build_path, source_paths, install_path, get_repository, get_repositorypath
from easybuild.tools.config import log_file_format
from easybuild.tools.config import get_build_log_path, ConfigurationVariables, DEFAULT_PATH_SUBDIRS
from easybuild.tools.filetools import write_file
from easybuild.tools.repository import FileRepository, init_repository


class EasyBuildConfigTest(TestCase):
    """Test cases for EasyBuild configuration."""

    tmpdir = None

    def cleanup(self):
        """Cleanup enviroment"""
        for envvar in os.environ.keys():
            if envvar.startswith('EASYBUILD'):
                del os.environ[envvar]

    def setUp(self):
        """Prepare for running a config test."""

        config.variables = ConfigurationVariables()
        self.tmpdir = tempfile.mkdtemp()
        self.cleanup()

    def tearDown(self):
        """Clean up after a config test."""
        self.cleanup()
        try:
            shutil.rmtree(self.tmpdir)
        except OSError:
            pass

    def configure_options(self, args=None):
        """(re)Configure."""
        eb_go = eboptions.parse_options(args=args)
        options = eb_go.options
        config_options = eb_go.get_options_by_section('config')
        config.init(options, config_options)
        return eb_go.options

    def configure(self, args=None):
        """(re)Configure and return configfile"""
        options = self.configure_options(args=args)
        return options.config

    def test_default_config(self):
        """Test default configuration."""
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
        self.assertEqual(config_options['tmp_logdir'], tempfile.gettempdir())

    def test_legacy_env_vars(self):
        """Test legacy environment variables."""

        # build path
        test_buildpath = os.path.join(self.tmpdir, 'build', 'path')
        os.environ['EASYBUILDBUILDPATH'] = test_buildpath
        self.configure(args=[])
        self.assertEqual(build_path(), test_buildpath)
        del os.environ['EASYBUILDBUILDPATH']

        # source path(s)
        test_sourcepaths = [
            os.path.join(self.tmpdir, 'source', 'path'),
            ':'.join([
                os.path.join(self.tmpdir, 'source', 'path1'),
                os.path.join(self.tmpdir, 'source', 'path2'),
            ]),
            ':'.join([
                os.path.join(self.tmpdir, 'source', 'path1'),
                os.path.join(self.tmpdir, 'source', 'path2'),
                os.path.join(self.tmpdir, 'source', 'path3'),
            ]),
        ]
        for test_sourcepath in test_sourcepaths:
            config.variables = ConfigurationVariables()
            os.environ['EASYBUILDSOURCEPATH'] = test_sourcepath
            self.configure(args=[])
            self.assertEqual(build_path(), os.path.join(os.path.expanduser('~'), '.local', 'easybuild',
                                                        DEFAULT_PATH_SUBDIRS['buildpath']))
            self.assertEqual(source_paths(), test_sourcepath.split(':'))
            del os.environ['EASYBUILDSOURCEPATH']

        test_sourcepath = os.path.join(self.tmpdir, 'source', 'path')

        # install path
        config.variables = ConfigurationVariables()
        test_installpath = os.path.join(self.tmpdir, 'install', 'path')
        os.environ['EASYBUILDINSTALLPATH'] = test_installpath
        self.configure(args=[])
        self.assertEqual(source_paths()[0], os.path.join(os.path.expanduser('~'), '.local', 'easybuild',
                                                          DEFAULT_PATH_SUBDIRS['sourcepath']))
        self.assertEqual(install_path(), os.path.join(test_installpath, DEFAULT_PATH_SUBDIRS['subdir_software']))
        self.assertEqual(install_path(typ='mod'), os.path.join(test_installpath,
                                                                 DEFAULT_PATH_SUBDIRS['subdir_modules']))
        del os.environ['EASYBUILDINSTALLPATH']

        # prefix: should change build/install/source/repo paths
        config.variables = ConfigurationVariables()
        test_prefixpath = os.path.join(self.tmpdir, 'prefix', 'path')
        os.environ['EASYBUILDPREFIX'] = test_prefixpath
        self.configure(args=[])
        self.assertEqual(build_path(), os.path.join(test_prefixpath, DEFAULT_PATH_SUBDIRS['buildpath']))
        self.assertEqual(source_paths()[0], os.path.join(test_prefixpath, DEFAULT_PATH_SUBDIRS['sourcepath']))
        self.assertEqual(install_path(), os.path.join(test_prefixpath, DEFAULT_PATH_SUBDIRS['subdir_software']))
        self.assertEqual(install_path(typ='mod'), os.path.join(test_prefixpath,
                                                               DEFAULT_PATH_SUBDIRS['subdir_modules']))
        repo = init_repository(get_repository(), get_repositorypath())
        self.assertTrue(isinstance(repo, FileRepository))
        self.assertEqual(repo.repo, os.path.join(test_prefixpath, DEFAULT_PATH_SUBDIRS['repositorypath']))

        # build/source/install path overrides prefix
        config.variables = ConfigurationVariables()
        os.environ['EASYBUILDBUILDPATH'] = test_buildpath
        self.configure(args=[])
        self.assertEqual(build_path(), test_buildpath)
        self.assertEqual(source_paths()[0], os.path.join(test_prefixpath, DEFAULT_PATH_SUBDIRS['sourcepath']))
        self.assertEqual(install_path(), os.path.join(test_prefixpath, DEFAULT_PATH_SUBDIRS['subdir_software']))
        self.assertEqual(install_path(typ='mod'), os.path.join(test_prefixpath,
                                                               DEFAULT_PATH_SUBDIRS['subdir_modules']))
        repo = init_repository(get_repository(), get_repositorypath())
        self.assertTrue(isinstance(repo, FileRepository))
        self.assertEqual(repo.repo, os.path.join(test_prefixpath, DEFAULT_PATH_SUBDIRS['repositorypath']))
        # also check old style vs new style
        self.assertEqual(config.variables['build_path'], config.variables['buildpath'])
        self.assertEqual(config.variables['install_path'], config.variables['installpath'])
        del os.environ['EASYBUILDBUILDPATH']

        config.variables = ConfigurationVariables()
        os.environ['EASYBUILDSOURCEPATH'] = test_sourcepath
        self.configure(args=[])
        self.assertEqual(build_path(), os.path.join(test_prefixpath, DEFAULT_PATH_SUBDIRS['buildpath']))
        self.assertEqual(source_paths()[0], test_sourcepath)
        self.assertEqual(install_path(), os.path.join(test_prefixpath, DEFAULT_PATH_SUBDIRS['subdir_software']))
        self.assertEqual(install_path(typ='mod'), os.path.join(test_prefixpath,
                                                               DEFAULT_PATH_SUBDIRS['subdir_modules']))
        repo = init_repository(get_repository(), get_repositorypath())
        self.assertTrue(isinstance(repo, FileRepository))
        self.assertEqual(repo.repo, os.path.join(test_prefixpath, DEFAULT_PATH_SUBDIRS['repositorypath']))
        del os.environ['EASYBUILDSOURCEPATH']

        config.variables = ConfigurationVariables()
        os.environ['EASYBUILDINSTALLPATH'] = test_installpath
        self.configure(args=[])
        self.assertEqual(build_path(), os.path.join(test_prefixpath, DEFAULT_PATH_SUBDIRS['buildpath']))
        self.assertEqual(source_paths()[0], os.path.join(test_prefixpath, DEFAULT_PATH_SUBDIRS['sourcepath']))
        self.assertEqual(install_path(), os.path.join(test_installpath, DEFAULT_PATH_SUBDIRS['subdir_software']))
        self.assertEqual(install_path(typ='mod'), os.path.join(test_installpath,
                                                               DEFAULT_PATH_SUBDIRS['subdir_modules']))
        repo = init_repository(get_repository(), get_repositorypath())
        self.assertTrue(isinstance(repo, FileRepository))
        self.assertEqual(repo.repo, os.path.join(test_prefixpath, DEFAULT_PATH_SUBDIRS['repositorypath']))
        del os.environ['EASYBUILDINSTALLPATH']

        del os.environ['EASYBUILDPREFIX']

    def test_legacy_config_file(self):
        """Test finding/using legacy configuration files."""

        cfg_fn = self.configure(args=[])
        self.assertTrue(cfg_fn.endswith('easybuild/easybuild_config.py'))

        configtxt = """
build_path = '%(buildpath)s'
source_path = '%(sourcepath)s'
install_path = '%(installpath)s'
repository_path = '%(repopath)s'
repository = FileRepository(repository_path)
log_format = ('%(logdir)s', '%(logtmpl)s')
log_dir = '%(tmplogdir)s'
software_install_suffix = '%(softsuffix)s'
modules_install_suffix = '%(modsuffix)s'
"""

        buildpath = os.path.join(self.tmpdir, 'my', 'test', 'build', 'path')
        sourcepath = os.path.join(self.tmpdir, 'my', 'test', 'source', 'path')
        installpath = os.path.join(self.tmpdir, 'my', 'test', 'install', 'path')
        repopath = os.path.join(self.tmpdir, 'my', 'test', 'repo', 'path')
        logdir = 'somedir'
        logtmpl = 'test-eb-%(name)s%(version)s_date-%(date)s__time-%(time)s.log'
        tmplogdir = os.path.join(self.tmpdir, 'my', 'test', 'tmplogdir')
        softsuffix = 'myfavoritesoftware'
        modsuffix = 'modulesgohere'

        configdict = {
            'buildpath': buildpath,
            'sourcepath': sourcepath,
            'installpath': installpath,
            'repopath': repopath,
            'logdir': logdir,
            'logtmpl': logtmpl,
            'tmplogdir': tmplogdir,
            'softsuffix': softsuffix,
            'modsuffix': modsuffix
        }

        # create user config file on default location
        myconfigfile = os.path.join(self.tmpdir, '.easybuild', 'config.py')
        if not os.path.exists(os.path.dirname(myconfigfile)):
            os.makedirs(os.path.dirname(myconfigfile))
        write_file(myconfigfile, configtxt % configdict)

        # redefine home so we can test user config file on default location
        home = os.environ.get('HOME', None)
        os.environ['HOME'] = self.tmpdir
        config.variables = ConfigurationVariables()
        cfg_fn = self.configure(args=[])
        if home is not None:
            os.environ['HOME'] = home

        # check finding and use of config file
        self.assertEqual(cfg_fn, myconfigfile)
        self.assertEqual(build_path(), buildpath)
        self.assertEqual(source_paths()[0], sourcepath)
        self.assertEqual(install_path(), os.path.join(installpath, softsuffix))
        self.assertEqual(install_path(typ='mod'), os.path.join(installpath, modsuffix))
        repo = init_repository(get_repository(), get_repositorypath())
        self.assertTrue(isinstance(repo, FileRepository))
        self.assertEqual(repo.repo, repopath)
        self.assertEqual(log_file_format(return_directory=True), logdir)
        self.assertEqual(log_file_format(), logtmpl)
        self.assertEqual(get_build_log_path(), tmplogdir)

        # redefine config file entries for proper testing below
        buildpath = os.path.join(self.tmpdir, 'my', 'custom', 'test', 'build', 'path')
        sourcepath = os.path.join(self.tmpdir, 'my', 'custom', 'test', 'source', 'path')
        installpath = os.path.join(self.tmpdir, 'my', 'custom', 'test', 'install', 'path')
        repopath = os.path.join(self.tmpdir, 'my', 'custom', 'test', 'repo', 'path')
        logdir = 'somedir_custom'
        logtmpl = 'test-custom-eb-%(name)_%(date)s%(time)s__%(version)s.log'
        tmplogdir = os.path.join(self.tmpdir, 'my', 'custom', 'test', 'tmplogdir')
        softsuffix = 'myfavoritesoftware_custom'
        modsuffix = 'modulesgohere_custom'

        configdict = {
            'buildpath': buildpath,
            'sourcepath': sourcepath,
            'installpath': installpath,
            'repopath': repopath,
            'logdir': logdir,
            'logtmpl': logtmpl,
            'tmplogdir': tmplogdir,
            'softsuffix': softsuffix,
            'modsuffix': modsuffix }

        # create custom config file, and point to it
        mycustomconfigfile = os.path.join(self.tmpdir, 'mycustomconfig.py')
        if not os.path.exists(os.path.dirname(mycustomconfigfile)):
            os.makedirs(os.path.dirname(mycustomconfigfile))
        write_file(mycustomconfigfile, configtxt % configdict)
        os.environ['EASYBUILDCONFIG'] = mycustomconfigfile

        # reconfigure
        config.variables = ConfigurationVariables()
        cfg_fn = self.configure(args=[])

        # verify configuration
        self.assertEqual(cfg_fn, mycustomconfigfile)
        self.assertEqual(build_path(), buildpath)
        self.assertEqual(source_paths()[0], sourcepath)
        self.assertEqual(install_path(), os.path.join(installpath, softsuffix))
        self.assertEqual(install_path(typ='mod'), os.path.join(installpath, modsuffix))
        repo = init_repository(get_repository(), get_repositorypath())
        self.assertTrue(isinstance(repo, FileRepository))
        self.assertEqual(repo.repo, repopath)
        self.assertEqual(log_file_format(return_directory=True), logdir)
        self.assertEqual(log_file_format(), logtmpl)
        self.assertEqual(get_build_log_path(), tmplogdir)
        del os.environ['EASYBUILDCONFIG']

    def test_generaloption_config(self):
        """Test new-style configuration (based on generaloption)."""

        # check whether configuration via environment variables works as expected
        prefix = os.path.join(self.tmpdir, 'testprefix')
        buildpath_env_var = os.path.join(self.tmpdir, 'envvar', 'build', 'path')
        os.environ['EASYBUILD_PREFIX'] = prefix
        os.environ['EASYBUILD_BUILDPATH'] = buildpath_env_var
        options = self.configure_options(args=[])
        self.assertEqual(build_path(), buildpath_env_var)
        del os.environ['EASYBUILD_PREFIX']
        del os.environ['EASYBUILD_BUILDPATH']

        # check whether configuration via command line arguments works
        prefix = os.path.join(self.tmpdir, 'test1')
        install = os.path.join(self.tmpdir, 'test2', 'install')
        repopath = os.path.join(self.tmpdir, 'test2', 'repo')
        config_file = os.path.join(self.tmpdir, 'nooldconfig.py')

        write_file(config_file, '')

        args = [
            '--config', config_file,  # force empty oldstyle config file
            '--prefix', prefix,
            '--installpath', install,
            '--repositorypath', repopath,
        ]

        options = self.configure_options(args=args)

        self.assertEqual(build_path(), os.path.join(prefix, 'build'))
        self.assertEqual(install_path(), os.path.join(install, 'software'))
        self.assertEqual(install_path(typ='mod'), os.path.join(install, 'modules'))

        self.assertEqual(options.installpath, install)
        self.assertEqual(options.config, config_file)

        # check mixed command line/env var configuration
        prefix = os.path.join(self.tmpdir, 'test3')
        install = os.path.join(self.tmpdir, 'test4', 'install')
        subdir_software = 'eb-soft'
        args = [
            '--config', config_file,  # force empty oldstyle config file
            '--installpath', install,
        ]

        os.environ['EASYBUILD_PREFIX'] = prefix
        os.environ['EASYBUILD_SUBDIR_SOFTWARE'] = subdir_software

        options = self.configure_options(args=args)

        self.assertEqual(build_path(), os.path.join(prefix, 'build'))
        self.assertEqual(install_path(), os.path.join(install, subdir_software))

        del os.environ['EASYBUILD_PREFIX']
        del os.environ['EASYBUILD_SUBDIR_SOFTWARE']

def suite():
    return TestLoader().loadTestsFromTestCase(EasyBuildConfigTest)

if __name__ == '__main__':
    unittestmain()
