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
import functools

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import OUTPUT_STYLE_RICH, build_option, get_output_style
from easybuild.tools.py2vs3 import OrderedDict

try:
    from rich.console import Console, RenderGroup
    from rich.live import Live
    from rich.table import Table
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    from rich.progress import DownloadColumn, FileSizeColumn, TransferSpeedColumn, TimeRemainingColumn
except ImportError:
    pass


PROGRESS_BAR_DOWNLOAD_ALL = 'download_all'
PROGRESS_BAR_DOWNLOAD_ONE = 'download_one'
PROGRESS_BAR_EXTENSIONS = 'extensions'
PROGRESS_BAR_EASYCONFIG = 'easyconfig'
PROGRESS_BAR_OVERALL = 'overall'

_progress_bar_cache = {}


class DummyRich(object):
    """
    Dummy shim for Rich classes.
    Used in case Rich is not available, or when EasyBuild is not configured to use rich output style.
    """

    # __enter__ and __exit__ must be implemented to allow use as context manager
    def __enter__(self, *args, **kwargs):
        pass

    def __exit__(self, *args, **kwargs):
        pass

    # dummy implementations for methods supported by rich.progress.Progress class
    def add_task(self, *args, **kwargs):
        pass

    def stop_task(self, *args, **kwargs):
        pass

    def update(self, *args, **kwargs):
        pass

    # internal Rich methods
    def __rich_console__(self, *args, **kwargs):
        pass


def use_rich():
    """
    Return whether or not to use Rich to produce rich output.
    """
    return get_output_style() == OUTPUT_STYLE_RICH


def show_progress_bars():
    """
    Return whether or not to show progress bars.
    """
    return use_rich() and build_option('show_progress_bar') and not build_option('extended_dry_run')


def rich_live_cm():
    """
    Return Live instance to use as context manager.
    """
    if show_progress_bars():
        pbar_group = RenderGroup(
                download_one_progress_bar(),
                download_one_progress_bar_unknown_size(),
                download_all_progress_bar(),
                extensions_progress_bar(),
                easyconfig_progress_bar(),
                overall_progress_bar(),
        )
        live = Live(pbar_group)
    else:
        live = DummyRich()

    return live


def progress_bar_cache(func):
    """
    Function decorator to cache created progress bars for easy retrieval.
    """
    @functools.wraps(func)
    def new_func(ignore_cache=False):
        if hasattr(func, 'cached') and not ignore_cache:
            progress_bar = func.cached
        elif use_rich() and build_option('show_progress_bar'):
            progress_bar = func()
        else:
            progress_bar = DummyRich()

        func.cached = progress_bar
        return func.cached

    return new_func


@progress_bar_cache
def overall_progress_bar():
    """
    Get progress bar to display overall progress.
    """
    progress_bar = Progress(
        TimeElapsedColumn(),
        TextColumn("{task.description}({task.completed} out of {task.total} easyconfigs done)"),
        BarColumn(bar_width=None),
    )

    return progress_bar


@progress_bar_cache
def easyconfig_progress_bar():
    """
    Get progress bar to display progress for installing a single easyconfig file.
    """
    progress_bar = Progress(
        SpinnerColumn('point'),
        TextColumn("[bold green]{task.description} ({task.completed} out of {task.total} steps done)"),
        BarColumn(),
        TimeElapsedColumn(),
    )

    return progress_bar


@progress_bar_cache
def download_all_progress_bar():
    """
    Get progress bar to show progress on downloading of all source files.
    """
    progress_bar = Progress(
        TextColumn("[bold blue]Fetching files: {task.percentage:>3.0f}% ({task.completed}/{task.total})"),
        BarColumn(),
        TimeElapsedColumn(),
        TextColumn("({task.description})"),
    )

    return progress_bar


@progress_bar_cache
def download_one_progress_bar():
    """
    Get progress bar to show progress for downloading a file of known size.
    """
    progress_bar = Progress(
        TextColumn('[bold yellow]Downloading {task.description}'),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    )

    return progress_bar


@progress_bar_cache
def download_one_progress_bar_unknown_size():
    """
    Get progress bar to show progress for downloading a file of unknown size.
    """
    progress_bar = Progress(
        TextColumn('[bold yellow]Downloading {task.description}'),
        FileSizeColumn(),
        TransferSpeedColumn(),
    )

    return progress_bar


@progress_bar_cache
def extensions_progress_bar():
    """
    Get progress bar to show progress for installing extensions.
    """
    progress_bar = Progress(
        TextColumn("[bold blue]{task.description} ({task.completed}/{task.total})"),
        BarColumn(),
        TimeElapsedColumn(),
    )

    return progress_bar


def get_progress_bar(bar_type, size=None):
    """
    Get progress bar of given type.
    """
    progress_bar_types = {
        PROGRESS_BAR_DOWNLOAD_ALL: download_all_progress_bar,
        PROGRESS_BAR_DOWNLOAD_ONE: download_one_progress_bar,
        PROGRESS_BAR_EXTENSIONS: extensions_progress_bar,
        PROGRESS_BAR_EASYCONFIG: easyconfig_progress_bar,
        PROGRESS_BAR_OVERALL: overall_progress_bar,
    }

    if bar_type == PROGRESS_BAR_DOWNLOAD_ONE and not size:
        pbar = download_one_progress_bar_unknown_size()
    elif bar_type in progress_bar_types:
        pbar = progress_bar_types[bar_type]()
    else:
        raise EasyBuildError("Unknown progress bar type: %s", bar_type)

    return pbar


def start_progress_bar(bar_type, size, label=None):
    """
    Start progress bar of given type.

    :param label: label for progress bar
    :param size: total target size of progress bar
    """
    pbar = get_progress_bar(bar_type, size=size)
    task_id = pbar.add_task('')
    _progress_bar_cache[bar_type] = (pbar, task_id)

    # don't bother showing progress bar if there's only 1 item to make progress on
    if size == 1:
        pbar.update(task_id, visible=False)
    elif size:
        pbar.update(task_id, total=size)

    if label:
        pbar.update(task_id, description=label)


def update_progress_bar(bar_type, label=None, progress_size=1):
    """
    Update progress bar of given type, add progress of given size.

    :param bar_type: type of progress bar
    :param label: label for progress bar
    :param progress_size: amount of progress made
    """
    (pbar, task_id) = _progress_bar_cache[bar_type]
    if label:
        pbar.update(task_id, description=label)
    if progress_size:
        pbar.update(task_id, advance=progress_size)


def stop_progress_bar(bar_type, visible=False):
    """
    Stop progress bar of given type.
    """
    (pbar, task_id) = _progress_bar_cache[bar_type]
    pbar.stop_task(task_id)
    if not visible:
        pbar.update(task_id, visible=False)


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
