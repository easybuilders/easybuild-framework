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
This describes the easyconfig format version 1.X

This is the original pure python code, to be exec'ed rather then parsed

@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

import os
import re
import tempfile
from vsc.utils import fancylogger

from easybuild.framework.easyconfig.format.format import EXCLUDED_KEYS_REPLACE_TEMPLATES, FORMAT_DEFAULT_VERSION
from easybuild.framework.easyconfig.format.format import GROUPED_PARAMS, LAST_PARAMS, get_format_version
from easybuild.framework.easyconfig.format.pyheaderconfigobj import EasyConfigFormatConfigObj
from easybuild.framework.easyconfig.format.version import EasyVersion
from easybuild.framework.easyconfig.templates import to_template_str
from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.filetools import write_file
from easybuild.tools.utilities import quote_py_str


_log = fancylogger.getLogger('easyconfig.format.one', fname=False)


def dump_dependency(dep, toolchain):
    """Dump parsed dependency in tuple format"""

    if dep['external_module']:
        res = "(%s, EXTERNAL_MODULE)" % quote_py_str(dep['full_mod_name'])
    else:
        # mininal spec: (name, version)
        tup = (dep['name'], dep['version'])
        if dep['toolchain'] != toolchain:
            if dep['dummy']:
                tup += (dep['versionsuffix'], True)
            else:
                tup += (dep['versionsuffix'], (dep['toolchain']['name'], dep['toolchain']['version']))

        elif dep['versionsuffix']:
            tup += (dep['versionsuffix'],)

        res = str(tup)
    return res


class FormatOneZero(EasyConfigFormatConfigObj):
    """Support for easyconfig format 1.x"""
    VERSION = EasyVersion('1.0')
    USABLE = True  # TODO: disable it at some point, too insecure

    PYHEADER_ALLOWED_BUILTINS = None  # allow all
    PYHEADER_MANDATORY = ['version', 'name', 'toolchain', 'homepage', 'description']
    PYHEADER_BLACKLIST = []

    def validate(self):
        """Format validation"""
        # minimal checks
        self._validate_pyheader()

    def get_config_dict(self):
        """
        Return parsed easyconfig as a dictionary, based on specified arguments.
        This is easyconfig format 1.x, so there is only one easyconfig instance available.
        """
        spec_version = self.specs.get('version', None)
        spec_tc = self.specs.get('toolchain', {})
        spec_tc_name = spec_tc.get('name', None)
        spec_tc_version = spec_tc.get('version', None)
        cfg = self.pyheader_localvars
        if spec_version is not None and not spec_version == cfg['version']:
            raise EasyBuildError('Requested version %s not available, only %s', spec_version, cfg['version'])

        tc_name = cfg['toolchain']['name']
        tc_version = cfg['toolchain']['version']
        if spec_tc_name is not None and not spec_tc_name == tc_name:
            raise EasyBuildError('Requested toolchain name %s not available, only %s', spec_tc_name, tc_name)
        if spec_tc_version is not None and not spec_tc_version == tc_version:
            raise EasyBuildError('Requested toolchain version %s not available, only %s', spec_tc_version, tc_version)

        return cfg

    def parse(self, txt):
        """
        Pre-process txt to extract header, docstring and pyheader, with non-indented section markers enforced.
        """
        super(FormatOneZero, self).parse(txt, strict_section_markers=True)

    def _format(self, key, value, item_comments, comments, outer=False):
        """ Returns string version of the value, including comments and newlines in lists, tuples and dicts """
        res = ''

        for k, v in comments['iter'].get(key, {}).items():
            if str(value) in k:
                item_comments[str(value)] = v

        if outer:
            if isinstance(value, list):
                res += '[\n'
                for el in value:
                    res += '    ' + self._format(key, el, item_comments, comments)
                    res += ',' + item_comments.get(str(el), '') + '\n'
                res += ']'
            elif isinstance(value, tuple):
                res += '(\n'
                for el in value:
                    res += '    ' + self._format(key, el, item_comments, comments)
                    res += ',' + item_comments.get(str(el), '') + '\n'
                res += ')'
            elif isinstance(value, dict) and key not in ['toolchain']:  # FIXME
                res += '{\n'
                for k, v in sorted(value.items())[::-1]:  # FIXME
                    res += '    ' + quote_py_str(k) + ': ' + self._format(key, v, item_comments, comments)
                    res += ',' + item_comments.get(str(v), '') + '\n'
                res += '}'

            res = res or str(value)

        else:
            # dependencies are already dumped as strings, so they do not need to be quoted again
            if isinstance(value, basestring) and key not in ['builddependencies', 'dependencies', 'hiddendependencies']:
                res = quote_py_str(value)
            else:
                res = str(value)

        return res

    def _add_key_and_comments(self, key, val, comments, templ_const, templ_val):
        """ Add key, value pair and comments (if there are any) to the dump file (helper method for dump()) """
        res = []
        val = self._format(key, val, {}, comments, outer=True)

        # templates
        if key not in EXCLUDED_KEYS_REPLACE_TEMPLATES:
            new_val = to_template_str(val, templ_const, templ_val)
            if not r'%(' + key in new_val:
                val = new_val

        if key in comments['inline']:
            res.append("%s = %s%s" % (key, val, comments['inline'][key]))
        else:
            if key in comments['above']:
                res.extend(comments['above'][key])
            res.append("%s = %s" % (key, val))

        return res

    def _include_defined_parameters(self, ecfg, keyset, default_values, comments, templ_const, templ_val):
        """
        Internal function to include parameters in the dumped easyconfig file which have a non-default value.
        """
        eclines = []
        printed_keys = []
        for group in keyset:
            printed = False
            for key in group:
                if ecfg[key] != default_values[key]:
                    # dependency easyconfig parameters were parsed, so these need special care to 'unparse' them
                    if key in ['builddependencies', 'dependencies', 'hiddendependencies']:
                        dumped_deps = [dump_dependency(d, ecfg['toolchain']) for d in ecfg[key]]
                        val = dumped_deps
                    else:
                        val = quote_py_str(ecfg[key])

                    eclines.extend(self._add_key_and_comments(key, val, comments, templ_const, templ_val))

                    printed_keys.append(key)
                    printed = True
            if printed:
                eclines.append('')

        return eclines, printed_keys

    def dump(self, ecfg, default_values, comments, templ_const, templ_val):
        """
        Dump easyconfig in format v1.

        @param ecfg: EasyConfig instance
        @param default_values: default values for easyconfig parameters
        @param comments: comments extracted from easyconfig file
        @param templ_const: known template constants
        @param templ_val: known template values
        """
        # include header comments first
        eclines = comments['header'][:]

        # print easyconfig parameters ordered and in groups specified above
        more_eclines, printed_keys = self._include_defined_parameters(ecfg, GROUPED_PARAMS, default_values, comments, templ_const, templ_val)
        eclines.extend(more_eclines)

        # print other easyconfig parameters at the end
        keys_to_ignore = printed_keys + LAST_PARAMS
        for key in default_values:
            if key not in keys_to_ignore and ecfg[key] != default_values[key]:
                eclines.extend(self._add_key_and_comments(key, quote_py_str(ecfg[key]), comments, templ_const, templ_val))
        eclines.append('')

        # print last parameters
        more_eclines, _ = self._include_defined_parameters(ecfg, [[k] for k in LAST_PARAMS], default_values, comments, templ_const, templ_val)
        eclines.extend(more_eclines)

        return '\n'.join(eclines)


