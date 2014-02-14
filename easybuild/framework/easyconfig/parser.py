# #
# Copyright 2013-2014 Ghent University
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

from easybuild.framework.easyconfig.format.format import FORMAT_DEFAULT_VERSION
from easybuild.framework.easyconfig.format.format import get_format_version, get_format_version_classes
from easybuild.tools.filetools import read_file, write_file


class EasyConfigParser(object):
    """Read the easyconfig file, return a parsed config object
        Can contain references to multiple version and toolchain/toolchain versions
    """

    def __init__(self, filename=None, format_version=None):
        """Initialise the EasyConfigParser class"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.rawcontent = None  # the actual unparsed content

        self.get_fn = None  # read method and args
        self.set_fn = None  # write method and args

        self.format_version = format_version
        self._formatter = None

        if filename is not None:
            self._check_filename(filename)
            self.process()

    def process(self, filename=None):
        """Create an instance"""
        self._read(filename=filename)
        self._set_formatter()

    def _check_filename(self, fn):
        """Perform sanity check on the filename, and set mechanism to set the content of the file"""
        if os.path.isfile(fn):
            self.get_fn = (read_file, (fn,))
            self.set_fn = (write_file, (fn, self.rawcontent))

        self.log.debug("Process filename %s with get function %s, set function %s" % (fn, self.get_fn, self.set_fn))

        if self.get_fn is None:
            self.log.error('Failed to determine get function for filename %s' % fn)
        if self.set_fn is None:
            self.log.error('Failed to determine set function for filename %s' % fn)

    def _read(self, filename=None):
        """Read the easyconfig, dump content in self.rawcontent"""
        if filename is not None:
            self._check_filename(filename)

        try:
            self.rawcontent = self.get_fn[0](*self.get_fn[1])
        except IOError, err:
            self.log.error('Failed to obtain content with %s: %s' % (self.get_fn, err))

        if not isinstance(self.rawcontent, basestring):
            msg = 'rawcontent is not basestring: type %s, content %s' % (type(self.rawcontent), self.rawcontent)
            self.log.error("Unexpected result for raw content: %s" % msg)

    def _det_format_version(self):
        """Extract the format version from the raw content"""
        if self.format_version is None:
            self.format_version = get_format_version(self.rawcontent)
            if self.format_version is None:
                self.format_version = FORMAT_DEFAULT_VERSION
                self.log.debug('No version found, using default %s' % self.format_version)

    def _get_format_version_class(self):
        """Locate the class matching the version"""
        if self.format_version is None:
            self._det_format_version()
        found_classes = get_format_version_classes(version=self.format_version)
        if len(found_classes) == 1:
            return found_classes[0]
        elif not found_classes:
            self.log.error('No format classes found matching version %s' % self.format_version)
        else:
            msg = 'More than one format class found matching version %s in %s' % (self.format_version, found_classes)
            self.log.error(msg)

    def _set_formatter(self):
        """Obtain instance of the formatter"""
        if self._formatter is None:
            klass = self._get_format_version_class()
            self._formatter = klass()
        self._formatter.parse(self.rawcontent)

    def set_format_text(self):
        """Create the text for the formatter instance"""
        # TODO create the data in self.rawcontent
        raise NotImplementedError

    def write(self, filename=None):
        """Write the easyconfig format instance, using content in self.rawcontent."""
        if filename is not None:
            self._check_filename(filename)

        try:
            self.set_fn[0](*self.set_fn[1])
        except IOError, err:
            self.log.error('Failed to process content with %s: %s' % (self.set_fn, err))

    def set_specifications(self, specs):
        """Set specifications."""
        self._formatter.set_specifications(specs)

    def get_config_dict(self, validate=True):
        """Return parsed easyconfig as a dict."""
        # allows to bypass the validation step, typically for testing
        if validate:
            self._formatter.validate()
        return self._formatter.get_config_dict()
