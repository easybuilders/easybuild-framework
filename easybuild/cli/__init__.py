# #
# Copyright 2009-2026 Ghent University
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
Click-based command line interface entrypoints that wraps the old optparse-based CLI.
The actual argument parsing is still done by optparse, here we just offer the other features of click:
- automatic shell autocompletion for different shells
- better help/error messages (requires also rich_click)

Authors:

* Davide Grassano (CECAM)
"""
from easybuild.main import main_with_hooks
from easybuild.tools.version import this_is_easybuild

try:
    import click as original_click
except ImportError:
    raise ImportError(
        "`EB_CLI_CLICK` was set to use the `click`-based CLI but click cannot be found. "
        "Please install click to use the new CLI or unset `EB_CLI_CLICK` (or different from '1') to use the old CLI."
    )
else:
    try:
        import rich_click as click
    except ImportError:
        import click

    try:
        from rich.traceback import install
    except ImportError:
        pass
    else:
        install(suppress=[
            click, original_click
        ])

    from .options import EasyBuildCliOption, EasyconfigParam

    @click.command()
    @EasyBuildCliOption.apply_options
    @click.argument('other_args', nargs=-1, type=EasyconfigParam(), required=False)
    @click.version_option(version=this_is_easybuild(), message='%(version)s')
    def eb(other_args):
        """EasyBuild command line interface."""
        # Really no need to re-build the arguments if we support the exact same syntax we can just let them pass
        # through to optparse
        main_with_hooks()
