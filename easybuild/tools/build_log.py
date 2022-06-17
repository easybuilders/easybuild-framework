# #
# Copyright 2009-2022 Ghent University
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
EasyBuild logger and log utilities, including our own EasybuildError class.

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
"""
import logging
import os
import re
import sys
import tempfile
from copy import copy
from datetime import datetime

from easybuild.base import fancylogger
from easybuild.base.exceptions import LoggedException
from easybuild.tools.version import VERSION, this_is_easybuild


# EasyBuild message prefix
EB_MSG_PREFIX = "=="

# the version seen by log.deprecated
CURRENT_VERSION = VERSION

# allow some experimental experimental code
EXPERIMENTAL = False

DEPRECATED_DOC_URL = 'http://easybuild.readthedocs.org/en/latest/Deprecated-functionality.html'

DRY_RUN_BUILD_DIR = None
DRY_RUN_SOFTWARE_INSTALL_DIR = None
DRY_RUN_MODULES_INSTALL_DIR = None


DEVEL_LOG_LEVEL = logging.DEBUG - 1
logging.addLevelName(DEVEL_LOG_LEVEL, 'DEVEL')


class EasyBuildError(LoggedException):
    """
    EasyBuildError is thrown when EasyBuild runs into something horribly wrong.
    """
    LOC_INFO_TOP_PKG_NAMES = ['easybuild', 'vsc']
    LOC_INFO_LEVEL = 1
    # always include location where error was raised from, even under 'python -O'
    INCLUDE_LOCATION = True

    def __init__(self, msg, *args):
        """Constructor: initialise EasyBuildError instance."""
        if args:
            msg = msg % args
        LoggedException.__init__(self, msg)
        self.msg = msg

    def __str__(self):
        """Return string representation of this EasyBuildError instance."""
        return repr(self.msg)


def raise_easybuilderror(msg, *args):
    """Raise EasyBuildError with given message, formatted by provided string arguments."""
    raise EasyBuildError(msg, *args)


def raise_nosupport(msg, ver):
    """Construct error message for no longer supported behaviour, and raise an EasyBuildError."""
    nosupport_msg = "NO LONGER SUPPORTED since v%s: %s; see %s for more information"
    raise_easybuilderror(nosupport_msg, ver, msg, DEPRECATED_DOC_URL)


class EasyBuildLog(fancylogger.FancyLogger):
    """
    The EasyBuild logger, with its own error and exception functions.
    """

    RAISE_EXCEPTION_CLASS = EasyBuildError

    def caller_info(self):
        """Return string with caller info."""
        # findCaller returns a 3-tupe in Python 2, a 4-tuple in Python 3 (stack info as extra element)
        (filepath, line, function_name) = self.findCaller()[:3]
        filepath_dirs = filepath.split(os.path.sep)

        for dirName in copy(filepath_dirs):
            if dirName != "easybuild":
                filepath_dirs.remove(dirName)
            else:
                break
            if not filepath_dirs:
                filepath_dirs = ['?']
        return "(at %s:%s in %s)" % (os.path.join(*filepath_dirs), line, function_name)

    def experimental(self, msg, *args, **kwargs):
        """Handle experimental functionality if EXPERIMENTAL is True, otherwise log error"""
        common_msg = "Experimental functionality. Behaviour might change/be removed later"
        if EXPERIMENTAL:
            msg = common_msg + ': ' + msg
            self.warning(msg, *args, **kwargs)
        else:
            msg = common_msg + " (use --experimental option to enable): " + msg
            raise EasyBuildError(msg, *args)

    def deprecated(self, msg, ver, max_ver=None, more_info=None, silent=False, *args, **kwargs):
        """
        Print deprecation warning or raise an exception, depending on specified version(s)

        :param: msg: deprecation message
        :param ver: if max_ver is None: threshold for EasyBuild version to determine warning vs exception
                    else: version to check against max_ver to determine warning vs exception
        :param max_ver: version threshold for warning vs exception (compared to 'ver')
        :param more_info: additional message with instructions where to get more information
        :param silent: stay silent (don't *print* deprecation warnings, only log them)
        """
        # provide log_callback function that both logs a warning and prints to stderr
        def log_callback_warning_and_print(msg):
            """Log warning message, and also print it to stderr."""
            self.warning(msg)
            print_warning(msg, silent=silent)

        kwargs['log_callback'] = log_callback_warning_and_print

        # always raise an EasyBuildError, nothing else
        kwargs['exception'] = EasyBuildError

        if max_ver is None:
            if more_info:
                msg += more_info
            else:
                msg += "; see %s for more information" % DEPRECATED_DOC_URL
            fancylogger.FancyLogger.deprecated(self, msg, str(CURRENT_VERSION), ver, *args, **kwargs)
        else:
            fancylogger.FancyLogger.deprecated(self, msg, ver, max_ver, *args, **kwargs)

    def nosupport(self, msg, ver):
        """Raise error message for no longer supported behaviour, and raise an EasyBuildError."""
        raise_nosupport(msg, ver)

    def error(self, msg, *args, **kwargs):
        """Print error message and raise an EasyBuildError."""
        ebmsg = "EasyBuild crashed with an error %s: " % self.caller_info()
        fancylogger.FancyLogger.error(self, ebmsg + msg, *args, **kwargs)

    def devel(self, msg, *args, **kwargs):
        """Print development log message"""
        self.log(DEVEL_LOG_LEVEL, msg, *args, **kwargs)

    def exception(self, msg, *args):
        """Print exception message and raise EasyBuildError."""
        # don't raise the exception from within error
        ebmsg = "EasyBuild encountered an exception %s: " % self.caller_info()
        fancylogger.FancyLogger.exception(self, ebmsg + msg, *args)


# set format for logger
LOGGING_FORMAT = EB_MSG_PREFIX + ' %(asctime)s %(filename)s:%(lineno)s %(levelname)s %(message)s'
fancylogger.setLogFormat(LOGGING_FORMAT)

# set the default LoggerClass to EasyBuildLog
fancylogger.logging.setLoggerClass(EasyBuildLog)

# you can't easily set another LoggerClass before fancylogger calls getLogger on import
_init_fancylog = fancylogger.getLogger(fname=False)
del _init_fancylog.manager.loggerDict[_init_fancylog.name]

# we need to make sure there is a handler
fancylogger.logToFile(filename=os.devnull, max_bytes=0)

# EasyBuildLog
_init_easybuildlog = fancylogger.getLogger(fname=False)


def init_logging(logfile, logtostdout=False, silent=False, colorize=fancylogger.Colorize.AUTO, tmp_logdir=None):
    """Initialize logging."""
    if logtostdout:
        fancylogger.logToScreen(enable=True, stdout=True, colorize=colorize)
    else:
        if logfile is None:
            # if logdir is specified but doesn't exist yet, create it first
            if tmp_logdir and not os.path.exists(tmp_logdir):
                try:
                    os.makedirs(tmp_logdir)
                except (IOError, OSError) as err:
                    raise EasyBuildError("Failed to create temporary log directory %s: %s", tmp_logdir, err)

            # mkstemp returns (fd,filename), fd is from os.open, not regular open!
            fd, logfile = tempfile.mkstemp(suffix='.log', prefix='easybuild-', dir=tmp_logdir)
            os.close(fd)

        fancylogger.logToFile(logfile, max_bytes=0)
        print_msg('Temporary log file in case of crash %s' % (logfile), log=None, silent=silent)

    log = fancylogger.getLogger(fname=False)

    return log, logfile


def log_start(log, eb_command_line, eb_tmpdir):
    """Log startup info."""
    log.info(this_is_easybuild())

    # log used command line
    log.info("Command line: %s", ' '.join(eb_command_line))

    log.info("Using %s as temporary directory", eb_tmpdir)


def stop_logging(logfile, logtostdout=False):
    """Stop logging."""
    if logtostdout:
        fancylogger.logToScreen(enable=False, stdout=True)
    if logfile is not None:
        fancylogger.logToFile(logfile, enable=False)


def print_msg(msg, *args, **kwargs):
    """
    Print a message.

    :param log: logger instance to also message to
    :param silent: be silent (only log, don't print)
    :param prefix: include message prefix characters ('== ')
    :param newline: end message with newline
    :param stderr: print to stderr rather than stdout
    """
    if args:
        msg = msg % args

    log = kwargs.pop('log', None)
    silent = kwargs.pop('silent', False)
    prefix = kwargs.pop('prefix', True)
    newline = kwargs.pop('newline', True)
    stderr = kwargs.pop('stderr', False)
    if kwargs:
        raise EasyBuildError("Unknown named arguments passed to print_msg: %s", kwargs)

    if log:
        log.info(msg)
    if not silent:
        if prefix:
            msg = ' '.join([EB_MSG_PREFIX, msg])

        if newline:
            msg += '\n'

        if stderr:
            sys.stderr.write(msg)
        else:
            sys.stdout.write(msg)


def dry_run_set_dirs(prefix, builddir, software_installdir, module_installdir):
    """
    Initialize for printing dry run messages.

    Define DRY_RUN_*DIR constants, so they can be used in dry_run_msg to replace fake build/install dirs.

    :param prefix: prefix of fake build/install dirs, that can be stripped off when printing
    :param builddir: fake build dir
    :param software_installdir: fake software install directory
    :param module_installdir: fake module install directory
    """
    global DRY_RUN_BUILD_DIR
    DRY_RUN_BUILD_DIR = (re.compile(re.escape(builddir)), builddir[len(prefix):])

    global DRY_RUN_MODULES_INSTALL_DIR
    DRY_RUN_MODULES_INSTALL_DIR = (re.compile(re.escape(module_installdir)), module_installdir[len(prefix):])

    global DRY_RUN_SOFTWARE_INSTALL_DIR
    DRY_RUN_SOFTWARE_INSTALL_DIR = (re.compile(re.escape(software_installdir)), software_installdir[len(prefix):])


def dry_run_msg(msg, *args, **kwargs):
    """Print dry run message."""
    # replace fake build/install dir in dry run message with original value
    if args:
        msg = msg % args

    silent = kwargs.pop('silent', False)
    if kwargs:
        raise EasyBuildError("Unknown named arguments passed to dry_run_msg: %s", kwargs)

    for dry_run_var in [DRY_RUN_BUILD_DIR, DRY_RUN_MODULES_INSTALL_DIR, DRY_RUN_SOFTWARE_INSTALL_DIR]:
        if dry_run_var is not None:
            msg = dry_run_var[0].sub(dry_run_var[1], msg)

    print_msg(msg, silent=silent, prefix=False)


def dry_run_warning(msg, *args, **kwargs):
    """Print dry run message."""
    if args:
        msg = msg % args

    silent = kwargs.pop('silent', False)
    if kwargs:
        raise EasyBuildError("Unknown named arguments passed to dry_run_warning: %s", kwargs)

    dry_run_msg("\n!!!\n!!! WARNING: %s\n!!!\n" % msg, silent=silent)


def print_error(msg, *args, **kwargs):
    """
    Print error message and exit EasyBuild
    """
    if args:
        msg = msg % args

    log = kwargs.pop('log', None)
    exitCode = kwargs.pop('exitCode', 1)
    opt_parser = kwargs.pop('opt_parser', None)
    exit_on_error = kwargs.pop('exit_on_error', True)
    silent = kwargs.pop('silent', False)
    if kwargs:
        raise EasyBuildError("Unknown named arguments passed to print_error: %s", kwargs)

    if exit_on_error:
        if not silent:
            if opt_parser:
                opt_parser.print_shorthelp()
            sys.stderr.write("ERROR: %s\n" % msg)
        sys.exit(exitCode)
    elif log is not None:
        raise EasyBuildError(msg)


def print_warning(msg, *args, **kwargs):
    """
    Print warning message.
    """
    if args:
        msg = msg % args

    log = kwargs.pop('log', None)
    silent = kwargs.pop('silent', False)
    if kwargs:
        raise EasyBuildError("Unknown named arguments passed to print_warning: %s", kwargs)

    if log:
        log.warning(msg)
    if not silent:
        sys.stderr.write("\nWARNING: %s\n\n" % msg)


def time_str_since(start_time):
    """
    Return string representing amount of time that has passed since specified timestamp

    :param start_time: datetime value representing start time
    :return: string value representing amount of time passed since start_time;
             format: "[[%d hours, ]%d mins, ]%d sec(s)"
    """
    tot_time = datetime.now() - start_time
    tot_secs = tot_time.seconds + tot_time.days * 24 * 3600
    if tot_secs > 0:
        res = datetime.utcfromtimestamp(tot_secs).strftime('%Hh%Mm%Ss')
    else:
        res = "< 1s"

    return res
