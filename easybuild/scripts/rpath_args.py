#!/usr/bin/env python
##
# Copyright 2016-2016 Ghent University
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
##
"""
Utility script used by RPATH wrapper script;
output is statements that define the following environment variables
* $CMD_ARGS: new list of command line arguments to pass
* $RPATH_ARGS: command line option to specify list of paths to RPATH

author: Kenneth Hoste (HPC-UGent)
"""
import os
import re
import sys


def det_cmd_args(args):
    """Determine list of command line arguments to pass based on list of original command line arguments."""

    # filter out --enable-new-dtags if it's used;
    # this would result in copying rpath to runpath, meaning that $LD_LIBRARY_PATH is taken into account again
    args = [a for a in args if a != '--enable-new-dtags']

    # FIXME: filter -L entries from list of arguments?

    # wrap all retained arguments into single quotes to avoid further bash expansion
    args = ["'%s'" % a.replace("'", "''") for a in args]

    return ' '.join(args)


def det_rpath_args(cmd, args):
    """Determine -rpath command line arguments to pass based on list of command line arguments."""

    if any(f in args for f in ['-v', '-V', '--version', '-dumpversion']):
        # command is run in 'version check' mode, make sure we don't include *any* -rpath arguments
        return ''

    # option to specify RPATH paths depends on command used (compiler vs linker)
    flag_prefix = ''
    if cmd not in ['ld', 'ld.gold']:
        flag_prefix = '-Wl,'

    # always include '$ORIGIN/../lib' and '$ORIGIN/../lib64'
    # $ORIGIN will be resolved by the loader to be the full path to the 'executable'
    # see also https://linux.die.net/man/8/ld-linux;
    lib_paths = ['$ORIGIN/../lib', '$ORIGIN/../lib64']

    # determine set of library paths to RPATH in
    # FIXME can/should we actually resolve the path? what if ../../../lib was specified?
    # FIXME skip paths in /tmp?
    # FIXME: also consider $LIBRARY_PATH?
    # FIXME: support to hard inject additional library paths?
    # FIXME: support to specify list of path prefixes that should not be RPATH'ed into account?
    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg.startswith('-L'):
            # take into account that argument to -L may be separated with one or more spaces...
            if arg == '-L':
                # grab the next argument when arg='-L'
                idx += 1
                lib_paths.append(args[idx])
            else:
                lib_paths.append(os.path.realpath(arg[2:]))

        idx += 1

    # try to make sure that RUNPATH is not used by always injecting --disable-new-dtags
    flags = [flag_prefix + '--disable-new-dtags']

    flags.extend(flag_prefix + '-rpath=' + lib_path for lib_path in lib_paths)

    return ' '.join(flags)


cmd = sys.argv[1]
args = sys.argv[2:]

# output: statement to define $CMD_ARGS and $RPATH_ARGS
print "CMD_ARGS=(%s)" % det_cmd_args(args)
print "RPATH_ARGS='%s'" % det_rpath_args(cmd, args)
