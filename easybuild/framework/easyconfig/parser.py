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
This describes the easyconfig parser

The parser is format version aware

:author: Stijn De Weirdt (Ghent University)
"""
import os
import re
from vsc.utils import fancylogger

from easybuild.framework.easyconfig.format.format import FORMAT_DEFAULT_VERSION
from easybuild.framework.easyconfig.format.format import get_format_version, get_format_version_classes
from easybuild.framework.easyconfig.format.yeb import FormatYeb, is_yeb_format
from easybuild.framework.easyconfig.types import PARAMETER_TYPES, check_type_of_param_value
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
    :param rawtxt: contents of the easyconfig file
    :param params: list of parameter names to fetch values for
    """
    param_values = []
    for param in params:
        regex = re.compile(r"^\s*%s\s*(=|: )\s*(?P<param>\S.*?)\s*(#.*)?$" % param, re.M)
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

    def __init__(self, filename=None, format_version=None, rawcontent=None,
                 auto_convert_value_types=True):
        """
        Initialise the EasyConfigParser class
        :param filename: path to easyconfig file to parse (superseded by rawcontent, if specified)
        :param format_version: version of easyconfig file format, used to determine how to parse supplied easyconfig
        :param rawcontent: raw content of easyconfig file to parse (preferred over easyconfig file supplied via filename)
        :param auto_convert_value_types: indicates whether types of easyconfig values should be automatically converted
                                         in case they are wrong
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.rawcontent = None  # the actual unparsed content

        self.auto_convert = auto_convert_value_types

        self.get_fn = None  # read method and args
        self.set_fn = None  # write method and args

        self.format_version = format_version
        self._formatter = None
        if rawcontent is not None:
            self.rawcontent = rawcontent
            self._set_formatter(filename)
        elif filename is not None:
            self._check_filename(filename)
            self.process()
        else:
            raise EasyBuildError("Neither filename nor rawcontent provided to EasyConfigParser")

        self._formatter.extract_comments(self.rawcontent)

    def process(self, filename=None):
        """Create an instance"""
        self._read(filename=filename)
        self._set_formatter(filename)

    def check_values_types(self, cfg):
        """
        Check types of easyconfig parameter values.

        :param cfg: dictionary with easyconfig parameter values (result of get_config_dict())
        """
        wrong_type_msgs = []
        for key in cfg:
            type_ok, newval = check_type_of_param_value(key, cfg[key], self.auto_convert)
            if not type_ok:
                wrong_type_msgs.append("value for '%s' should be of type '%s'" % (key, PARAMETER_TYPES[key].__name__))
            elif newval != cfg[key]:
                self.log.warning("Value for '%s' easyconfig parameter was converted from %s (type: %s) to %s (type: %s)",
                                 key, cfg[key], type(cfg[key]), newval, type(newval))
                cfg[key] = newval

        if wrong_type_msgs:
            raise EasyBuildError("Type checking of easyconfig parameter values failed: %s", ', '.join(wrong_type_msgs))
        else:
            self.log.info("Type checking of easyconfig parameter values passed!")

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

    def _set_formatter(self, filename):
        """Obtain instance of the formatter"""
        if self._formatter is None:
            if is_yeb_format(filename, self.rawcontent):
                self._formatter = FormatYeb()
            else:
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

        cfg = self._formatter.get_config_dict()
        self.check_values_types(cfg)

        return cfg

    def dump(self, ecfg, default_values, templ_const, templ_val):
        """Dump easyconfig in format it was parsed from."""
        return self._formatter.dump(ecfg, default_values, templ_const, templ_val)
