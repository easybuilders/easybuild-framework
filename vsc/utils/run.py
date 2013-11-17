#
# Copyright 2009-2013 Ghent University
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
#

"""
Python module to execute a command

Historical overview of existing equivalent code

 - EasyBuild filetools module
    - C{run_cmd(cmd, log_ok=True, log_all=False, simple=False, inp=None, regexp=True, log_output=False, path=None)}
    - C{run_cmd_qa(cmd, qa, no_qa=None, log_ok=True, log_all=False, simple=False, regexp=True, std_qa=None, path=None)}

 - Executes a command cmd
    - looks for questions and tries to answer based on qa dictionary
    - returns exitcode and stdout+stderr (mixed)
    - no input though stdin
    - if C{log_ok} or C{log_all} are set -> will C{log.error} if non-zero exit-code
    - if C{simple} is C{True} -> instead of returning a tuple (output, ec) it will just return C{True} or C{False} signifying succes
    - C{regexp} -> Regex used to check the output for errors. If C{True} will use default (see C{parselogForError})
    - if log_output is True -> all output of command will be logged to a tempfile
    - path is the path run_cmd should chdir to before doing anything

 - Q&A: support reading stdout asynchronous and replying to a question through stdin

 - Manage C{managecommands} module C{Command} class
    - C{run} method

 - python-package-vsc-utils run module Command class
    - C{run} method

 - C{mympirun} (old)
    - C{runrun(self, cmd, returnout=False, flush=False, realcmd=False)}:
        - C{runrunnormal(self, cmd, returnout=False, flush=False)}
        - C{runrunfile(self, cmd, returnout=False, flush=False)}

 - C{hanything} commands/command module
    - C{run} method
        - fake pty support

@author: Stijn De Weirdt (Ghent University)
"""

import errno
import logging
import os
import pty
import re
import signal
import sys
import time

from vsc.utils.fancylogger import getLogger, getAllExistingLoggers


PROCESS_MODULE_ASYNCPROCESS_PATH = 'vsc.utils.asyncprocess'
PROCESS_MODULE_SUBPROCESS_PATH = 'subprocess'

RUNRUN_TIMEOUT_OUTPUT = ''
RUNRUN_TIMEOUT_EXITCODE = 123
RUNRUN_QA_MAX_MISS_EXITCODE = 124


class DummyFunction(object):
    def __getattr__(self, name):
        def dummy(*args, **kwargs):
            pass
        return dummy


