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
This describes the easyconfig parser

The parser is format version aware

@author: Stijn De Weirdt (Ghent University)
"""
import os

from vsc import fancylogger

from easybuild.framework.easyconfig.format.format import get_format_version, FORMAT_DEFAULT_VERSION
from easybuild.framework.easyconfig.format.locate import get_format_version_classes
from easybuild.tools.filetools import read_file, write_file


class EasyConfigParser(object):
    """Read the easyconfig file, return a parsed config object
        Can contain references to multiple version and toolchain/toolchain versions
    """

    def __init__(self, filename=None):
        """Initialise the EasyConfigParser class"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.rawcontent = None  # the actual unparsed content

        self.get = None  # write method and args
        self.set = None  # read method and args

        self.formatversion = None
        self.format = None

        if filename is not None:
            self._check_filename(filename)
            self.process()

    def process(self):
        """Create an instance"""
        self.read()
        self.get_format_instance()

    def _check_filename(self, filename):
        """Perform sanity check on the filename, and set mechanism to set the content of the file"""
        if os.path.isfile(filename):
            self.get = (read_file, [filename])
            self.set = (write_file, [filename, self.rawcontent])

        self.log.debug("Process filename %s with set method %s and get method %s" %
                       (filename, self.set, self.get))

        if self.set is None:
            self.log.raiseException('Failed to determine set method for filename %s' % filename)
        if self.get is None:
            self.log.raiseException('Failed to determine get method for filename %s' % filename)

    def read(self, filename=None):
        """Read the easyconfig, dump content in self.rawcontent"""
        if filename is not None:
            self._check_filename(filename)

        try:
            self.rawcontent = self.get[0](*self.get[1])
        except:
            self.log.raiseException('Failed to process content with method %s and args %s' %
                                    (self.get[0], self.get[1]))

    def get_format_version(self):
        """Extract the format version from the raw content"""
        self.formatversion = get_format_version(self.rawcontent)
        if self.formatversion is None:
            self.log.debug('No version found, using default %s' % FORMAT_DEFAULT_VERSION)
            self.formatversion = FORMAT_DEFAULT_VERSION

    def get_format_version_class(self):
        """Locate the class matching the version"""
        self.get_format_version()
        found_classes = get_format_version_classes(version=self.formatversion)
        if len(found_classes) == 0:
            self.log.error('No format classes found matching version %s' % (self.formatversion))
        elif len(found_classes) > 1:
            self.log.error('More then one format class found matching version %s: %s' %
                           (self.formatversion, found_classes))
        else:
            return found_classes[0]

    def get_format_instance(self):
        """Return an instance of the formatter"""
        klass = self.get_format_version_class()
        self.format = klass()
        self.format.parse(self.rawcontent)

    def set_format_text(self):
        """Create the text for the formatter instance"""
        # TODO create the data in self.rawcontent

    def write(self, filename=None):
        """Write the easyconfig format instance, using content in self.rawcontent"""
        if filename is not None:
            self._check_filename(filename)

        try:
            self.set[0](*self.set[1])
        except:
            self.log.raiseException('Failed to process content with method %s and args %s' %
                                    (self.set[0], self.set[1]))
