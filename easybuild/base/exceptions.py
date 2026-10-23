#
# Copyright 2015-2026 Ghent University
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
#
"""
Module providing custom exceptions.

Authors:

* Kenneth Hoste (Ghent University)
* Riccardo Murri (University of Zurich)
"""
import inspect
import logging
import os
from enum import IntEnum

from easybuild.base import fancylogger


def get_callers_logger():
    """
    Get logger defined in caller's environment
    :return: logger instance (or None if none was found)
    """
    logger_cls = logging.getLoggerClass()
    if __debug__:
        frame = inspect.currentframe()
    else:
        frame = None
    logger = None

    # frame may be None, see https://docs.python.org/2/library/inspect.html#inspect.currentframe
    if frame is not None:
        try:
            # consider calling stack in reverse order, i.e. most inner frame (closest to caller) first
            for frameinfo in inspect.getouterframes(frame)[::-1]:
                bindings = inspect.getargvalues(frameinfo[0]).locals
                for val in bindings.values():
                    if isinstance(val, logger_cls):
                        logger = val
                        break
        finally:
            # make very sure that reference to frame object is removed, to avoid reference cycles
            # see https://docs.python.org/2/library/inspect.html#the-interpreter-stack
            del frame

    return logger


class LoggedException(Exception):
    """Exception that logs it's message when it is created."""

    # logger module to use (must provide getLogger() function)
    LOGGER_MODULE = fancylogger
    # name of logging method to use
    # must accept an argument of type string, i.e. the log message, and an optional list of formatting arguments
    LOGGING_METHOD_NAME = 'error'
    # list of top-level package names to use to format location info; None implies not to include location info
    LOC_INFO_TOP_PKG_NAMES = []
    # include location where error was raised from (enabled by default under 'python', disabled under 'python -O')
    INCLUDE_LOCATION = __debug__

    def __init__(self, msg, *args, **kwargs):
        """
        Constructor.
        :param msg: exception message
        :param *args: list of formatting arguments for exception message
        :param logger: logger to use
        """
        # format message with (optional) list of formatting arguments
        if args:
            msg = msg % args

        backtrace = []
        if self.LOC_INFO_TOP_PKG_NAMES is not None:
            # determine correct frame to fetch location information from
            frames_up = 1
            if self.__class__ != LoggedException:
                # move a level up when this instance is derived from LoggedException
                frames_up += 1

            if self.INCLUDE_LOCATION:
                # figure out where error was raised from
                # current frame: this constructor, one frame above: location where LoggedException was created/raised
                frames = inspect.getouterframes(inspect.currentframe())[frames_up:]
                backtrace = []
                for frame in frames:
                    # determine short location of Python module where error was raised from,
                    # i.e. starting with an entry from LOC_INFO_TOP_PKG_NAMES
                    path_parts = frame[1].split(os.path.sep)
                    if path_parts[0] == '':
                        path_parts[0] = os.path.sep
                    try:
                        top_idx = max(path_parts.index(n) for n in self.LOC_INFO_TOP_PKG_NAMES if n in path_parts)
                    except ValueError:
                        # If none found (outside PKG) stop backtrace if we have at least 1 entry
                        if backtrace:
                            break
                        relpath = frame[1]
                    else:
                        relpath = os.path.join(*path_parts[top_idx:])
                    backtrace.append(f'{relpath}:{frame[2]} in {frame[3]}')

                # include location info at the end of the message
                # for example: "Nope, giving up (at easybuild/tools/somemodule.py:123 in some_function)"
                msg = f"{msg} (at {backtrace[0]})"

        super().__init__(msg)

        logger = kwargs.get('logger', None)
        # try to use logger defined in caller's environment
        if logger is None:
            logger = get_callers_logger()
            # search can fail, use root logger as a fallback
            if logger is None:
                logger = self.LOGGER_MODULE.getLogger()

        if backtrace:
            msg += '\nCallstack:\n\t' + '\n\t'.join(backtrace)
        getattr(logger, self.LOGGING_METHOD_NAME)(msg)


class EasyBuildExit(IntEnum):
    """
    Table of exit codes
    """
    SUCCESS = 0
    ERROR = 1
    # core errors
    OPTION_ERROR = 2
    VALUE_ERROR = 3
    MISSING_EASYCONFIG = 4
    EASYCONFIG_ERROR = 5
    MISSING_EASYBLOCK = 6
    EASYBLOCK_ERROR = 7
    MODULE_ERROR = 8
    # step errors in order of execution
    FAIL_FETCH_STEP = 10
    FAIL_READY_STEP = 11
    FAIL_SOURCE_STEP = 12
    FAIL_PATCH_STEP = 13
    FAIL_PREPARE_STEP = 14
    FAIL_CONFIGURE_STEP = 15
    FAIL_BUILD_STEP = 16
    FAIL_TEST_STEP = 17
    FAIL_INSTALL_STEP = 18
    FAIL_EXTENSIONS_STEP = 19
    FAIL_POST_ITER_STEP = 20
    FAIL_POST_PROC_STEP = 21
    FAIL_SANITY_CHECK_STEP = 22
    FAIL_CLEANUP_STEP = 23
    FAIL_MODULE_STEP = 24
    FAIL_PERMISSIONS_STEP = 25
    FAIL_PACKAGE_STEP = 26
    FAIL_TEST_CASES_STEP = 27
    # errors on missing things
    MISSING_SOURCES = 30
    MISSING_DEPENDENCY = 31
    MISSING_SYSTEM_DEPENDENCY = 32
    MISSING_EB_DEPENDENCY = 33
    # errors on specific task failures
    FAIL_SYSTEM_CHECK = 40
    FAIL_DOWNLOAD = 41
    FAIL_CHECKSUM = 42
    FAIL_EXTRACT = 43
    FAIL_PATCH_APPLY = 44
    FAIL_SANITY_CHECK = 45
    FAIL_MODULE_WRITE = 46
    FAIL_GITHUB = 47


class EasyBuildError(LoggedException):
    """
    EasyBuildError is thrown when EasyBuild runs into something horribly wrong.
    """
    LOC_INFO_TOP_PKG_NAMES = ['easybuild', 'vsc']
    LOC_INFO_LEVEL = 1
    # always include location where error was raised from, even under 'python -O'
    INCLUDE_LOCATION = True

    def __init__(self, msg, *args, exit_code=EasyBuildExit.ERROR, **kwargs):
        """Constructor: initialise EasyBuildError instance."""
        if args:
            msg = msg % args
        LoggedException.__init__(self, msg, exit_code=exit_code, **kwargs)
        self.msg = msg
        self.exit_code = exit_code

    def __str__(self):
        """Return string representation of this EasyBuildError instance."""
        return self.msg