def retrieve_blocks_in_spec(spec, only_blocks, silent=False):
    """
    Easyconfigs can contain blocks (headed by a [Title]-line)
    which contain commands specific to that block. Commands in the beginning of the file
    above any block headers are common and shared between each block.
    """
    reg_block = re.compile(r"^\s*\[([\w.-]+)\]\s*$", re.M)
    reg_dep_block = re.compile(r"^\s*block\s*=(\s*.*?)\s*$", re.M)

    spec_fn = os.path.basename(spec)
    try:
        txt = open(spec).read()
    except IOError, err:
        raise EasyBuildError("Failed to read file %s: %s", spec, err)

    # split into blocks using regex
    pieces = reg_block.split(txt)
    # the first block contains common statements
    common = pieces.pop(0)

    # determine version of easyconfig format
    ec_format_version = get_format_version(txt)
    if ec_format_version is None:
        ec_format_version = FORMAT_DEFAULT_VERSION
    _log.debug("retrieve_blocks_in_spec: derived easyconfig format version: %s" % ec_format_version)

    # blocks in easyconfigs are only supported in format versions prior to 2.0
    if pieces and ec_format_version < EasyVersion('2.0'):
        # make a map of blocks
        blocks = []
        while pieces:
            block_name = pieces.pop(0)
            block_contents = pieces.pop(0)

            if block_name in [b['name'] for b in blocks]:
                raise EasyBuildError("Found block %s twice in %s.", block_name, spec)

            block = {'name': block_name, 'contents': block_contents}

            # dependency block
            dep_block = reg_dep_block.search(block_contents)
            if dep_block:
                dependencies = eval(dep_block.group(1))
                if type(dependencies) == list:
                    block['dependencies'] = dependencies
                else:
                    block['dependencies'] = [dependencies]

            blocks.append(block)

        # make a new easyconfig for each block
        # they will be processed in the same order as they are all described in the original file
        specs = []
        for block in blocks:
            name = block['name']
            if only_blocks and not (name in only_blocks):
                print_msg("Skipping block %s-%s" % (spec_fn, name), silent=silent)
                continue

            (fd, block_path) = tempfile.mkstemp(prefix='easybuild-', suffix='%s-%s' % (spec_fn, name))
            os.close(fd)

            txt = common

            if 'dependencies' in block:
                for dep in block['dependencies']:
                    if not dep in [b['name'] for b in blocks]:
                        raise EasyBuildError("Block %s depends on %s, but block was not found.", name, dep)

                    dep = [b for b in blocks if b['name'] == dep][0]
                    txt += "\n# Dependency block %s" % (dep['name'])
                    txt += dep['contents']

            txt += "\n# Main block %s" % name
            txt += block['contents']

            write_file(block_path, txt)

            specs.append(block_path)

        _log.debug("Found %s block(s) in %s" % (len(specs), spec))
        return specs
    else:
        # no blocks, one file
        return [spec]
