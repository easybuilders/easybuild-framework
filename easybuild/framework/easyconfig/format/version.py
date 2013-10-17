# #
# Copyright 2013-2013 Ghent University
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
This describes the easyconfig version class. To be used in easybuild for anythin related to version checking

@author: Stijn De Weirdt (Ghent University)
"""

import operator as op
import re
from distutils.version import LooseVersion
from vsc import fancylogger

from easybuild.tools.toolchain.utilities import search_toolchain


DEFAULT_VERSION_OPERATOR = '=='


class EasyVersion(LooseVersion):
    """Exact LooseVersion. No modifications needed (yet)"""
    # TODO: replace all LooseVersion with EasyVersion in eb, after moving EasyVersion to easybuild/tools?

    def __len__(self):
        """Determine length of this EasyVersion instance."""
        return len(self.version)


class VersionOperator(object):
    """
    VersionOperator class represents a version expression that includes an operator.

    Supports ordered list of versions, ordering according to operator
    Ordering is highest first, such that versions[idx] >= versions[idx+1]
    """

    SEPARATOR = ' '  # single space as (mandatory) separator in section markers, excellent readability
    OPERATOR = {
        '==': op.eq,  # no !=, exceptions to the default should be handled with a dedicated section using ==
        '>': op.gt,
        '>=': op.ge,
        '<': op.lt,
        '<=': op.le,
    }

    def __init__(self, ver_str=None):
        """Initialise.
            @param txt: intialise with txt
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.regex = self.operator_regex()

        self.versions = []

        if ver_str is not None:
            self.add_version_ordered(ver_str)

    def operator_regex(self, begin_end=True):
        """
        Create the version regular expression with operator support.
        This supports version expressions like '> 5' (anything strict larger than 5),
        or '<= 1.2' (anything smaller than or equal to 1.2)
        @param begin_end: boolean, create a regex with begin/end match
        """
        # construct escaped operator symbols, e.g. '\<\='
        ops = []
        for op in self.OPERATOR.keys():
            ops.append(re.sub(r'(.)', r'\\\1', op))

        # regex to parse version expression
        # - operator part at the start is optional
        # - ver_str should start/end with any word character except separator
        # - minimal ver_str length is 1
        reg_text = r"(?:(?P<operator>%(ops)s)%(sep)s)?(?P<ver_str>[^%(sep)s\W](?:\S*[^%(sep)s\W])?)" % {
            'sep': self.SEPARATOR,
            'ops': '|'.join(ops),
        }
        if begin_end:
            reg_text = r"^%s$" % reg_text
        reg = re.compile(reg_text)

        self.log.debug("version_operator pattern '%s' (begin_end: %s)" % (reg.pattern, begin_end))
        return reg

    def _convert(self, ver_str):
        """Convert string to EasyVersion instance that can be compared"""
        if ver_str is None:
            ver_str = '0.0.0'
            self.log.warning('_convert: no version passed, set it to %s' % ver_str)
        try:
            version = EasyVersion(ver_str)
        except (AttributeError, ValueError), err:
            self.log.error('Failed to convert %s to an EasyVersion instance: %s' % (ver_str, err))

        self.log.debug('converted string %s to version %s' % (ver_str, version))
        return version

    def _operator_check(self, ver_str=None, operator=DEFAULT_VERSION_OPERATOR):
        """
        Return function that functions as a check against version and operator
            @param ver_str: version string, sort-of mandatory
            @param operator: operator string
        No positional args to allow **reg.search(txt).groupdict()
        """
        version = self._convert(ver_str)

        if operator in self.OPERATOR:
            op = self.OPERATOR[operator]
        else:
            self.log.error('Failed to match specified operator %s to operator function' % operator)

        def check(test_ver_str):
            """The check function; test version is always the second arg in comparing"""
            test_ver = self._convert(test_ver_str)
            res = op(test_ver, version)
            self.log.debug('Check %s version %s using operator %s: %s' % (version, test_ver, op, res))
            return res

        return check

    def parse_version_str(self, ver_str):
        """
        See if argument contains a version operator
        If so, returns dict with version, operator and check; returns None otherwise
        """
        res = self.regex.search(ver_str)
        if not res:
            self.log.error('No version_match for version expression %s' % ver_str)
            return None

        ver_dict = res.groupdict()
        ver_dict['ver_str'] = ver_str
        ver_dict['check_fn'] = self._operator_check(**ver_dict)
        ver_dict['easyversion'] = self._convert(ver_dict['ver_str'])
        self.log.debug('version_match for version expression %s: %s' % (ver_str, ver_dict))
        return ver_dict

    def add_version_ordered(self, ver_str):
        """
        Add version to ordered list of versions.
        Ordering is highest first, such that versions[idx] >= versions[idx+1]
        @param ver_str: text to match
        Build easyconfig with most recent version (=most relevant) first
        """
        version_dict = self.parse_version_str(ver_str)
        if version_dict is None:
            self.log.error('version string %s does not parse' % ver_str)
        else:
            insert_idx = 0
            for idx, v_dict in enumerate(self.versions):
                if self.OPERATOR['<'](version_dict['easyversion'], v_dict['easyversion']):
                    self.log.debug('Found version %s (idx %s) < then new to add %s' %
                                   (v_dict['easyversion'], idx, version_dict['easyversion']))
                    insert_idx = idx
                    break
            self.log.debug('Insert version %s in index %s' % (version_dict, insert_idx))
            self.versions.insert(insert_idx, version_dict)

