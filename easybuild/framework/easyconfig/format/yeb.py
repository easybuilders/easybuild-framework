# #
# Copyright 2013-2016 Ghent University
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

@author: Caroline De Brouwer (Ghent University)
@author: Kenneth Hoste (Ghent University)
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


def yaml_join(loader, node):
    """
    defines custom YAML join function.
    see http://stackoverflow.com/questions/5484016/how-can-i-do-string-concatenation-or-string-replacement-in-yaml/23212524#23212524
    @param loader: the YAML Loader
    @param node: the YAML (sequence) node
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
        return self.parsed_yeb

    @only_if_module_is_available('yaml')
    def parse(self, txt):
        """
        Process YAML file
        """
        txt = self._inject_constants_dict(txt)
        self.parsed_yeb = yaml.load(txt)

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
                if lines[i+1].startswith(YAML_SEP):
                    yaml_header.extend([lines.pop(i), lines.pop(i)])

        injected_constants = ['__CONSTANTS__: ']
        for key, value in constants_dict.items():
            injected_constants.append('%s- &%s %s' % (INDENT_4SPACES, key, quote_str(value)))

        full_txt = '\n'.join(yaml_header + injected_constants + lines)

        return full_txt

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
