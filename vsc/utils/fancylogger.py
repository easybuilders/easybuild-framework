#!/usr/bin/env python
# #
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
# #
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
 - internal debugging through environment variables
    FANCYLOGGER_GETLOGGER_DEBUG for getLogger
    FANCYLOGGER_LOGLEVEL_DEBUG for setLogLevel

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
>>> formatstring = '%(asctime)-15s %(levelname)-10s %(mpirank)-5s %(funcname)-15s %(threadName)-10s %(message)s'
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

@author: Jens Timmerman (Ghent University)
@author: Stijn De Weirdt (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

import inspect
import logging
import logging.handlers
import os
import sys
import threading
import traceback
import weakref
from distutils.version import LooseVersion

# constants
TEST_LOGGING_FORMAT = '%(levelname)-10s %(name)-15s %(threadName)-10s  %(message)s'
DEFAULT_LOGGING_FORMAT = '%(asctime)-15s ' + TEST_LOGGING_FORMAT
FANCYLOG_LOGGING_FORMAT = None

# DEFAULT_LOGGING_FORMAT= '%(asctime)-15s %(levelname)-10s %(module)-15s %(threadName)-10s %(message)s'
MAX_BYTES = 100 * 1024 * 1024  # max bytes in a file with rotating file handler
BACKUPCOUNT = 10  # number of rotating log files to save

DEFAULT_UDP_PORT = 5005

# register new loglevelname
logging.addLevelName(logging.CRITICAL * 2 + 1, 'APOCALYPTIC')
# register QUIET, EXCEPTION and FATAL alias
logging._levelNames['EXCEPTION'] = logging.ERROR
logging._levelNames['FATAL'] = logging.CRITICAL
logging._levelNames['QUIET'] = logging.WARNING


# mpi rank support
try:
    from mpi4py import MPI
    _MPIRANK = str(MPI.COMM_WORLD.Get_rank())
    if MPI.COMM_WORLD.Get_size() > 1:
        # enable mpi rank when mpi is used
        DEFAULT_LOGGING_FORMAT = '%(asctime)-15s %(levelname)-10s %(name)-15s' \
                                 " mpi: %(mpirank)s %(threadName)-10s  %(message)s"
except ImportError:
    _MPIRANK = "N/A"


class MissingLevelName(KeyError):
    pass


def getLevelInt(level_name):
    """Given a level name, return the int value"""
    if not isinstance(level_name, basestring):
        raise TypeError('Provided name %s is not a string (type %s)' % (level_name, type(level_name)))

    level = logging.getLevelName(level_name)
    if isinstance(level, basestring):
        raise MissingLevelName('Unknown loglevel name %s' % level_name)

    return level


class FancyStreamHandler(logging.StreamHandler):
    """The logging StreamHandler with uniform named arg in __init__ for selecting the stream."""
    def __init__(self, stream=None, stdout=None):
        """Initialize the stream (default is sys.stderr)
            - stream : a specific stream to use
            - stdout: if True and no stream specified, set stream to sys.stdout (False log to stderr)
        """
        logging.StreamHandler.__init__(self)
        if stream is not None:
            pass
        elif stdout is False or stdout is None:
            stream = sys.stderr
        elif stdout is True:
            stream = sys.stdout

        self.stream = stream


class FancyLogRecord(logging.LogRecord):
    """
    This class defines a custom log record.
    Adding extra specifiers is as simple as adding attributes to the log record
    """
    def __init__(self, *args, **kwargs):
        logging.LogRecord.__init__(self, *args, **kwargs)
        # modify custom specifiers here
        # we won't do this when running with -O, becuase this might be a heavy operation
        # the __debug__ operation is actually recognised by the python compiler and it won't even do a single comparison
        if __debug__:
            self.className = _getCallingClassName(depth=5)
        else:
            self.className = 'N/A'
        self.mpirank = _MPIRANK


# Custom logger that uses our log record
class FancyLogger(logging.getLoggerClass()):
    """
    This is a custom Logger class that uses the FancyLogRecord
    and has extra log methods raiseException and deprecated and
    streaming versions for debug,info,warning and error.
    """
    # this attribute can be checked to know if the logger is thread aware
    _thread_aware = True

    # method definition as it is in logging, can't change this
    def makeRecord(self, name, level, pathname, lineno, msg, args, excinfo, func=None, extra=None):
        """
        overwrite make record to use a fancy record (with more options)
        """
        logrecordcls = logging.LogRecord
        if hasattr(self, 'fancyrecord') and self.fancyrecord:
            logrecordcls = FancyLogRecord
        try:
            new_msg = str(msg)
        except UnicodeEncodeError:
            new_msg = msg.encode('utf8', 'replace')
        return logrecordcls(name, level, pathname, lineno, new_msg, args, excinfo)

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

    def deprecated(self, msg, cur_ver, max_ver, depth=2, exception=None, *args, **kwargs):
        """
        Log deprecation message, throw error if current version is passed given threshold.

        Checks only major/minor version numbers (MAJ.MIN.x) by default, controlled by 'depth' argument.
        """
        loose_cv = LooseVersion(cur_ver)
        loose_mv = LooseVersion(max_ver)

        loose_cv.version = loose_cv.version[:depth]
        loose_mv.version = loose_mv.version[:depth]

        if loose_cv >= loose_mv:
            self.raiseException("DEPRECATED (since v%s) functionality used: %s" % (max_ver, msg), exception=exception)
        else:
            deprecation_msg = "Deprecated functionality, will no longer work in v%s: %s" % (max_ver, msg)
            self.warning(deprecation_msg)

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

    def setLevelName(self, level_name):
        """Set the level by name."""
        # This is supported in py27 setLevel code, but not in py24
        self.setLevel(getLevelInt(level_name))

    def streamLog(self, levelno, data):
        """
        Add (continuous) data to an existing message stream (eg a stream after a logging.info()
        """
        if isinstance(levelno, str):
            levelno = getLevelInt(levelno)

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
        """Get a DEBUG loglevel streamLog"""
        self.streamLog('DEBUG', data)

    def streamInfo(self, data):
        """Get a INFO loglevel streamLog"""
        self.streamLog('INFO', data)

    def streamError(self, data):
        """Get a ERROR loglevel streamLog"""
        self.streamLog('ERROR', data)

    def _get_parent_info(self, verbose=True):
        """Return some logger parent related information"""
        def info(x):
            res = [x, x.name, logging.getLevelName(x.getEffectiveLevel()), logging.getLevelName(x.level), x.disabled]
            if verbose:
                res.append([(h, logging.getLevelName(h.level)) for h in x.handlers])
            return res

        parentinfo = []
        logger = self
        parentinfo.append(info(logger))
        while logger.parent is not None:
            logger = logger.parent
            parentinfo.append(info(logger))
        return parentinfo

    def get_parent_info(self, prefix, verbose=True):
        """Return pretty text version"""
        rev_parent_info = self._get_parent_info(verbose=verbose)
        return ["%s %s%s" % (prefix, " " * 4 * idx, info) for idx, info in enumerate(rev_parent_info)]

    def __copy__(self):
        """Return shallow copy, in this case reference to current logger"""
        return getLogger(self.name, fname=False, clsname=False)

    def __deepcopy__(self, memo):
        """This behaviour is undefined, fancylogger will return shallow copy, instead just crashing."""
        return self.__copy__()


def thread_name():
    """
    returns the current threads name
    """
    return threading.currentThread().getName()


def getLogger(name=None, fname=False, clsname=False, fancyrecord=None):
    """
    returns a fancylogger
    if fname is True, the loggers name will be 'name[.classname].functionname'
    if clsname is True the loggers name will be 'name.classname[.functionname]'
    This will return a logger with a fancylog record, which includes the className template for the logformat
    This can make your code a lot slower, so this can be dissabled by setting fancyrecord to False, and
    will also be disabled if a Name is set, and fancyrecord is not set to True
    """
    nameparts = [getRootLoggerName()]

    if name:
        nameparts.append(name)
    elif fancyrecord is None or fancyrecord:  # only be fancy if fancyrecord is True or no name is given
        fancyrecord = True
    fancyrecord = bool(fancyrecord)  # make sure fancyrecord is a nice bool, not None

    if clsname:
        nameparts.append(_getCallingClassName())
    if fname:
        nameparts.append(_getCallingFunctionName())
    fullname = ".".join(nameparts)

    l = logging.getLogger(fullname)
    l.fancyrecord = fancyrecord
    if os.environ.get('FANCYLOGGER_GETLOGGER_DEBUG', '0').lower() in ('1', 'yes', 'true', 'y'):
        print 'FANCYLOGGER_GETLOGGER_DEBUG',
        print 'name', name, 'fname', fname, 'fullname', fullname,
        print "getRootLoggerName: ", getRootLoggerName()
        if hasattr(l, 'get_parent_info'):
            print 'parent_info verbose'
            print "\n".join(l.get_parent_info("FANCYLOGGER_GETLOGGER_DEBUG"))
        sys.stdout.flush()
    return l


def _getCallingFunctionName():
    """
    returns the name of the function calling the function calling this function
    (for internal use only)
    """
    try:
        return inspect.stack()[2][3]
    except Exception:
        return "?"


def _getCallingClassName(depth=2):
    """
    returns the name of the class calling the function calling this function
    (for internal use only)
    """
    try:
        return inspect.stack()[depth][0].f_locals['self'].__class__.__name__

    except Exception:
        return "?"


def getRootLoggerName():
    """
    returns the name of the root module
    this is the module that is actually running everything and so doing the logging
    """
    try:
        return inspect.stack()[-1][1].split('/')[-1].split('.')[0]
    except Exception:
        return "?"


def logToScreen(enable=True, handler=None, name=None, stdout=False):
    """
    enable (or disable) logging to screen
    returns the screenhandler (this can be used to later disable logging to screen)

    if you want to disable logging to screen, pass the earlier obtained screenhandler

    you can also pass the name of the logger for which to log to the screen
    otherwise you'll get all logs on the screen

    by default, logToScreen will log to stderr; logging to stdout instead can be done
    by setting the 'stdout' parameter to True
    """
    handleropts = {'stdout': stdout}

    return _logToSomething(FancyStreamHandler,
                           handleropts,
                           loggeroption='logtoscreen_stdout_%s' % str(stdout),
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
                           loggeroption='logtofile_%s' % filename,
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
                           loggeroption='logtoudp_%s:%s' % (hostname, str(port)),
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
    logger = getLogger(name, fname=False, clsname=False)

    if not hasattr(logger, loggeroption):
        # not set.
        setattr(logger, loggeroption, False)  # set default to False

    if enable:
        if not getattr(logger, loggeroption):
            if handler is None:
                if FANCYLOG_LOGGING_FORMAT is None:
                    f_format = DEFAULT_LOGGING_FORMAT
                else:
                    f_format = FANCYLOG_LOGGING_FORMAT
                formatter = logging.Formatter(f_format)
                handler = handlerclass(**handleropts)
                handler.setFormatter(formatter)
            logger.addHandler(handler)
            setattr(logger, loggeroption, handler)
        else:
            handler = getattr(logger, loggeroption)
    elif not enable:
        # stop logging to X
        if handler is None:
            if len(logger.handlers) == 1:
                # removing the last logger doesn't work
                # it will be re-added if only one handler is present
                # so we will just make it quiet by setting the loglevel extremely high
                zerohandler = logger.handlers[0]
                # no logging should be done with APOCALYPTIC, so silence happens
                zerohandler.setLevel(getLevelInt('APOCALYPTIC'))
            else:  # remove the handler set with this loggeroption
                handler = getattr(logger, loggeroption)
                logger.removeHandler(handler)
                if hasattr(handler, 'close') and callable(handler.close):
                    handler.close()
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

    facility = getattr(logging.handlers.SysLogHandler,
                       "LOG_%s" % name.upper(), logging.handlers.SysLogHandler.LOG_USER)

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
    if isinstance(level, basestring):
        level = getLevelInt(level)
    logger = getLogger(fname=False, clsname=False)
    logger.setLevel(level)
    if os.environ.get('FANCYLOGGER_LOGLEVEL_DEBUG', '0').lower() in ('1', 'yes', 'true', 'y'):
        print "FANCYLOGGER_LOGLEVEL_DEBUG", level, logging.getLevelName(level)
        print "\n".join(logger.get_parent_info("FANCYLOGGER_LOGLEVEL_DEBUG"))
        sys.stdout.flush()


def setLogLevelDebug():
    """
    shorthand for setting debug level
    """
    setLogLevel('DEBUG')


def setLogLevelInfo():
    """
    shorthand for setting loglevel to Info
    """
    setLogLevel('INFO')


def setLogLevelWarning():
    """
    shorthand for setting loglevel to Warning
    """
    setLogLevel('WARNING')


def setLogLevelError():
    """
    shorthand for setting loglevel to Error
    """
    setLogLevel('ERROR')


def getAllExistingLoggers():
    """
    @return: the existing loggers, in a list of C{(name, logger)} tuples
    """
    rootlogger = logging.getLogger(name=False)
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


def setLogFormat(f_format):
    """Set the log format. (Has to be set before logToSomething is called)."""
    global FANCYLOG_LOGGING_FORMAT
    FANCYLOG_LOGGING_FORMAT = f_format


def setTestLogFormat():
    """Set the log format to the test format (i.e. without timestamp)."""
    setLogFormat(TEST_LOGGING_FORMAT)


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


def _enable_disable_default_handlers(enable):
    """Interact with the default handlers to enable or disable them"""
    if _default_logTo is None:
        return
    for hndlr in _default_handlers:
        # py2.7 are weakrefs, 2.6 not
        if isinstance(hndlr, weakref.ref):
            handler = hndlr()
        else:
            handler = hndlr

        try:
            _default_logTo(enable=enable, handler=handler)
        except:
            pass


def disableDefaultHandlers():
    """Disable the default handlers on all fancyloggers
        - if this is the last logger, it will just set the logLevel very high
    """
    _enable_disable_default_handlers(False)


def enableDefaultHandlers():
    """(re)Enable the default handlers on all fancyloggers"""
    _enable_disable_default_handlers(True)


def getDetailsLogLevels(fancy=True):
    """
    Return list of (name,loglevelname) pairs of existing loggers

    @param fancy: if True, returns only Fancylogger; if False, returns non-FancyLoggers,
                  anything else, return all loggers
    """
    func_map = {
        True: getAllFancyloggers,
        False: getAllNonFancyloggers,
    }
    func = func_map.get(fancy, getAllExistingLoggers)
    res = []
    for name, logger in func():
        # PlaceHolder instances have no level attribute set
        level_name = logging.getLevelName(getattr(logger, 'level', logging.NOTSET))
        res.append((name, level_name))
    return res