class Run(object):
    """Base class for static run method"""
    INIT_INPUT_CLOSE = True
    USE_SHELL = True

    @classmethod
    def run(cls, cmd, **kwargs):
        """static method
            return (exitcode,output)
        """
        r = cls(cmd, **kwargs)
        return r._run()

    def __init__(self, cmd=None, **kwargs):
        """
        Handle initiliastion
            @param cmd: command to run
            @param input: set "simple" input
            @param startpath: directory to change to before executing command
            @param disable_log: use fake logger (won't log anything)
        """
        self.input = kwargs.pop('input', None)
        self.startpath = kwargs.pop('startpath', None)
        if kwargs.pop('disable_log', None):
            self.log = DummyFunction()  # No logging
        if not hasattr(self, 'log'):
            self.log = getLogger(self._get_log_name())

        self.cmd = cmd  # actual command

        self._cwd_before_startpath = None

        self._process_module = None
        self._process = None

        self.readsize = 1024  # number of bytes to read blocking

        self._shellcmd = None
        self._popen_named_args = None

        self._process_exitcode = None
        self._process_output = None

        self._post_exitcode_log_failure = self.log.error

        super(Run, self).__init__(**kwargs)

    def _get_log_name(self):
        """Set the log name"""
        return self.__class__.__name__

    def _prep_module(self, modulepath=None, extendfromlist=None):
        # these will provide the required Popen, PIPE and STDOUT
        if modulepath is None:
            modulepath = PROCESS_MODULE_SUBPROCESS_PATH

        fromlist = ['Popen', 'PIPE', 'STDOUT']
        if extendfromlist is not None:
            fromlist.extend(extendfromlist)

        self._process_modulepath = modulepath

        self._process_module = __import__(self._process_modulepath, globals(), locals(), fromlist)

    def _run(self):
        """actual method
        Structure

         - pre
            - convert command to shell command - DONE
            - chdir before start - DONE

            - start C{Popen} - DONE
                - support async and subprocess - DONE
                - support for
                    - filehandle
                    - PIPE - DONE
                    - pty - DONE

         - main
            - should capture exitcode and output
            - features
                - separate stdout and stderr ?
                - simple single run
                    - no timeout/waiting - DONE
                - flush to
                    - stdout
                    - logger - DONE
                    - both stdout and logger
                - process intermediate output
                    - qa
                - input
                    - qa
                    - from file ?
                    - text - DONE

         - post
            - parse with regexp
                - raise/log error on match
         - return
            - return output
                - log output
                - write to file
                - return in string - DONE
            - on C{ec > 0}
                - error - DONE
                - raiseException
            - simple
                - just return True/False

"""
        self._run_pre()
        self._wait_for_process()
        return self._run_post()

    def _run_pre(self):
        """Non-blocking start"""
        if self._process_module is None:
            self._prep_module()

        if self.startpath is not None:
            self._start_in_path()

        if self._shellcmd is None:
            self._make_shell_command()

        if self._popen_named_args is None:
            self._make_popen_named_args()

        self._init_process()

        self._init_input()

    def _run_post(self):
        self._cleanup_process()

        self._post_exitcode()

        self._post_output()

        if self.startpath is not None:
            self._return_to_previous_start_in_path()

        return self._run_return()

    def _start_in_path(self):
        """Change path before the run"""
        if self.startpath is None:
            self.log.debug("_start_in_path: no startpath set")
            return

        if os.path.exists(self.startpath):
            if os.path.isdir(self.startpath):
                try:
                    self._cwd_before_startpath = os.getcwd()  # store it some one can return to it
                    os.chdir(self.startpath)
                except:
                    self.raiseException("_start_in_path: failed to change path from %s to startpath %s" %
                                        (self._cwd_before_startpath, self.startpath))
            else:
                self.log.raiseExcpetion("_start_in_path: provided startpath %s exists but is no directory" %
                                        self.startpath)
        else:
            self.raiseException("_start_in_path: startpath %s does not exist" % self.startpath)

    def _return_to_previous_start_in_path(self):
        """Change to original path before the change to startpath"""
        if self._cwd_before_startpath is None:
            self.log.warning("_return_to_previous_start_in_path: previous cwd is empty. Not trying anything")
            return

        if os.path.exists(self._cwd_before_startpath):
            if os.path.isdir(self._cwd_before_startpath):
                try:
                    currentpath = os.getcwd()
                    if not currentpath == self.startpath:
                        self.log.warning(("_return_to_previous_start_in_path: current diretory %s does not match "
                                          "startpath %s") % (currentpath, self.startpath))
                    os.chdir(self._cwd_before_startpath)
                except:
                    self.raiseException(("_return_to_previous_start_in_path: failed to change path from current %s "
                                         "to previous path %s") % (currentpath, self._cwd_before_startpath))
            else:
                self.log.raiseExcpetion(("_return_to_previous_start_in_path: provided previous cwd path %s exists "
                                         "but is no directory") % self._cwd_before_startpath)
        else:
            self.raiseException("_return_to_previous_start_in_path: previous cwd path %s does not exist" %
                                self._cwd_before_startpath)

    def _make_popen_named_args(self, others=None):
        """Create the named args for Popen"""
        self._popen_named_args = {
                                  'stdout': self._process_module.PIPE,
                                  'stderr': self._process_module.STDOUT,
                                  'stdin': self._process_module.PIPE,
                                  'close_fds': True,
                                  'shell': self.USE_SHELL,
                                  'executable': "/bin/bash",
                                  }
        if others is not None:
            self._popen_named_args.update(others)

        self.log.debug("_popen_named_args %s" % self._popen_named_args)

    def _make_shell_command(self):
        """Convert cmd into shell command"""
        if self.cmd is None:
            self.log.raiseExcpetion("_make_shell_command: no cmd set.")

        if isinstance(self.cmd, basestring):
            self._shellcmd = self.cmd
        elif isinstance(self.cmd, (list, tuple,)):
            self._shellcmd = " ".join(self.cmd)
        else:
            self.log.raiseException("Failed to convert cmd %s (type %s) into shell command" % (self.cmd, type(self.cmd)))

    def _init_process(self):
        """Initialise the self._process"""
        try:
            self._process = self._process_module.Popen(self._shellcmd, **self._popen_named_args)
        except OSError:
            self.log.raiseException("_init_process: init Popen shellcmd %s failed: %s" % (self._shellcmd))

    def _init_input(self):
        """Handle input, if any in a simple way"""
        if self.input is not None:  # allow empty string (whatever it may mean)
            try:
                self._process.stdin.write(self.input)
            except:
                self.log.raiseException("_init_input: Failed write input %s to process" % self.input)

        if self.INIT_INPUT_CLOSE:
            self._process.stdin.close()
            self.log.debug("_init_input: process stdin closed")
        else:
            self.log.debug("_init_input: process stdin NOT closed")

    def _wait_for_process(self):
        """The main loop
            This one has most simple loop
        """
        try:
            self._process_exitcode = self._process.wait()
            self._process_output = self._read_process(-1)  # -1 is read all
        except:
            self.log.raiseException("_wait_for_process: problem during wait exitcode %s output %s" %
                                    (self._process_exitcode, self._process_output))

    def _cleanup_process(self):
        """Cleanup any leftovers from the process"""

    def _read_process(self, readsize=None):
        """Read from process, return out"""
        if readsize is None:
            readsize = self.readsize
        if readsize is None:
            readsize = -1  # read all
        self.log.debug("_read_process: going to read with readsize %s" % readsize)
        out = self._process.stdout.read(readsize)
        return out

    def _post_exitcode(self):
        """Postprocess the exitcode in self._process_exitcode"""
        if not self._process_exitcode == 0:
            self._post_exitcode_log_failure("_post_exitcode: problem occured with cmd %s: output %s" %
                                            (self.cmd, self._process_output))
        else:
            self.log.debug("_post_exitcode: success cmd %s: output %s" % (self.cmd, self._process_output))

    def _post_output(self):
        """Postprocess the output in self._process_output"""
        pass

    def _run_return(self):
        """What to return"""
        return self._process_exitcode, self._process_output

    def _killtasks(self, tasks=None, sig=signal.SIGKILL, kill_pgid=False):
        """
        Kill all tasks
            @param: tasks list of processids
            @param: sig, signal to use to kill
            @apram: kill_pgid, send kill to group
        """
        if tasks is None:
            self.log.error("killtasks no tasks passed")
        elif isinstance(tasks, basestring):
            try:
                tasks = [int(tasks)]
            except:
                self.log.error("killtasks failed to convert tasks string %s to int" % tasks)

        for pid in tasks:
            pgid = os.getpgid(pid)
            try:
                os.kill(int(pid), sig)
                if kill_pgid:
                    os.killpg(pgid, sig)
                self.log.debug("Killed %s with signal %s" % (pid, sig))
            except OSError, err:
                # ERSCH is no such process, so no issue
                if not err.errno == errno.ESRCH:
                    self.log.error("Failed to kill %s: %s" % (pid, err))
            except Exception, err:
                self.log.error("Failed to kill %s: %s" % (pid, err))

    def stop_tasks(self):
        """Cleanup current run"""
        self._killtasks(tasks=[self._process.pid])
        try:
            os.waitpid(-1, os.WNOHANG)
        except:
            pass


