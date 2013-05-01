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
The main easyconfig format class

@author: Stijn De Weirdt (Ghent University)
"""
import re

from distutils.version import LooseVersion
from vsc import fancylogger


# format is mandatory major.minor
FORMAT_VERSION_TEMPLATE = "%(major)s.%(minor)s"
FORMAT_VERSION_HEADER_TEMPLATE = "# EASYCONFIGFORMAT %s\n" % FORMAT_VERSION_TEMPLATE  # should end in newline
FORMAT_VERSION_REGEXP = re.compile(r'^#\s+EASYCONFIGFORMAT\s*(?P<major>\d+)\.(?P<minor>\d+)\s*$', re.M)
FORMAT_DEFAULT_VERSION_STRING = '1.0'
FORMAT_DEFAULT_VERSION = LooseVersion(FORMAT_DEFAULT_VERSION_STRING)

_log = fancylogger.getLogger('easyconfig.format.format', fname=False)


def get_format_version(txt):
    """Get the format version as LooseVersion instance."""
    r = FORMAT_VERSION_REGEXP.search(txt)
    format_version = None
    if r is not None:
        try:
            maj_min = r.groupdict()
            format_version = LooseVersion(FORMAT_VERSION_TEMPLATE % maj_min)
        except:
            _log.raiseException('Failed to get version from match %s' % (r.groups(),))
    return format_version


class EasyConfigFormat(object):
    """EasyConfigFormat class"""
    VERSION = LooseVersion('0.0')
    USABLE = False  # Disable this class as usable format

    def __init__(self):
        """Initialise the EasyConfigFormat class"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        if not len(self.VERSION.version) == 2:
            self.log.error('Invalid version number %s' % (self.VERSION))

        self.rawtext = None  # text version of the

        self.header = None  # the header
        self.docstring = None  # the docstring

    def get_config_dict(self, version=None, toolchain_name=None, toolchain_version=None):
        """Returns a single easyconfig dictionary."""
        self.log.error('get_config_dict needs implementation')

    def validate(self):
        """Verify the format"""
        self._check_docstring()

    def _check_docstring(self):
        """Verify docstring placeholder. Do nothing by default."""
        pass

    def parse(self, txt):
        """Parse the txt according to this format. This is highly version specific"""
        self.log.error('parse needs implementation')

    def text(self):
        """Create text according to this format. This is higly version specific"""
        self.log.error('text needs implementation')


