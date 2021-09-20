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

from easybuild.tools.config import OUTPUT_STYLE_RICH, build_option, get_output_style
from easybuild.tools.py2vs3 import OrderedDict

try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
except ImportError:
    pass


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


def use_rich():
    """Return whether or not to use Rich to produce rich output."""
    return get_output_style() == OUTPUT_STYLE_RICH


def create_progress_bar():
    """
    Create progress bar to display overall progress.

    Returns rich.progress.Progress instance if the Rich Python package is available,
    or a shim DummyProgress instance otherwise.
    """
    if use_rich() and build_option('show_progress_bar'):

        # pick random spinner, from a selected subset of available spinner (see 'python3 -m rich.spinner')
        spinner = random.choice(('aesthetic', 'arc', 'bounce', 'dots', 'line', 'monkey', 'point', 'simpleDots'))

        progress_bar = Progress(
            SpinnerColumn(spinner),
            "[progress.percentage]{task.percentage:>3.1f}%",
            TextColumn("[blue bold]{task.description} {task.fields[software]}"
                       " ({task.completed:.0f}/{task.total} done)"),
            BarColumn(bar_width=None),
            TimeElapsedColumn(),
            transient=True,
            expand=True,
        )
    else:
        progress_bar = DummyProgress()

    return progress_bar


def print_checks(checks_data):
    """Print overview of checks that were made."""

    col_titles = checks_data.pop('col_titles', ('name', 'info', 'description'))

    col2_label = col_titles[1]

    if use_rich():
        console = Console()
        # don't use console.print, which causes SyntaxError in Python 2
        console_print = getattr(console, 'print')  # noqa: B009
        console_print('')

    for section in checks_data:
        section_checks = checks_data[section]

        if use_rich():
            table = Table(title=section)
            table.add_column(col_titles[0])
            table.add_column(col_titles[1])
            # only add 3rd column if there's any information to include in it
            if any(x[1] for x in section_checks.values()):
                table.add_column(col_titles[2])
        else:
            lines = [
                '',
                section + ':',
                '-' * (len(section) + 1),
                '',
            ]

        if isinstance(section_checks, OrderedDict):
            check_names = section_checks.keys()
        else:
            check_names = sorted(section_checks, key=lambda x: x.lower())

        if use_rich():
            for check_name in check_names:
                (info, descr) = checks_data[section][check_name]
                if info is None:
                    info = ':yellow_circle:  [yellow]%s?!' % col2_label
                elif info is False:
                    info = ':cross_mark:  [red]not found'
                else:
                    info = ':white_heavy_check_mark:  [green]%s' % info
                if descr:
                    table.add_row(check_name.rstrip(':'), info, descr)
                else:
                    table.add_row(check_name.rstrip(':'), info)
        else:
            for check_name in check_names:
                (info, descr) = checks_data[section][check_name]
                if info is None:
                    info = '(found, UNKNOWN %s)' % col2_label
                elif info is False:
                    info = '(NOT FOUND)'
                line = "* %s %s" % (check_name, info)
                if descr:
                    line = line.ljust(40) + '[%s]' % descr
                lines.append(line)
            lines.append('')

        if use_rich():
            console_print(table)
        else:
            print('\n'.join(lines))