class RunNoWorries(Run):
    """When the exitcode is >0, log.debug instead of log.error"""
    def __init__(self, cmd, **kwargs):
        super(RunNoWorries, self).__init__(cmd, **kwargs)
        self._post_exitcode_log_failure = self.log.debug


class RunLoopException(Exception):
    def __init__(self, code, output):
        self.code = code
        self.output = output

    def __str__(self):
        return "%s code %s output %s" % (self.__class__.__name__, self.code, self.output)


class RunLoop(Run):
    """Main process is a while loop which reads the output in blocks
        need to read from time to time.
        otherwise the stdout/stderr buffer gets filled and it all stops working
    """
    LOOP_TIMEOUT_INIT = 0.1
    LOOP_TIMEOUT_MAIN = 1

    def __init__(self, cmd, **kwargs):
        super(RunLoop, self).__init__(cmd, **kwargs)
        self._loop_count = None
        self._loop_continue = None  # intial state, change this to break out the loop

    def _wait_for_process(self):
        """Loop through the process in timesteps
            collected output is run through _loop_process_output
        """
        # these are initialised outside the function (cannot be forgotten, but can be overwritten)
        self._loop_count = 0  # internal counter
        self._loop_continue = True
        self._process_output = ''

        # further initialisation
        self._loop_initialise()

        time.sleep(self.LOOP_TIMEOUT_INIT)
        ec = self._process.poll()
        try:
            while self._loop_continue and ec < 0:
                output = self._read_process()
                self._process_output += output
                # process after updating the self._process_ vars
                self._loop_process_output(output)

                if len(output) == 0:
                    time.sleep(self.LOOP_TIMEOUT_MAIN)
                ec = self._process.poll()

                self._loop_count += 1

            self.log.debug("_wait_for_process: loop stopped after %s iterations (ec %s loop_continue %s)" %
                           (self._loop_count, ec, self._loop_continue))

            # read remaining data (all of it)
            output = self._read_process(-1)

            self._process_output += output
            self._process_exitcode = ec

            # process after updating the self._process_ vars
            self._loop_process_output_final(output)
        except RunLoopException, err:
            self.log.debug('RunLoopException %s' % err)
            self._process_output = err.output
            self._process_exitcode = err.code

    def _loop_initialise(self):
        """Initialisation before the loop starts"""
        pass

    def _loop_process_output(self, output):
        """Process the output that is read in blocks
            simplest form: do nothing
        """
        pass

    def _loop_process_output_final(self, output):
        """Process the remaining output that is read
            simplest form: do the same as _loop_process_output
        """
        self._loop_process_output(output)


