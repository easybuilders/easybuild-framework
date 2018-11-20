#!/usr/bin/env python
##
# Copyright 2016-2018 Ghent University
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


cmd = sys.argv[1]
rpath_filter = sys.argv[2]
rpath_include = sys.argv[3]
args = sys.argv[4:]

# wheter or not to use -Wl to pass options to the linker
if cmd in ['ld', 'ld.gold', 'ld.bfd']:
    flag_prefix = ''
else:
    flag_prefix = '-Wl,'

rpath_filter = rpath_filter.split(',')
if rpath_filter:
    rpath_filter = re.compile('^%s$' % '|'.join(rpath_filter))
else:
    rpath_filter = None

if rpath_include:
    rpath_include = rpath_include.split(',')
else:
    rpath_include = []

version_mode = False
cmd_args, cmd_args_rpath = [], []

# process list of original command line arguments
idx = 0
while idx < len(args):

    arg = args[idx]

    # if command is run in 'version check' mode, make sure we don't include *any* -rpath arguments
    if arg in ['-v', '-V', '--version', '-dumpversion']:
        version_mode = True
        cmd_args.append(arg)

    # FIXME: also consider $LIBRARY_PATH?
    # FIXME: support to hard inject additional library paths?
    # FIXME: support to specify list of path prefixes that should not be RPATH'ed into account?
    # FIXME skip paths in /tmp, build dir, etc.?

    # handle -L flags, inject corresponding -rpath flag
    elif arg.startswith('-L'):
        # take into account that argument to -L may be separated with one or more spaces...
        if arg == '-L':
            # actual library path is next argument when arg='-L'
            idx += 1
            lib_path = args[idx]
        else:
            lib_path = arg[2:]

        if os.path.isabs(lib_path) and (rpath_filter is None or not rpath_filter.match(lib_path)):
            # inject -rpath flag in front for every -L with an absolute path,
            # also retain the -L flag (without reordering!)
            cmd_args_rpath.append(flag_prefix + '-rpath=%s' % lib_path)
            cmd_args.append('-L%s' % lib_path)
        else:
            # don't RPATH in relative paths;
            # it doesn't make much sense, and it can also break the build because it may result in reordering lib paths
            cmd_args.append('-L%s' % lib_path)

    # replace --enable-new-dtags with --disable-new-dtags if it's used;
    # --enable-new-dtags would result in copying rpath to runpath, meaning that $LD_LIBRARY_PATH is taken into account again
    # --enable-new-dtags is not removed but replaced to prevent issues when the linker flag is forwarded from the compiler 
    # to the linker with an extra prefixed flag (either -Xlinker or -Wl,). In that case, the compiler would erroneously pass
    # the next random argument to the linker.
    elif arg == '--enable-new-dtags':
        cmd_args.append('--disable-new-dtags');
    else:
        cmd_args.append(arg)

    idx += 1

# add -rpath flags in front
cmd_args = cmd_args_rpath + cmd_args

cmd_args_rpath = [flag_prefix + '-rpath=%s' % inc for inc in rpath_include]

if not version_mode:
    cmd_args = cmd_args_rpath + [
        # try to make sure that RUNPATH is not used by always injecting --disable-new-dtags
        flag_prefix + '--disable-new-dtags',
    ] + cmd_args

# wrap all arguments into single quotes to avoid further bash expansion
cmd_args = ["'%s'" % arg.replace("'", "''") for arg in cmd_args]

# output: statement to define $CMD_ARGS and $RPATH_ARGS
print("CMD_ARGS=(%s)" % ' '.join(cmd_args))
