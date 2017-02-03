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
Style tests for easyconfig files using pep8.

:author: Ward Poelmans (Ghent University)
"""
import re
from vsc.utils import fancylogger

from easybuild.tools.build_log import print_msg
from easybuild.tools.utilities import only_if_module_is_available

try:
    import pep8
except ImportError:
    pass

_log = fancylogger.getLogger('easyconfig.style', fname=False)

EB_CHECK = '_eb_check_'


# any function starting with _eb_check_ (see EB_CHECK variable) will be
# added to the tests if the test number is added to the select list.
# The test number is definied as WXXX and EXXX (for warnings and errors)
# where XXX is a 3 digit number.
#
# It should be mentioned in the docstring as a single word.
# Read the pep8 docs to understand the arguments of these functions:
# https://pep8.readthedocs.org or more specifically:
# https://pep8.readthedocs.org/en/latest/developer.html#contribute
def _eb_check_trailing_whitespace(physical_line, lines, line_number, total_lines):  # pylint:disable=unused-argument
    """
    W299
    Warn about trailing whitespace, except for the description and comments.
    This differs from the standard trailing whitespace check as that
    will warn for any trailing whitespace.
    The arguments are explained at
    https://pep8.readthedocs.org/en/latest/developer.html#contribute
    """
    comment_re = re.compile(r'^\s*#')
    if comment_re.match(physical_line):
        return None

    result = pep8.trailing_whitespace(physical_line)
    if result:
        result = (result[0], result[1].replace("W291", "W299"))

    # if the warning is about the multiline string of description
    # we will not issue a warning
    keys_re = re.compile(r"^(?P<key>[a-z_]+)\s*=\s*")

    # starting from the current line and going to the top,
    # check that if the first `key = value` that is found, has
    # key == description, then let the test pass, else return
    # the result of the general pep8 check.
    for line in reversed(lines[:line_number]):
        res = keys_re.match(line)
        if res and res.group("key") == "description":
            result = None
            break

    return result


@only_if_module_is_available('pep8')
def check_easyconfigs_style(easyconfigs, verbose=False):
    """
    Check the given list of easyconfigs for style
    :param: easyconfigs list of file paths to easyconfigs
    :param: verbose print our statistics and be verbose about the errors and warning
    :return: the number of warnings and errors
    """
    # importing autopep8 changes some pep8 functions.
    # We reload it to be sure to get the real pep8 functions.
    reload(pep8)

    # register the extra checks before using pep8:
    # any function in this module starting with `_eb_check_` will be used.
    cands = globals()
    for check_function in sorted([cands[f] for f in cands if callable(cands[f]) and f.startswith(EB_CHECK)]):
        _log.debug("Adding custom style check %s", check_function)
        pep8.register_check(check_function)

    pep8style = pep8.StyleGuide(quiet=False, config_file=None)
    options = pep8style.options
    # we deviate from standard pep8 and allow 120 chars
    # on a line: the default of 79 is too narrow.
    options.max_line_length = 120
    # we ignore some tests
    # note that W291 has be replaced by our custom W299
    options.ignore = (
        'W291',  # replaced by W299
    )
    options.verbose = int(verbose)

    result = pep8style.check_files(easyconfigs)

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
