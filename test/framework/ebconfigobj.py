# #
# Copyright 2014-2016 Ghent University
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
Unit tests for easyconfig/format/format EBConfigObj

@author: Stijn De Weirdt (Ghent University)
"""
import os
import re

from easybuild.framework.easyconfig.format.format import EBConfigObj
from easybuild.framework.easyconfig.format.version import VersionOperator, ToolchainVersionOperator
from easybuild.framework.easyconfig.format.version import OrderedVersionOperators
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.configobj import ConfigObj
from easybuild.tools.toolchain.utilities import search_toolchain
from test.framework.utilities import EnhancedTestCase
from unittest import TestLoader, main

from vsc.utils.fancylogger import setLogLevelDebug, logToScreen


class TestEBConfigObj(EnhancedTestCase):
    """Unit tests for EBConfigObj from format.format module."""

    def setUp(self):
        """Set some convenience attributes"""
        super(TestEBConfigObj, self).setUp()

        _, tcs = search_toolchain('')
        self.tc_names = [x.NAME for x in tcs]
        self.tcmax = min(len(self.tc_names), 3)
        if len(self.tc_names) < self.tcmax:
            self.tcmax = len(self.tc_names)
        self.tc_namesmax = self.tc_names[:self.tcmax]

        self.tc_first = self.tc_names[0]
        self.tc_last = self.tc_names[-1]
        self.tc_lastmax = self.tc_namesmax[-1]

    def test_ebconfigobj_default(self):
        """Tests wrt ebconfigobj default parsing"""
        data = [
            ('versions=1', {'version': '1'}),
            # == is usable
            ('toolchains=%s == 1' % self.tc_first, {'toolchain':{'name': self.tc_first, 'version': '1'}}),
        ]

        for val, res in  data:
            configobj_txt = ['[SUPPORTED]', val]
            co = ConfigObj(configobj_txt)
            cov = EBConfigObj(co)

            self.assertEqual(cov.default, res)

    def test_ebconfigobj_unusable_default(self):
        """Tests wrt ebconfigobj handling of unusable defaults"""
        # TODO implement proper default as per JSC meeting, remove this test
        # these will not raise error forever
        # the defaults will be interpreted with dedicated default_version and default_toochain
        data = [
            # default operator > and/or version 0.0.0 are not usable for default
            ('toolchains=%s' % self.tc_first, {}),
            # > not usable for default
            ('toolchains=%s > 1' % self.tc_first, {}),
        ]

        for val, res in  data:
            configobj_txt = ['[SUPPORTED]', val]
            co = ConfigObj(configobj_txt)
            self.assertErrorRegex(EasyBuildError,
                                  r'First\s+(toolchain|version)\s.*?\scan\'t\s+be\s+used\s+as\s+default',
                                  EBConfigObj, co)

    def test_squash_simple(self):
        """Test toolchain filter"""
        tc_first = {'version': '10', 'name': self.tc_first}
        tc_last = {'version': '100', 'name': self.tc_last}

        tc_tmpl = '%(name)s == %(version)s'

        default_version = '1.0'
        all_versions = [default_version, '0.0', '1.0']
        txt = [
            '[SUPPORTED]',
            'versions = %s' % ', '.join(all_versions),
            'toolchains = %s,%s' % (tc_tmpl % tc_first, tc_tmpl % tc_last),
        ]
        co = ConfigObj(txt)
        cov = EBConfigObj(co)
        found_tcs = [tmptc.as_dict() for tmptc in cov.sections['toolchains']]

        self.assertEqual(found_tcs, [tc_first, tc_last])

        for tc in [tc_first, tc_last]:
            for version in all_versions:
                co = ConfigObj(txt)
                cov = EBConfigObj(co)
                res = cov.squash(version, tc['name'], tc['version'])
                self.assertEqual(res, {})  # very simple

    def test_squash_invalid(self):
        """Try to squash invalid files. Should trigger error"""
        tc_first = {'version': '10', 'name': self.tc_first}
        tc_last = {'version': '100', 'name': self.tc_last}

        tc_tmpl = '%(name)s == %(version)s'

        default_version = '1.0'
        all_wrong_versions = [default_version, '>= 0.0', '< 1.0']

        # all txt should have default version and first toolchain unmodified

        txt_wrong_versions = [
            '[SUPPORTED]',
            'versions = %s' % ', '.join(all_wrong_versions),  # there's a conflict in the versions list
            'toolchains = %s,%s' % (tc_tmpl % tc_first, tc_tmpl % tc_last),
        ]
        txt_conflict_nested_versions = [
            '[SUPPORTED]',
            'versions = %s' % default_version,
            'toolchains = %s,%s' % (tc_tmpl % tc_first, tc_tmpl % tc_last),
            '[> 1]',
            '[[< 2]]',  # although this makes sense, it's considered a conflict
        ]
        for txt in [
            txt_wrong_versions,
            txt_conflict_nested_versions,
            ]:
            co = ConfigObj(txt)
            cov = EBConfigObj(co)
            self.assertErrorRegex(EasyBuildError, r'conflict', cov.squash,
                                  default_version, tc_first['name'], tc_first['version'])

    def test_toolchain_squash_nested(self):
        """Test toolchain filter on nested sections"""
        tc_first = {'version': '10', 'name': self.tc_first}
        tc_last = {'version': '100', 'name': self.tc_last}

        tc_tmpl = '%(name)s == %(version)s'
        tc_section_first = tc_tmpl % tc_first
        tc_section_last = tc_tmpl % tc_last

        txt = [
            '[SUPPORTED]',
            'versions = 1.0, 0.0, 1.1, 1.6, 2.1',
            'toolchains = %s,%s' % (tc_section_first, tc_tmpl % tc_last),
            '[DEFAULT]',
            'y=a',
            '[> 1.0]',
            'y=b',
            'x = 1',
            '[[>= 1.5]]',
            'x = 2',
            'y=c',
            '[[[%s]]]' % tc_section_first,
            'y=z2',
            '[[>= 1.6]]',
            'z=3',
            '[> 2.0]',
            'x = 3',
            'y=d',
            '[%s]' % tc_section_first,
            'y=z1',
        ]

        # tests
        tests = [
            (tc_last, '1.0', {'y':'a'}),
            (tc_last, '1.1', {'y':'b', 'x':'1'}),
            (tc_last, '1.5', {}),  # not a supported version
            (tc_last, '1.6', {'y':'c', 'x':'2', 'z':'3'}),  # nested
            (tc_last, '2.1', {'y':'d', 'x':'3', 'z':'3'}),  # values from most precise versop

            (tc_first, '1.0', {'y':'z1'}),  # toolchain section, not default
            (tc_first, '1.1', {'y':'b', 'x':'1'}),  # the version section precedes the toolchain section
            (tc_first, '1.5', {}),  # not a supported version
            (tc_first, '1.6', {'y':'z2', 'x':'2', 'z':'3'}),  # nested
            (tc_first, '2.1', {'y':'d', 'x':'3', 'z':'3'}),  # values from most precise versop
        ]
        for tc, version, res in tests:
            co = ConfigObj(txt)
            cov = EBConfigObj(co)
            squashed = cov.squash(version, tc['name'], tc['version'])
            self.assertEqual(squashed, res, 'Test for tc %s version %s' % (tc, version))

    def test_nested_version(self):
        """Test nested config"""
        tc = {'version': '10', 'name': self.tc_first}
        default_version = '1.0'
        txt = [
            '[SUPPORTED]',
            'versions = %s, 0.0, 1.1, 1.5, 1.6, 2.0, 3.0' % default_version,
            'toolchains = %(name)s == %(version)s' % tc,  # set tc, don't use it
            '[> 1.0]',
            'versionprefix = stable-',
            '[[>= 1.5]]',
            'versionsuffix = -early',
            '[> 2.0]',
            'versionprefix = production-',
            'versionsuffix = -mature',
        ]

        # version string, attributes without version and toolchain
        data = [
            (None, {}),
            (default_version, {}),
            ('0.0', {}),
            ('1.1', {'versionprefix': 'stable-'}),
            ('1.5', {'versionprefix': 'stable-', 'versionsuffix': '-early'}),
            ('1.6', {'versionprefix': 'stable-', 'versionsuffix': '-early'}),
            ('2.0', {'versionprefix': 'stable-', 'versionsuffix': '-early'}),
            ('3.0', {'versionprefix': 'production-', 'versionsuffix': '-mature'}),
        ]

        for version, res in  data:
            # yes, redo this for each test, even if it's static text
            # some of the data is modified in place
            co = ConfigObj(txt)
            cov = EBConfigObj(co)
            specs = cov.get_specs_for(version=version)

            self.assertEqual(specs, res)

    def test_ebconfigobj(self):
        """Test configobj sort"""
        # the as_dict method is crap
        # tc >= 0.0.0 returns empty as_dict, although the boundary can be used
        # anyway, will go away with proper defaults
        tcfirst = ",".join(['%s == 0.0.0' % self.tc_namesmax[0], '%s > 0.0.0' % self.tc_namesmax[0]])
        configobj_txt = [
            '[SUPPORTED]',
            'toolchains=%s,%s >= 7.8.9' % (tcfirst, ','.join(self.tc_namesmax[1:])),
            'versions=1.2.3,2.3.4,3.4.5',
            '[>= 2.3.4]',
            'foo=bar',
            '[== 3.4.5]',
            'baz=biz',
            '[%s == 5.6.7]' % self.tc_first,
            '[%s > 7.8.9]' % self.tc_lastmax,
        ]

        co = ConfigObj(configobj_txt)
        cov = EBConfigObj(co)

        # default tc is cgoolf -> cgoolf > 0.0.0
        res = cov.get_specs_for(version='2.3.4', tcname=self.tc_first, tcversion='1.0.0')
        self.assertEqual(res, {'foo':'bar'})


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(TestEBConfigObj)


if __name__ == '__main__':
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
