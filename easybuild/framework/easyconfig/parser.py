# #
# Copyright 2013-2015 Ghent University
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

import ast
import copy
import os
import re
from vsc.utils import fancylogger

from easybuild.framework.easyconfig.format.format import FORMAT_DEFAULT_VERSION
from easybuild.framework.easyconfig.format.format import get_format_version, get_format_version_classes
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import read_file, write_file


# deprecated easyconfig parameters, and their replacements
DEPRECATED_PARAMETERS = {
    # <old_param>: (<new_param>, <deprecation_version>),
}

# replaced easyconfig parameters, and their replacements
REPLACED_PARAMETERS = {
    'license': 'license_file',
    'makeopts': 'buildopts',
    'premakeopts': 'prebuildopts',
}


_log = fancylogger.getLogger('easyconfig.parser', fname=False)


def fetch_parameters_from_easyconfig(rawtxt, params):
    """
    Fetch (initial) parameter definition from the given easyconfig file contents.
    @param rawtxt: contents of the easyconfig file
    @param params: list of parameter names to fetch values for
    """
    param_values = []
    for param in params:
        regex = re.compile(r"^\s*%s\s*=\s*(?P<param>\S.*?)\s*$" % param, re.M)
        res = regex.search(rawtxt)
        if res:
            param_values.append(res.group('param').strip("'\""))
        else:
            param_values.append(None)
    _log.debug("Obtained parameters value for %s: %s" % (params, param_values))
    return param_values


class EasyConfigParser(object):
    """Read the easyconfig file, return a parsed config object
        Can contain references to multiple version and toolchain/toolchain versions
    """

    def __init__(self, filename=None, format_version=None, rawcontent=None):
        """Initialise the EasyConfigParser class"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.rawcontent = None  # the actual unparsed content

        # comments in the easyconfig file
        self.comments = None

        self.get_fn = None  # read method and args
        self.set_fn = None  # write method and args

        self.format_version = format_version
        self._formatter = None

        if rawcontent is not None:
            self.rawcontent = rawcontent
            self._set_formatter()
        elif filename is not None:
            self._check_filename(filename)
            self.process()
        else:
            raise EasyBuildError("Neither filename nor rawcontent provided to EasyConfigParser")

        self._extract_comments()

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
            raise EasyBuildError('Failed to determine get function for filename %s', fn)
        if self.set_fn is None:
            raise EasyBuildError('Failed to determine set function for filename %s', fn)

    def _read(self, filename=None):
        """Read the easyconfig, dump content in self.rawcontent"""
        if filename is not None:
            self._check_filename(filename)

        try:
            self.rawcontent = self.get_fn[0](*self.get_fn[1])
        except IOError, err:
            raise EasyBuildError('Failed to obtain content with %s: %s', self.get_fn, err)

        if not isinstance(self.rawcontent, basestring):
            msg = 'rawcontent is not basestring: type %s, content %s' % (type(self.rawcontent), self.rawcontent)
            raise EasyBuildError("Unexpected result for raw content: %s", msg)

    def _extract_comments(self):
        """Extract comments from raw content."""
        # Keep track of comments and their location (top of easyconfig, key they are intended for, line they are on
        # discriminate between header comments (top of easyconfig file), single-line comments (at end of line) and other
        # At the moment there is no support for inline comments on lines that don't contain the key value

        self.comments = {
            'above' : {},  # comments for a particular parameter definition
            'header' : [],  # header comment lines
            'inline' : {},  # inline comments
            'iter': {},  # (inline) comments on elements of iterable values
         }

        rawlines = self.rawcontent.split('\n')

        # extract header first
        while rawlines[0].startswith('#'):
            self.comments['header'].append(rawlines.pop(0))

        parsed_ec = None
        while rawlines:
            rawline = rawlines.pop(0)
            if rawline.startswith('#'):
                comment = []
                # comment could be multi-line
                while rawline.startswith('#') or not rawline:
                    # drop empty lines (that don't even include a #)
                    if rawline:
                        comment.append(rawline)
                    rawline = rawlines.pop(0)
                key = rawline.split('=', 1)[0].strip()
                self.comments['above'][key] = comment

            elif '#' in rawline:  # inline comment
                if parsed_ec is None:
                    # obtain parsed easyconfig as a dict, if it wasn't already
                    # note: this currently trigger a reparse
                    parsed_ec = self.get_config_dict()

                comment = rawline.rsplit('#', 1)[1].strip()
                key = None
                comment_value = None
                if '=' in rawline:
                    key = rawline.split('=', 1)[0].strip()
                else:
                    # search for key and index of comment in config dict
                    for k, v in parsed_ec.items():
                        val = re.sub(r',$', r'', rawline.rsplit('#', 1)[0].strip())
                        if not isinstance(v, basestring) and val in str(v):
                            key = k
                            comment_value = val
                            if not self.comments['iter'].get(key):
                                self.comments['iter'][key] = {}

                # check if hash actually indicated a comment; or is part of the value
                if key in parsed_ec:
                    if comment.replace("'", "").replace('"', '') not in str(parsed_ec[key]):
                        if comment_value:
                            self.comments['iter'][key][comment_value] = '  # ' + comment
                        else:
                            self.comments['inline'][key] = '  # ' + comment

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
            raise EasyBuildError('No format classes found matching version %s', self.format_version)
        else:
            raise EasyBuildError("More than one format class found matching version %s in %s",
                                 self.format_version, found_classes)

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
            raise EasyBuildError("Failed to process content with %s: %s", self.set_fn, err)

    def set_specifications(self, specs):
        """Set specifications."""
        self._formatter.set_specifications(specs)

    def get_config_dict(self, validate=True):
        """Return parsed easyconfig as a dict."""
        # allows to bypass the validation step, typically for testing
        if validate:
            self._formatter.validate()
        return self._formatter.get_config_dict()

    def dump(self, ecfg, default_values, templ_const, templ_val):
        """Dump easyconfig in format it was parsed from."""
        return self._formatter.dump(ecfg, default_values, self.comments, templ_const, templ_val)
