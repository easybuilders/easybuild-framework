"""
This describes the easyconfig parser

The parser is format version aware
"""
import os
import re
from vsc import fancylogger

from easybuild.tools.filetools import read_file, write_file


class EasyConfigParser(object):
    """Read the easyconfig file, return a parsed config object
        Can contain references to multiple version and toolchain/toolchain versions
    """

    # TODO unittest to check that something written by FORMAT_VERSION_TEMPLATE
    #    can be parsed by FORMAT_VERSION_REGEXP
    # format is mandatory major.minor
    FORMAT_VERSION_TEMPLATE = "# EASYCONFIGFORMAT %(major)d.%(minor)d\n"  # should end in newline
    FORMAT_VERSION_REGEXP = re.compile(r'^\s+EASYCONFIGFORMAT\s*(?P<major>\d+)\.(?P<minor>\d+)\s*$', re.M)

    def __init__(self, filename=None):
        """Initialise the EasyConfigParser class"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self._check_filename(filename)

        self.rawcontent = None  # the actual unparsed content

        self.get = None  # write method and args
        self.set = None  # read method and args

    def _check_filename(self, filename):
        """Perform sanity check on the filename, and set mechanism to set the content of the file"""
        if os.path.isfile(filename):
            self.get = (read_file, [filename])
            self.set = (write_file, [filename, self.rawcontent])

        self.log.debug("Process filename %s with set method %s and get method %s" % (filename, self.set, self.get))

    def read(self, filename=None):
        """Read the easyconfig, dump content in self.rawcontent"""
        if filename is not None:
            self._check_filename(filename)

    def get_format_version(self):
        """Extract the format version from the raw content"""
        # TODO implement

    def get_format_instance(self):
        """Return an instance of the formatter"""
        # TODO implement using data in self.rawcontent

    def set_format_text(self):
        """Create the text for the formatter instance"""
        # TODO create the data in self.rawcontent

    def write(self, filename=None):
        """Write the easyconfig format instance, using content in self.rawcontent"""
        if filename is not None:
            self._check_filename(filename)
