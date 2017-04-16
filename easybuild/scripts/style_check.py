#!/usr/bin/env python
##
# Copyright 2016-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
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
##

"""
Script to check code style in easyconfig files

@author: Kenneth Hoste (Ghent University)
"""

import os
import re
import sys
from vsc.utils.generaloption import simple_option

from easybuild.tools.filetools import find_easyconfigs, read_file

#######################################################################################################################
#
# Each check should be implemented as a function, with the following characteristics:
# * its name must start with 'check_'
# * it takes one argument: a list of (path, lines) tuples for easyconfig files
# * it prints a single-line message starting with '* ' and ending with 'OK' or 'FAILED (<reason>)'
# * it returns a boolean value indicating whether the check pass
#
#######################################################################################################################


def _check_by_line(ecs, line_check, ignore_keys=None):
    """Template check performed on a per-line basis."""

    if ignore_keys is None:
        ignore_keys = []

    comment_regex = re.compile('^\s*#', re.M)

    last_key = None
    key_line_regex = re.compile('^(?P<key>[a-z_]+)\s*=\s*', re.M)

    faulty_ecs = []
    for path, lines in ecs:
        faulty_lines = []
        for i, line in enumerate(lines):
            # take keys to ignore into account (if any)
            if ignore_keys:
                res = key_line_regex.match(line)
                if res:
                    last_key = res.group('key')

                if last_key in ignore_keys:
                    continue

            # ignore comment lines
            if comment_regex.match(line):
                continue

            # keep track of line numbers for faulty lines
            if line_check(line):
                faulty_lines.append(i)

        # keep track of easyconfigs with faulty lines
        if faulty_lines:
            faulty_ecs.append(path + ':' + ':'.join([str(l) for l in faulty_lines]))

    if faulty_ecs:
        print "FAILED (%d faulty easyconfigs: %s)" % (len(faulty_ecs), ' '.join(faulty_ecs))
    else:
        print "OK"

    return faulty_ecs == []


def check_no_tabs(ecs):
    """Check whether easyconfig includes tab characters."""

    print "* checking for tab characters...",
    return _check_by_line(ecs, lambda line: '\t' in line)


def check_trailing_whitespace(ecs):
    """Check for trailing whitespace."""

    print "* checking for trailing whitespace...",
    regex = re.compile(r'\s+$')
    return _check_by_line(ecs, lambda line: regex.search(line), ignore_keys=['description'])


#######################################################################################################################


def run_all_checks(ecs):
    """Run all style checks on provided easyconfig files."""
    res = True
    cands = globals()

    print "Running style checks..."
    print ''
    for check_function in sorted([cands[f] for f in cands if callable(cands[f]) and f.startswith('check_')]):
        res = res and check_function(ecs)

    if res:
        print "\nAll style checks passed.\n"
    else:
        print "\nOne or more style checks FAILed.\n"

    return res


def main():
    opts = {
    }
    go = simple_option(go_dict=opts, descr="Script to check code style for EasyBuild")

    path = os.path.join(os.getcwd(), 'easybuild', 'easyconfigs')
    ec_paths = find_easyconfigs(path, ignore_dirs=['.git'])
    ecs = [(p, read_file(p).split('\n')) for p in ec_paths]

    sys.exit((1, 0)[run_all_checks(ecs)])


if __name__ == '__main__':
    main()
