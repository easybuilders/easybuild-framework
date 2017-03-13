##
# Copyright 2016-2017 Ghent University
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
Style tests for easyconfig files using pycodestyle.

:author: Ward Poelmans (Ghent University)
"""
import re
import sys
from vsc.utils import fancylogger

from easybuild.framework.easyconfig.default import DEFAULT_CONFIG
from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.utilities import only_if_module_is_available

try:
    import pycodestyle
    from pycodestyle import StyleGuide, register_check, trailing_whitespace
except ImportError:
    try:
        # fallback to importing from 'pep8', which was renamed to pycodestyle in 2016
        import pep8
        from pep8 import StyleGuide, register_check, trailing_whitespace
    except ImportError:
        pass

_log = fancylogger.getLogger('easyconfig.style', fname=False)

EB_CHECK = '_eb_check_'

BLANK_LINE_REGEX = re.compile(r'^\s*$')
COMMENT_REGEX = re.compile(r'^\s*#')
PARAM_DEF_REGEX = re.compile(r"^(?P<key>[a-z_]+)\s*=\s*")


PARAM_GROUPS_HEAD = [
    ((), ('easyblock',)),
    (('name', 'version'), ()),
    (('homepage', 'description'), ()),
    (('toolchain',), ('toolchainopts',)),
    (('source_urls', 'sources'), ('patches', 'checksums')),
]


# Any function starting with _eb_check_ (see EB_CHECK variable) will be
# added to the tests if the test number is added to the select list.
#
# Note: only functions that have a first argument named 'physical_line' or 'logical_line'
# will actually be used!
#
# The test number is definied as WXXX and EXXX (for warnings and errors)
# where XXX is a 3 digit number.
#
# It should be mentioned in the docstring as a single word.
# Read the pycodestyle docs to understand the arguments of these functions:
# https://pycodestyle.readthedocs.io or more specifically:
# https://pycodestyle.readthedocs.io/en/latest/developer.html#contribute


def _check_param_group(params, done_params):
    """
    Check whether the specified group of parameters conforms to the style guide w.r.t. order & grouping of parameters
    """
    result, fail_msgs = None, []

    fail_msgs.extend(_check_param_group_head(params, done_params))

    if fail_msgs:
        result = (0, "W001 %s" % ', '.join(fail_msgs))

    return result


def _check_param_group_head(params, done_params):
    """
    Check whether the specified group of parameters conforms to the style guide w.r.t. order & grouping of parameters,
    for head of easyconfig file
    """
    fail_msgs = []

    for param_group in PARAM_GROUPS_HEAD:
        full_param_group = param_group[0] + param_group[1]
        if any(p in params for p in full_param_group):
            fail_msgs.extend(_check_specific_param_group_isolation_order(param_group[0], param_group[1], params))
            done_params.extend(full_param_group)

    # check whether any unexpected parameter definitions are found in the head of the easyconfig file
    expected_params_head = [p for (pg1, pg2) in PARAM_GROUPS_HEAD for p in pg1 + pg2]
    unexpected = [p for p in params if p not in expected_params_head]
    if unexpected:
        fail_msgs.append("found unexpected parameter definitions in head of easyconfig: %s" % ', '.join(unexpected))

    return fail_msgs


def _check_specific_param_group_isolation_order(required_params, optional_params, params):
    """
    Check whether provided parameters adher to style of specified parameter group w.r.t. isolation, order, ...
    """
    fail_msgs = []

    expected_params = required_params + optional_params
    is_are = (' is', 's are')[len(expected_params) > 1]

    if any(p not in params for p in required_params):
        fail_msgs.append("Not all required parameters found in group: %s" % '.'.join(required_params))

    if sorted(params) != sorted(expected_params):
        fail_msgs.append("%s parameter definition%s not isolated" % ('/'.join(expected_params), is_are))

    if tuple(p for p in params if p in expected_params) != expected_params:
        fail_msgs.append("%s parameter definition%s out of order" % ('/'.join(expected_params), is_are))

    return fail_msgs


def _eb_check_order_grouping_params(physical_line, lines, line_number, total_lines, checker_state):
    """
    W001
    Check order and grouping easyconfig parameter definitions
    The arguments are explained at
    https://pep8.readthedocs.org/en/latest/developer.html#contribute
    """
    result = None

    # apparently this is not the same as physical_line line?!
    line = lines[line_number-1]

    # list of parameters that should to be defined already at this point
    done_params = checker_state.setdefault('eb_done_params', [])

    # list of groups of already defined parameters
    defined_params = checker_state.setdefault('eb_defined_params', [[]])

    # keep track of order parameter definitions via checker state
    param_def = PARAM_DEF_REGEX.search(line)
    if param_def:
        key = param_def.group('key')

        # include key in last group of parameters;
        # only if its a known easyconfig parameter, easyconfigs may include local variables
        if key in DEFAULT_CONFIG:
            defined_params[-1].append(key)

    # if we're at the end of the file, or if the next line is blank, check this group of parameters
    if line_number == total_lines or BLANK_LINE_REGEX.match(lines[line_number]):
        if defined_params[-1]:
            # check whether last group of parameters is in the expected order
            result = _check_param_group(defined_params[-1], done_params)

            # blank line starts a new group of parameters
            defined_params.append([])

    return result


def _eb_check_trailing_whitespace(physical_line, lines, line_number, checker_state):  # pylint:disable=unused-argument
    """
    W299
    Warn about trailing whitespace, except for the description and comments.
    This differs from the standard trailing whitespace check as that
    will warn for any trailing whitespace.
    The arguments are explained at
    https://pycodestyle.readthedocs.io/en/latest/developer.html#contribute
    """
    # apparently this is not the same as physical_line line?!
    line = lines[line_number-1]

    if COMMENT_REGEX.match(line):
        return None

    result = trailing_whitespace(line)
    if result:
        result = (result[0], result[1].replace('W291', 'W299'))

    # keep track of name of last parameter that was defined
    param_def = PARAM_DEF_REGEX.search(line)
    if param_def:
        checker_state['eb_last_key'] = param_def.group('key')

    # if the warning is about the multiline string of description
    # we will not issue a warning
    if checker_state.get('eb_last_key') == 'description':
        result = None

    return result


@only_if_module_is_available(('pycodestyle', 'pep8'))
def check_easyconfigs_style(easyconfigs, verbose=False):
    """
    Check the given list of easyconfigs for style
    :param: easyconfigs list of file paths to easyconfigs
    :param: verbose print our statistics and be verbose about the errors and warning
    :return: the number of warnings and errors
    """
    # importing autopep8 changes some pep8 functions.
    # We reload it to be sure to get the real pep8 functions.
    if 'pycodestyle' in sys.modules:
        reload(pycodestyle)
    else:
        reload(pep8)

    # register the extra checks before using pep8:
    # any function in this module starting with `_eb_check_` will be used.
    cands = globals()
    for check_function in sorted([cands[f] for f in cands if callable(cands[f]) and f.startswith(EB_CHECK)]):
        _log.debug("Adding custom style check %s", check_function)
        register_check(check_function)

    styleguide = StyleGuide(quiet=False, config_file=None)
    options = styleguide.options
    # we deviate from standard pep8 and allow 120 chars
    # on a line: the default of 79 is too narrow.
    options.max_line_length = 120
    # we ignore some tests
    # note that W291 has been replaced by our custom W299
    options.ignore = (
        'W291',  # replaced by W299
    )
    options.verbose = int(verbose)

    result = styleguide.check_files(easyconfigs)

    if verbose:
        result.print_statistics()

    return result.total_errors


def cmdline_easyconfigs_style_check(paths):
    """
    Run easyconfigs style check of each of the specified paths, triggered from 'eb' command line

    :param paths: list of paths to easyconfig files to check
    :return: True when style check passed on all easyconfig files, False otherwise
    """
    print_msg("Running style check on %d easyconfig(s)..." % len(paths), prefix=False)
    style_check_passed = True
    for path in paths:
        if check_easyconfigs_style([path]) == 0:
            res = 'PASS'
        else:
            res = 'FAIL'
            style_check_passed = False
        print_msg('[%s] %s' % (res, path), prefix=False)

    return style_check_passed
