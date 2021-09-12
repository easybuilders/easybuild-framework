# -*- coding: utf-8 -*-
# #
# Copyright 2021-2021 Ghent University
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
Tools for controlling output to terminal produced by EasyBuild.

:author: Kenneth Hoste (Ghent University)
:author: Jørgen Nordmoen (University of Oslo)
"""
import random

from easybuild.tools.config import build_option

try:
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    HAVE_RICH = True
except ImportError:
    HAVE_RICH = False


class DummyProgress(object):
    """Shim for Rich's Progress class."""

    # __enter__ and __exit__ must be implemented to allow use as context manager
    def __enter__(self, *args, **kwargs):
        pass

    def __exit__(self, *args, **kwargs):
        pass

    # dummy implementations for methods supported by rich.progress.Progress class
    def add_task(self, *args, **kwargs):
        pass

    def update(self, *args, **kwargs):
        pass


def create_progress_bar():
    """
    Create progress bar to display overall progress.

    Returns rich.progress.Progress instance if the Rich Python package is available,
    or a shim DummyProgress instance otherwise.
    """
    if HAVE_RICH and build_option('show_progress_bar'):

        # pick random spinner, from a selected subset of available spinner (see 'python3 -m rich.spinner')
        spinner = random.choice(('aesthetic', 'arc', 'bounce', 'dots', 'line', 'monkey', 'point', 'simpleDots'))

        progress_bar = Progress(
            SpinnerColumn(spinner),
            "[progress.percentage]{task.percentage:>3.1f}%",
            TextColumn("[bold blue]Installing {task.description} ({task.completed:.0f}/{task.total} done)"),
            BarColumn(bar_width=None),
            TimeElapsedColumn(),
            transient=True,
            expand=True,
        )
    else:
        progress_bar = DummyProgress()

    return progress_bar