class RunLoopLog(RunLoop):
    LOOP_LOG_LEVEL = logging.INFO

    def _wait_for_process(self):
        # initialise the info logger
        self.log.info("Going to run cmd %s" % self._shellcmd)
        super(RunLoopLog, self)._wait_for_process()

    def _loop_process_output(self, output):
        """Process the output that is read in blocks
            send it to the logger. The logger need to be stream-like
        """
        self.log.streamLog(self.LOOP_LOG_LEVEL, output)
        super(RunLoopLog, self)._loop_process_output(output)


class RunLoopStdout(RunLoop):

    def _loop_process_output(self, output):
        """Process the output that is read in blocks
            send it to the stdout
        """
        sys.stdout.write(output)
        sys.stdout.flush()
        super(RunLoopStdout, self)._loop_process_output(output)


class RunAsync(Run):
    """Async process class"""

    def _prep_module(self, modulepath=None, extendfromlist=None):
        # these will provide the required Popen, PIPE and STDOUT
        if modulepath is None:
            modulepath = PROCESS_MODULE_ASYNCPROCESS_PATH
        if extendfromlist is None:
            extendfromlist = ['send_all', 'recv_some']
        super(RunAsync, self)._prep_module(modulepath=modulepath, extendfromlist=extendfromlist)

    def _read_process(self, readsize=None):
        """Read from async process, return out"""
        if readsize is None:
            readsize = self.readsize

        if self._process.stdout is None:
            # Nothing yet/anymore
            return ''

        try:
            if readsize is not None  and readsize < 0:
                # read all blocking (it's not why we should use async
                out = self._process.stdout.read()
            else:
                # non-blocking read (readsize is a maximum to return !
                out = self._process_module.recv_some(self._process, maxread=readsize)
            return out
        except (IOError, Exception):
            # recv_some may throw Exception
            self.log.exception("_read_process: read failed")
            return ''


