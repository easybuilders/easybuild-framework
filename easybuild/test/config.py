# #
# Copyright 2012-2013 Ghent University
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
Unit tests for config.py

@author: Stijn De Weirdt (Ghent University)
"""
import os
import tempfile
import shutil

from unittest import TestCase, TestLoader, main

import easybuild.tools.config as config
import easybuild.tools.options as eboptions


BASE_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))  # PWD/..
CONFIG_PATH = os.path.join(BASE_PATH, 'easybuild_config.py')


class EasyBuildConfigTest(TestCase):

    def cleanup(self):
        """Cleanup enviroment"""
        for k in os.environ.keys():
            if k.startswith('EASYBUILD'):
                del os.environ[k]

    def get_opts_config(self, args=[]):
        """Return config, options. This is what main does."""

        eb_go = eboptions.parse_options(args=args)
        options = eb_go.options
        config.init(options, eb_go.get_options_by_section('config'))

        return options, config.variables

    def test_legacy_opts(self):
        """Test the legacyopts."""
        self.cleanup()
        def set_leg_env(newname, value):
            try:
                name = config.oldstyle_environment_variables[newname]
            except KeyError:
                name = 'EASYBUILD%s' % newname.upper()

            os.putenv(name, value)
            os.environ[name] = value

        tmpdir = tempfile.mkdtemp()
        PREFIX = os.path.join(tmpdir, 'test1')
        INSTALL = os.path.join(tmpdir, 'test2', 'install')

        set_leg_env('config_file', CONFIG_PATH)
        set_leg_env('prefix', PREFIX)
        set_leg_env('install_path', INSTALL)

        opts, evars = self.get_opts_config()

        self.assertEqual(evars['build_path'], os.path.join(PREFIX, 'build'))
        self.assertEqual(evars['install_path'], INSTALL)

        # check new style
        self.assertEqual(evars['build_path'], evars['buildpath'])
        self.assertEqual(evars['install_path'], evars['installpath'])

        self.cleanup()
        shutil.rmtree(tmpdir)



def suite():
    """ return all the tests in this file """
    return TestLoader().loadTestsFromTestCase(EasyBuildConfigTest)

if __name__ == '__main__':
    main()


