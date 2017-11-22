# #
# Copyright 2017-2017 Ghent University
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
import imp
import os
from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError


_log = fancylogger.getLogger('hooks', fname=False)

# this should be obtained via EasyBlock.get_steps(),
# but we can't import from easybuild.framework.easyblock without introducing a cyclic dependency...
STEP_NAMES = ['fetch', 'ready', 'source', 'patch', 'prepare', 'configure', 'build', 'test', 'install', 'extensions',
              'postproc', 'sanitycheck', 'cleanup', 'module', 'permissions', 'package', 'testcases']
KNOWN_HOOKS = ['%s_hook' % h for h in ['start'] + [p + '_' + s for s in STEP_NAMES for p in ['pre', 'post']] + ['end']]


def load_hooks(hooks_path):
    """Load defined hooks (if any)."""
    hooks = []

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
                    if attr.endswith('_hook'):
                        hook = getattr(imported_hooks, attr)
                        if callable(hook):
                            hooks.append(hook)
                        else:
                            _log.debug("Skipping non-callable attribute '%s' when loading hooks", attr)
                _log.debug("Found hooks: %s", hooks)
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
    for hook in hooks:
        if hook.__name__ not in KNOWN_HOOKS:
            unknown_hooks.append(hook.__name__)

    if unknown_hooks:
        raise EasyBuildError("Found one or more unknown hooks: %s (known hooks: %s)",
                             ', '.join(unknown_hooks), ', '.join(KNOWN_HOOKS))
    else:
        _log.info("Defined hooks verified, all known hooks: %s", ', '.join(h.__name__ for h in hooks))


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
        hook_prefix = 'pre_'
    elif post_step_hook:
        hook_prefix = 'post_'
    else:
        hook_prefix = ''

    hook_name = hook_prefix + label + '_hook'

    for hook in hooks:
        if hook.__name__ == hook_name:
            _log.info("Found %s hook", hook_name)
            res = hook
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

        _log.info("Running %s hook (arguments: %s)...", hook.__name__, args)
        hook(*args)