class RunFile(Run):
    """Popen to filehandle"""
    def __init__(self, cmd, **kwargs):
        self.filename = kwargs.pop('filename', None)
        self.filehandle = None
        super(RunFile, self).__init__(cmd, **kwargs)

    def _make_popen_named_args(self, others=None):
        if others is None:
            if os.path.exists(self.filename):
                if os.path.isfile(self.filename):
                    self.log.warning("_make_popen_named_args: going to overwrite existing file %s" % self.filename)
                elif os.path.isdir(self.filename):
                    self.raiseException(("_make_popen_named_args: writing to filename %s impossible. Path exists and "
                                         "is a directory.") % self.filename)
                else:
                    self.raiseException("_make_popen_named_args: path exists and is not a file or directory %s" %
                                        self.filename)
            else:
                dirname = os.path.dirname(self.filename)
                if not os.path.isdir(dirname):
                    try:
                        os.makedirs(dirname)
                    except:
                        self.log.raiseException(("_make_popen_named_args: dirname %s for file %s does not exists. "
                                                 "Creating it failed.") % (dirname, self.filename))

            try:
                self.filehandle = open(self.filename, 'w')
            except:
                self.log.raiseException("_make_popen_named_args: failed to open filehandle for file %s" % self.filename)

            others = {
                      'stdout': self.filehandle,
                      }

        super(RunFile, self)._make_popen_named_args(others=others)

    def _cleanup_process(self):
        """Close the filehandle"""
        try:
            self.filehandle.close()
        except:
            self.log.raiseException("_cleanup_process: failed to close filehandle for filename %s" % self.filename)

    def _read_process(self, readsize=None):
        """Meaningless for filehandle"""
        return ''


class RunPty(Run):
    """Pty support (eg for screen sessions)"""
    def _read_process(self, readsize=None):
        """This does not work for pty"""
        return ''

    def _make_popen_named_args(self, others=None):
        if others is None:
            (master, slave) = pty.openpty()
            others = {
                'stdin': slave,
                'stdout': slave,
                'stderr': slave
                }
        super(RunPty, self)._make_popen_named_args(others=others)


class RunTimeout(RunLoop, RunAsync):
    """Question/Answer processing"""

    def __init__(self, cmd, **kwargs):
        self.timeout = float(kwargs.pop('timeout', None))
        self.start = time.time()
        super(RunTimeout, self).__init__(cmd, **kwargs)

    def _loop_process_output(self, output):
        """"""
        time_passed = time.time() - self.start
        if self.timeout is not None and  time_passed > self.timeout:
            self.log.debug("Time passed %s > timeout %s." % (time_passed, self.timeout))
            self.stop_tasks()

            # go out of loop
            raise RunLoopException(RUNRUN_TIMEOUT_EXITCODE, RUNRUN_TIMEOUT_OUTPUT)
        super(RunTimeout, self)._loop_process_output(output)


