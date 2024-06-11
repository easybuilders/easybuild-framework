# #
# Copyright 2009-2024 Ghent University
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
Tools to run commands.

Authors:

* Stijn De Weirdt (Ghent University)
* Dries Verdegem (Ghent University)
* Kenneth Hoste (Ghent University)
* Pieter De Baets (Ghent University)
* Jens Timmerman (Ghent University)
* Toon Willems (Ghent University)
* Ward Poelmans (Ghent University)
"""
import fcntl
import functools
import inspect
import locale
import os
import re
import shlex
import shutil
import string
import subprocess
import sys
import tempfile
import time
from collections import namedtuple
from datetime import datetime

# import deprecated functions so they can still be imported from easybuild.tools.run, for now
from easybuild._deprecated import check_async_cmd, check_log_for_errors, complete_cmd, extract_errors_from_log  # noqa
from easybuild._deprecated import get_output_from_process, parse_cmd_output, parse_log_for_error  # noqa
from easybuild._deprecated import run_cmd, run_cmd_qa  # noqa

try:
    # get_native_id is only available in Python >= 3.8
    from threading import get_native_id as get_thread_id
except ImportError:
    # get_ident is available in Python >= 3.3
    from threading import get_ident as get_thread_id

from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError, CWD_NOTFOUND_ERROR, dry_run_msg, print_msg, time_str_since
from easybuild.tools.config import build_option
from easybuild.tools.hooks import RUN_SHELL_CMD, load_hooks, run_hook
from easybuild.tools.utilities import trace_msg


_log = fancylogger.getLogger('run', fname=False)


CACHED_COMMANDS = (
    "sysctl -n hw.cpufrequency_max",  # used in get_cpu_speed (OS X)
    "sysctl -n hw.memsize",  # used in get_total_memory (OS X)
    "sysctl -n hw.ncpu",  # used in get_avail_core_count (OS X)
    "sysctl -n machdep.cpu.brand_string",  # used in get_cpu_model (OS X)
    "sysctl -n machdep.cpu.vendor",  # used in get_cpu_vendor (OS X)
    "type module",  # used in ModulesTool.check_module_function
    "type _module_raw",  # used in EnvironmentModules.check_module_function
    "ulimit -u",  # used in det_parallelism
)

RunShellCmdResult = namedtuple('RunShellCmdResult', ('cmd', 'exit_code', 'output', 'stderr', 'work_dir',
                                                     'out_file', 'err_file', 'thread_id', 'task_id'))


class RunShellCmdError(BaseException):

    def __init__(self, cmd_result, caller_info, *args, **kwargs):
        """Constructor for RunShellCmdError."""
        self.cmd = cmd_result.cmd
        self.cmd_name = os.path.basename(self.cmd.split(' ')[0])
        self.exit_code = cmd_result.exit_code
        self.work_dir = cmd_result.work_dir
        self.output = cmd_result.output
        self.out_file = cmd_result.out_file
        self.stderr = cmd_result.stderr
        self.err_file = cmd_result.err_file

        self.caller_info = caller_info

        msg = f"Shell command '{self.cmd_name}' failed!"
        super(RunShellCmdError, self).__init__(msg, *args, **kwargs)

    def print(self):
        """
        Report failed shell command for this RunShellCmdError instance
        """

        def pad_4_spaces(msg):
            return ' ' * 4 + msg

        error_info = [
            '',
            "ERROR: Shell command failed!",
            pad_4_spaces(f"full command              ->  {self.cmd}"),
            pad_4_spaces(f"exit code                 ->  {self.exit_code}"),
            pad_4_spaces(f"working directory         ->  {self.work_dir}"),
        ]

        if self.out_file is not None:
            # if there's no separate file for error/warnings, then out_file includes both stdout + stderr
            out_info_msg = "output (stdout + stderr)" if self.err_file is None else "output (stdout)         "
            error_info.append(pad_4_spaces(f"{out_info_msg}  ->  {self.out_file}"))

        if self.err_file is not None:
            error_info.append(pad_4_spaces(f"error/warnings (stderr)   ->  {self.err_file}"))

        caller_file_name, caller_line_nr, caller_function_name = self.caller_info
        called_from_info = f"'{caller_function_name}' function in {caller_file_name} (line {caller_line_nr})"
        error_info.extend([
            pad_4_spaces(f"called from               ->  {called_from_info}"),
            '',
        ])

        sys.stderr.write('\n'.join(error_info) + '\n')


def raise_run_shell_cmd_error(cmd_res):
    """
    Raise RunShellCmdError for failed shell command, after collecting additional caller info
    """

    # figure out where failing command was run
    # need to go 3 levels down:
    # 1) this function
    # 2) run_shell_cmd function
    # 3) run_shell_cmd_cache decorator
    # 4) actual caller site
    frameinfo = inspect.getouterframes(inspect.currentframe())[3]
    caller_info = (frameinfo.filename, frameinfo.lineno, frameinfo.function)

    raise RunShellCmdError(cmd_res, caller_info)


def run_shell_cmd_cache(func):
    """Function decorator to cache (and retrieve cached) results of running commands."""
    cache = {}

    @functools.wraps(func)
    def cache_aware_func(cmd, *args, **kwargs):
        """Retrieve cached result of selected commands, or run specified and collect & cache result."""
        # cache key is combination of command and input provided via stdin
        key = (cmd, kwargs.get('stdin', None))
        # fetch from cache if available, cache it if it's not, but only on cmd strings
        if isinstance(cmd, str) and key in cache:
            _log.debug("Using cached value for command '%s': %s", cmd, cache[key])
            return cache[key]
        else:
            res = func(cmd, *args, **kwargs)
            if cmd in CACHED_COMMANDS:
                cache[key] = res
            return res

    # expose clear/update methods of cache to wrapped function
    cache_aware_func.clear_cache = cache.clear
    cache_aware_func.update_cache = cache.update

    return cache_aware_func


def fileprefix_from_cmd(cmd, allowed_chars=False):
    """
    Simplify the cmd to only the allowed_chars we want in a filename

    :param cmd: the cmd (string)
    :param allowed_chars: characters allowed in filename (defaults to string.ascii_letters + string.digits + "_-")
    """
    if not allowed_chars:
        allowed_chars = f"{string.ascii_letters}{string.digits}_-"

    return ''.join([c for c in cmd if c in allowed_chars])


def create_cmd_scripts(cmd_str, work_dir, env, tmpdir):
    """
    Create helper scripts for specified command in specified directory:
    - env.sh which can be sourced to define environment in which command was run;
    - cmd.sh to create interactive (bash) shell session with working directory and environment,
      and with the command in shell history;
    """
    # Save environment variables in env.sh which can be sourced to restore environment
    if env is None:
        env = os.environ.copy()

    env_fp = os.path.join(tmpdir, 'env.sh')
    with open(env_fp, 'w') as fid:
        # unset all environment variables in current environment first to start from a clean slate;
        # we need to be careful to filter out functions definitions, so first undefine those
        fid.write("unset -f $(env | grep '%=' | cut -f1 -d'%' | sed 's/BASH_FUNC_//g')\n")
        fid.write("unset $(env | cut -f1 -d=)\n")

        # excludes bash functions (environment variables ending with %)
        fid.write('\n'.join(f'export {key}={shlex.quote(value)}' for key, value in sorted(env.items())
                            if not key.endswith('%')) + '\n')

        fid.write('\n\nPS1="eb-shell> "')

        # also change to working directory (to ensure that working directory is correct for interactive bash shell)
        fid.write(f'\ncd "{work_dir}"')

        # reset shell history to only include executed command
        fid.write(f'\nhistory -s {shlex.quote(cmd_str)}')

    # Make script that sets up bash shell with specified environment and working directory
    cmd_fp = os.path.join(tmpdir, 'cmd.sh')
    with open(cmd_fp, 'w') as fid:
        fid.write('#!/usr/bin/env bash\n')
        fid.write('# Run this script to set up a shell environment that EasyBuild used to run the shell command\n')
        fid.write('\n'.join([
            'EB_SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )',
            f'echo "# Shell for the command: {shlex.quote(cmd_str)}"',
            'echo "# Use command history, exit to stop"',
            # using -i to force interactive shell, so env.sh is also sourced when -c is used to run commands
            'bash --rcfile $EB_SCRIPT_DIR/env.sh -i "$@"',
            ]))
    os.chmod(cmd_fp, 0o775)


def _answer_question(stdout, proc, qa_patterns, qa_wait_patterns):
    """
    Private helper function to try and answer questions raised in interactive shell commands.
    """
    match_found = False

    space_line_break_pattern = r'[\s\n]+'
    space_line_break_regex = re.compile(space_line_break_pattern)

    stdout_end = stdout.decode(errors='ignore')[-1000:]
    for question, answers in qa_patterns:
        # first replace hard spaces by regular spaces, since they would mess up the join/split below
        question = question.replace(r'\ ', ' ')
        # replace spaces/line breaks with regex pattern that matches one or more spaces/line breaks,
        # and allow extra whitespace at the end
        question = space_line_break_pattern.join(space_line_break_regex.split(question)) + r'[\s\n]*$'
        regex = re.compile(question.encode())
        res = regex.search(stdout)
        if res:
            _log.debug(f"Found match for question pattern '{question}' at end of stdout: {stdout_end}")
            # if answer is specified as a list, we take the first item as current answer,
            # and add it to the back of the list (so we cycle through answers)
            if isinstance(answers, list):
                answer = answers.pop(0)
                answers.append(answer)
            elif isinstance(answers, str):
                answer = answers
            else:
                raise EasyBuildError(f"Unknown type of answers encountered for question ({question}): {answers}")

            # answer may need to be completed via pattern extracted from question
            _log.debug(f"Raw answer for question pattern '{question}': {answer}")
            answer = answer % {k: v.decode() for (k, v) in res.groupdict().items()}
            answer += '\n'
            _log.info(f"Found match for question pattern '{question}', replying with: {answer}")

            try:
                os.write(proc.stdin.fileno(), answer.encode())
            except OSError as err:
                raise EasyBuildError("Failed to answer question raised by interactive command: %s", err)

            match_found = True
            break
    else:
        _log.info("No match found for question patterns, considering question wait patterns")
        # if no match was found among question patterns,
        # take into account patterns for non-questions (qa_wait_patterns)
        for pattern in qa_wait_patterns:
            # first replace hard spaces by regular spaces, since they would mess up the join/split below
            pattern = pattern.replace(r'\ ', ' ')
            # replace spaces/line breaks with regex pattern that matches one or more spaces/line breaks,
            # and allow extra whitespace at the end
            pattern = space_line_break_pattern.join(space_line_break_regex.split(pattern)) + r'[\s\n]*$'
            regex = re.compile(pattern.encode())
            if regex.search(stdout):
                _log.info(f"Found match for wait pattern '{pattern}'")
                _log.debug(f"Found match for wait pattern '{pattern}' at end of stdout: {stdout_end}")
                match_found = True
                break
        else:
            _log.info("No match found for question wait patterns")
            _log.debug(f"No match found in question/wait patterns at end of stdout: {stdout_end}")

    return match_found


@run_shell_cmd_cache
def run_shell_cmd(cmd, fail_on_error=True, split_stderr=False, stdin=None, env=None,
                  hidden=False, in_dry_run=False, verbose_dry_run=False, work_dir=None, use_bash=True,
                  output_file=True, stream_output=None, asynchronous=False, task_id=None, with_hooks=True,
                  qa_patterns=None, qa_wait_patterns=None, qa_timeout=100):
    """
    Run specified (interactive) shell command, and capture output + exit code.

    :param fail_on_error: fail on non-zero exit code (enabled by default)
    :param split_stderr: split of stderr from stdout output
    :param stdin: input to be sent to stdin (nothing if set to None)
    :param env: environment to use to run command (if None, inherit current process environment)
    :param hidden: do not show command in terminal output (when using --trace, or with --extended-dry-run / -x)
    :param in_dry_run: also run command in dry run mode
    :param verbose_dry_run: show that command is run in dry run mode (overrules 'hidden')
    :param work_dir: working directory to run command in (current working directory if None)
    :param use_bash: execute command through bash shell (enabled by default)
    :param output_file: collect command output in temporary output file
    :param stream_output: stream command output to stdout (auto-enabled with --logtostdout if None)
    :param asynchronous: indicate that command is being run asynchronously
    :param task_id: task ID for specified shell command (included in return value)
    :param with_hooks: trigger pre/post run_shell_cmd hooks (if defined)
    :param qa_patterns: list of 2-tuples with patterns for questions + corresponding answers
    :param qa_wait_patterns: list of strings with patterns for non-questions
    :param qa_timeout: amount of seconds to wait until more output is produced when there is no matching question

    :return: Named tuple with:
    - output: command output, stdout+stderr combined if split_stderr is disabled, only stdout otherwise
    - exit_code: exit code of command (integer)
    - stderr: stderr output if split_stderr is enabled, None otherwise
    """
    def to_cmd_str(cmd):
        """
        Helper function to create string representation of specified command.
        """
        if isinstance(cmd, str):
            cmd_str = cmd.strip()
        elif isinstance(cmd, list):
            cmd_str = ' '.join(cmd)
        else:
            raise EasyBuildError(f"Unknown command type ('{type(cmd)}'): {cmd}")

        return cmd_str

    # make sure that qa_patterns is a list of 2-tuples (not a dict, or something else)
    if qa_patterns:
        if not isinstance(qa_patterns, list) or any(not isinstance(x, tuple) or len(x) != 2 for x in qa_patterns):
            raise EasyBuildError("qa_patterns passed to run_shell_cmd should be a list of 2-tuples!")

    interactive = bool(qa_patterns)

    if qa_wait_patterns is None:
        qa_wait_patterns = []

    if work_dir is None:
        try:
            work_dir = os.getcwd()
        except FileNotFoundError:
            raise EasyBuildError(CWD_NOTFOUND_ERROR)

    if with_hooks:
        hooks = load_hooks(build_option('hooks'))
        kwargs = {
            'interactive': interactive,
            'work_dir': work_dir,
        }
        hook_res = run_hook(RUN_SHELL_CMD, hooks, pre_step_hook=True, args=[cmd], kwargs=kwargs)
        if hook_res:
            cmd, old_cmd = hook_res, cmd
            _log.info("Command to run was changed by pre-%s hook: '%s' (was: '%s')", RUN_SHELL_CMD, cmd, old_cmd)

    cmd_str = to_cmd_str(cmd)

    thread_id = None
    if asynchronous:
        thread_id = get_thread_id()
        _log.info(f"Initiating running of shell command '{cmd_str}' via thread with ID {thread_id}")

    # auto-enable streaming of command output under --logtostdout/-l, unless it was disabled explicitely
    if stream_output is None and build_option('logtostdout'):
        _log.info(f"Auto-enabling streaming output of '{cmd_str}' command because logging to stdout is enabled")
        stream_output = True

    # temporary output file(s) for command output, along with helper scripts
    if output_file:
        toptmpdir = os.path.join(tempfile.gettempdir(), 'run-shell-cmd-output')
        os.makedirs(toptmpdir, exist_ok=True)
        cmd_name = fileprefix_from_cmd(os.path.basename(cmd_str.split(' ')[0]))
        tmpdir = tempfile.mkdtemp(dir=toptmpdir, prefix=f'{cmd_name}-')

        _log.info(f'run_shell_cmd: command environment of "{cmd_str}" will be saved to {tmpdir}')

        create_cmd_scripts(cmd_str, work_dir, env, tmpdir)

        cmd_out_fp = os.path.join(tmpdir, 'out.txt')
        _log.info(f'run_shell_cmd: Output of "{cmd_str}" will be logged to {cmd_out_fp}')
        if split_stderr:
            cmd_err_fp = os.path.join(tmpdir, 'err.txt')
            _log.info(f'run_shell_cmd: Errors and warnings of "{cmd_str}" will be logged to {cmd_err_fp}')
        else:
            cmd_err_fp = None
    else:
        tmpdir, cmd_out_fp, cmd_err_fp = None, None, None

    interactive_msg = 'interactive ' if interactive else ''

    # early exit in 'dry run' mode, after printing the command that would be run (unless 'hidden' is enabled)
    if not in_dry_run and build_option('extended_dry_run'):
        if not hidden or verbose_dry_run:
            silent = build_option('silent')
            msg = f"  running {interactive_msg}shell command \"{cmd_str}\"\n"
            msg += f"  (in {work_dir})"
            dry_run_msg(msg, silent=silent)

        return RunShellCmdResult(cmd=cmd_str, exit_code=0, output='', stderr=None, work_dir=work_dir,
                                 out_file=cmd_out_fp, err_file=cmd_err_fp, thread_id=thread_id, task_id=task_id)

    start_time = datetime.now()
    if not hidden:
        _cmd_trace_msg(cmd_str, start_time, work_dir, stdin, tmpdir, thread_id, interactive=interactive)

    if stream_output:
        print_msg(f"(streaming) output for command '{cmd_str}':")

    # use bash as shell instead of the default /bin/sh used by subprocess.run
    # (which could be dash instead of bash, like on Ubuntu, see https://wiki.ubuntu.com/DashAsBinSh)
    # stick to None (default value) when not running command via a shell
    if use_bash:
        bash = shutil.which('bash')
        _log.info(f"Path to bash that will be used to run shell commands: {bash}")
        executable, shell = bash, True
    else:
        executable, shell = None, False

    stderr = subprocess.PIPE if split_stderr else subprocess.STDOUT

    log_msg = f"Running {interactive_msg}shell command '{cmd_str}' in {work_dir}"
    if thread_id:
        log_msg += f" (via thread with ID {thread_id})"
    _log.info(log_msg)

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=stderr, stdin=subprocess.PIPE,
                            cwd=work_dir, env=env, shell=shell, executable=executable)

    # 'input' value fed to subprocess.run must be a byte sequence
    if stdin:
        stdin = stdin.encode()

    if stream_output or qa_patterns:

        if qa_patterns:
            # make stdout, stderr, stdin non-blocking files
            channels = [proc.stdout, proc.stdin]
            if split_stderr:
                channels += proc.stderr
            for channel in channels:
                fd = channel.fileno()
                flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        if stdin:
            proc.stdin.write(stdin)

        exit_code = None
        stdout, stderr = b'', b''
        check_interval_secs = 0.1
        time_no_match = 0

        # collect output piece-wise, while checking for questions to answer (if qa_patterns is provided)
        while exit_code is None:

            # use small read size (128 bytes) when streaming output, to make it stream more fluently
            # -1 means reading until EOF
            read_size = 128 if exit_code is None else -1

            # get output as long as output is available;
            # note: can't use proc.stdout.read without read_size argument,
            # since that will always wait until EOF
            more_stdout = True
            while more_stdout:
                more_stdout = proc.stdout.read(read_size) or b''
                _log.debug(f"Obtained more stdout: {more_stdout}")
                stdout += more_stdout

            # note: we assume that there won't be any questions in stderr output
            if split_stderr:
                more_stderr = True
                while more_stderr:
                    more_stderr = proc.stderr.read(read_size) or b''
                    stderr += more_stderr

            if qa_patterns:
                if _answer_question(stdout, proc, qa_patterns, qa_wait_patterns):
                    time_no_match = 0
                else:
                    # this will only run if the for loop above was *not* stopped by the break statement
                    time_no_match += check_interval_secs
                    if time_no_match > qa_timeout:
                        error_msg = "No matching questions found for current command output, "
                        error_msg += f"giving up after {qa_timeout} seconds!"
                        raise EasyBuildError(error_msg)
                    else:
                        _log.debug(f"{time_no_match:0.1f} seconds without match in output of interactive shell command")

            time.sleep(check_interval_secs)

            exit_code = proc.poll()

        # collect last bit of output once processed has exited
        stdout += proc.stdout.read()
        if split_stderr:
            stderr += proc.stderr.read()
    else:
        (stdout, stderr) = proc.communicate(input=stdin)

    # return output as a regular string rather than a byte sequence (and non-UTF-8 characters get stripped out)
    # getpreferredencoding normally gives 'utf-8' but can be ASCII (ANSI_X3.4-1968)
    # for Python 3.6 and older with LC_ALL=C
    encoding = locale.getpreferredencoding(False)
    output = stdout.decode(encoding, 'ignore')
    stderr = stderr.decode(encoding, 'ignore') if split_stderr else None

    # store command output to temporary file(s)
    if output_file:
        try:
            with open(cmd_out_fp, 'w') as fp:
                fp.write(output)
            if split_stderr:
                with open(cmd_err_fp, 'w') as fp:
                    fp.write(stderr)
        except IOError as err:
            raise EasyBuildError(f"Failed to dump command output to temporary file: {err}")

    res = RunShellCmdResult(cmd=cmd_str, exit_code=proc.returncode, output=output, stderr=stderr, work_dir=work_dir,
                            out_file=cmd_out_fp, err_file=cmd_err_fp, thread_id=thread_id, task_id=task_id)

    # always log command output
    cmd_name = cmd_str.split(' ')[0]
    if split_stderr:
        _log.info(f"Output of '{cmd_name} ...' shell command (stdout only):\n{res.output}")
        _log.info(f"Warnings and errors of '{cmd_name} ...' shell command (stderr only):\n{res.stderr}")
    else:
        _log.info(f"Output of '{cmd_name} ...' shell command (stdout + stderr):\n{res.output}")

    if res.exit_code == 0:
        _log.info(f"Shell command completed successfully (see output above): {cmd_str}")
    else:
        _log.warning(f"Shell command FAILED (exit code {res.exit_code}, see output above): {cmd_str}")
        if fail_on_error:
            raise_run_shell_cmd_error(res)

    if with_hooks:
        run_hook_kwargs = {
            'exit_code': res.exit_code,
            'interactive': interactive,
            'output': res.output,
            'stderr': res.stderr,
            'work_dir': res.work_dir,
        }
        run_hook(RUN_SHELL_CMD, hooks, post_step_hook=True, args=[cmd], kwargs=run_hook_kwargs)

    if not hidden:
        time_since_start = time_str_since(start_time)
        trace_msg(f"command completed: exit {res.exit_code}, ran in {time_since_start}")

    return res


def _cmd_trace_msg(cmd, start_time, work_dir, stdin, tmpdir, thread_id, interactive=False):
    """
    Helper function to construct and print trace message for command being run

    :param cmd: command being run
    :param start_time: datetime object indicating when command was started
    :param work_dir: path of working directory in which command is run
    :param stdin: stdin input value for command
    :param tmpdir: path to temporary output directory for command
    :param thread_id: thread ID (None when not running shell command asynchronously)
    :param interactive: boolean indicating whether it is an interactive command, or not
    """
    start_time = start_time.strftime('%Y-%m-%d %H:%M:%S')

    interactive = 'interactive ' if interactive else ''
    if thread_id:
        run_cmd_msg = f"running {interactive}shell command (asynchronously, thread ID: {thread_id}):"
    else:
        run_cmd_msg = f"running {interactive}shell command:"

    lines = [
        run_cmd_msg,
        f"\t{cmd}",
        f"\t[started at: {start_time}]",
        f"\t[working dir: {work_dir}]",
    ]
    if stdin:
        lines.append(f"\t[input: {stdin}]")
    if tmpdir:
        lines.append(f"\t[output and state saved to {tmpdir}]")

    trace_msg('\n'.join(lines))


def subprocess_popen_text(cmd, **kwargs):
    """Call subprocess.Popen in text mode with specified named arguments."""
    # open stdout/stderr in text mode in Popen when using Python 3
    kwargs.setdefault('stderr', subprocess.PIPE)
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True, **kwargs)


def subprocess_terminate(proc, timeout):
    """Terminate the subprocess if it hasn't finished after the given timeout"""
    try:
        proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        for pipe in (proc.stdout, proc.stderr, proc.stdin):
            if pipe:
                pipe.close()
        proc.terminate()
