##
# Copyright 2015-2016 Ghent University
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
##
"""
Unit tests for general aspects of the EasyBuild framework

@author: Kenneth hoste (Ghent University)
"""
import os
import re
from test.framework.utilities import EnhancedTestCase
from unittest import TestLoader, main

import vsc

import easybuild.framework
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import read_file
from easybuild.tools.utilities import only_if_module_is_available


class GeneralTest(EnhancedTestCase):
    """Test for general aspects of EasyBuild framework."""

    def test_vsc_location(self):
        """Make sure location of imported vsc module is not the framework itself."""
        # cfr. https://github.com/hpcugent/easybuild-framework/pull/1160
        # easybuild.framework.__file__ provides location to <prefix>/easybuild/framework/__init__.py
        framework_loc = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(easybuild.framework.__file__))))
        # vsc.__file__ provides location to <prefix>/vsc/__init__.py
        vsc_loc = os.path.dirname(os.path.dirname(os.path.abspath(vsc.__file__)))
        # make sure vsc is being imported from outside of framework
        msg = "vsc-base is not provided by EasyBuild framework itself, found location: %s" % vsc_loc
        self.assertFalse(os.path.samefile(framework_loc, vsc_loc), msg)

    def test_error_reporting(self):
        """Make sure error reporting is done correctly (no more log.error, log.exception)."""
        # easybuild.framework.__file__ provides location to <prefix>/easybuild/framework/__init__.py
        easybuild_loc = os.path.dirname(os.path.dirname(os.path.abspath(easybuild.framework.__file__)))

        log_method_regexes = [
            re.compile("log\.error\("),
            re.compile("log\.exception\("),
            re.compile("log\.raiseException\("),
        ]

        for dirpath, _, filenames in os.walk(easybuild_loc):
            for filename in [f for f in filenames if f.endswith('.py')]:
                path = os.path.join(dirpath, filename)
                txt = read_file(path)
                for regex in log_method_regexes:
                    self.assertFalse(regex.search(txt), "No match for '%s' in %s" % (regex.pattern, path))

    def test_only_if_module_is_available(self):
        """Test only_if_module_is_available decorator."""
        @only_if_module_is_available('easybuild')
        def foo():
            pass

        foo()

        @only_if_module_is_available('nosuchmoduleoutthere', pkgname='nosuchpkg')
        def bar():
            pass

        err_pat = "required module 'nosuchmoduleoutthere' is not available.*package nosuchpkg.*pypi/nosuchpkg"
        self.assertErrorRegex(EasyBuildError, err_pat, bar)

        class Foo():
            @only_if_module_is_available('thisdoesnotexist', url='http://example.com')
            def foobar(self):
                pass

        err_pat = r"required module 'thisdoesnotexist' is not available \(available from http://example.com\)"
        self.assertErrorRegex(EasyBuildError, err_pat, Foo().foobar)


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(GeneralTest)

if __name__ == '__main__':
    main()
