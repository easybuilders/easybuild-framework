# #
# Copyright 2013-2021 Ghent University
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
This describes the easyconfig format version 1.X

This is the original pure python code, to be exec'ed rather then parsed

:author: Stijn De Weirdt (Ghent University)
:author: Kenneth Hoste (Ghent University)
"""
import copy
import os
import pprint
import re
import tempfile

from easybuild.base import fancylogger
from easybuild.framework.easyconfig.format.format import DEPENDENCY_PARAMETERS, EXCLUDED_KEYS_REPLACE_TEMPLATES
from easybuild.framework.easyconfig.format.format import FORMAT_DEFAULT_VERSION, GROUPED_PARAMS, LAST_PARAMS
from easybuild.framework.easyconfig.format.format import SANITY_CHECK_PATHS_DIRS, SANITY_CHECK_PATHS_FILES
from easybuild.framework.easyconfig.format.format import get_format_version
from easybuild.framework.easyconfig.format.pyheaderconfigobj import EasyConfigFormatConfigObj
from easybuild.framework.easyconfig.format.version import EasyVersion
from easybuild.framework.easyconfig.templates import to_template_str
from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.filetools import read_file, write_file
from easybuild.tools.toolchain.toolchain import SYSTEM_TOOLCHAIN_NAME
from easybuild.tools.py2vs3 import string_type
from easybuild.tools.utilities import INDENT_4SPACES, quote_py_str


EB_FORMAT_EXTENSION = '.eb'

# dependency parameters always need to be reformatted, to correctly deal with dumping parsed dependencies
REFORMAT_FORCED_PARAMS = ['sanity_check_paths'] + DEPENDENCY_PARAMETERS
REFORMAT_SKIPPED_PARAMS = ['toolchain', 'toolchainopts']
REFORMAT_LIST_OF_LISTS_OF_TUPLES = ['builddependencies']
REFORMAT_THRESHOLD_LENGTH = 100  # only reformat lines that would be longer than this amount of characters
REFORMAT_ORDERED_ITEM_KEYS = {
    'sanity_check_paths': [SANITY_CHECK_PATHS_FILES, SANITY_CHECK_PATHS_DIRS],
}


_log = fancylogger.getLogger('easyconfig.format.one', fname=False)


def dump_dependency(dep, toolchain, toolchain_hierarchy=None):
    """Dump parsed dependency in tuple format"""
    if not toolchain_hierarchy:
        toolchain_hierarchy = [toolchain]

    if dep['external_module']:
        res = "(%s, EXTERNAL_MODULE)" % quote_py_str(dep['full_mod_name'])
    else:
        # minimal spec: (name, version)
        tup = (dep['name'], dep['version'])
        if all(dep['toolchain'] != subtoolchain for subtoolchain in toolchain_hierarchy):
            if dep[SYSTEM_TOOLCHAIN_NAME]:
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

    def __init__(self, *args, **kwargs):
        """FormatOneZero constructor."""
        super(FormatOneZero, self).__init__(*args, **kwargs)

        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.strict_sanity_check_paths_keys = True

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

        tc_name = cfg.get('toolchain', {}).get('name', None)
        tc_version = cfg.get('toolchain', {}).get('version', None)
        if spec_tc_name is not None and not spec_tc_name == tc_name:
            raise EasyBuildError('Requested toolchain name %s not available, only %s', spec_tc_name, tc_name)
        if spec_tc_version is not None and not spec_tc_version == tc_version:
            raise EasyBuildError('Requested toolchain version %s not available, only %s', spec_tc_version, tc_version)

        # avoid passing anything by reference, so next time get_config_dict is called
        # we can be sure we return a dictionary that correctly reflects the contents of the easyconfig file;
        # we can't use copy.deepcopy() directly because in Python 2 copying the (irrelevant) __builtins__ key fails...
        cfg_copy = {}
        for key in cfg:
            # skip special variables like __builtins__, and imported modules (like 'os')
            if key != '__builtins__' and "'module'" not in str(type(cfg[key])):
                try:
                    cfg_copy[key] = copy.deepcopy(cfg[key])
                except Exception as err:
                    raise EasyBuildError("Failed to copy '%s' easyconfig parameter: %s" % (key, err))
            else:
                self.log.debug("Not copying '%s' variable from parsed easyconfig", key)

        return cfg_copy

    def parse(self, txt):
        """
        Pre-process txt to extract header, docstring and pyheader, with non-indented section markers enforced.
        """
        self.rawcontent = txt
        super(FormatOneZero, self).parse(self.rawcontent, strict_section_markers=True)

    def _reformat_line(self, param_name, param_val, outer=False, addlen=0):
        """
        Construct formatted string representation of iterable parameter (list/tuple/dict), including comments.

        :param param_name: parameter name
        :param param_val: parameter value
        :param outer: reformat for top-level parameter, or not
        :param addlen: # characters to add to line length
        """
        param_strval = str(param_val)
        res = param_strval

        # determine whether line would be too long
        # note: this does not take into account the parameter name + '=', only the value
        line_too_long = len(param_strval) + addlen > REFORMAT_THRESHOLD_LENGTH
        forced = param_name in REFORMAT_FORCED_PARAMS
        list_of_lists_of_tuples_param = param_name in REFORMAT_LIST_OF_LISTS_OF_TUPLES

        if param_name in REFORMAT_SKIPPED_PARAMS:
            self.log.info("Skipping reformatting value for parameter '%s'", param_name)

        elif outer:
            # only reformat outer (iterable) values for (too) long lines (or for select parameters)
            if isinstance(param_val, (list, tuple, dict)) and ((len(param_val) > 1 or line_too_long) or forced):

                item_tmpl = INDENT_4SPACES + '%(item)s,%(inline_comment)s\n'

                start_char, end_char = param_strval[0], param_strval[-1]

                # start with opening character: [, (, {
                res = '%s\n' % start_char

                # add items one-by-one, special care for dict values (order of keys, different format for elements)
                if isinstance(param_val, dict):
                    ordered_item_keys = REFORMAT_ORDERED_ITEM_KEYS.get(param_name, sorted(param_val.keys()))
                    for item_key in ordered_item_keys:
                        if item_key in param_val:
                            item_val = param_val[item_key]
                            item_comments = self._get_item_comments(param_name, item_val)
                        elif param_name == 'sanity_check_paths' and not self.strict_sanity_check_paths_keys:
                            item_val = []
                            item_comments = {}
                            self.log.info("Using default value for '%s' in sanity_check_paths: %s", item_key, item_val)
                        else:
                            raise EasyBuildError("Missing mandatory key '%s' in %s.", item_key, param_name)

                        inline_comment = item_comments.get('inline', '')
                        item_tmpl_dict = {'inline_comment': inline_comment}

                        for comment in item_comments.get('above', []):
                            res += INDENT_4SPACES + comment + '\n'

                        key_pref = quote_py_str(item_key) + ': '
                        addlen = addlen + len(INDENT_4SPACES) + len(key_pref) + len(inline_comment)
                        formatted_item_val = self._reformat_line(param_name, item_val, addlen=addlen)
                        item_tmpl_dict['item'] = key_pref + formatted_item_val

                        res += item_tmpl % item_tmpl_dict

                else:  # list, tuple
                    for item in param_val:
                        item_comments = self._get_item_comments(param_name, item)

                        inline_comment = item_comments.get('inline', '')
                        item_tmpl_dict = {'inline_comment': inline_comment}

                        for comment in item_comments.get('above', []):
                            res += INDENT_4SPACES + comment + '\n'

                        addlen = addlen + len(INDENT_4SPACES) + len(inline_comment)
                        # the tuples are really strings here that are constructed from the dependency dicts
                        # so for a plain list of builddependencies param_val is a list of strings here;
                        # and for iterated builddependencies it is a list of lists of strings
                        is_list_of_lists_of_tuples = isinstance(item, list) and all(isinstance(x, str) for x in item)
                        if list_of_lists_of_tuples_param and is_list_of_lists_of_tuples:
                            itemstr = '[' + (',\n ' + INDENT_4SPACES).join([
                                self._reformat_line(param_name, subitem, outer=True, addlen=addlen)
                                for subitem in item]) + ']'
                        else:
                            itemstr = self._reformat_line(param_name, item, addlen=addlen)
                        item_tmpl_dict['item'] = itemstr

                        res += item_tmpl % item_tmpl_dict

                # take into account possible closing comments
                # see https://github.com/easybuilders/easybuild-framework/issues/3082
                end_comments = self._get_item_comments(param_name, end_char)
                for comment in end_comments.get('above', []):
                    res += INDENT_4SPACES + comment + '\n'

                # end with closing character (']', ')', '}'), incl. possible inline comment
                res += end_char
                if 'inline' in end_comments:
                    res += end_comments['inline']

        else:
            # dependencies are already dumped as strings, so they do not need to be quoted again
            if isinstance(param_val, string_type) and param_name not in DEPENDENCY_PARAMETERS:
                res = quote_py_str(param_val)

        return res

    def _get_item_comments(self, key, val):
        """Get per-item comments for specified parameter name/value."""
        item_comments = {}

        for comment_key, comment_val in self.comments['iterabove'].get(key, {}).items():
            if str(val) in comment_key:
                item_comments['above'] = comment_val

        for comment_key, comment_val in self.comments['iterinline'].get(key, {}).items():
            if str(val) in comment_key:
                item_comments['inline'] = comment_val

        return item_comments

    def _find_param_with_comments(self, key, val, templ_const, templ_val):
        """Find parameter definition and accompanying comments, to include in dumped easyconfig file."""
        res = []

        val = self._reformat_line(key, val, outer=True)

        # templates
        if key not in EXCLUDED_KEYS_REPLACE_TEMPLATES:
            val = to_template_str(key, val, templ_const, templ_val)

        if key in self.comments['inline']:
            res.append("%s = %s%s" % (key, val, self.comments['inline'][key]))
        else:
            if key in self.comments['above']:
                res.extend(self.comments['above'][key])
            res.append("%s = %s" % (key, val))

        return res

    def _find_defined_params(self, ecfg, keyset, default_values, templ_const, templ_val, toolchain_hierarchy=None):
        """
        Determine parameters in the dumped easyconfig file which have a non-default value.
        """
        eclines = []
        printed_keys = []
        for group in keyset:
            printed = False
            for key in group:
                val = ecfg[key]
                if val != default_values[key]:
                    # dependency easyconfig parameters were parsed, so these need special care to 'unparse' them;
                    # take into account that these parameters may be iterative (i.e. a list of lists of parsed deps)
                    if key in DEPENDENCY_PARAMETERS:
                        if key in ecfg.iterate_options:
                            if 'multi_deps' in ecfg:
                                # the way that builddependencies are constructed with multi_deps
                                # we just need to dump the first entry without the dependencies
                                # that are listed in multi_deps
                                valstr = [
                                    dump_dependency(d, ecfg['toolchain'], toolchain_hierarchy=toolchain_hierarchy)
                                    for d in val[0] if d['name'] not in ecfg['multi_deps']
                                ]
                            else:
                                valstr = [
                                    [dump_dependency(d, ecfg['toolchain'], toolchain_hierarchy=toolchain_hierarchy)
                                     for d in dep] for dep in val
                                ]
                        else:
                            valstr = [dump_dependency(d, ecfg['toolchain'], toolchain_hierarchy=toolchain_hierarchy)
                                      for d in val]
                    elif key == 'toolchain':
                        valstr = "{'name': '%(name)s', 'version': '%(version)s'}" % ecfg[key]
                    else:
                        valstr = quote_py_str(ecfg[key])

                    eclines.extend(self._find_param_with_comments(key, valstr, templ_const, templ_val))

                    printed_keys.append(key)
                    printed = True
            if printed:
                eclines.append('')

        return eclines, printed_keys

    def dump(self, ecfg, default_values, templ_const, templ_val, toolchain_hierarchy=None):
        """
        Dump easyconfig in format v1.

        :param ecfg: EasyConfig instance
        :param default_values: default values for easyconfig parameters
        :param templ_const: known template constants
        :param templ_val: known template values
        :param toolchain_hierarchy: hierarchy of toolchains for easyconfig
        """
        # figoure out whether we should be strict about the format of sanity_check_paths;
        # if enhance_sanity_check is set, then both files/dirs keys are not strictly required...
        self.strict_sanity_check_paths_keys = not ecfg['enhance_sanity_check']

        # include header comments first
        dump = self.comments['header'][:]

        # print easyconfig parameters ordered and in groups specified above
        params, printed_keys = self._find_defined_params(ecfg, GROUPED_PARAMS, default_values, templ_const, templ_val,
                                                         toolchain_hierarchy=toolchain_hierarchy)
        dump.extend(params)

        # print other easyconfig parameters at the end
        keys_to_ignore = printed_keys + LAST_PARAMS
        for key in default_values:
            mandatory = ecfg.is_mandatory_param(key)
            non_default_value = ecfg[key] != default_values[key]
            if key not in keys_to_ignore and (mandatory or non_default_value):
                dump.extend(self._find_param_with_comments(key, quote_py_str(ecfg[key]), templ_const, templ_val))
        dump.append('')

        # print last parameters
        params, _ = self._find_defined_params(ecfg, [[k] for k in LAST_PARAMS], default_values, templ_const, templ_val)
        dump.extend(params)

        dump.extend(self.comments['tail'])

        return '\n'.join(dump)

    @property
    def comments(self):
        """
        Return comments (and extract them first if needed).
        """
        if not self._comments:
            self.extract_comments(self.rawcontent)

        return self._comments

    def extract_comments(self, rawtxt):
        """
        Extract comments from raw content.

        Discriminates between comment header, comments above a line (parameter definition), and inline comments.
        Inline comments on items of iterable values are also extracted.
        """
        self._comments = {
            'above': {},  # comments above a parameter definition
            'header': [],  # header comment lines
            'inline': {},  # inline comments
            'iterabove': {},  # comment above elements of iterable values
            'iterinline': {},  # inline comments on elements of iterable values
            'tail': [],  # comment at the end of the easyconfig file
        }

        parsed_ec = self.get_config_dict()

        comment_regex = re.compile(r'^\s*#')
        param_def_regex = re.compile(r'^([a-z_0-9]+)\s*=')
        whitespace_regex = re.compile(r'^\s*$')

        def clean_part(part):
            """Helper function to strip off trailing whitespace + trailing quotes."""
            return part.rstrip().rstrip("'").rstrip('"')

        def split_on_comment_hash(line, param_key):
            """Helper function to split line on first (actual) comment character '#'."""

            # string representation of easyconfig parameter value,
            # used to check if supposed comment isn't actual part of the parameter value
            # (and thus not actually a comment at all)
            param_strval = str(parsed_ec.get(param_key))

            parts = line.split('#')

            # first part (before first #) is definitely not part of comment
            before_comment = parts.pop(0)

            # strip out parts that look like a comment but are actually part of a parameter value
            while parts and ('#' + clean_part(parts[0])) in param_strval:
                before_comment += '#' + parts.pop(0)

            comment = '#'.join(parts)

            return before_comment, comment.strip()

        def grab_more_comment_lines(lines, param_key):
            """Grab more comment lines."""

            comment_lines = []

            while lines and (comment_regex.match(lines[0]) or whitespace_regex.match(lines[0])):
                line = lines.pop(0)
                _, actual_comment = split_on_comment_hash(line, param_key)
                # prefix comment with '#' unless line was empty
                if line.strip():
                    actual_comment = '# ' + actual_comment
                comment_lines.append(actual_comment.strip())

            return comment_lines

        rawlines = rawtxt.split('\n')

        # extract header first (include empty lines too)
        self.comments['header'] = grab_more_comment_lines(rawlines, None)

        last_param_key = None
        while rawlines:
            rawline = rawlines.pop(0)

            # keep track of last parameter definition we have seen,
            # current line may be (the start of) a parameter definition
            res = param_def_regex.match(rawline)
            if res:
                key = res.group(1)
                if key in parsed_ec:
                    last_param_key = key

            if last_param_key:
                before_comment, inline_comment = split_on_comment_hash(rawline, last_param_key)

                # short-circuit to next line in case there are no actual comments on this (non-empty) line
                if before_comment and not inline_comment:
                    continue

            # lines that start with a hash indicate (start of a block of) comment line(s)
            if rawline.startswith('#'):
                comment = [rawline] + grab_more_comment_lines(rawlines, last_param_key)

                if rawlines:
                    # try to pin comment to parameter definition below it
                    # don't consume the line yet though, it may also include inline comments...
                    res = param_def_regex.match(rawlines[0])
                    if res:
                        last_param_key = res.group(1)
                        self.comments['above'][last_param_key] = comment
                    else:
                        # if the comment is not above a parameter definition,
                        # then it must be a comment for an item of an iterable parameter value
                        before_comment, _ = split_on_comment_hash(rawlines[0], last_param_key)
                        comment_key = before_comment.rstrip()
                        self.comments['iterabove'].setdefault(last_param_key, {})[comment_key] = comment
                else:
                    # if there are no more lines, the comment (block) is at the tail
                    self.comments['tail'] = comment

            elif '#' in rawline:
                # if there's a hash character elsewhere in the line (not at the start),
                # there are a couple of possibilities:
                # - inline comment for a parameter definition (at the end of a non-empty line)
                # - indented comment for an item value of an iterable easyconfig parameter (list, dict, ...)
                # - inline comment for an item value of an iterable easyconfig parameter

                before_comment, comment = split_on_comment_hash(rawline, last_param_key)
                comment = ('# ' + comment).rstrip()

                # first check whether current line is an easyconfig parameter definition
                # if so, the comment is an inline comment
                if param_def_regex.match(before_comment):
                    self.comments['inline'][last_param_key] = '  ' + comment

                # if there's only whitespace before the comment,
                # then we have an indented comment, and we need to figure out for what exactly
                elif whitespace_regex.match(before_comment):
                    # first consume possible additional comment lines with same indentation
                    comment = [comment] + grab_more_comment_lines(rawlines, last_param_key)

                    before_comment, inline_comment = split_on_comment_hash(rawlines.pop(0), last_param_key)
                    comment_key = before_comment.rstrip()
                    self.comments['iterabove'].setdefault(last_param_key, {})[comment_key] = comment
                    if inline_comment:
                        inline_comment = ('  # ' + inline_comment).rstrip()
                        self.comments['iterinline'].setdefault(last_param_key, {})[comment_key] = inline_comment
                else:
                    # inline comment for item of iterable value
                    comment_key = before_comment.rstrip()
                    self.comments['iterinline'].setdefault(last_param_key, {})[comment_key] = '  ' + comment

        self.log.debug("Extracted comments:\n%s", pprint.pformat(self.comments, width=120))


def retrieve_blocks_in_spec(spec, only_blocks, silent=False):
    """
    Easyconfigs can contain blocks (headed by a [Title]-line)
    which contain commands specific to that block. Commands in the beginning of the file
    above any block headers are common and shared between each block.
    """
    reg_block = re.compile(r"^\s*\[([\w.-]+)\]\s*$", re.M)
    reg_dep_block = re.compile(r"^\s*block\s*=(\s*.*?)\s*$", re.M)

    spec_fn = os.path.basename(spec)
    txt = read_file(spec)

    # split into blocks using regex
    pieces = reg_block.split(txt)
    # the first block contains common statements
    common = pieces.pop(0)

    # determine version of easyconfig format
    ec_format_version = get_format_version(txt)
    if ec_format_version is None:
        ec_format_version = FORMAT_DEFAULT_VERSION
    _log.debug("retrieve_blocks_in_spec: derived easyconfig format version: %s" % ec_format_version)

    # blocks in easyconfigs are only supported in easyconfig format 1.0
    if pieces and ec_format_version == EasyVersion('1.0'):
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
                if isinstance(dependencies, list):
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
                    if dep not in [b['name'] for b in blocks]:
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
