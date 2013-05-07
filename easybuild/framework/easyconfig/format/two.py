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
This describes the easyconfig format versions 2.X

This is a mix between version 1 and configparser-style configuration

@author: Stijn De Weirdt (Ghent University)
"""

import operator
import re

from distutils.version import LooseVersion
from easybuild.framework.easyconfig.format.pyheaderconfigobj import EasyConfigFormatConfigObj
from easybuild.tools.toolchain.utilities import search_toolchain
from vsc import fancylogger


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
    """
    VERSION_SEPARATOR = '_'
    VERSION_OPERATOR = {
        '==': operator.eq,
        '>': operator.gt,
        '>=': operator.ge,
        '<': operator.lt,
        '<=': operator.le,
        '!=': operator.ne,
    }

    def __init__(self, configobj=None):
        """
        Initialise.
            @param configobj: ConfigObj instance
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.configobj = None
        self.version_regexp = self._version_operator_regexp()
        self.toolchain_regexp = self._toolchain_operator_regexp()

        if configobj is not None:
            self.set_configobj(configobj)

    def set_configobj(self, configobj):
        """
        Set the configobj
            @param configobj: ConfigObj instance
        """


    def _version_operator_regexp(self, begin_end=True):
        """
        Create the version regular expression with operator support. Support for version indications like
            5_> (anything strict larger then 5)
            @param begin_end: boolean, create a regexp with begin/end match
        """
        ops = []
        for op in self.VERSION_OPERATOR.keys():
            ops.append(re.sub(r'(.)', r'\\\1', op))
        reg_text = r"(?P<version>\S+)(?:%s(?P<oper>%s))?" % (self.VERSION_SEPARATOR, '|'.join(ops))
        if begin_end:
            reg_text = r"^%s$" % reg_text
        version_reg = re.compile(reg_text)
        self.log.debug("version_operator pattern %s (begin_end %s)" % (version_reg, begin_end))
        return version_reg

    def _toolchain_operator_regexp(self):
        """
        Create the regular expression for toolchain support of format
            ^toolchain_version$
        with toolchain one of the supported toolchains and version in version_operator syntax
        """
        _, all_tcs = search_toolchain('')
        tc_names = [x.NAME for x in all_tcs]
        self.log.debug("found toolchain names %s " % (tc_names))

        version_operator = self._version_operator_regexp(begin_end=False).pattern
        toolchains = r'(%s)' % '|'.join(tc_names)
        toolchain_reg = re.compile(r'^(?P<toolchainname>%s)(?:%s(?P<toolchainversion>%s))?$' %
                                   (toolchains, self.VERSION_SEPARATOR, version_operator))

        self.log.debug("toolchain_operator pattern %s " % (toolchain_reg))
        return toolchain_reg

    def _convert_version(self, txt):
        """Convert string to version-like instance that can be compared"""
        try:
            vers = LooseVersion(txt)
        except:
            self.log.raiseException('Failed to convert txt %s to version' % txt)
        self.log.debug('converted txt %s to version %s' % (txt, vers))
        return vers

    def _version_operator_check(self, version=None, oper=None):
        """
        Return function that functions as a check against version and operator
            @param version: string, sortof mandatory
            @param oper: string, default to ==
        No positional args to allow **reg.search(txt).groupdict()
        """
        if version is None:
            version = '0.0.0'
            self.log.debug('_version_operator_check: no version passed, set it to %s' % version)
        if oper is None:
            oper = '=='
            self.log.debug('_version_operator_check: no operator passed, set it to %s' % oper)

        vers = self._convert_version(version)
        if oper in self.VERSION_OPERATOR:
            op = self.VERSION_OPERATOR[oper]
        else:
            self.log.raiseException('Failed to match operator %s to operator function' % oper)

        def check(txt):
            """The check function. txt-version is always the second arg in comparison"""
            testvers = self._convert_version(txt)
            res = op(vers, testvers)
            self.log.debug('Check %s vs %s using operator %s: %s' % (vers, testvers, op, res))
            return res

        return check

    def toolchain_match(self, txt):
        """
        See if txt matches a toolchain_operator
        If so, return dict with tcname and optional version and operator lamdba
        """


class FormatTwoZero(EasyConfigFormatConfigObj):
    """Simple extension of FormatOne with configparser blocks
    Deprecates setting version and toolchain/toolchain version in FormatOne
        - if no version in pyheader, then no references to it directly!
            - either templates or insert it !

    NOT in 2.0
        - order preservation: need more recent ConfigParser
        - nested sections (need other ConfigParser, eg INITools)
        - type validation
        - commandline generation
    """
    VERSION = LooseVersion('2.0')
    USABLE = True
    PYHEADER_ALLOWED_BUILTINS = ['len']

    def check_docstring(self):
        """Verify docstring"""
        # TODO check for @author and/or @maintainer

    def get_config_dict(self, version=None, toolchain_name=None, toolchain_version=None):
        """Return the best matching easyconfig dict"""
        # Do not allow toolchain name and / or version, do allow other toolchain options in pyheader

