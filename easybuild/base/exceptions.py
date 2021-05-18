#
# Copyright 2015-2021 Ghent University
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

:author: Kenneth Hoste (Ghent University)
:author: Riccardo Murri (University of Zurich)
"""
import inspect
import logging
import os

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

        if self.LOC_INFO_TOP_PKG_NAMES is not None:
            # determine correct frame to fetch location information from
            frames_up = 1
            if self.__class__ != LoggedException:
                # move a level up when this instance is derived from LoggedException
                frames_up += 1

            if self.INCLUDE_LOCATION:
                # figure out where error was raised from
                # current frame: this constructor, one frame above: location where LoggedException was created/raised
                frameinfo = inspect.getouterframes(inspect.currentframe())[frames_up]

                # determine short location of Python module where error was raised from,
                # i.e. starting with an entry from LOC_INFO_TOP_PKG_NAMES
                path_parts = frameinfo[1].split(os.path.sep)
                if path_parts[0] == '':
                    path_parts[0] = os.path.sep
                top_indices = [path_parts.index(n) for n in self.LOC_INFO_TOP_PKG_NAMES if n in path_parts]
                relpath = os.path.join(*path_parts[max(top_indices or [0]):])

                # include location info at the end of the message
                # for example: "Nope, giving up (at easybuild/tools/somemodule.py:123 in some_function)"
                msg = "%s (at %s:%s in %s)" % (msg, relpath, frameinfo[2], frameinfo[3])

        logger = kwargs.get('logger', None)
        # try to use logger defined in caller's environment
        if logger is None:
            logger = get_callers_logger()
            # search can fail, use root logger as a fallback
            if logger is None:
                logger = self.LOGGER_MODULE.getLogger()

        getattr(logger, self.LOGGING_METHOD_NAME)(msg)

        super(LoggedException, self).__init__(msg)
