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

from easybuild.tools.configobj import ConfigObj
from easybuild.tools.systemtools import get_shared_lib_ext
# TODO move this code here, make no sense to have it in easyconfig module
from easybuild.framework.easyconfig.easyconfig import build_easyconfig_constants_dict

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

    def __init__(self):
        """Initialise the EasyConfigFormat class"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        if not len(self.VERSION.version) == 2:
            self.log.error('Invalid version number %s' % (self.VERSION))

        self.rawtext = None  # text version of the

        self.header = None  # the header
        self.docstring = None  # the docstring
        self.cfg = None  # configuration data
        self.versions = None  # supported versions
        self.toolchains = None  # supported toolchains/toolchain versions

    def validate(self):
        """Verify the format"""
        self._check_docstring()

    def check_docstring(self):
        """Verify docstring placeholder. Do nothing by default."""
        pass

    def parse(self, txt):
        """Parse the txt according to this format. This is highly version specific"""
        self.log.error('parse needs implementation')

    def text(self):
        """Create text according to this format. This is higly version specific"""
        self.log.error('text needs implementation')


class EasyConfigFormatConfigObj(EasyConfigFormat):
    """
    Base class to reuse parts of the ConfigObj

    It's very very limited, but is already huge improvement.

    4 parts in text file

    - header (^# style)
    - pyheader
     - exec txt, extrac doctstring and remainder
    - begin of regular section until EOF
     - fed to ConfigObj
    """

    def parse(self, txt):
        """
        Pre-process txt to extract header, docstring and pyheader
        """
        # where is the first section?
        regex = re.compile(ConfigObj._sectionmarker.pattern, re.VERBOSE | re.M)
        reg = regex.search(txt)
        if reg is None:
            # no section
            self.log.debug("No section found.")
            start_section = -1
        else:
            start_section = reg.start()
            self.log.debug('Section starts at idx %s' % start_section)

        self.parse_pre_section(txt[:start_section])
        self.parse_section(txt[start_section:])

    def parse_pre_section(self, txt):
        """Parse the text block before the section start"""
        header_reg = re.compile(r'^\s*(#.*)?$')

        txt_list = txt.split('\n')

        header_text = []

        while len(txt_list) > 0:
            line = txt_list.pop(0)

            format_version = get_format_version(line)
            if format_version is not None:
                if not format_version == self.VERSION:
                    self.log.error('Invalid version %s for current format class' % (format_version))
                # version is not part of header
                continue

            r = header_reg.search(line)
            if not r:
                # put the line back
                txt_list.insert(0, line)
                break
            header_text.append(line)

        self.parse_header("\n".join(header_text))
        self.parse_pyheader("\n".join(txt_list))

    def parse_header(self, txt):
        """Parse the header, assign to self.header"""
        # do something with the header
        self.log.debug("Found header %s" % txt)
        self.header = txt

    def parse_pyheader(self, txt):
        """Parse the python header, assign to docstring and cfg"""
        global_vars, local_vars = self.pyheader_env()
        self.log.debug("pyheader initial global_vars %s" % global_vars)
        self.log.debug("pyheader initial local_vars %s" % local_vars)

        try:
            exec(txt, global_vars, local_vars)
        except SyntaxError, err:
            self.log.raiseException("SyntaxError in easyconfig pyheader %s: %s" % (txt, err))

        self.log.debug("pyheader final global_vars %s" % global_vars)
        self.log.debug("pyheader final local_vars %s" % local_vars)

    def pyheader_env(self):
        """Create the global/local environment to use with eval/execfile"""
        # TODO this is 1.0 code. move it there.
        global_vars = {"shared_lib_ext": get_shared_lib_ext()}
        const_dict = build_easyconfig_constants_dict()
        global_vars.update(const_dict)
        local_vars = {}

        return global_vars, local_vars

    def parse_section(self, txt):
        """Parse the section block"""
        try:
            cfgobj = ConfigObj(txt.split('\n'))
        except:
            self.log.raiseException('Failed to convert section text %s' % txt)

        self.log.debug("Found ConfigObj instance %s" % cfgobj)
