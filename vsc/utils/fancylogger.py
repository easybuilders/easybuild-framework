#!/usr/bin/env python
##
# Copyright 2011-2013 Ghent University
#
# This file is part of vsc-base,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/vsc-base
#
# vsc-base is free software: you can redistribute it and/or modify
# it under the terms of the GNU Library General Public License as
# published by the Free Software Foundation, either version 2 of
# the License, or (at your option) any later version.
#
# vsc-base is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public License
# along with vsc-base. If not, see <http://www.gnu.org/licenses/>.
##
"""
This module implements a fancy logger on top of python logging

It adds:
 - custom specifiers for mpi logging (the mpirank) with autodetection of mpi
 - custom specifier for always showing the calling function's name
 - rotating file handler
 - a default formatter.
 - logging to an UDP server (vsc.logging.logdaemon.py f.ex.)
 - easily setting loglevel
 - easily add extra specifiers in the log record

usage:

>>> from vsc.utils import fancylogger
>>> # will log to screen by default
>>> fancylogger.logToFile('dir/filename')
>>> fancylogger.setLogLevelDebug()  # set global loglevel to debug
>>> logger = fancylogger.getLogger(name)  # get a logger with a specific name
>>> logger.setLevel(level)  # set local debugging level
>>> # If you want the logger to be showing modulename.functionname as the name, use
>>> fancylogger.getLogger(fname=True)
>>> # you can use the handler to set a different formatter by using
>>> handler = fancylogger.logToFile('dir/filename')
>>> formatstring = '%(asctime)-15s %(levelname)-10s %(mpirank)-5s %(funcname)-15s %(threadname)-10s %(message)s'
>>> handler.setFormatter(logging.Formatter(formatstring))
>>> # setting a global loglevel will impact all logers:
>>> from vsc.utils import fancylogger
>>> logger = fancylogger.getLogger("test")
>>> logger.warning("warning")
2012-01-05 14:03:18,238 WARNING    <stdin>.test.<module>    MainThread  warning
>>> logger.debug("warning")
>>> fancylogger.setLogLevelDebug()
>>> logger.debug("warning")
2012-01-05 14:03:46,222 DEBUG      <stdin>.test.<module>    MainThread  warning

Logging to a udp server:
 - set an environment variable FANCYLOG_SERVER and FANCYLOG_SERVER_PORT (optionally)
 - this will make fancylogger log to that that server and port instead of the screen.

@date: Oct 14, 2011
@author: Jens Timmerman (Ghent University)
@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

import inspect
import logging.handlers
import os
import sys
import threading
import traceback
import logging

# constants
DEFAULT_LOGGING_FORMAT = '%(asctime)-15s %(levelname)-10s %(name)-15s %(threadname)-10s  %(message)s'
# DEFAULT_LOGGING_FORMAT= '%(asctime)-15s %(levelname)-10s %(module)-15s %(threadname)-10s %(message)s'
MAX_BYTES = 100 * 1024 * 1024  # max bytes in a file with rotating file handler
BACKUPCOUNT = 10  # number of rotating log files to save

DEFAULT_UDP_PORT = 5005

# log level constants, in order of severity
DEBUG = logging.DEBUG
INFO = logging.INFO
WARN = logging.WARN
WARNING = logging.WARNING
ERROR = logging.ERROR
EXCEPTION = logging.ERROR  # exception and error have same logging level, see logging docs
FATAL = logging.FATAL
CRITICAL = logging.CRITICAL
APOCALYPTIC = logging.CRITICAL * 2 + 1  # when log level is set to this, silence happens

# mpi rank support
try:
    from mpi4py import MPI
    _MPIRANK = str(MPI.COMM_WORLD.Get_rank())
    if MPI.COMM_WORLD.Get_size() > 1:
        # enable mpi rank when mpi is used
        DEFAULT_LOGGING_FORMAT = '%(asctime)-15s %(levelname)-10s %(name)-15s' \
                                 " mpi: %(mpirank)s %(threadname)-10s  %(message)s"
except ImportError:
    _MPIRANK = "N/A"


class FancyLogRecord(logging.LogRecord):
    """
    This class defines a custom log record.
    Adding extra specifiers is as simple as adding attributes to the log record
    """
    def __init__(self, *args, **kwargs):
        logging.LogRecord.__init__(self, *args, **kwargs)
        # modify custom specifiers here
        self.threadname = thread_name()  # actually threadName already exists?
        self.mpirank = _MPIRANK


# Custom logger that uses our log record
class FancyLogger(logging.getLoggerClass()):
    """
    This is a custom Logger class that uses the FancyLogRecord
    and has an extra method raiseException
    """
    # this attribute can be checked to know if the logger is thread aware
    _thread_aware = True

    # method definition as it is in logging, can't change this
    def makeRecord(self, name, level, pathname, lineno, msg, args, excinfo, func=None, extra=None):
        """
        overwrite make record to use a fancy record (with more options)
        """
        new_msg = msg.decode('utf8', 'replace')
        return FancyLogRecord(name, level, pathname, lineno, new_msg, args, excinfo)

    def raiseException(self, message, exception=None, catch=False):
        """
        logs an exception (as warning, since it can be caught higher up and handled)
        and raises it afterwards
            catch: boolean, try to catch raised exception and add relevant info to message
                (this will also happen if exception is not specified)
        """
        fullmessage = message

        if catch or exception is None:
            # assumes no control by codemonkey
            # lets see if there is something more to report on
            exc, detail, tb = sys.exc_info()
            if exc is not None:
                if exception is None:
                    exception = exc
                # extend the message with the traceback and some more details
                # or use self.exception() instead of self.warning()?
                tb_text = "\n".join(traceback.format_tb(tb))
                message += " (%s)" % detail
                fullmessage += " (%s\n%s)" % (detail, tb_text)

        if exception is None:
            exception = Exception

        self.warning(fullmessage)
        raise exception(message)

    def _handleFunction(self, function, levelno, **kwargs):
        """
        Walk over all handlers like callHandlers and execute function on each handler
        """
        c = self
        found = 0
        while c:
            for hdlr in c.handlers:
                found = found + 1
                if levelno >= hdlr.level:
                    function(hdlr, **kwargs)
            if not c.propagate:
                c = None  # break out
            else:
                c = c.parent

    def streamLog(self, levelno, data):
        """
        Add (continuous) data to an existing message stream (eg a stream after a logging.info()
        """

        def write_and_flush_stream(hdlr, data=None):
            """Write to stream and flush the handler"""
            if (not hasattr(hdlr, 'stream')) or hdlr.stream is None:
                # no stream or not initialised.
                raise("write_and_flush_stream failed. No active stream attribute.")
            if data is not None:
                hdlr.stream.write(data)
                hdlr.flush()

        # only log when appropriate (see logging.Logger.log())
        if self.isEnabledFor(levelno):
            self._handleFunction(write_and_flush_stream, levelno, data=data)

    def streamDebug(self, data):
        self.streamLog(logging.DEBUG, data)

    def streamInfo(self, data):
        self.streamLog(logging.INFO, data)

    def streamError(self, data):
        self.streamLog(logging.ERROR, data)

    def deprecated(self, msg, cur_ver, max_ver, depth=2, exception=None, *args, **kwargs):
        """
        Log deprecation message, throw error if current version is passed given threshold.

        Checks only major/minor version numbers (MAJ.MIN.x) by default, controlled by 'depth' argument.
        """

        cur_ver_parts = [int(x) for x in str(cur_ver).split('.')]
        max_ver_parts = [int(x) for x in str(max_ver).split('.')]

        deprecated = True
        for i in xrange(0, depth):
            if cur_ver_parts[i] < max_ver_parts[i]:
                deprecated = False
                break

        if deprecated:
            self.raiseException("DEPRECATED (since v%s) functionality used: %s" % (max_ver, msg), exception=exception)
        else:
            deprecation_msg = "Deprecated functionality, will no longer work in v%s: %s" % (max_ver, msg)
            self.warning(deprecation_msg)


def thread_name():
    """
    returns the current threads name
    """
    return threading.currentThread().getName()


def getLogger(name=None, fname=True):
    """
    returns a fancylogger
    if fname is True, the loggers name will be 'name.functionname'
    where functionname is the name of the function calling this function
    """
    nameparts = [getRootLoggerName()]
    if name:
        nameparts.append(name)
    if fname:
        nameparts.append(_getCallingFunctionName())
    fullname = ".".join(nameparts)

    return logging.getLogger(fullname)


def _getCallingFunctionName():
    """
    returns the name of the function calling the function calling this function
    (for internal use only)
    """
    try:
        return inspect.stack()[2][3]
    except Exception:
        return None


def getRootLoggerName():
    """
    returns the name of the root module
    this is the module that is actually running everything and so doing the logging
    """
    try:
        return inspect.stack()[-1][1].split('/')[-1].split('.')[0]
    except Exception:
        return None


def logToScreen(enable=True, handler=None, name=None, stdout=False):
    """
    enable (or disable) logging to screen
    returns the screenhandler (this can be used to later disable logging to screen)

    if you want to disable logging to screen, pass the earlier obtained screenhandler

    you can also pass the name of the logger for which to log to the screen
    otherwise you'll get all logs on the screen

    by default, logToScreen will log to stderr; logging to stderr instead can be done
    by setting the 'stdout' parameter to True
    """
    handleropts = {}

    if stdout:
        handleropts.update({'stream': sys.stdout})
    else:
        handleropts.update({'stream': sys.stderr})

    return _logToSomething(logging.StreamHandler,
                           handleropts,
                           loggeroption='logtoscreen',
                           name=name,
                           enable=enable,
                           handler=handler,
                           )


def logToFile(filename, enable=True, filehandler=None, name=None, max_bytes=MAX_BYTES, backup_count=BACKUPCOUNT):
    """
    enable (or disable) logging to file
    given filename
    will log to a file with the given name using a rotatingfilehandler
    this will let the file grow to MAX_BYTES and then rotate it
    saving the last BACKUPCOUNT files.

    returns the filehandler (this can be used to later disable logging to file)

    if you want to disable logging to file, pass the earlier obtained filehandler
    """
    handleropts = {'filename': filename,
                   'mode': 'a',
                   'maxBytes': max_bytes,
                   'backupCount': backup_count,
                   }
    return _logToSomething(logging.handlers.RotatingFileHandler,
                           handleropts,
                           loggeroption='logtofile',
                           name=name,
                           enable=enable,
                           handler=filehandler,
                           )


def logToUDP(hostname, port=5005, enable=True, datagramhandler=None, name=None):
    """
    enable (or disable) logging to udp
    given hostname and port.

    returns the filehandler (this can be used to later disable logging to udp)

    if you want to disable logging to udp, pass the earlier obtained filehandler,
    and set boolean = False
    """
    handleropts = {'hostname': hostname, 'port': port}
    return _logToSomething(logging.handlers.DatagramHandler,
                           handleropts,
                           loggeroption='logtoudp',
                           name=name,
                           enable=enable,
                           handler=datagramhandler,
                           )


def _logToSomething(handlerclass, handleropts, loggeroption, enable=True, name=None, handler=None):
    """
    internal function to enable (or disable) logging to handler named handlername
    handleropts is options dictionary passed to create the handler instance

    returns the handler (this can be used to later disable logging to file)

    if you want to disable logging to the handler, pass the earlier obtained handler
    """
    logger = getLogger(name, fname=False)

    if not hasattr(logger, loggeroption):
        # not set.
        setattr(logger, loggeroption, False)  # set default to False

    if enable and not getattr(logger, loggeroption):
        if handler is None:
            formatter = logging.Formatter(DEFAULT_LOGGING_FORMAT)
            handler = handlerclass(**handleropts)
            handler.setFormatter(formatter)
        logger.addHandler(handler)
        setattr(logger, loggeroption, handler)
    elif not enable:
        # stop logging to X
        if handler is None:
            if len(logger.handlers) == 1:
                # removing the last logger doesn't work
                # it will be re-added if only one handler is present
                # so we will just make it quiet by setting the loglevel extremely high
                zerohandler = logger.handlers[0]
                zerohandler.setLevel(APOCALYPTIC)  # no logging should be done with APOCALYPTIC, so silence happens
            else:  # remove the handler set with this loggeroption
                handler = getattr(logger, loggeroption)
                logger.removeHandler(handler)
        else:
            logger.removeHandler(handler)
        setattr(logger, loggeroption, False)
    return handler


def _getSysLogFacility(name=None):
    """Look for proper syslog facility
        typically the syslog/rsyslog config has an entry
            # Log anything (except mail) of level info or higher.
            # Don't log private authentication messages!
            *.info;mail.none;authpriv.none;cron.none                /var/log/messages

        name -> LOG_%s % name.upper()
        Default log facility is user /LOG_USER
    """

    if name is None:
        name = 'user'

    facility = getattr(logging.handlers.SysLogHandler, "LOG_%s" % name.upper(), logging.handlers.SysLogHandler.LOG_USER)

    return facility


def logToDevLog(enable=True, name=None, handler=None):
    """Log to syslog through /dev/log"""
    devlog = '/dev/log'
    syslogoptions = {'address': devlog,
                     'facility': _getSysLogFacility()
                     }
    return _logToSomething(logging.handlers.SysLogHandler,
                           syslogoptions, 'logtodevlog', enable=enable, name=name, handler=handler)


#  Change loglevel
def setLogLevel(level):
    """
    set a global log level (for this root logger)
    """
    getLogger(fname=False).setLevel(level)


def setLogLevelDebug():
    """
    shorthand for setting debug level
    """
    setLogLevel(logging.DEBUG)


def setLogLevelInfo():
    """
    shorthand for setting loglevel to Info
    """
    setLogLevel(logging.INFO)


def setLogLevelWarning():
    """
    shorthand for setting loglevel to Warning
    """
    setLogLevel(logging.WARNING)


def setLogLevelError():
    """
    shorthand for setting loglevel to Error
    """
    setLogLevel(logging.ERROR)


def getAllExistingLoggers():
    """
    @return: the existing loggers, in a list of C{(name, logger)} tuples
    """
    rootlogger = logging.getLogger(fname=False)
    # undocumented manager (in 2.4 and later)
    manager = rootlogger.manager

    loggerdict = getattr(manager, 'loggerDict')

    # return list of (name,logger) tuple
    return [x for x in loggerdict.items()]


def getAllNonFancyloggers():
    """
    @return: all loggers that are not fancyloggers
    """
    return [x for x in getAllExistingLoggers() if not isinstance(x[1], FancyLogger)]


def getAllFancyloggers():
    """
    Return all loggers that are not fancyloggers
    """
    return [x for x in getAllExistingLoggers() if isinstance(x[1], FancyLogger)]


# Register our logger
logging.setLoggerClass(FancyLogger)

# log to a server if FANCYLOG_SERVER is set.
_default_logTo = None
if 'FANCYLOG_SERVER' in os.environ:
    server = os.environ['FANCYLOG_SERVER']
    port = DEFAULT_UDP_PORT
    if ':' in server:
        server, port = server.split(':')

    # maybe the port was specified in the FANCYLOG_SERVER_PORT env var. this takes precedence
    if 'FANCYLOG_SERVER_PORT' in os.environ:
        port = int(os.environ['FANCYLOG_SERVER_PORT'])
    port = int(port)

    logToUDP(server, port)
    _default_logTo = logToUDP
else:
    # log to screen by default
    logToScreen(enable=True)
    _default_logTo = logToScreen


_default_handlers = logging._handlerList[:]  # There's always one


def disableDefaultHandlers():
    """Disable the default handlers on all fancyloggers
        DANGEROUS: if not other handler is available, logging will fail (and raise IOError [Errno 32] Broken pipe)
    """
    if _default_logTo is None:
        return
    for weakref_handler in _default_handlers:
        try:
            _default_logTo(enable=False, handler=weakref_handler())
        except:
            pass


def enableDefaultHandlers():
    """(re)Enable the default handlers on all fancyloggers"""
    if _default_logTo is None:
        return
    for weakref_handler in _default_handlers:
        try:
            _default_logTo(enable=True, handler=weakref_handler())
        except:
            pass
