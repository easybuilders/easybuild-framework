# #
# Copyright 2013-2023 Ghent University
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
YAML easyconfig format (.yeb)
Useful: http://www.yaml.org/spec/1.2/spec.html

Authors:

* Caroline De Brouwer (Ghent University)
* Kenneth Hoste (Ghent University)
"""
import copy
import os
import platform

from easybuild.base import fancylogger
from easybuild.framework.easyconfig.format.format import EasyConfigFormat
from easybuild.framework.easyconfig.format.pyheaderconfigobj import build_easyconfig_constants_dict
from easybuild.tools import LooseVersion
from easybuild.tools.py2vs3 import string_type
from easybuild.tools.utilities import INDENT_4SPACES, only_if_module_is_available, quote_str


_log = fancylogger.getLogger('easyconfig.format.yeb', fname=False)


YAML_DIR = r'%YAML'
YAML_SEP = '---'
YEB_FORMAT_EXTENSION = '.yeb'
YAML_SPECIAL_CHARS = set(":{}[],&*#?|-<>=!%@\\")


def yaml_join(loader, node):
    """
    defines custom YAML join function.
    see http://stackoverflow.com/questions/5484016/
        how-can-i-do-string-concatenation-or-string-replacement-in-yaml/23212524#23212524
    :param loader: the YAML Loader
    :param node: the YAML (sequence) node
    """
    seq = loader.construct_sequence(node)
    return ''.join([str(i) for i in seq])


try:
    import yaml
    # register the tag handlers
    if LooseVersion(platform.python_version()) < LooseVersion(u'2.7'):
        yaml.add_constructor('!join', yaml_join)
    else:
        yaml.add_constructor(u'!join', yaml_join, Loader=yaml.SafeLoader)
except ImportError:
    pass


class FormatYeb(EasyConfigFormat):
    """Support for easyconfig YAML format"""
    USABLE = True

    def __init__(self):
        """FormatYeb constructor"""
        super(FormatYeb, self).__init__()
        self.log.experimental("Parsing .yeb easyconfigs")

    def validate(self):
        """Format validation"""
        _log.info(".yeb format validation isn't implemented (yet) - validation always passes")
        return True

    def get_config_dict(self):
        """
        Return parsed easyconfig as a dictionary, based on specified arguments.
        """
        # avoid passing anything by reference, so next time get_config_dict is called
        # we can be sure we return a dictionary that correctly reflects the contents of the easyconfig file
        return copy.deepcopy(self.parsed_yeb)

    @only_if_module_is_available('yaml')
    def parse(self, txt):
        """
        Process YAML file
        """
        txt = self._inject_constants_dict(txt)
        if LooseVersion(platform.python_version()) < LooseVersion(u'2.7'):
            self.parsed_yeb = yaml.load(txt)
        else:
            self.parsed_yeb = yaml.load(txt, Loader=yaml.SafeLoader)

    def _inject_constants_dict(self, txt):
        """Inject constants so they are resolved when actually parsing the YAML text."""
        constants_dict = build_easyconfig_constants_dict()

        lines = txt.splitlines()

        # extract possible YAML header, for example
        # %YAML 1.2
        # ---
        yaml_header = []
        for i, line in enumerate(lines):
            if line.startswith(YAML_DIR):
                if lines[i + 1].startswith(YAML_SEP):
                    yaml_header.extend([lines.pop(i), lines.pop(i)])

        injected_constants = ['__CONSTANTS__: ']
        for key, value in constants_dict.items():
            injected_constants.append('%s- &%s %s' % (INDENT_4SPACES, key, quote_str(value)))

        full_txt = '\n'.join(yaml_header + injected_constants + lines)

        return full_txt

    def dump(self, ecfg, default_values, templ_const, templ_val, toolchain_hierarchy=None):
        """Dump parsed easyconfig in .yeb format"""
        raise NotImplementedError("Dumping of .yeb easyconfigs not supported yet")

    def extract_comments(self, txt):
        """Extract comments from easyconfig file"""
        self.log.debug("Not extracting comments from .yeb easyconfigs")


def is_yeb_format(filename, rawcontent):
    """
    Determine whether easyconfig is in .yeb format.
    If filename is None, rawcontent will be used to check the format.
    """
    isyeb = False
    if filename:
        isyeb = os.path.splitext(filename)[-1] == YEB_FORMAT_EXTENSION
    else:
        # if one line like 'name: ' is found, this must be YAML format
        for line in rawcontent.splitlines():
            if line.startswith('name: '):
                isyeb = True
    return isyeb


def quote_yaml_special_chars(val):
    """
    Single-quote values that contain special characters, specifically to be used in YAML context (.yeb files)
    Single quotes inside the string are escaped by doubling them.
    (see: http://symfony.com/doc/current/components/yaml/yaml_format.html#strings)
    """
    if isinstance(val, string_type):
        if "'" in val or YAML_SPECIAL_CHARS.intersection(val):
            val = "'%s'" % val.replace("'", "''")

    return val
