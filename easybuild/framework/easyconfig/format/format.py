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
from vsc import fancylogger
from vsc.utils.missing import get_subclasses

from easybuild.framework.easyconfig.format.version import EasyVersion


# format is mandatory major.minor
FORMAT_VERSION_KEYWORD = "EASYCONFIGFORMAT"
FORMAT_VERSION_TEMPLATE = "%(major)s.%(minor)s"
FORMAT_VERSION_HEADER_TEMPLATE = "# %s %s\n" % (FORMAT_VERSION_KEYWORD, FORMAT_VERSION_TEMPLATE)  # must end in newline
FORMAT_VERSION_REGEXP = re.compile(r'^#\s+%s\s*(?P<major>\d+)\.(?P<minor>\d+)\s*$' % FORMAT_VERSION_KEYWORD, re.M)
FORMAT_DEFAULT_VERSION = EasyVersion('1.0')

_log = fancylogger.getLogger('easyconfig.format.format', fname=False)


def get_format_version(txt):
    """Get the easyconfig format version as EasyVersion instance."""
    res = FORMAT_VERSION_REGEXP.search(txt)
    format_version = None
    if res is not None:
        try:
            maj_min = res.groupdict()
            format_version = EasyVersion(FORMAT_VERSION_TEMPLATE % maj_min)
        except (KeyError, TypeError), err:
            _log.error("Failed to get version from match %s: %s" % (res.groups(), err))
    return format_version


class EasyConfigFormat(object):
    """EasyConfigFormat class"""
    VERSION = EasyVersion('0.0')  # dummy EasyVersion instance (shouldn't be None)
    USABLE = False  # disable this class as usable format

    def __init__(self):
        """Initialise the EasyConfigFormat class"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        if not len(self.VERSION) == len(FORMAT_VERSION_TEMPLATE.split('.')):
            self.log.error('Invalid version number %s (incorrect length)' % self.VERSION)

        self.rawtext = None  # text version of the easyconfig
        self.header = None  # easyconfig header (e.g., format version, license, ...)
        self.docstring = None  # easyconfig docstring (e.g., author, maintainer, ...)

    def get_config_dict(self, version=None, toolchain_name=None, toolchain_version=None):
        """Returns a single easyconfig dictionary."""
        raise NotImplementedError

    def validate(self):
        """Verify the easyconfig format"""
        raise NotImplementedError

    def parse(self, txt, **kwargs):
        """Parse the txt according to this format. This is highly version specific"""
        raise NotImplementedError

    def dump(self):
        """Dump easyconfig according to this format. This is higly version specific"""
        raise NotImplementedError


def get_format_version_classes(version=None):
    """Return the (usable) subclasses from EasyConfigFormat that have a matching version."""
    all_classes = get_subclasses(EasyConfigFormat)
    if version is None:
        return all_classes
    else:
        return [x for x in all_classes if x.VERSION == version and x.USABLE]
