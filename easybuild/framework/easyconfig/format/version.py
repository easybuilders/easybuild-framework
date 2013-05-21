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

import operator as _operator
import re

from distutils.version import LooseVersion
from easybuild.tools.toolchain.utilities import search_toolchain
from vsc import fancylogger


class EasyVersion(LooseVersion):
    """Exact LooseVersion. No modifications needed (yet)"""
    # TODO: replace all LooseVersion with EasyVersion in eb


class VersionOperator(object):
    """
    Ordered list of versions, ordering according to operator
    Ordering is highest first, is such that version[idx] >= version[idx+1]
    """

    SEPARATOR = '_'
    OPERATOR = {
        '==': _operator.eq,
        '>': _operator.gt,
        '>=': _operator.ge,
        '<': _operator.lt,
        '<=': _operator.le,
        '!=': _operator.ne,
    }

    def __init__(self, txt=None):
        """Initialise.
            @param txt: intialise with txt
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.regexp = self._operator_regexp()

        self.versions = []

        if txt is not None:
            self.add(txt)

    def _operator_regexp(self, begin_end=True):
        """
        Create the version regular expression with operator support. Support for version indications like
            5_> (anything strict larger then 5)
            @param begin_end: boolean, create a regexp with begin/end match
        """
        ops = []
        for op in self.OPERATOR.keys():
            ops.append(re.sub(r'(.)', r'\\\1', op))

        reg_text = r"(?P<version>[^%(sep)s\W](?:\S*[^%(sep)s\W])?)(?:%(sep)s(?P<operator>%(ops)s))?" % {
                        'sep': self.SEPARATOR,
                        'ops': '|'.join(ops),
                        }
        if begin_end:
            reg_text = r"^%s$" % reg_text
        reg = re.compile(reg_text)

        self.log.debug("version_operator pattern %s (begin_end %s)" % (reg, begin_end))
        return reg

    def _convert(self, version):
        """Convert string to EasyVersion instance that can be compared"""
        if version is None:
            version = '0.0.0'
            self.log.debug('_operator_check: no version passed, set it to %s' % version)
        try:
            e_version = EasyVersion(version)
        except:
            self.log.raiseException('Failed to convert txt %s to version' % version)

        self.log.debug('converted txt %s to version %s' % (version, e_version))
        return e_version

    def _operator_check(self, version=None, operator=None):
        """
        Return function that functions as a check against version and operator
            @param version: string, sort-of mandatory
            @param oper: string, default to ==
        No positional args to allow **reg.search(txt).groupdict()
        """
        e_version = self._convert(version)
        if operator is None:
            operator = '=='
            self.log.debug('_operator_check: no operator passed, set it to %s' % operator)

        if operator in self.OPERATOR:
            op = self.OPERATOR[operator]
        else:
            self.log.raiseException('Failed to match operator %s to operator function' % operator)

        def check(txt):
            """The check function. txt-version is always the second arg in comparing"""
            e_testvers = self._convert(txt)
            res = op(e_version, e_testvers)
            self.log.debug('Check %s version %s using operator %s: %s' % (e_version, e_testvers, op, res))
            return res

        return check

    def match(self, txt):
        """
        See if txt matches a version operator
        If so, return dict with version, operator and check
        """
        r = self.regexp.search(txt)
        if not r:
            self.log.error('No version_match for txt %s' % txt)
            return None

        res = r.groupdict()
        res['txt'] = txt
        res['easyversion'] = self._convert(res['version'])
        res['check'] = self._operator_check(**res)
        self.log.debug('version_match for txt %s: %s' % (txt, res))
        return res

    def add(self, txt):
        """
        Add version to ordered list of versions
            Ordering is highest first, is such that version[idx] >= version[idx+1]
            @param txt: text to match
        Build easyconfig with most recent (=most important) first
        """
        version_dict = self.match(txt)
        if version_dict is None:
            msg = 'version %s does not version_match' % txt
            self.log.error(msg)
        else:
            insert_idx = 0
            for idx, v_dict in enumerate(self.versions):
                if self.OPERATOR['<'](version_dict['easyversion'], v_dict['easyversion']):
                    self.log.debug('Found version %s (idx %s) < then new to add %s' %
                                   (v_dict['easyversion'], idx, version_dict['easyversion']))
                    insert_idx = idx
                    break
            self.log.debug('Insert version %s in index %s' % ())
            self.versions.insert(version_dict, insert_idx)


class ToolchainOperator(object):
    """Dict with toolchains and versionoperator instance"""
    SEPARATOR = '_'

    def __init__(self):
        """Initialise"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.regexp = self._operator_regexp()

    def _operator_regexp(self):
        """
        Create the regular expression for toolchain support of format
            ^toolchain_version$
        with toolchain one of the supported toolchains and version in version_operator syntax
        """
        _, all_tcs = search_toolchain('')
        tc_names = [x.NAME for x in all_tcs]
        self.log.debug("found toolchain names %s " % (tc_names))

        vop = VersionOperator()
        vop_pattern = vop._operator_regexp(begin_end=False).pattern
        toolchains = r'(%s)' % '|'.join(tc_names)
        toolchain_reg = re.compile(r'^(?P<toolchainname>%s)(?:%s(?P<toolchainversion>%s))?$' %
                                   (toolchains, self.SEPARATOR, vop_pattern))

        self.log.debug("toolchain_operator pattern %s " % (toolchain_reg))
        return toolchain_reg

    def toolchain_match(self, txt):
        """
        See if txt matches a toolchain_operator
        If so, return dict with tcname and optional version, operator and check
        """
        r = self.toolchain_regexp.search(txt)
        if not r:
            self.log.error('No toolchain_match for txt %s' % txt)
            return None

        res = r.groupdict()
        res['txt'] = txt
        versiontxt = res.get('toolchainversion', None)
        if versiontxt is None:
            self.log.debug('No toolchainversion specified in txt %s (%s)' % (txt, res))
        else:
            vop = VersionOperator()
            res['check'] = vop._operator_check(version=res['version'], oper=res['operator'])
        self.log.debug('toolchain_match for txt %s: %s' % (txt, res))
        return res


class ConfigObjVersion(object):
    """
    ConfigObj version checker
    - first level sections except default
      - check toolchain
      - check version
    - second level
      - version : dependencies

    Given ConfigObj instance, make instance that can check if toolchain/version is allowed,
        return version / toolchain / toolchainversion and dependency

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

        self.configobj = None

        if configobj is not None:
            self.set_configobj(configobj)

    def set_configobj(self, configobj):
        """
        Set the configobj
            @param configobj: ConfigObj instance
        """
        for name, section in configobj.items():
            if name == 'DEFAULT':
                if 'version' in section:
                    self.add_version(section['version'], section=name)
                if 'toolchain' in section:
                    toolchain = self.toolchain_match(section['toolchain'])
                    if toolchain is None:
                        self.log.error('Section %s toolchain %s does not toolchain_match' %
                                       (name, section['toolchain']))
            else:
                toolchain = self.add_toolchain(name, section=name, error=False)
                if toolchain is None:
                    version = self.add_version(name, section=name, error=False)
                    if version is None:
                        self.log.debug('Name %s section %s no version nor toolchain' % (name, section))