class ToolchainOperator(object):
    """Dict with toolchains and versionoperator instance"""
    SEPARATOR = ' '  # single space as (mandatory) separator in section markers, excellent readability

    def __init__(self):
        """Initialise"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.regex = self.operator_regex()

    def operator_regex(self):
        """
        Create the regular expression for toolchain support of format
            ^<toolchain> <ver_expr>$
        with <toolchain> the name of one of the supported toolchains and <ver_expr> in <version>_<operator> syntax
        """
        _, all_tcs = search_toolchain('')
        tc_names = [x.NAME for x in all_tcs]
        self.log.debug("found toolchain names %s " % tc_names)

        vop = VersionOperator()
        vop_pattern = vop.operator_regex(begin_end=False).pattern
        tc_names_regex = r'(%s)' % '|'.join(tc_names)
        tc_regex = re.compile(r'^(?P<tc_name>%s)(?:%s(?P<tc_ver>%s))?$' % (tc_names_regex, self.SEPARATOR, vop_pattern))

        self.log.debug("toolchain_operator pattern %s " % tc_regex.pattern)
        return tc_regex

    def toolchain_parse_version_str(self, tc_str):
        """
        See if argument matches a toolchain_operator
        If so, return dict with toolchain and version (may be None), and optionally operator and check;
        otherwise, return None
        """
        res = self.toolchain_regex.search(tc_str)
        if not res:
            self.log.error('No toolchain match for %s' % tc_str)
            return None

        tc_dict = r.groupdict()
        tc_dict['tc_ver_str'] = tc_str
        tc_ver_str = res.get('tc_ver', None)
        if tc_ver_str is None:
            self.log.debug('No toolchain version specified in %s (%s)' % (tc_ver_str, tc_dict))
        else:
            vop = VersionOperator()
            tc_dict['check_fn'] = vop._operator_check(version=tc_dict['ver_str'], oper=tc_dict['operator'])
        self.log.debug('toolchain expression %s parsed to %s' % (tc_str, tc_dict))
        return tc_dict


class ConfigObjVersion(object):
    """
    ConfigObj version checker
    - first level sections except default
      - check toolchain
      - check version
    - second level
      - version : dependencies

    Given ConfigObj instance, make instance that can check if toolchain/version is allowed,
    return version, toolchain name, toolchain version and dependency

    Mandatory (to fake v1.0 behaviour)? Set this eb wide through other config file?
    [DEFAULT]
    version=version_operator
    toolchain=toolchain_operator
    Optional
    [DEFAULT]
    [[SUPPORTED]]
    toolchains=toolchain_operator,...
    versions=version_operator,...
    [versionX_operator]
    [versionY_operator]
    [toolchainX_operator]
    [toolchainY_operator]
    """

    def __init__(self, configobj=None):
        """
        Initialise.
            @param configobj: ConfigObj instance
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        # FIXME: not used?
        self.configobj = None
        if configobj is not None:
            self.set_configobj(configobj)

    def set_configobj(self, configobj):
        """
        Set the configobj
        @param configobj: ConfigObj instance
        """
        # FIXME: clarify docstring, what's going on here?
        # FIXME: add_version, add_toolchain functions totally missing?
        for name, section in configobj.items():
            if name == 'DEFAULT':
                if 'version' in section:
                    self.add_version(section['version'], section=name)
                if 'toolchain' in section:
                    toolchain = self.toolchain_parse_version_str(section['toolchain'])
                    if toolchain is None:
                        self.log.error('Section %s toolchain %s does not toolchain_match' %
                                       (name, section['toolchain']))
            else:
                toolchain = self.add_toolchain(name, section=name, error=False)
                if toolchain is None:
                    version = self.add_version(name, section=name, error=False)
                    if version is None:
                        self.log.debug('Name %s section %s no version nor toolchain' % (name, section))
