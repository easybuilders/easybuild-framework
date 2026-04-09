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
from easybuild.main import main_with_hooks

try:
    import click as original_click
except ImportError:
    def eb(*args, **kwargs):
        """Placeholder function to inform the user that `click` is required."""
        main_with_hooks()
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
    def eb(other_args):
        """EasyBuild command line interface."""
        # Really no need to re-build the arguments if we support the exact same syntax we can just let them pass
        # through to optparse
        main_with_hooks()