class RunQA(RunLoop, RunAsync):
    """Question/Answer processing"""
    LOOP_MAX_MISS_COUNT = 20
    INIT_INPUT_CLOSE = False

    def __init__(self, cmd, **kwargs):
        """
        Add  question and answer style running
            @param qa: dict with exact questions and answers
            @param qa_reg: dict with (named) regex-questions and answers (answers can contain named string templates)
            @param no_qa: list of regex that can block the output, but is not seen as a question.

        Regular expressions are compiled, just pass the (raw) text.
        """
        qa = kwargs.pop('qa', {})
        qa_reg = kwargs.pop('qa_reg', {})
        no_qa = kwargs.pop('no_qa', [])
        self._loop_miss_count = None  # maximum number of misses
        self._loop_previous_ouput_length = None  # track length of output through loop

        super(RunQA, self).__init__(cmd, **kwargs)

        self.qa, self.qa_reg, self.no_qa = self._parse_qa(qa, qa_reg, no_qa)

    def _parse_qa(self, qa, qa_reg, no_qa):
        """
        process the QandA dictionary
            - given initial set of Q and A (in dict), return dict of reg. exp. and A

        - make regular expression that matches the string with
            - replace whitespace
            - replace newline
        - qa_reg: question is compiled as is, and whitespace+ending is added
        """

        def escape_special(string):
            specials = '.*+?(){}[]|\$^'
            return re.sub(r"([%s])" % ''.join(['\%s' % x for x in specials]), r"\\\1", string)

        split = '[\s\n]+'
        reg_split = re.compile(r"" + split)

        def process_qa(q, a):
            split_q = [escape_special(x) for x in reg_split.split(q)]
            reg_q_txt = split.join(split_q) + split.rstrip('+') + "*$"
            # add optional split at the end
            if not a.endswith('\n'):
                a += '\n'
            reg_q = re.compile(r"" + reg_q_txt)
            if reg_q.search(q):
                return (a, reg_q)
            else:
                self.log.error("_parse_q_a process_qa: question %s converted in %s does not match itself" %
                               (q, reg_q_txt))

        new_qa = {}
        self.log.debug("new_qa: ")
        for question, answer in qa.items():
            (a, reg_q) = process_qa(question, answer)
            new_qa[reg_q] = a
            self.log.debug("new_qa[%s]: %s" % (reg_q.pattern.__repr__(), a))

        new_qa_reg = {}
        self.log.debug("new_qa_reg: ")
        for question, answer in qa_reg.items():
            reg_q = re.compile(r"" + question + r"[\s\n]*$")
            if not answer.endswith('\n'):
                answer += '\n'
            new_qa_reg[reg_q] = answer
            self.log.debug("new_qa_reg[%s]: %s" % (reg_q.pattern.__repr__(), answer))

        # simple statements, can contain wildcards
        new_no_qa = [re.compile(r"" + x + r"[\s\n]*$") for x in no_qa]
        self.log.debug("new_no_qa: %s" % [x.pattern.__repr__() for x in new_no_qa])

        return new_qa, new_qa_reg, new_no_qa

    def _loop_initialise(self):
        """Initialisation before the loop starts"""
        self._loop_miss_count = 0
        self._loop_previous_ouput_length = 0

    def _loop_process_output(self, output):
        """Process the output that is read in blocks
            check the output passed to questions available
        """
        hit = False

        self.log.debug('output %s all_output %s' % (output, self._process_output))

        # qa first and then qa_reg
        nr_qa = len(self.qa)
        for idx, (q, a) in enumerate(self.qa.items() + self.qa_reg.items()):
            res = q.search(self._process_output)
            if output and res:
                fa = a % res.groupdict()
                self.log.debug("_loop_process_output: answer %s question %s (std: %s) out %s" %
                               (fa, q.pattern, idx >= nr_qa, self._process_output[-50:]))
                self._process_module.send_all(self._process, fa)
                hit = True
                break

        if not hit:
            curoutlen = len(self._process_output)
            if curoutlen > self._loop_previous_ouput_length:
                # still progress in output, just continue (but don't reset miss counter either)
                self._loop_previous_ouput_length = curoutlen
            else:
                noqa = False
                for r in self.no_qa:
                    if r.search(self._process_output):
                        self.log.debug("_loop_process_output: no_qa found for out %s" % self._process_output[-50:])
                        noqa = True
                if not noqa:
                    self._loop_miss_count += 1
        else:
            self._loop_miss_count = 0  # rreset miss counter on hit

        if  self._loop_miss_count > self.LOOP_MAX_MISS_COUNT:
            self.log.debug("loop_process_output: max misses LOOP_MAX_MISS_COUNT %s reached. End of output: %s" %
                           (self.LOOP_MAX_MISS_COUNT, self._process_output[-500:]))
            self.stop_tasks()

            # go out of loop
            raise RunLoopException(RUNRUN_QA_MAX_MISS_EXITCODE, self._process_output)
        super(RunQA, self)._loop_process_output(output)


class RunAsyncLoop(RunLoop, RunAsync):
    """Async read in loop"""
    pass


class RunAsyncLoopLog(RunLoopLog, RunAsync):
    """Async read, log to logger"""
    pass


class RunQALog(RunLoopLog, RunQA):
    """Async loop QA with LoopLog"""
    pass


class RunQAStdout(RunLoopStdout, RunQA):
    """Async loop QA with LoopLogStdout"""
    pass


class RunAsyncLoopStdout(RunLoopStdout, RunAsync):
    """Async read, flush to stdout"""
    pass


# convenient names
# eg: from vsc.utils.run import trivial

run_simple = Run.run
run_simple_noworries = RunNoWorries.run

run_async = RunAsync.run
run_asyncloop = RunAsyncLoop.run
run_timeout = RunTimeout.run

run_to_file = RunFile.run
run_async_to_stdout = RunAsyncLoopStdout.run

run_qa = RunQA.run
run_qalog = RunQALog.run
run_qastdout = RunQAStdout.run

if __name__ == "__main__":
    run_simple('echo ok')
