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
Various test utility functions.

@author: Kenneth Hoste (Ghent University)
"""
import copy
import os
import re
import shutil
import sys
import tempfile
from unittest import TestCase
from vsc.utils import fancylogger

import easybuild.tools.options as eboptions
from easybuild.framework.easyblock import EasyBlock
from easybuild.main import main
from easybuild.tools import config
from easybuild.tools.config import module_classes
from easybuild.tools.environment import modify_env
from easybuild.tools.filetools import read_file


class EnhancedTestCase(TestCase):
    """Enhanced test case, provides extra functionality (e.g. an assertErrorRegex method)."""

    def assertErrorRegex(self, error, regex, call, *args, **kwargs):
        """Convenience method to match regex with the expected error message"""
        try:
            call(*args, **kwargs)
            str_kwargs = ', '.join(['='.join([k,str(v)]) for (k,v) in kwargs.items()])
            str_args = ', '.join(map(str, args) + [str_kwargs])
            self.assertTrue(False, "Expected errors with %s(%s) call should occur" % (call.__name__, str_args))
        except error, err:
            if hasattr(err, 'msg'):
                msg = err.msg
            elif hasattr(err, 'message'):
                msg = err.message
            elif hasattr(err, 'args'):  # KeyError in Python 2.4 only provides message via 'args' attribute
                msg = err.args[0]
            else:
                msg = err
            try:
                msg = str(msg)
            except UnicodeEncodeError:
                msg = msg.encode('utf8', 'replace')
            self.assertTrue(re.search(regex, msg), "Pattern '%s' is found in '%s'" % (regex, msg))
            self.assertTrue(re.search(regex, msg), "Pattern '%s' is found in '%s'" % (regex, msg))

    def setUp(self):
        """Set up testcase."""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        fd, self.logfile = tempfile.mkstemp(suffix='.log', prefix='eb-test-')
        os.close(fd)
        self.cwd = os.getcwd()

        # keep track of original environment to restore
        self.orig_environ = copy.deepcopy(os.environ)

        # keep track of original environment/Python search path to restore
        self.orig_sys_path = sys.path[:]

        self.orig_paths = {}
        for path in ['buildpath', 'installpath', 'sourcepath']:
            self.orig_paths[path] = os.environ.get('EASYBUILD_%s' % path.upper(), None)

        testdir = os.path.dirname(os.path.abspath(__file__))

        self.test_sourcepath = os.path.join(testdir, 'sandbox', 'sources')
        os.environ['EASYBUILD_SOURCEPATH'] = self.test_sourcepath
        self.test_buildpath = tempfile.mkdtemp()
        os.environ['EASYBUILD_BUILDPATH'] = self.test_buildpath
        self.test_installpath = tempfile.mkdtemp()
        os.environ['EASYBUILD_INSTALLPATH'] = self.test_installpath
        init_config()

        # add test easyblocks to Python search path and (re)import and reload easybuild modules
        import easybuild
        sys.path.append(os.path.join(testdir, 'sandbox'))
        reload(easybuild)
        import easybuild.easyblocks
        reload(easybuild.easyblocks)
        import easybuild.easyblocks.generic
        reload(easybuild.easyblocks.generic)
        reload(easybuild.tools.module_naming_scheme)  # required to run options unit tests stand-alone

        # set MODULEPATH to included test modules
        os.environ['MODULEPATH'] = os.path.join(testdir, 'modules')

    def tearDown(self):
        """Clean up after running testcase."""
        os.remove(self.logfile)
        os.chdir(self.cwd)
        modify_env(os.environ, self.orig_environ)
        tempfile.tempdir = None

        # restore original Python search path
        sys.path = self.orig_sys_path

        for path in [self.test_buildpath, self.test_installpath]:
            try:
                shutil.rmtree(path)
            except OSError, err:
                pass

        for path in ['buildpath', 'installpath', 'sourcepath']:
            if self.orig_paths[path] is not None:
                os.environ['EASYBUILD_%s' % path.upper()] = self.orig_paths[path]
            else:
                if 'EASYBUILD_%s' % path.upper() in os.environ:
                    del os.environ['EASYBUILD_%s' % path.upper()]
        init_config()

    def eb_main(self, args, do_build=False, return_error=False, logfile=None, verbose=False, raise_error=False):
        """Helper method to call EasyBuild main function."""
        # clear instance of BuildOptions and ConfigurationVariables to ensure configuration is reinitialized
        config.ConfigurationVariables.__metaclass__._instances.pop(config.ConfigurationVariables, None)
        config.BuildOptions.__metaclass__._instances.pop(config.BuildOptions, None)
        myerr = False
        if logfile is None:
            logfile = self.logfile
        try:
            main((args, logfile, do_build))
        except SystemExit:
            pass
        except Exception, err:
            myerr = err
            if verbose:
                print "err: %s" % err

        os.chdir(self.cwd)

        # make sure config is reinitialized
        init_config()

        if myerr and raise_error:
            raise myerr

        if return_error:
            return read_file(self.logfile), myerr
        else:
            return read_file(self.logfile)


def init_config(args=None, build_options=None):
    """(re)initialize configuration"""

    # clean up any instances of BuildOptions and ConfigurationVariables before reinitializing configuration
    config.ConfigurationVariables.__metaclass__._instances.pop(config.ConfigurationVariables, None)
    config.BuildOptions.__metaclass__._instances.pop(config.BuildOptions, None)

    # initialize configuration so config.get_modules_tool function works
    eb_go = eboptions.parse_options(args=args)
    config.init(eb_go.options, eb_go.get_options_by_section('config'))

    # initialize build options
    if build_options is None:
        build_options = {
            'valid_module_classes': module_classes(),
            'valid_stops': [x[0] for x in EasyBlock.get_steps()],
        }
    config.init_build_options(build_options)

    return eb_go.options

def find_full_path(base_path, trim=(lambda x: x)):
    """
    Determine full path for given base path by looking in sys.path and PYTHONPATH.
    trim: a function that takes a path and returns a trimmed version of that path
    """

    full_path = None

    pythonpath = os.getenv('PYTHONPATH')
    if pythonpath:
        pythonpath = pythonpath.split(':')
    else:
        pythonpath = []
    for path in sys.path + pythonpath:
        tmp_path = os.path.join(trim(path), base_path)
        if os.path.exists(tmp_path):
            full_path = tmp_path
            break

    return full_path
