# #
# Copyright 2017-2018 Ghent University
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
Hook support.

:author: Kenneth Hoste (Ghent University)
"""
import difflib
import imp
import os
from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError, print_msg


_log = fancylogger.getLogger('hooks', fname=False)

BUILD_STEP = 'build'
CLEANUP_STEP = 'cleanup'
CONFIGURE_STEP = 'configure'
EXTENSIONS_STEP = 'extensions'
FETCH_STEP = 'fetch'
INSTALL_STEP = 'install'
MODULE_STEP = 'module'
PACKAGE_STEP = 'package'
PATCH_STEP = 'patch'
PERMISSIONS_STEP = 'permissions'
POSTPROC_STEP = 'postproc'
PREPARE_STEP = 'prepare'
READY_STEP = 'ready'
SANITYCHECK_STEP = 'sanitycheck'
SOURCE_STEP = 'source'
TEST_STEP = 'test'
TESTCASES_STEP = 'testcases'

START = 'start'
END = 'end'

PRE_PREF = 'pre_'
POST_PREF = 'post_'
HOOK_SUFF = '_hook'

# list of names for steps in installation procedure (in order of execution)
STEP_NAMES = [FETCH_STEP, READY_STEP, SOURCE_STEP, PATCH_STEP, PREPARE_STEP, CONFIGURE_STEP, BUILD_STEP, TEST_STEP,
              INSTALL_STEP, EXTENSIONS_STEP, POSTPROC_STEP, SANITYCHECK_STEP, CLEANUP_STEP, MODULE_STEP,
              PERMISSIONS_STEP, PACKAGE_STEP, TESTCASES_STEP]

KNOWN_HOOKS = [h + HOOK_SUFF for h in [START] + [p + s for s in STEP_NAMES for p in [PRE_PREF, POST_PREF]] + [END]]


def load_hooks(hooks_path):
    """Load defined hooks (if any)."""
    hooks = {}

    if hooks_path:
        if not os.path.exists(hooks_path):
            raise EasyBuildError("Specified path for hooks implementation does not exist: %s", hooks_path)

        (hooks_filename, hooks_file_ext) = os.path.splitext(os.path.split(hooks_path)[1])
        if hooks_file_ext == '.py':
            _log.info("Importing hooks implementation from %s...", hooks_path)
            try:
                # import module that defines hooks, and collect all functions of which name ends with '_hook'
                imported_hooks = imp.load_source(hooks_filename, hooks_path)
                for attr in dir(imported_hooks):
                    if attr.endswith(HOOK_SUFF):
                        hook = getattr(imported_hooks, attr)
                        if callable(hook):
                            hooks.update({attr: hook})
                        else:
                            _log.debug("Skipping non-callable attribute '%s' when loading hooks", attr)
                _log.info("Found hooks: %s", sorted(hooks.keys()))
            except ImportError as err:
                raise EasyBuildError("Failed to import hooks implementation from %s: %s", hooks_path, err)
        else:
            raise EasyBuildError("Provided path for hooks implementation should be location of a Python file (*.py)")
    else:
        _log.info("No location for hooks implementation provided, no hooks defined")

    verify_hooks(hooks)

    return hooks


def verify_hooks(hooks):
    """Check whether list of obtained hooks only includes known hooks."""
    unknown_hooks = []
    for key in hooks:
        if key not in KNOWN_HOOKS:
            unknown_hooks.append(key)

    if unknown_hooks:
        error_lines = ["Found one or more unknown hooks:"]

        for unknown_hook in unknown_hooks:
            error_lines.append("* %s" % unknown_hook)
            # try to find close match, may be just a typo in the hook name
            close_matching_hooks = difflib.get_close_matches(unknown_hook, KNOWN_HOOKS, 2, 0.8)
            if close_matching_hooks:
                error_lines[-1] += " (did you mean %s?)" % ', or '.join("'%s'" % h for h in close_matching_hooks)

        error_lines.extend(['', "Run 'eb --avail-hooks' to get an overview of known hooks"])

        raise EasyBuildError('\n'.join(error_lines))
    else:
        _log.info("Defined hooks verified, all known hooks: %s", ', '.join(h for h in hooks))


def find_hook(label, hooks, pre_step_hook=False, post_step_hook=False):
    """
    Find hook with specified label.

    :param label: name of hook
    :param hooks: list of defined hooks
    :param pre_step_hook: indicates whether hook to run is a pre-step hook
    :param post_step_hook: indicates whether hook to run is a post-step hook
    """
    res = None

    if pre_step_hook:
        hook_prefix = PRE_PREF
    elif post_step_hook:
        hook_prefix = POST_PREF
    else:
        hook_prefix = ''

    hook_name = hook_prefix + label + HOOK_SUFF

    for key in hooks:
        if key == hook_name:
            _log.info("Found %s hook", hook_name)
            res = hooks[key]
            break

    return res


def run_hook(label, hooks, pre_step_hook=False, post_step_hook=False, args=None):
    """
    Run hook with specified label.

    :param label: name of hook
    :param hooks: list of defined hooks
    :param pre_step_hook: indicates whether hook to run is a pre-step hook
    :param post_step_hook: indicates whether hook to run is a post-step hook
    :param args: arguments to pass to hook function
    """
    hook = find_hook(label, hooks, pre_step_hook=pre_step_hook, post_step_hook=post_step_hook)
    if hook:
        if args is None:
            args = []

        if pre_step_hook:
            label = 'pre-' + label
        elif post_step_hook:
            label = 'post-' + label

        print_msg("Running %s hook..." % label)
        _log.info("Running '%s' hook function (arguments: %s)...", hook.__name__, args)
        hook(*args)
