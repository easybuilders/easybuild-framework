# #
# Copyright 2013-2017 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
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
YAML easyconfig format (.yeb)
Useful: http://www.yaml.org/spec/1.2/spec.html

:author: Caroline De Brouwer (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""
import os
from vsc.utils import fancylogger

from easybuild.framework.easyconfig.format.format import INDENT_4SPACES, EasyConfigFormat
from easybuild.framework.easyconfig.format.pyheaderconfigobj import build_easyconfig_constants_dict
from easybuild.framework.easyconfig.format.pyheaderconfigobj import build_easyconfig_variables_dict
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import read_file
from easybuild.tools.utilities import only_if_module_is_available, quote_str


_log = fancylogger.getLogger('easyconfig.format.yeb', fname=False)


YAML_DIR = r'%YAML'
YAML_SEP = '---'
YEB_FORMAT_EXTENSION = '.yeb'
YAML_SPECIAL_CHARS = set(":{}[],&*#?|-<>=!%@\\")


def yaml_join(loader, node):
    """
    defines custom YAML join function.
    see http://stackoverflow.com/questions/5484016/how-can-i-do-string-concatenation-or-string-replacement-in-yaml/23212524#23212524
    :param loader: the YAML Loader
    :param node: the YAML (sequence) node
    """
    seq = loader.construct_sequence(node)
    return ''.join([str(i) for i in seq])


try:
    import yaml
    # register the tag handlers
    yaml.add_constructor('!join', yaml_join)
except ImportError:
    pass


class FormatYeb(EasyConfigFormat):
    """Support for easyconfig YAML format"""
    USABLE = True

    def __init__(self, build_specs=None):
        """FormatYeb constructor"""
        super(FormatYeb, self).__init__()
        self.log.experimental("Parsing .yeb easyconfigs")
        self._build_specs = build_specs

    def validate(self):
        """Format validation"""
        _log.info(".yeb format validation isn't implemented (yet) - validation always passes")
        return True

    def get_config_dict(self):
        """
        Return parsed easyconfig as a dictionary, based on specified arguments.
        """
        return self.parsed_yeb

    @only_if_module_is_available('yaml')
    def parse(self, txt):
        """
        Process YAML file
        """
        txt = self._inject_constants_dict(txt)
        if self._build_specs:
            self.log.experimental("We have found a yeb with build_specs, lets load_all")
            self.parsed_yeb_list = list(yaml.load_all(txt))
            self.parsed_yeb = self._handle_replacement()
        else:
            self.log.experimental("A yeb without build_specs, just load the first document and hope it works")
            self.parsed_yeb = yaml.load(txt)

    def _inject_constants_dict(self, txt):
        """Inject constants so they are resolved when actually parsing the YAML text."""
        constants_dict = build_easyconfig_constants_dict()

        lines = txt.splitlines()

        # extract possible YAML header, for example
        # %YAML 1.2
        # ---
        yaml_header = []
        start_doc_arr = []
        for i, line in enumerate(lines):
            if line.startswith(YAML_DIR):
                if lines[i+1].startswith(YAML_SEP):
                    yaml_header.extend([lines.pop(i), lines.pop(i)])
            if line.startswith(YAML_SEP):
                start_doc_arr.append(i+1)

        injected_constants = ['__CONSTANTS__: ']
        for key, value in constants_dict.items():
            injected_constants.append('%s- &%s %s' % (INDENT_4SPACES, key, quote_str(value)))
        add_len = 0

        for inject_point in start_doc_arr:
            fix_inject_point = inject_point + add_len
            lines[fix_inject_point:fix_inject_point] = injected_constants
            add_len = add_len + len(injected_constants)

        full_txt = '\n'.join(yaml_header + lines)
        self.log.experimental("Full text with constants injected: %s" % full_txt)
        print full_txt
        return full_txt

    def _handle_replacement(self):
        meta_yeb = self.parsed_yeb_list[0]
        root_yeb = self.parsed_yeb_list[1]
        for parsed_yeb in self.parsed_yeb_list[1:]:
            target_yeb = root_yeb
            parsed_add = parsed_yeb.get('add')
            parsed_replace = parsed_yeb.get('replace')
            for key in parsed_yeb.keys():
                target_yeb[key] = parsed_yeb[key]
            if parsed_add:
                for add_key in parsed_add.keys():
                    target_yeb[add_key].append(parsed_yeb['add'][add_key])
            if parsed_replace:
                for rep_key in parsed_replace.keys():
                    target_yeb[rep_key] = parsed_yeb['replace'][rep_key]

            target_toolchain = target_yeb.get('toolchain')

            if self._build_specs == target_toolchain:
                return target_yeb

    def dump(self, ecfg, default_values, templ_const, templ_val):
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
    if isinstance(val, basestring):
        if "'" in val or YAML_SPECIAL_CHARS.intersection(val):
            val = "'%s'" % val.replace("'", "''")

    return val
