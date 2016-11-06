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


def det_rpath_args(cmd, args):
    """Determine -rpath command line arguments to pass based on list of command line arguments."""

    # determine set of library paths to RPATH in
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


cmd = sys.argv[1]
args = sys.argv[2:]

# option to specify flags to linker
flag_prefix = ''
if cmd not in ['ld', 'ld.gold']:
    flag_prefix = '-Wl,'

version_mode = False
cmd_args = []

# process list of original command line arguments
idx = 0
while idx < len(args):

    arg = args[idx]

    # if command is run in 'version check' mode, make sure we don't include *any* -rpath arguments
    if arg in ['-v', '-V', '--version', '-dumpversion']:
        version_mode = True
        cmd_args.append(arg)

    # FIXME: filter -L entries from list of arguments?
    # FIXME can/should we actually resolve the path? what if ../../../lib was specified?
    # FIXME skip paths in /tmp?
    # FIXME: also consider $LIBRARY_PATH?
    # FIXME: support to hard inject additional library paths?
    # FIXME: support to specify list of path prefixes that should not be RPATH'ed into account?

    # handle -L flags, inject corresponding -rpath flag
    elif arg.startswith('-L'):
        # take into account that argument to -L may be separated with one or more spaces...
        if arg == '-L':
            # actual library path is next argument when arg='-L'
            idx += 1
            lib_path = args[idx]
        else:
            lib_path = arg[2:]

        cmd_args.extend([
            flag_prefix + '-rpath=%s' % lib_path,
            '-L%s' % lib_path,
        ])

    # filter out --enable-new-dtags if it's used;
    # this would result in copying rpath to runpath, meaning that $LD_LIBRARY_PATH is taken into account again
    elif arg != '--enable-new-dtags':
        cmd_args.append(arg)

    idx += 1

if not version_mode:
    cmd_args.extend([
        # always include '$ORIGIN/../lib' and '$ORIGIN/../lib64'
        # $ORIGIN will be resolved by the loader to be the full path to the 'executable'
        # see also https://linux.die.net/man/8/ld-linux;
        flag_prefix + '-rpath=$ORIGIN/../lib',
        flag_prefix + '-rpath=$ORIGIN/../lib64',
        # try to make sure that RUNPATH is not used by always injecting --disable-new-dtags
        flag_prefix + '--disable-new-dtags',
    ])

# wrap all arguments into single quotes to avoid further bash expansion
cmd_args = ["'%s'" % arg.replace("'", "''") for arg in cmd_args]

# output: statement to define $CMD_ARGS and $RPATH_ARGS
print "CMD_ARGS=(%s)" % ' '.join(cmd_args)
