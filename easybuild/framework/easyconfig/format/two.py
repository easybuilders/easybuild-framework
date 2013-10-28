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
import re

from easybuild.framework.easyconfig.format.pyheaderconfigobj import EasyConfigFormatConfigObj
from easybuild.framework.easyconfig.format.version import EasyVersion, ConfigObjVersion


class FormatTwoZero(EasyConfigFormatConfigObj):
    """Support for easyconfig format 2.x
    Simple extension of FormatOneZero with configparser blocks

    Doesn't set version and toolchain/toolchain version like in FormatOneZero
        - if no 'version' in pyheader, then referencing it directly in pyheader doesn't work
            - either use templates ('%(version)s'), or include version spec

    NOT in 2.0
        - order preservation: need more recent ConfigParser (more recent Python as minimal version)
        - nested sections (need other ConfigParser/ConfigObj, eg INITools)
        - type validation
        - command line generation (--try-X command line options)
    """
    VERSION = EasyVersion('2.0')
    USABLE = True
    PYHEADER_ALLOWED_BUILTINS = ['len']

    AUTHOR_DOCSTRING_REGEX = re.compile(r'^\s*@author\s*:\s*(?P<author>\S.*?)\s*$', re.M)
    MAINTAINER_DOCSTRING_REGEX = re.compile(r'^\s*@maintainer\s*:\s*(?P<maintainer>\S.*?)\s*$', re.M)

    AUTHOR_REQUIRED = True
    MAINTAINER_REQUIRED = False

    PYHEADER_WHITELIST = ['name', 'homepage', 'description', 'license', 'docurl', ]
    PYHEADER_BLACKLIST = ['version', 'toolchain']

    def validate(self):
        """Format validation"""
        self._check_docstring()

    def _check_docstring(self):
        """Verify docstring
            field @author: people who contributed to the easyconfig
            field @maintainer: people who can be contacted in case of problems
        """
        authors = []
        maintainers = []
        for auth_reg in self.AUTHOR_DOCSTRING_REGEX.finditer(self.docstring):
            res = auth_reg.groupdict()
            authors.append(res['author'])

        for maint_reg in self.MAINTAINER_DOCSTRING_REGEX.finditer(self.docstring):
            res = maint_reg.groupdict()
            maintainers.append(res['maintainer'])

        if self.AUTHOR_REQUIRED and not authors:
            self.log.error('No author in docstring')

        if self.MAINTAINER_REQUIRED and not maintainers:
            self.log.error('No maintainer in docstring')


    def get_config_dict(self, version=None, toolchain_name=None, toolchain_version=None):
        """Return the best matching easyconfig dict"""
        # the toolchain name/version should not be specified in the pyheader,
        #     but other toolchain options are allowed

        cov = ConfigObjVersion(self.configobj)

        # we only need to find one version / toolchain combo
        # esp the toolchain name should be fixed, so no need to process anything but one toolchain
        if version is None:
            # check for default version
            if 'default_version' in cov.default:
                version = cov.default['default_version']
                self.log.debug('get_config_dict: no version specified, using default version %s' % version)
            else:
                self.log.error('get_config_dict: no version specified, no default version found')

        if toolchain_name is None:
            # check for default version
            if 'default_toolchain' in cov.default:
                toolchain = cov.default['default_toolchain']
                toolchain_name = toolchain.tc_name
                self.log.debug('get_config_dict: no toolchain_name specified, using default %s' % toolchain)
            else:
                self.log.error('get_config_dict: no toolchain_name specified, no default toolchain found')

        # toolchain name is known, remove all others from processed
        cov.set_toolchain(toolchain_name)

        if toolchain_version is None:
            # is there any toolchain with this version?
            # TODO implement
            pass

        pass
