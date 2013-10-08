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

from easybuild.framework.easyconfig.constants import EASYCONFIG_CONSTANTS
from easybuild.framework.easyconfig.format.format import get_format_version, EasyConfigFormat
from easybuild.framework.easyconfig.licenses import EASYCONFIG_LICENSES_DICT
from easybuild.framework.easyconfig.templates import TEMPLATE_CONSTANTS
from easybuild.tools.configobj import ConfigObj
from easybuild.tools.systemtools import get_shared_lib_ext

_log = fancylogger.getLogger('easyconfig.format.pyheaderconfigobj', fname=False)


def build_easyconfig_constants_dict():
    """Make a dictionary with all constants that can be used"""
    # sanity check
    all_consts = [
        (dict([(x[0], x[1]) for x in TEMPLATE_CONSTANTS]), 'TEMPLATE_CONSTANTS'),
        (dict([(x[0], x[1]) for x in EASYCONFIG_CONSTANTS]), 'EASYCONFIG_CONSTANTS'),
        (EASYCONFIG_LICENSES_DICT, 'EASYCONFIG_LICENSES')
        ]
    err = []
    const_dict = {}

    for (csts, name) in all_consts:
        for cst_key, cst_val in csts.items():
            ok = True
            for (other_csts, other_name) in all_consts:
                if name == other_name:
                    continue
                if cst_key in other_csts:
                    err.append('Found name %s from %s also in %s' % (cst_key, name, other_name))
                    ok = False
            if ok:
                const_dict[cst_key] = cst_val

    if len(err) > 0:
        _log.error("EasyConfig constants sanity check failed: %s" % ("\n".join(err)))
    else:
        return const_dict


def build_easyconfig_variables_dict():
    """Make a dictionary with all variables that can be used"""
    vars_dict = {
        "shared_lib_ext": get_shared_lib_ext(),  # FIXME: redeprecate this
        }

    return vars_dict


class EasyConfigFormatConfigObj(EasyConfigFormat):
    """
    It's very very limited, but is already huge improvement.

    4 parts in text file

    - header (^# style)
    - pyheader
     - exec txt, extract doctstring and remainder
    - begin of regular section until EOF
     - feed to ConfigObj
    """

    PYHEADER_ALLOWED_BUILTINS = []  # default no builtins

    def __init__(self, *args, **kwargs):
        """Extend super with some more attributes"""
        self.pyheader_localvars = None
        self.configobj = None

        super(EasyConfigFormatConfigObj, self).__init__(*args, **kwargs)

    def parse(self, txt, strict_section_markers=False):
        """
        Pre-process txt to extract header, docstring and pyheader
        """
        # where is the first section?
        sectionmarker_pattern = ConfigObj._sectionmarker.pattern
        if strict_section_markers:
            # don't allow indentation for section markers
            sectionmarker_pattern = re.sub('^.*?indentation.*$', '', sectionmarker_pattern, flags=re.M)
        regex = re.compile(sectionmarker_pattern, re.VERBOSE | re.M)
        reg = regex.search(txt)
        if reg is None:
            # no section
            self.log.debug("No section found.")
            start_section = None
        else:
            start_section = reg.start()
            self.log.debug('Section starts at idx %s' % start_section)

        self.parse_pre_section(txt[:start_section])
        if start_section is not None:
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
            self.log.error("SyntaxError in easyconfig pyheader %s: %s" % (txt, err))

        self.log.debug("pyheader final global_vars %s" % global_vars)
        self.log.debug("pyheader final local_vars %s" % local_vars)

        if '__doc__' in local_vars:
            self.docstring = local_vars.pop('__doc__')
        else:
            self.log.debug('No docstring found in local_vars')

        self.pyheader_localvars = local_vars

    def pyheader_env(self):
        """Create the global/local environment to use with eval/execfile"""
        local_vars = {}
        global_vars = {}

        # all variables
        global_vars.update(build_easyconfig_variables_dict())
        # all constants
        global_vars.update(build_easyconfig_constants_dict())

        # allowed builtins
        if self.PYHEADER_ALLOWED_BUILTINS is not None:
            current_builtins = globals()['__builtins__']
            builtins = {}
            for name in self.PYHEADER_ALLOWED_BUILTINS:
                if isinstance(current_builtins, dict) and name in current_builtins:
                    # in unittest environment?
                    builtins[name] = current_builtins.get(name)
                elif hasattr(current_builtins, name):
                    builtins[name] = getattr(current_builtins, name)
                else:
                    self.log.warning('No builtin %s found.' % name)
            global_vars['__builtins__'] = builtins

        return global_vars, local_vars

    def parse_section(self, txt):
        """Parse the section block"""
        try:
            cfgobj = ConfigObj(txt.split('\n'))
        except:
            self.log.raiseException('Failed to convert section text %s' % txt)

        self.log.debug("Found ConfigObj instance %s" % cfgobj)

        self.configobj = cfgobj
