# #
# Copyright 2009-2014 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
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
import sys
from copy import copy
from vsc.utils import fancylogger

from easybuild.tools.version import VERSION


# EasyBuild message prefix
EB_MSG_PREFIX = "=="

# the version seen by log.deprecated
CURRENT_VERSION = VERSION

# allow some experimental experimental code
EXPERIMENTAL = False


class EasyBuildError(Exception):
    """
    EasyBuildError is thrown when EasyBuild runs into something horribly wrong.
    """
    def __init__(self, msg):
        Exception.__init__(self, msg)
        self.msg = msg

    def __str__(self):
        return repr(self.msg)


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
        return "(at %s:%s in %s)" % (os.path.join(*filepath_dirs), line, function_name)

    def experimental(self, msg, *args, **kwargs):
        """Handle experimental functionality if EXPERIMENTAL is True, otherwise log error"""
        if EXPERIMENTAL:
            msg = 'Experimental functionality. Behaviour might change/be removed later. ' + msg
            self.warning(msg, *args, **kwargs)
        else:
            msg = 'Experimental functionality. Behaviour might change/be removed later (use --experimental option to enable). ' + msg
            self.error(msg, *args)

    def deprecated(self, msg, max_ver):
        """Print deprecation warning or raise an EasyBuildError, depending on max version allowed."""
        fancylogger.FancyLogger.deprecated(self, msg, str(CURRENT_VERSION), max_ver, exception=EasyBuildError)

    def error(self, msg, *args, **kwargs):
        """Print error message and raise an EasyBuildError."""
        newMsg = "EasyBuild crashed with an error %s: %s" % (self.caller_info(), msg)
        fancylogger.FancyLogger.error(self, newMsg, *args, **kwargs)
        if self.raiseError:
            raise EasyBuildError(newMsg)

    def exception(self, msg, *args):
        """Print exception message and raise EasyBuildError."""
        # don't raise the exception from within error
        newMsg = "EasyBuild encountered an exception %s: %s" % (self.caller_info(), msg)

        self.raiseError = False
        fancylogger.FancyLogger.exception(self, newMsg, *args)
        self.raiseError = True

        raise EasyBuildError(newMsg)


# set format for logger
LOGGING_FORMAT = EB_MSG_PREFIX + ' %(asctime)s %(name)s %(levelname)s %(message)s'
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


def get_log(name=None):
    """
    Generate logger object
    """
    # fname is always get_log, useless
    log = fancylogger.getLogger(name, fname=False)
    log.info("Logger started for %s." % name)
    log.deprecated("get_log", "2.0")
    return log


def print_msg(msg, log=None, silent=False, prefix=True):
    """
    Print a message to stdout.
    """
    if log:
        log.info(msg)
    if not silent:
        if prefix:
            print "%s %s" % (EB_MSG_PREFIX, msg)
        else:
            print msg

def print_error(message, log=None, exitCode=1, opt_parser=None, exit_on_error=True, silent=False):
    """
    Print error message and exit EasyBuild
    """
    if exit_on_error:
        if not silent:
            print_msg("ERROR: %s\n" % message)
            if opt_parser:
                opt_parser.print_shorthelp()
                print_msg("ERROR: %s\n" % message)
        sys.exit(exitCode)
    elif log is not None:
        log.error(message)

def print_warning(message, silent=False):
    """
    Print warning message.
    """
    print_msg("WARNING: %s\n" % message, silent=silent)


