# #
# Copyright 2009-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/easybuild
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

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
"""
import os
import re
import sys
import tempfile
from copy import copy
from vsc.utils import fancylogger
from vsc.utils.exceptions import LoggedException

from easybuild.tools.version import VERSION


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


class EasyBuildError(LoggedException):
    """
    EasyBuildError is thrown when EasyBuild runs into something horribly wrong.
    """
    LOC_INFO_TOP_PKG_NAMES = ['easybuild', 'vsc']
    LOC_INFO_LEVEL = 1
    # always include location where error was raised from, even under 'python -O'
    INCLUDE_LOCATION = True

    # use custom error logging method, to make sure EasyBuildError isn't being raised again to avoid infinite recursion
    # only required because 'error' log method raises (should no longer be needed in EB v3.x)
    LOGGING_METHOD_NAME = '_error_no_raise'

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


class EasyBuildLog(fancylogger.FancyLogger):
    """
    The EasyBuild logger, with its own error and exception functions.
    """

    # self.raiseError can be set to False disable raising the exception which is
    # necessary because logging.Logger.exception calls self.error
    raiseError = True

    def caller_info(self):
        """Return string with caller info."""
        (filepath, line, function_name) = self.findCaller()
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
        if EXPERIMENTAL:
            msg = 'Experimental functionality. Behaviour might change/be removed later. ' + msg
            self.warning(msg, *args, **kwargs)
        else:
            msg = 'Experimental functionality. Behaviour might change/be removed later (use --experimental option to enable). ' + msg
            raise EasyBuildError(msg, *args)

    def deprecated(self, msg, max_ver):
        """Print deprecation warning or raise an EasyBuildError, depending on max version allowed."""
        msg += "; see %s for more information" % DEPRECATED_DOC_URL
        fancylogger.FancyLogger.deprecated(self, msg, str(CURRENT_VERSION), max_ver, exception=EasyBuildError)

    def nosupport(self, msg, ver):
        """Print error message for no longer supported behaviour, and raise an EasyBuildError."""
        nosupport_msg = "NO LONGER SUPPORTED since v%s: %s; see %s for more information"
        raise EasyBuildError(nosupport_msg, ver, msg, DEPRECATED_DOC_URL)

    def error(self, msg, *args, **kwargs):
        """Print error message and raise an EasyBuildError."""
        ebmsg = "EasyBuild crashed with an error %s: " + msg
        args = (self.caller_info(),) + args

        fancylogger.FancyLogger.error(self, ebmsg, *args, **kwargs)

        if self.raiseError:
            self.deprecated("Use 'raise EasyBuildError' rather than error() logging method that raises", '3.0')
            raise EasyBuildError(ebmsg, *args)

    # FIXME: remove this when error() no longer raises EasyBuildError
    def _error_no_raise(self, msg):
        """Utility function to log an error with raising an exception."""

        # make sure raising of error is disabled
        orig_raise_error = self.raiseError
        self.raiseError = False

        fancylogger.FancyLogger.error(self, msg)

        # reinstate previous raiseError setting
        self.raiseError = orig_raise_error

    def exception(self, msg, *args):
        """Print exception message and raise EasyBuildError."""
        # don't raise the exception from within error
        ebmsg = "EasyBuild encountered an exception %s: " + msg
        args = (self.caller_info(),) + args

        self.raiseError = False
        fancylogger.FancyLogger.exception(self, ebmsg, *args)
        self.raiseError = True

        self.deprecated("Use 'raise EasyBuildError' rather than exception() logging method that raises", '3.0')
        raise EasyBuildError(ebmsg, *args)


# set format for logger
LOGGING_FORMAT = EB_MSG_PREFIX + ' %(asctime)s %(filename)s:%(lineno)s %(levelname)s %(message)s'
fancylogger.setLogFormat(LOGGING_FORMAT)

# set the default LoggerClass to EasyBuildLog
fancylogger.logging.setLoggerClass(EasyBuildLog)

# you can't easily set another LoggerClass before fancylogger calls getLogger on import
_init_fancylog = fancylogger.getLogger(fname=False)
del _init_fancylog.manager.loggerDict[_init_fancylog.name]

# we need to make sure there is a handler
fancylogger.logToFile(filename=os.devnull)

# EasyBuildLog
_init_easybuildlog = fancylogger.getLogger(fname=False)


def init_logging(logfile, logtostdout=False, silent=False):
    """Initialize logging."""
    if logtostdout:
        fancylogger.logToScreen(enable=True, stdout=True)
    else:
        if logfile is None:
            # mkstemp returns (fd,filename), fd is from os.open, not regular open!
            fd, logfile = tempfile.mkstemp(suffix='.log', prefix='easybuild-')
            os.close(fd)

        fancylogger.logToFile(logfile)
        print_msg('temporary log file in case of crash %s' % (logfile), log=None, silent=silent)

    log = fancylogger.getLogger(fname=False)

    return log, logfile


def stop_logging(logfile, logtostdout=False):
    """Stop logging."""
    if logtostdout:
        fancylogger.logToScreen(enable=False, stdout=True)
    if logfile is not None:
        fancylogger.logToFile(logfile, enable=False)


def get_log(name=None):
    """
    (NO LONGER SUPPORTED!) Generate logger object
    """
    log.nosupport("Use of get_log function", '2.0')


def print_msg(msg, log=None, silent=False, prefix=True, newline=True):
    """
    Print a message to stdout.
    """
    if log:
        log.info(msg)
    if not silent:
        if prefix:
            msg = ' '.join([EB_MSG_PREFIX, msg])

        if newline:
            print msg
        else:
            print msg,


def dry_run_set_dirs(prefix, builddir, software_installdir, module_installdir):
    """
    Initialize for printing dry run messages.

    Define DRY_RUN_*DIR constants, so they can be used in dry_run_msg to replace fake build/install dirs.

    @param prefix: prefix of fake build/install dirs, that can be stripped off when printing
    @param builddir: fake build dir
    @param software_installdir: fake software install directory
    @param module_installdir: fake module install directory
    """
    global DRY_RUN_BUILD_DIR
    DRY_RUN_BUILD_DIR = (re.compile(builddir), builddir[len(prefix):])

    global DRY_RUN_MODULES_INSTALL_DIR
    DRY_RUN_MODULES_INSTALL_DIR = (re.compile(module_installdir), module_installdir[len(prefix):])

    global DRY_RUN_SOFTWARE_INSTALL_DIR
    DRY_RUN_SOFTWARE_INSTALL_DIR = (re.compile(software_installdir), software_installdir[len(prefix):])


def dry_run_msg(msg, silent=False):
    """Print dry run message."""
    # replace fake build/install dir in dry run message with original value
    for dry_run_var in [DRY_RUN_BUILD_DIR, DRY_RUN_MODULES_INSTALL_DIR, DRY_RUN_SOFTWARE_INSTALL_DIR]:
        if dry_run_var is not None:
            msg = dry_run_var[0].sub(dry_run_var[1], msg)

    print_msg(msg, silent=silent, prefix=False)


def dry_run_warning(msg, silent=False):
    """Print dry run message."""
    dry_run_msg("\n!!!\n!!! WARNING: %s\n!!!\n" % msg, silent=silent)


def print_error(message, log=None, exitCode=1, opt_parser=None, exit_on_error=True, silent=False):
    """
    Print error message and exit EasyBuild
    """
    if exit_on_error:
        if not silent:
            if opt_parser:
                opt_parser.print_shorthelp()
            sys.stderr.write("ERROR: %s\n" % message)
        sys.exit(exitCode)
    elif log is not None:
        raise EasyBuildError(message)


def print_warning(message, silent=False):
    """
    Print warning message.
    """
    print_msg("WARNING: %s\n" % message, silent=silent)
