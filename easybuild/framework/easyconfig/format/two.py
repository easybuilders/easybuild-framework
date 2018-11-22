# #
# Copyright 2013-2018 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# https://github.com/easybuilders/easybuild
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
This describes the easyconfig format versions 2.x

This is a mix between version 1.0 and configparser-style configuration

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""
import copy
import re

from easybuild.framework.easyconfig.format.pyheaderconfigobj import EasyConfigFormatConfigObj
from easybuild.framework.easyconfig.format.format import EBConfigObj
from easybuild.framework.easyconfig.format.version import EasyVersion, ToolchainVersionOperator, VersionOperator
from easybuild.tools.build_log import EasyBuildError


class FormatTwoZero(EasyConfigFormatConfigObj):
    """
    Support for easyconfig format 2.0
    Simple extension of FormatOneZero with configparser blocks

    Doesn't set version and toolchain/toolchain version like in FormatOneZero;
    referencing 'version' directly in pyheader doesn't work => use templating '%(version)s'

    NOT in 2.0
        - order preservation: need more recent ConfigObj (more recent Python as minimal version)
        - nested sections (need other ConfigParser/ConfigObj, eg INITools)
        - type validation
        - command line generation (--try-X command line options)
    """
    VERSION = EasyVersion('2.0')
    USABLE = True

    PYHEADER_ALLOWED_BUILTINS = ['len', 'False', 'True']
    PYHEADER_MANDATORY = ['name', 'homepage', 'description', 'software_license', 'software_license_urls', 'docurls']
    PYHEADER_BLACKLIST = ['version', 'toolchain']

    NAME_DOCSTRING_REGEX_TEMPLATE = r'^\s*@%s\s*:\s*(?P<name>\S.*?)\s*$'  # non-greedy match in named pattern
    AUTHOR_DOCSTRING_REGEX = re.compile(NAME_DOCSTRING_REGEX_TEMPLATE % 'author', re.M)
    MAINTAINER_DOCSTRING_REGEX = re.compile(NAME_DOCSTRING_REGEX_TEMPLATE % 'maintainer', re.M)

    AUTHOR_REQUIRED = True
    MAINTAINER_REQUIRED = False

    def validate(self):
        """Format validation"""
        self._check_docstring()
        self._validate_pyheader()

    def _check_docstring(self):
        """
        Verify docstring.
        field :author: people who contributed to the easyconfig
        field @maintainer: people who can be contacted in case of problems
        """
        authors = []
        maintainers = []
        for auth_reg in self.AUTHOR_DOCSTRING_REGEX.finditer(self.docstring):
            res = auth_reg.groupdict()
            authors.append(res['name'])

        for maint_reg in self.MAINTAINER_DOCSTRING_REGEX.finditer(self.docstring):
            res = maint_reg.groupdict()
            maintainers.append(res['name'])

        if self.AUTHOR_REQUIRED and not authors:
            raise EasyBuildError("No author in docstring (regex: '%s')", self.AUTHOR_DOCSTRING_REGEX.pattern)

        if self.MAINTAINER_REQUIRED and not maintainers:
            raise EasyBuildError("No maintainer in docstring (regex: '%s')", self.MAINTAINER_DOCSTRING_REGEX.pattern)

    def get_config_dict(self):
        """Return the best matching easyconfig dict"""
        self.log.experimental(self.__class__.__name__)

        # the toolchain name/version should not be specified in the pyheader,
        # but other toolchain options are allowed

        cfg = copy.deepcopy(self.pyheader_localvars)
        self.log.debug("Config dict based on Python header: %s" % cfg)

        co = EBConfigObj(self.configobj)

        version = self.specs.get('version', None)
        tc_spec = self.specs.get('toolchain', {})
        toolchain_name = tc_spec.get('name', None)
        toolchain_version = tc_spec.get('version', None)

        # parse and interpret, dealing with defaults etc
        version, tcname, tcversion = co.get_version_toolchain(version, toolchain_name, toolchain_version)

        # format 2.0 will squash
        self.log.debug('Squashing with version %s and toolchain %s' % (version, (tcname, tcversion)))
        res = co.squash(version, tcname, tcversion)

        cfg.update(res)
        self.log.debug("Config dict after processing applicable easyconfig sections: %s" % cfg)
        # FIXME what about updating dict values/appending to list values?
        # FIXME how do we allow both redefining and updating? = and +=?

        # update config with correct version/toolchain (to avoid using values specified in default section)
        cfg.update({
            'version': version,
            'toolchain': {'name': tcname, 'version': tcversion},
        })

        self.log.debug("Final config dict (including correct version/toolchain): %s" % cfg)
        return cfg

    def extract_comments(self, rawtxt):
        """Extract comments from raw content."""
        # this is fine-ish, it only implies that comments will be lost for format v2 easyconfig files that are dumped
        self.log.warning("Extraction of comments not supported yet for easyconfig format v2")
