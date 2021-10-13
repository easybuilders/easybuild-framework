#
# Copyright 2011-2021 Ghent University
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
A class that can be used to generated options to python scripts in a general way.

:author: Stijn De Weirdt (Ghent University)
:author: Jens Timmerman (Ghent University)
"""

import copy
import difflib
import inspect
import operator
import os
import re
import sys
import textwrap
from functools import reduce
from optparse import Option, OptionGroup, OptionParser, OptionValueError, Values
from optparse import SUPPRESS_HELP as nohelp  # supported in optparse of python v2.4

from easybuild.base.fancylogger import getLogger, setroot, setLogLevel, getDetailsLogLevels
from easybuild.base.optcomplete import autocomplete, CompleterOption
from easybuild.tools.py2vs3 import StringIO, configparser, string_type
from easybuild.tools.utilities import mk_rst_table, nub, shell_quote

try:
    import gettext
    eb_translation = None

    def get_translation():
        global eb_translation
        if not eb_translation:
            # Finding a translation is expensive, so do only once
            domain = gettext.textdomain()
            eb_translation = gettext.translation(domain, gettext.bindtextdomain(domain), fallback=True)
        return eb_translation

    def _gettext(message):
        return get_translation().gettext(message)
except ImportError:
    def _gettext(message):
        return message


HELP_OUTPUT_FORMATS = ['', 'rst', 'short', 'config']


def set_columns(cols=None):
    """Set os.environ COLUMNS variable
        - only if it is not set already
    """
    if 'COLUMNS' in os.environ:
        # do nothing
        return

    if cols is None:
        stty = '/usr/bin/stty'
        if os.path.exists(stty):
            try:
                cols = int(os.popen('%s size 2>/dev/null' % stty).read().strip().split(' ')[1])
            except (AttributeError, IndexError, OSError, ValueError):
                # do nothing
                pass

    if cols is not None:
        os.environ['COLUMNS'] = "%s" % cols


def what_str_list_tuple(name):
    """Given name, return separator, class and helptext wrt separator.
        (Currently supports strlist, strtuple, pathlist, pathtuple)
    """
    sep = ','
    helpsep = 'comma'
    if name.startswith('path'):
        sep = os.pathsep
        helpsep = 'pathsep'

    klass = None
    if name.endswith('list'):
        klass = list
    elif name.endswith('tuple'):
        klass = tuple

    return sep, klass, helpsep


def check_str_list_tuple(option, opt, value):  # pylint: disable=unused-argument
    """
    check function for strlist and strtuple type
        assumes value is comma-separated list
        returns list or tuple of strings
    """
    sep, klass, _ = what_str_list_tuple(option.type)
    split = value.split(sep)

    if klass is None:
        err = _gettext("check_strlist_strtuple: unsupported type %s" % option.type)
        raise OptionValueError(err)
    else:
        return klass(split)


def get_empty_add_flex(allvalues, self=None):
    """Return the empty element for add_flex action for allvalues"""
    empty = None

    if isinstance(allvalues, (list, tuple)):
        if isinstance(allvalues[0], string_type):
            empty = ''

    if empty is None:
        msg = "get_empty_add_flex cannot determine empty element for type %s (%s)"
        msg = msg % (type(allvalues), allvalues)
        exc_class = TypeError
        if self is None:
            raise exc_class(msg)
        else:
            self.log.raiseException(msg, exc_class)

    return empty


class ExtOption(CompleterOption):
    """Extended options class
        - enable/disable support

       Actions:
         - shorthelp : hook for shortend help messages
         - confighelp : hook for configfile-style help messages
         - store_debuglog : turns on fancylogger debugloglevel
            - also: 'store_infolog', 'store_warninglog'
         - add : add value to default (result is default + value)
             - add_first : add default to value (result is value + default)
             - extend : alias for add with strlist type
             - type must support + (__add__) and one of negate (__neg__) or slicing (__getslice__)
         - add_flex : similar to add / add_first, but replaces the first "empty" element with the default
             - the empty element is dependent of the type
                 - for {str,path}{list,tuple} this is the empty string
             - types must support the index method to determine the location of the "empty" element
             - the replacement uses +
             - e.g. a strlist type with value "0,,1"` and default [3,4] and action add_flex will
                   use the empty string '' as "empty" element, and will result in [0,3,4,1] (not [0,[3,4],1])
                   (but also a strlist with value "" and default [3,4] will result in [3,4];
                   so you can't set an empty list with add_flex)
         - date : convert into datetime.date
         - datetime : convert into datetime.datetime
         - regex: compile str in regexp
         - store_or_None
           - set default to None if no option passed,
           - set to default if option without value passed,
           - set to value if option with value passed

        Types:
          - strlist, strtuple : convert comma-separated string in a list resp. tuple of strings
          - pathlist, pathtuple : using os.pathsep, convert pathsep-separated string in a list resp. tuple of strings
              - the path separator is OS-dependent
    """
    EXTEND_SEPARATOR = ','

    ENABLE = 'enable'  # do nothing
    DISABLE = 'disable'  # inverse action

    EXTOPTION_EXTRA_OPTIONS = ('date', 'datetime', 'regex', 'add', 'add_first', 'add_flex',)
    EXTOPTION_STORE_OR = ('store_or_None', 'help')  # callback type
    EXTOPTION_LOG = ('store_debuglog', 'store_infolog', 'store_warninglog',)
    EXTOPTION_HELP = ('shorthelp', 'confighelp', 'help')

    ACTIONS = Option.ACTIONS + EXTOPTION_EXTRA_OPTIONS + EXTOPTION_STORE_OR + EXTOPTION_LOG + EXTOPTION_HELP
    STORE_ACTIONS = Option.STORE_ACTIONS + EXTOPTION_EXTRA_OPTIONS + EXTOPTION_LOG + ('store_or_None',)
    TYPED_ACTIONS = Option.TYPED_ACTIONS + EXTOPTION_EXTRA_OPTIONS + EXTOPTION_STORE_OR
    ALWAYS_TYPED_ACTIONS = Option.ALWAYS_TYPED_ACTIONS + EXTOPTION_EXTRA_OPTIONS

    TYPE_STRLIST = ['%s%s' % (name, klass) for klass in ['list', 'tuple'] for name in ['str', 'path']]
    TYPE_CHECKER = dict([(x, check_str_list_tuple) for x in TYPE_STRLIST] + list(Option.TYPE_CHECKER.items()))
    TYPES = tuple(TYPE_STRLIST + list(Option.TYPES))
    BOOLEAN_ACTIONS = ('store_true', 'store_false',) + EXTOPTION_LOG

    def __init__(self, *args, **kwargs):
        """Add logger to init"""
        CompleterOption.__init__(self, *args, **kwargs)
        self.log = getLogger(self.__class__.__name__)

    def _set_attrs(self, attrs):
        """overwrite _set_attrs to allow store_or callbacks"""
        Option._set_attrs(self, attrs)
        if self.action == 'extend':
            # alias
            self.action = 'add'
            self.type = 'strlist'
        elif self.action in self.EXTOPTION_STORE_OR:
            setattr(self, 'store_or', self.action)

            def store_or(option, opt_str, value, parser, *args, **kwargs):  # pylint: disable=unused-argument
                """Callback for supporting options with optional values."""
                # see http://stackoverflow.com/questions/1229146/parsing-empty-options-in-python
                # ugly code, optparse is crap
                if parser.rargs and not parser.rargs[0].startswith('-'):
                    val = option.check_value(opt_str, parser.rargs.pop(0))
                else:
                    val = kwargs.get('orig_default', None)

                setattr(parser.values, option.dest, val)

            # without the following, --x=y doesn't work; only --x y
            self.nargs = 0  # allow 0 args, will also use 0 args
            if self.type is None:
                # set to not None, for takes_value to return True
                self.type = 'string'

            self.callback = store_or
            self.callback_kwargs = {
                'orig_default': copy.deepcopy(self.default),
            }
            self.action = 'callback'  # act as callback

            if self.store_or in self.EXTOPTION_STORE_OR:
                self.default = None
            else:
                self.log.raiseException("_set_attrs: unknown store_or %s" % self.store_or, exception=ValueError)

    def process(self, opt, value, values, parser):
        """Handle option-as-value issues before actually processing option."""

        if hasattr(parser, 'is_value_a_commandline_option'):
            errmsg = parser.is_value_a_commandline_option(opt, value)
            if errmsg is not None:
                prefix = "%s=" % self._long_opts[0] if self._long_opts else self._short_opts[0]
                self.log.raiseException("%s. Use '%s%s' if the value is correct." % (errmsg, prefix, value),
                                        exception=OptionValueError)

        return Option.process(self, opt, value, values, parser)

    def take_action(self, action, dest, opt, value, values, parser):
        """Extended take_action"""
        orig_action = action  # keep copy

        # dest is None for actions like shorthelp and confighelp
        if dest and getattr(parser._long_opt.get('--' + dest, ''), 'store_or', '') == 'help':
            Option.take_action(self, action, dest, opt, value, values, parser)
            fn = getattr(parser, 'print_%shelp' % values.help, None)
            if fn is None:
                self.log.raiseException("Unsupported output format for help: %s" % value.help, exception=ValueError)
            else:
                fn()
            parser.exit()
        elif action == 'shorthelp':
            parser.print_shorthelp()
            parser.exit()
        elif action == 'confighelp':
            parser.print_confighelp()
            parser.exit()
        elif action in ('store_true', 'store_false',) + self.EXTOPTION_LOG:
            if action in self.EXTOPTION_LOG:
                action = 'store_true'

            if opt.startswith("--%s-" % self.ENABLE):
                # keep action
                pass
            elif opt.startswith("--%s-" % self.DISABLE):
                # reverse action
                if action in ('store_true',) + self.EXTOPTION_LOG:
                    action = 'store_false'
                elif action in ('store_false',):
                    action = 'store_true'

            if orig_action in self.EXTOPTION_LOG and action == 'store_true':
                newloglevel = orig_action.split('_')[1][:-3].upper()
                logstate = ", ".join(["(%s, %s)" % (n, l) for n, l in getDetailsLogLevels()])
                self.log.debug("changing loglevel to %s, current state: %s", newloglevel, logstate)
                setLogLevel(newloglevel)
                self.log.debug("changed loglevel to %s, previous state: %s", newloglevel, logstate)
                if hasattr(values, '_logaction_taken'):
                    values._logaction_taken[dest] = True

            Option.take_action(self, action, dest, opt, value, values, parser)

        elif action in self.EXTOPTION_EXTRA_OPTIONS:
            if action in ("add", "add_first", "add_flex",):
                # determine type from lvalue
                # set default first
                default = getattr(parser.get_default_values(), dest, None)
                if default is None:
                    default = type(value)()
                # 'add*' actions require that the default value is of type list or tuple,
                # which supports composing via '+' and slicing
                if not isinstance(default, (list, tuple)):
                    msg = "Unsupported type %s for action %s (requires list)"
                    self.log.raiseException(msg % (type(default), action))
                if action in ('add', 'add_flex'):
                    lvalue = default + value
                elif action == 'add_first':
                    lvalue = value + default

                if action == 'add_flex' and lvalue:
                    # use lvalue here rather than default to make sure there is 1 element
                    # to determine the type
                    if not hasattr(lvalue, 'index'):
                        msg = "Unsupported type %s for action %s (requires index method)"
                        self.log.raiseException(msg % (type(lvalue), action))
                    empty = get_empty_add_flex(lvalue, self=self)
                    if empty in value:
                        ind = value.index(empty)
                        lvalue = value[:ind] + default + value[ind + 1:]
                    else:
                        lvalue = value
            elif action == "regex":
                lvalue = re.compile(r'' + value)
            else:
                msg = "Unknown extended option action %s (known: %s)"
                self.log.raiseException(msg % (action, self.EXTOPTION_EXTRA_OPTIONS))
            setattr(values, dest, lvalue)
        else:
            Option.take_action(self, action, dest, opt, value, values, parser)

        # set flag to mark as passed by action (ie not by default)
        # - distinguish from setting default value through option
        if hasattr(values, '_action_taken'):
            values._action_taken[dest] = True


class ExtOptionGroup(OptionGroup):
    """An OptionGroup with support for configfile section names"""
    RESERVED_SECTIONS = [configparser.DEFAULTSECT]
    NO_SECTION = ('NO', 'SECTION')

    def __init__(self, *args, **kwargs):
        self.log = getLogger(self.__class__.__name__)
        section_name = kwargs.pop('section_name', None)
        if section_name in self.RESERVED_SECTIONS:
            self.log.raiseException('Cannot use reserved name %s for section name.' % section_name)

        OptionGroup.__init__(self, *args, **kwargs)
        self.section_name = section_name
        self.section_options = []

    def add_option(self, *args, **kwargs):
        """Extract configfile section info"""
        option = OptionGroup.add_option(self, *args, **kwargs)
        self.section_options.append(option)

        return option


class ExtOptionParser(OptionParser):
    """
    Make an option parser that limits the C{-h} / C{--shorthelp} to short opts only,
    C{-H} / C{--help} for all options.

    Pass options through environment. Like:

      - C{export PROGNAME_SOMEOPTION = value} will generate {--someoption=value}
      - C{export PROGNAME_OTHEROPTION = 1} will generate {--otheroption}
      - C{export PROGNAME_OTHEROPTION = 0} (or no or false) won't do anything

    distinction is made based on option.action in TYPED_ACTIONS allow
    C{--enable-} / C{--disable-} (using eg ExtOption option_class)
    """
    shorthelp = ('h', "--shorthelp",)
    longhelp = ('H', "--help",)

    VALUES_CLASS = Values
    DESCRIPTION_DOCSTRING = False

    ALLOW_OPTION_NAME_AS_VALUE = False  # exact match for option name (without the '-') as value
    ALLOW_OPTION_AS_VALUE = False  # exact match for option as value
    ALLOW_DASH_AS_VALUE = False  # any value starting with a '-'
    ALLOW_TYPO_AS_VALUE = True  # value with similarity score from difflib.get_close_matches

    def __init__(self, *args, **kwargs):
        """
        Following named arguments are specific to ExtOptionParser
        (the remaining ones are passed to the parent OptionParser class)

            :param help_to_string: boolean, if True, the help is written
                                   to a newly created StingIO instance
            :param help_to_file: filehandle, help is written to this filehandle
            :param envvar_prefix: string, specify the environment variable prefix
                                  to use (if you don't want the default one)
            :param process_env_options: boolean, if False, don't check the
                                        environment for options (default: True)
            :param error_env_options: boolean, if True, use error_env_options_method
                                      if an environment variable with correct envvar_prefix
                                      exists but does not correspond to an existing option
                                      (default: False)
            :param error_env_options_method: callable; method to use to report error
                                             in used environment variables (see error_env_options);
                                             accepts string value + additional
                                             string arguments for formatting the message
                                             (default: own log.error method)
        """
        self.log = getLogger(self.__class__.__name__)
        self.help_to_string = kwargs.pop('help_to_string', None)
        self.help_to_file = kwargs.pop('help_to_file', None)
        self.envvar_prefix = kwargs.pop('envvar_prefix', None)
        self.process_env_options = kwargs.pop('process_env_options', True)
        self.error_env_options = kwargs.pop('error_env_options', False)
        self.error_env_option_method = kwargs.pop('error_env_option_method', self.log.error)

        # py2.4 epilog compatibilty with py2.7 / optparse 1.5.3
        self.epilog = kwargs.pop('epilog', None)

        if 'option_class' not in kwargs:
            kwargs['option_class'] = ExtOption
        OptionParser.__init__(self, *args, **kwargs)

        # redefine formatter for py2.4 compat
        if not hasattr(self.formatter, 'format_epilog'):
            setattr(self.formatter, 'format_epilog', self.formatter.format_description)

        if self.epilog is None:
            self.epilog = []

        if hasattr(self.option_class, 'ENABLE') and hasattr(self.option_class, 'DISABLE'):
            epilogtxt = 'Boolean options support %(disable)s prefix to do the inverse of the action,'
            epilogtxt += ' e.g. option --someopt also supports --disable-someopt.'
            self.epilog.append(epilogtxt % {'disable': self.option_class.DISABLE})

        self.environment_arguments = None
        self.commandline_arguments = None

    def is_value_a_commandline_option(self, opt, value, index=None):
        """
        Determine if value is/could be an option passed via the commandline.
        If it is, return the reason why (can be used as message); or return None if it isn't.

        opt is the option flag to which the value is passed;
        index is the index of the value on the commandline (if None, it is determined from orig_rargs and rargs)

        The method tests for possible ambiguity on the commandline when the parser
        interprets the argument following an option as a value, whereas it is far more likely that
        it is (intended as) an option; --longopt=value is never considered ambiguous, regardless of the value.
        """
        # Values that are/could be options that are passed via
        # only --longopt=value is not a problem.
        # When processing the enviroment and/or configfile, we always set
        # --longopt=value, so no issues there either.

        # following checks assume that value is a string (not a store_or_None)
        if not isinstance(value, string_type):
            return None

        cmdline_index = None
        try:
            cmdline_index = self.commandline_arguments.index(value)
        except ValueError:
            # no index found for value, so not a stand-alone value
            if opt.startswith('--'):
                # only --longopt=value is unambigouos
                return None

        if index is None:
            # index of last parsed arg in commandline_arguments via remainder of rargs
            index = len(self.commandline_arguments) - len(self.rargs) - 1

        if cmdline_index is not None and index != cmdline_index:
            # This is not the value you are looking for
            return None

        if not self.ALLOW_OPTION_NAME_AS_VALUE:
            value_as_opt = '-%s' % value
            if value_as_opt in self._short_opt or value_as_opt in self._long_opt:
                return "'-%s' is a valid option" % value

        if (not self.ALLOW_OPTION_AS_VALUE) and (value in self._long_opt or value in self._short_opt):
            return "Value '%s' is also a valid option" % value

        if not self.ALLOW_DASH_AS_VALUE and value.startswith('-'):
            return "Value '%s' starts with a '-'" % value

        if not self.ALLOW_TYPO_AS_VALUE:
            possibilities = self._long_opt.keys() + self._short_opt.keys()
            # also on optionnames, i.e. without the -- / -
            possibilities.extend([x.lstrip('-') for x in possibilities])
            # max 3 options; minimum score is taken from EB experience
            matches = difflib.get_close_matches(value, possibilities, 3, 0.85)

            if matches:
                return "Value '%s' too close match to option(s) %s" % (value, ', '.join(matches))

        return None

    def set_description_docstring(self):
        """Try to find the main docstring and add it if description is not None"""
        stack = inspect.stack()[-1]
        try:
            docstr = stack[0].f_globals.get('__doc__', None)
        except (IndexError, ValueError, AttributeError):
            self.log.debug("set_description_docstring: no docstring found in latest stack globals")
            docstr = None

        if docstr is not None:
            indent = " "
            # kwargs and ** magic to deal with width
            kwargs = {
                'initial_indent': indent * 2,
                'subsequent_indent': indent * 2,
                'replace_whitespace': False,
            }
            width = os.environ.get('COLUMNS', None)
            if width is not None:
                # default textwrap width
                try:
                    kwargs['width'] = int(width)
                except ValueError:
                    pass

            # deal with newlines in docstring
            final_docstr = ['']
            for line in str(docstr).strip("\n ").split("\n"):
                final_docstr.append(textwrap.fill(line, **kwargs))
            final_docstr.append('')

            return "\n".join(final_docstr)

    def format_description(self, formatter):
        """Extend to allow docstring as description"""
        description = ''
        if self.description == 'NONE_AND_NOT_NONE':
            if self.DESCRIPTION_DOCSTRING:
                description = self.set_description_docstring()
        elif self.description:
            description = formatter.format_description(self.get_description())

        return str(description)

    def set_usage(self, usage):
        """Return usage and set try to set autogenerated description."""
        usage = OptionParser.set_usage(self, usage)

        if self.description is None:
            self.description = 'NONE_AND_NOT_NONE'

        return usage

    def get_default_values(self):
        """Introduce the ExtValues class with class constant
            - make it dynamic, otherwise the class constant is shared between multiple instances
            - class constant is used to avoid _action_taken as option in the __dict__
                - only works by using reference to object
                - same for _logaction_taken
        """
        values = OptionParser.get_default_values(self)

        class ExtValues(self.VALUES_CLASS):
            _action_taken = {}
            _logaction_taken = {}

        newvalues = ExtValues()
        newvalues.__dict__ = values.__dict__.copy()
        return newvalues

    def format_help(self, formatter=None):
        """For py2.4 compatibility reasons (missing epilog). This is the py2.7 / optparse 1.5.3 code"""
        if formatter is None:
            formatter = self.formatter
        result = []
        if self.usage:
            result.append(self.get_usage() + "\n")
        if self.description:
            result.append(self.format_description(formatter) + "\n")
        result.append(self.format_option_help(formatter))
        result.append(self.format_epilog(formatter))
        return "".join(result)

    def format_epilog(self, formatter):
        """Allow multiple epilog parts"""
        res = []
        if not isinstance(self.epilog, (list, tuple,)):
            self.epilog = [self.epilog]
        for epi in self.epilog:
            res.append(formatter.format_epilog(epi))
        return "".join(res)

    def print_shorthelp(self, fh=None):
        """Print a shortened help (no longopts)"""
        for opt in self._get_all_options():
            if opt._short_opts is None or len([x for x in opt._short_opts if len(x) > 0]) == 0:
                opt.help = nohelp
            opt._long_opts = []  # remove all long_opts

        removeoptgrp = []
        for optgrp in self.option_groups:
            # remove all option groups that have only nohelp options
            if reduce(operator.and_, [opt.help == nohelp for opt in optgrp.option_list]):
                removeoptgrp.append(optgrp)
        for optgrp in removeoptgrp:
            self.option_groups.remove(optgrp)

        self.print_help(fh)

    def check_help(self, fh):
        """Checks filehandle for help functions"""
        if self.help_to_string:
            self.help_to_file = StringIO()
        if fh is None:
            fh = self.help_to_file

        if hasattr(self.option_class, 'ENABLE') and hasattr(self.option_class, 'DISABLE'):
            def _is_enable_disable(x):
                """Does the option start with ENABLE/DISABLE"""
                _e = x.startswith("--%s-" % self.option_class.ENABLE)
                _d = x.startswith("--%s-" % self.option_class.DISABLE)
                return _e or _d
            for opt in self._get_all_options():
                # remove all long_opts with ENABLE/DISABLE naming
                opt._long_opts = [x for x in opt._long_opts if not _is_enable_disable(x)]
        return fh

    # pylint: disable=arguments-differ
    def print_help(self, fh=None):
        """Intercept print to file to print to string and remove the ENABLE/DISABLE options from help"""
        fh = self.check_help(fh)
        OptionParser.print_help(self, fh)

    def print_rsthelp(self, fh=None):
        """ Print help in rst format """
        fh = self.check_help(fh)
        result = []
        if self.usage:
            title = "Usage"
            result.extend([title, '-' * len(title), '', '``%s``' % self.get_usage().replace("Usage: ", '').strip(), ''])
        if self.description:
            title = "Description"
            result.extend([title, '-' * len(title), '', self.description, ''])

        result.append(self.format_option_rsthelp())

        rsthelptxt = '\n'.join(result)
        if fh is None:
            fh = sys.stdout
        fh.write(rsthelptxt)

    def format_option_rsthelp(self, formatter=None):
        """ Formatting for help in rst format """
        if not formatter:
            formatter = self.formatter
        formatter.store_option_strings(self)

        res = []
        titles = ["Option flag", "Option description"]

        all_opts = [("Help options", self.option_list)] + \
                   [(group.title, group.option_list) for group in self.option_groups]
        for title, opts in all_opts:
            values = []
            res.extend([title, '-' * len(title)])
            for opt in opts:
                if opt.help is not nohelp:
                    values.append(['``%s``' % formatter.option_strings[opt], formatter.expand_default(opt)])

            res.extend(mk_rst_table(titles, map(list, zip(*values))))
            res.append('')

        return '\n'.join(res)

    def print_confighelp(self, fh=None):
        """Print help as a configfile."""

        # walk through all optiongroups
        # append where necessary, keep track of sections
        all_groups = {}
        sections = []
        for gr in self.option_groups:
            section = gr.section_name
            if not (section is None or section == ExtOptionGroup.NO_SECTION):
                if section not in sections:
                    sections.append(section)
                ag = all_groups.setdefault(section, [])
                ag.extend(gr.section_options)

        # set MAIN section first if exists
        main_idx = sections.index('MAIN')
        if main_idx > 0:  # not needed if it main_idx == 0
            sections.remove('MAIN')
            sections.insert(0, 'MAIN')

        option_template = "# %(help)s\n#%(option)s=\n"
        txt = ''
        for section in sections:
            txt += "[%s]\n" % section
            for option in all_groups[section]:
                data = {
                    'help': option.help,
                    'option': option.get_opt_string().lstrip('-'),
                }
                txt += option_template % data
            txt += "\n"

        # overwrite the format_help to be able to use the the regular print_help
        def format_help(*args, **kwargs):  # pylint: disable=unused-argument
            return txt

        self.format_help = format_help
        self.print_help(fh)

    def _add_help_option(self):
        """Add shorthelp and longhelp"""
        self.add_option("-%s" % self.shorthelp[0],
                        self.shorthelp[1],  # *self.shorthelp[1:], syntax error in Python 2.4
                        action="shorthelp",
                        help=_gettext("show short help message and exit"))
        self.add_option("-%s" % self.longhelp[0],
                        self.longhelp[1],  # *self.longhelp[1:], syntax error in Python 2.4
                        action="help",
                        type="choice",
                        choices=HELP_OUTPUT_FORMATS,
                        default=HELP_OUTPUT_FORMATS[0],
                        metavar='OUTPUT_FORMAT',
                        help=_gettext("show full help message and exit"))
        self.add_option("--confighelp",
                        action="confighelp",
                        help=_gettext("show help as annotated configfile"))

    def _get_args(self, args):
        """Prepend the options set through the environment"""
        self.commandline_arguments = OptionParser._get_args(self, args)
        self.get_env_options()
        return self.environment_arguments + self.commandline_arguments  # prepend the environment options as longopts

    def get_env_options_prefix(self):
        """Return the prefix to use for options passed through the environment"""
        # sys.argv[0] or the prog= argument of the optionparser, strip possible extension
        if self.envvar_prefix is None:
            self.envvar_prefix = self.get_prog_name().rsplit('.', 1)[0].upper()
        return self.envvar_prefix

    def get_env_options(self):
        """Retrieve options from the environment: prefix_longopt.upper()"""
        self.environment_arguments = []

        if not self.process_env_options:
            self.log.debug("Not processing environment for options")
            return

        if self.envvar_prefix is None:
            self.get_env_options_prefix()

        epilogprefixtxt = "All long option names can be passed as environment variables. "
        epilogprefixtxt += "Variable name is %(prefix)s_<LONGNAME> "
        epilogprefixtxt += "eg. --some-opt is same as setting %(prefix)s_SOME_OPT in the environment."
        self.epilog.append(epilogprefixtxt % {'prefix': self.envvar_prefix})

        candidates = dict([(k, v) for k, v in os.environ.items() if k.startswith("%s_" % self.envvar_prefix)])

        for opt in self._get_all_options():
            if opt._long_opts is None:
                continue
            for lo in opt._long_opts:
                if len(lo) == 0:
                    continue
                env_opt_name = "%s_%s" % (self.envvar_prefix, lo.lstrip('-').replace('-', '_').upper())
                val = candidates.pop(env_opt_name, None)
                if val is not None:
                    if opt.action in opt.TYPED_ACTIONS:  # not all typed actions are mandatory, but let's assume so
                        self.environment_arguments.append("%s=%s" % (lo, val))
                    else:
                        # interpretation of values: 0/no/false means: don't set it
                        if ("%s" % val).lower() not in ("0", "no", "false",):
                            self.environment_arguments.append("%s" % lo)
                else:
                    self.log.debug("Environment variable %s is not set" % env_opt_name)

        if candidates:
            msg = "Found %s environment variable(s) that are prefixed with %s but do not match valid option(s): %s"
            if self.error_env_options:
                logmethod = self.error_env_option_method
            else:
                logmethod = self.log.debug
            logmethod(msg, len(candidates), self.envvar_prefix, ','.join(sorted(candidates)))

        self.log.debug("Environment variable options with prefix %s: %s",
                       self.envvar_prefix, self.environment_arguments)
        return self.environment_arguments

    def get_option_by_long_name(self, name):
        """Return the option matching the long option name"""
        for opt in self._get_all_options():
            if opt._long_opts is None:
                continue
            for lo in opt._long_opts:
                if len(lo) == 0:
                    continue
                dest = lo.lstrip('-')
                if name == dest:
                    return opt

        return None


class GeneralOption(object):
    """
    'Used-to-be simple' wrapper class for option parsing

    Options with go_ prefix are for this class, the remainder is passed to the parser
        - go_args : use these instead of of sys.argv[1:]
        - go_columns : specify column width (in columns)
        - go_useconfigfiles : use configfiles or not (default set by CONFIGFILES_USE)
            if True, an option --configfiles will be added
        - go_configfiles : list of configfiles to parse. Uses ConfigParser.read; last file wins
        - go_configfiles_initenv : section dict of key/value dict; inserted before configfileparsing
            As a special case, using all uppercase key in DEFAULT section with a case-sensitive
            configparser can be used to set "constants" for easy interpolation in all sections.
        - go_loggername : name of logger, default classname
        - go_mainbeforedefault : set the main options before the default ones
        - go_autocompleter : dict with named options to pass to the autocomplete call (eg arg_completer)
            if is None: disable autocompletion; default is {} (ie no extra args passed)

    Sections starting with the string 'raw_' in the sectionname will be parsed as raw sections,
    meaning there will be no interpolation of the strings. This comes in handy if you want to configure strings
    with templates in them.

    Options process order (last one wins)
        0. default defined with option
        1. value in (last) configfile (last configfile wins)
        2. options parsed by option parser
        In case the ExtOptionParser is used
            0. value set through environment variable
            1. value set through commandline option
    """
    OPTIONNAME_PREFIX_SEPARATOR = '-'

    DEBUG_OPTIONS_BUILD = False  # enable debug mode when building the options ?

    USAGE = None
    ALLOPTSMANDATORY = True
    PARSER = ExtOptionParser
    INTERSPERSED = True  # mix args with options

    CONFIGFILES_USE = True
    CONFIGFILES_RAISE_MISSING = False
    CONFIGFILES_INIT = []  # initial list of defaults, overwritten by go_configfiles options
    CONFIGFILES_IGNORE = []
    CONFIGFILES_MAIN_SECTION = 'MAIN'  # sectionname that contains the non-grouped/non-prefixed options
    CONFIGFILE_PARSER = configparser.SafeConfigParser
    CONFIGFILE_CASESENSITIVE = True

    METAVAR_DEFAULT = True  # generate a default metavar
    METAVAR_MAP = None  # metvar, list of longopts map

    OPTIONGROUP_SORTED_OPTIONS = True

    PROCESSED_OPTIONS_PROPERTIES = ['type', 'default', 'action', 'opt_name', 'prefix', 'section_name']

    VERSION = None  # set the version (will add --version)

    DEFAULTSECT = configparser.DEFAULTSECT
    DEFAULT_LOGLEVEL = None
    DEFAULT_CONFIGFILES = None
    DEFAULT_IGNORECONFIGFILES = None

    SETROOTLOGGER = False

    def __init__(self, **kwargs):
        go_args = kwargs.pop('go_args', None)
        self.no_system_exit = kwargs.pop('go_nosystemexit', None)  # unit test option
        self.use_configfiles = kwargs.pop('go_useconfigfiles', self.CONFIGFILES_USE)  # use or ignore config files
        self.configfiles = kwargs.pop('go_configfiles', self.CONFIGFILES_INIT[:])  # configfiles to parse
        configfiles_initenv = kwargs.pop('go_configfiles_initenv', None)  # initial environment for configfiles to parse
        prefixloggername = kwargs.pop('go_prefixloggername', False)  # name of logger is same as envvar prefix
        mainbeforedefault = kwargs.pop('go_mainbeforedefault', False)  # Set the main options before the default ones
        autocompleter = kwargs.pop('go_autocompleter', {})  # Pass these options to the autocomplete call

        if self.SETROOTLOGGER:
            setroot()

        set_columns(kwargs.pop('go_columns', None))

        kwargs.update({
            'option_class': ExtOption,
            'usage': kwargs.get('usage', self.USAGE),
            'version': self.VERSION,
        })

        self.parser = self.PARSER(**kwargs)
        self.parser.allow_interspersed_args = self.INTERSPERSED

        self.configfile_parser = None
        self.configfile_remainder = {}

        loggername = self.__class__.__name__
        if prefixloggername:
            prefix = self.parser.get_env_options_prefix()
            if prefix is not None and len(prefix) > 0:
                loggername = prefix.replace('.', '_')  # . indicate hierarchy in logging land

        self.log = getLogger(name=loggername)
        self.options = None
        self.args = None

        self.autocompleter = autocompleter

        self.auto_prefix = None
        self.auto_section_name = None

        self.processed_options = {}

        self.config_prefix_sectionnames_map = {}

        self.set_go_debug()

        if mainbeforedefault:
            self.main_options()
            self._default_options()
        else:
            self._default_options()
            self.main_options()

        self.parseoptions(options_list=go_args)

        if self.options is not None:
            # None for eg usage/help
            self.configfile_parser_init(initenv=configfiles_initenv)
            self.parseconfigfiles()

            self._set_default_loglevel()

            self.postprocess()

            self.validate()

    def set_go_debug(self):
        """Check if debug options are on and then set fancylogger to debug.
        This is not the default way to set debug, it enables debug logging
        in an earlier stage to debug generaloption itself.
        """
        if self.options is None:
            if self.DEBUG_OPTIONS_BUILD:
                setLogLevel('DEBUG')

    def _default_options(self):
        """Generate default options: debug/log and configfile"""
        self._make_debug_options()
        self._make_configfiles_options()

    def _make_debug_options(self):
        """Add debug/logging options: debug and info"""
        self._logopts = {
            'debug': ("Enable debug log mode", None, "store_debuglog", False, 'd'),
            'info': ("Enable info log mode", None, "store_infolog", False),
            'quiet': ("Enable quiet/warning log mode", None, "store_warninglog", False),
        }

        descr = ['Debug and logging options', '']
        self.log.debug("Add debug and logging options descr %s opts %s (no prefix)" % (descr, self._logopts))
        self.add_group_parser(self._logopts, descr, prefix=None)

    def _set_default_loglevel(self):
        """Set the default loglevel if no logging options are set"""
        loglevel_set = sum([getattr(self.options, name, False) for name in self._logopts.keys()])
        if not loglevel_set and self.DEFAULT_LOGLEVEL is not None:
            setLogLevel(self.DEFAULT_LOGLEVEL)

    def _make_configfiles_options(self):
        """Add configfiles option"""
        opts = {
            'configfiles': ("Parse (additional) configfiles", "strlist", "add", self.DEFAULT_CONFIGFILES),
            'ignoreconfigfiles': ("Ignore configfiles", "strlist", "add", self.DEFAULT_IGNORECONFIGFILES),
        }
        descr = ['Configfile options', '']
        self.log.debug("Add configfiles options descr %s opts %s (no prefix)" % (descr, opts))
        self.add_group_parser(opts, descr, prefix=None, section_name=ExtOptionGroup.NO_SECTION)

    def main_options(self):
        """Create the main options automatically"""
        # make_init is deprecated
        if hasattr(self, 'make_init'):
            self.log.debug('main_options: make_init is deprecated. Rename function to main_options.')
            getattr(self, 'make_init')()
        else:
            # function names which end with _options and do not start with main or _
            reg_main_options = re.compile("^(?!_|main).*_options$")
            names = [x for x in dir(self) if reg_main_options.search(x)]
            if len(names) == 0:
                self.log.error("main_options: no options functions implemented")
            else:
                for name in names:
                    fn = getattr(self, name)
                    if callable(fn):  # inspect.isfunction fails beacuse this is a boundmethod
                        self.auto_section_name = '_'.join(name.split('_')[:-1])
                        self.log.debug('main_options: adding options from %s (auto_section_name %s)' %
                                       (name, self.auto_section_name))
                        fn()
                        self.auto_section_name = None  # reset it

    def make_option_metavar(self, longopt, details):  # pylint: disable=unused-argument
        """Generate the metavar for option longopt
        @type longopt: str
        @type details: tuple
        """
        if self.METAVAR_MAP is not None:
            for metavar, longopts in self.METAVAR_MAP.items():
                if longopt in longopts:
                    return metavar

        if self.METAVAR_DEFAULT:
            return longopt.upper()

    def add_group_parser(self, opt_dict, description, prefix=None, otherdefaults=None, section_name=None):
        """Make a group parser from a dict


        @type opt_dict: dict
        @type description: a 2 element list (short and long description)
        @section_name: str, the name of the section group in the config file.

        :param opt_dict: options, with the form C{"long_opt" : value}.
        Value is a C{tuple} containing
        C{(help,type,action,default(,optional string=short option; list/tuple=choices; dict=add_option kwargs))}

        help message passed through opt_dict will be extended with type and default

        If section_name is None, prefix will be used. If prefix is None or '', 'DEFAULT' is used.

        """
        if opt_dict is None:
            # skip opt_dict None
            # if opt_dict is empty dict {}, the eg the descritionis added to the help
            self.log.debug("Skipping opt_dict %s with description %s prefix %s" %
                           (opt_dict, description, prefix))
            return

        if otherdefaults is None:
            otherdefaults = {}

        self.log.debug("add_group_parser: passed prefix %s section_name %s" % (prefix, section_name))
        self.log.debug("add_group_parser: auto_prefix %s auto_section_name %s" %
                       (self.auto_prefix, self.auto_section_name))

        if prefix is None:
            if self.auto_prefix is None:
                prefix = ''
            else:
                prefix = self.auto_prefix

        if section_name is None:
            if prefix is not None and len(prefix) > 0 and not (prefix == self.auto_prefix):
                section_name = prefix
            elif self.auto_section_name is not None and len(self.auto_section_name) > 0:
                section_name = self.auto_section_name
            else:
                section_name = self.CONFIGFILES_MAIN_SECTION

        self.log.debug("add_group_parser: set prefix %s section_name %s" % (prefix, section_name))

        # add the section name to the help output
        if section_name is None or section_name == ExtOptionGroup.NO_SECTION:
            section_help = ''
        else:
            section_help = " (configfile section %s)" % (section_name)

        if description[1]:
            short_description = description[0]
            long_description = "%s%s" % (description[1], section_help)
        else:
            short_description = "%s%s" % (description[0], section_help)
            long_description = description[1]

        opt_grp = ExtOptionGroup(self.parser, short_description, long_description, section_name=section_name)
        keys = list(opt_dict.keys())
        if self.OPTIONGROUP_SORTED_OPTIONS:
            keys.sort()  # alphabetical
        for key in keys:
            completer = None

            details = opt_dict[key]

            hlp = details[0]
            typ = details[1]
            action = details[2]
            default = details[3]
            # easy override default with otherdefault
            if key in otherdefaults:
                default = otherdefaults.get(key)

            extra_help = []
            if typ in ExtOption.TYPE_STRLIST:
                sep, klass, helpsep = what_str_list_tuple(typ)
                extra_help.append("type %s-separated %s" % (helpsep, klass.__name__))
            elif typ is not None:
                extra_help.append("type %s" % typ)

            if default is not None:
                if len(str(default)) == 0:
                    extra_help.append("default: ''")  # empty string
                elif typ in ExtOption.TYPE_STRLIST:
                    extra_help.append("default: %s" % sep.join(default))
                else:
                    extra_help.append("default: %s" % default)

                # for boolean options enabled by default, mention that they can be disabled using --disable-*
                if default is True:
                    extra_help.append("disable with --disable-%s" % key)

            if len(extra_help) > 0:
                hlp += " (%s)" % ("; ".join(extra_help))

            opt_name, opt_dest = self.make_options_option_name_and_destination(prefix, key)

            args = ["--%s" % opt_name]

            # this has to match PROCESSED_OPTIONS_PROPERTIES
            self.processed_options[opt_dest] = [typ, default, action, opt_name, prefix, section_name]  # add longopt
            if len(self.processed_options[opt_dest]) != len(self.PROCESSED_OPTIONS_PROPERTIES):
                self.log.raiseException("PROCESSED_OPTIONS_PROPERTIES length mismatch")

            nameds = {
                'dest': opt_dest,
                'action': action,
            }
            metavar = self.make_option_metavar(key, details)
            if metavar is not None:
                nameds['metavar'] = metavar

            if default is not None:
                nameds['default'] = default

            if typ:
                nameds['type'] = typ

            passed_kwargs = {}
            if len(details) >= 5:
                for extra_detail in details[4:]:
                    if isinstance(extra_detail, (list, tuple,)):
                        # choices
                        nameds['choices'] = ["%s" % x for x in extra_detail]  # force to strings
                        hlp += ' (choices: %s)' % ', '.join(nameds['choices'])
                    elif isinstance(extra_detail, string_type) and len(extra_detail) == 1:
                        args.insert(0, "-%s" % extra_detail)
                    elif isinstance(extra_detail, (dict,)):
                        # extract any optcomplete completer hints
                        completer = extra_detail.pop('completer', None)

                        # add remainder
                        passed_kwargs.update(extra_detail)
                    else:
                        self.log.raiseException("add_group_parser: unknown extra detail %s" % extra_detail)

            # add help
            nameds['help'] = _gettext(hlp)

            if hasattr(self.parser.option_class, 'ENABLE') and hasattr(self.parser.option_class, 'DISABLE'):
                if action in self.parser.option_class.BOOLEAN_ACTIONS:
                    args.append("--%s-%s" % (self.parser.option_class.ENABLE, opt_name))
                    args.append("--%s-%s" % (self.parser.option_class.DISABLE, opt_name))

            # force passed_kwargs as final nameds
            nameds.update(passed_kwargs)
            opt = opt_grp.add_option(*args, **nameds)

            if completer is not None:
                opt.completer = completer

        self.parser.add_option_group(opt_grp)

        # map between prefix and sectionnames
        prefix_section_names = self.config_prefix_sectionnames_map.setdefault(prefix, [])
        if section_name not in prefix_section_names:
            prefix_section_names.append(section_name)
            self.log.debug("Added prefix %s to list of sectionnames for %s" % (prefix, section_name))

    def default_parseoptions(self):
        """Return default options"""
        return sys.argv[1:]

    def autocomplete(self):
        """Set the autocompletion magic via optcomplete"""
        # very basic for now, no special options
        if self.autocompleter is None:
            self.log.debug('self.autocompleter is None, disabling autocompleter')
        else:
            self.log.debug('setting autocomplete with args %s' % self.autocompleter)
            autocomplete(self.parser, **self.autocompleter)

    def parseoptions(self, options_list=None):
        """Parse the options"""
        if options_list is None:
            options_list = self.default_parseoptions()

        self.autocomplete()

        try:
            (self.options, self.args) = self.parser.parse_args(options_list)
        except SystemExit as err:
            self.log.debug("parseoptions: parse_args err %s code %s" % (err, err.code))
            if self.no_system_exit:
                return
            else:
                sys.exit(err.code)

        self.log.debug("parseoptions: options from environment %s" % (self.parser.environment_arguments))
        self.log.debug("parseoptions: options from commandline %s" % (self.parser.commandline_arguments))

        # args should be empty, since everything is optional
        if len(self.args) > 1:
            self.log.debug("Found remaining args %s" % self.args)
            if self.ALLOPTSMANDATORY:
                self.parser.error("Invalid arguments args %s" % self.args)

        self.log.debug("Found options %s args %s" % (self.options, self.args))

    def configfile_parser_init(self, initenv=None):
        """
        Initialise the configparser to use.

            :params initenv: insert initial environment into the configparser.
                It is a dict of dicts; the first level key is the section name;
                the 2nd level key,value is the key=value.
                All section names, keys and values are converted to strings.
        """
        self.configfile_parser = self.CONFIGFILE_PARSER()

        # make case sensitive
        if self.CONFIGFILE_CASESENSITIVE:
            self.log.debug('Initialise case sensitive configparser')
            self.configfile_parser.optionxform = str
        else:
            self.log.debug('Initialise case insensitive configparser')
            self.configfile_parser.optionxform = str.lower

        # insert the initenv in the parser
        if initenv is None:
            initenv = {}

        for name, section in initenv.items():
            name = str(name)
            if name == self.DEFAULTSECT:
                # is protected/reserved (and hidden)
                pass
            elif not self.configfile_parser.has_section(name):
                self.configfile_parser.add_section(name)

            for key, value in section.items():
                self.configfile_parser.set(name, str(key), str(value))

    def parseconfigfiles(self):
        """Parse configfiles"""
        if not self.use_configfiles:
            self.log.debug('parseconfigfiles: use_configfiles False, skipping configfiles')
            return

        if self.configfiles is None:
            self.configfiles = []

        self.log.debug("parseconfigfiles: configfiles initially set %s" % self.configfiles)

        option_configfiles = self.options.__dict__.get('configfiles', [])  # empty list, will win so no defaults
        option_ignoreconfigfiles = self.options.__dict__.get('ignoreconfigfiles', self.CONFIGFILES_IGNORE)

        self.log.debug("parseconfigfiles: configfiles set through commandline %s" % option_configfiles)
        self.log.debug("parseconfigfiles: ignoreconfigfiles set through commandline %s" % option_ignoreconfigfiles)
        if option_configfiles is not None:
            self.configfiles.extend(option_configfiles)

        if option_ignoreconfigfiles is None:
            option_ignoreconfigfiles = []

        # Configparser fails on broken config files
        # - if config file doesn't exist, it's no issue
        configfiles = []
        for fn in self.configfiles:
            if not os.path.isfile(fn):
                if self.CONFIGFILES_RAISE_MISSING:
                    self.log.raiseException("parseconfigfiles: configfile %s not found." % fn)
                else:
                    self.log.debug("parseconfigfiles: configfile %s not found, will be skipped" % fn)

            if fn in option_ignoreconfigfiles:
                self.log.debug("parseconfigfiles: configfile %s will be ignored", fn)
            else:
                configfiles.append(fn)

        try:
            parsed_files = self.configfile_parser.read(configfiles)
        except Exception:
            self.log.raiseException("parseconfigfiles: problem during read")

        self.log.debug("parseconfigfiles: following files were parsed %s" % parsed_files)
        self.log.debug("parseconfigfiles: following files were NOT parsed %s" %
                       [x for x in configfiles if x not in parsed_files])
        self.log.debug("parseconfigfiles: sections (w/o %s) %s" %
                       (self.DEFAULTSECT, self.configfile_parser.sections()))

        # walk through list of section names
        # - look for options set though config files
        configfile_values = {}
        configfile_options_default = {}
        configfile_cmdline = []
        configfile_cmdline_dest = []  # expected destinations

        # won't parse
        cfg_sections = self.config_prefix_sectionnames_map.values()  # without DEFAULT
        for section in cfg_sections:
            if section not in self.config_prefix_sectionnames_map.values():
                self.log.warning("parseconfigfiles: found section %s, won't be parsed" % section)
                continue

        # add any non-option related configfile data to configfile_remainder dict
        cfg_sections_flat = [name for section_names in cfg_sections for name in section_names]
        for section in self.configfile_parser.sections():
            if section not in cfg_sections_flat:
                self.log.debug("parseconfigfiles: found section %s, adding to remainder" % section)
                remainder = self.configfile_remainder.setdefault(section, {})
                # parse the remaining options, sections starting with 'raw_'
                # as their name will be considered raw sections
                for opt, val in self.configfile_parser.items(section, raw=(section.startswith('raw_'))):
                    remainder[opt] = val

        # options are passed to the commandline option parser
        for prefix, section_names in self.config_prefix_sectionnames_map.items():
            for section in section_names:
                # default section is treated separate in ConfigParser
                if not self.configfile_parser.has_section(section):
                    self.log.debug('parseconfigfiles: no section %s' % str(section))
                    continue
                elif section == ExtOptionGroup.NO_SECTION:
                    self.log.debug('parseconfigfiles: ignoring NO_SECTION %s' % str(section))
                    continue
                elif section.lower() == 'default':
                    self.log.debug('parseconfigfiles: ignoring default section %s' % section)
                    continue

                for opt, val in self.configfile_parser.items(section):
                    self.log.debug('parseconfigfiles: section %s option %s val %s' % (section, opt, val))

                    opt_name, opt_dest = self.make_options_option_name_and_destination(prefix, opt)
                    actual_option = self.parser.get_option_by_long_name(opt_name)
                    if actual_option is None:
                        # don't fail on DEFAULT UPPERCASE options in case-sensitive mode.
                        in_def = self.configfile_parser.has_option(self.DEFAULTSECT, opt)
                        if in_def and self.CONFIGFILE_CASESENSITIVE and opt == opt.upper():
                            self.log.debug(('parseconfigfiles: no option corresponding with '
                                            'opt %s dest %s in section %s but found all uppercase '
                                            'in DEFAULT section. Skipping.') % (opt, opt_dest, section))
                            continue
                        else:
                            self.log.raiseException(('parseconfigfiles: no option corresponding with '
                                                     'opt %s dest %s in section %s') % (opt, opt_dest, section))

                    configfile_options_default[opt_dest] = actual_option.default

                    # log actions require special care
                    # if any log action was already taken before, it would precede the one from the configfile
                    # however, multiple logactions in a configfile (or environment for that matter) have
                    # undefined behaviour
                    is_log_action = actual_option.action in ExtOption.EXTOPTION_LOG
                    log_action_taken = getattr(self.options, '_logaction_taken', False)
                    if is_log_action and log_action_taken:
                        # value set through take_action. do not modify by configfile
                        self.log.debug(('parseconfigfiles: log action %s (value %s) found,'
                                        ' but log action already taken. Ignoring.') % (opt_dest, val))
                    elif actual_option.action in ExtOption.BOOLEAN_ACTIONS:
                        try:
                            newval = self.configfile_parser.getboolean(section, opt)
                            self.log.debug(('parseconfigfiles: getboolean for option %s value %s '
                                            'in section %s returned %s') % (opt, val, section, newval))
                        except Exception:
                            self.log.raiseException(('parseconfigfiles: failed to getboolean for option %s value %s '
                                                     'in section %s') % (opt, val, section))
                        if hasattr(self.parser.option_class, 'ENABLE') and hasattr(self.parser.option_class, 'DISABLE'):
                            if newval:
                                cmd_template = "--enable-%s"
                            else:
                                cmd_template = "--disable-%s"
                            configfile_cmdline_dest.append(opt_dest)
                            configfile_cmdline.append(cmd_template % opt_name)
                        else:
                            self.log.debug(("parseconfigfiles: no enable/disable, not trying to set boolean-valued "
                                            "option %s via cmdline, just setting value to %s" % (opt_name, newval)))
                            configfile_values[opt_dest] = newval
                    else:
                        configfile_cmdline_dest.append(opt_dest)
                        configfile_cmdline.append("--%s=%s" % (opt_name, val))

        # reparse
        self.log.debug('parseconfigfiles: going to parse options through cmdline %s' % configfile_cmdline)
        try:
            # can't reprocress the environment, since we are not reporcessing the commandline either
            self.parser.process_env_options = False
            (parsed_configfile_options, parsed_configfile_args) = self.parser.parse_args(configfile_cmdline)
            self.parser.process_env_options = True
        except Exception:
            self.log.raiseException('parseconfigfiles: failed to parse options through cmdline %s' %
                                    configfile_cmdline)

        # re-report the options as parsed via parser
        self.log.debug("parseconfigfiles: options from configfile %s" % (self.parser.commandline_arguments))

        if len(parsed_configfile_args) > 0:
            self.log.raiseException('parseconfigfiles: not all options were parsed: %s' % parsed_configfile_args)

        for opt_dest in configfile_cmdline_dest:
            try:
                configfile_values[opt_dest] = getattr(parsed_configfile_options, opt_dest)
            except AttributeError:
                self.log.raiseException('parseconfigfiles: failed to retrieve dest %s from parsed_configfile_options' %
                                        opt_dest)

        self.log.debug('parseconfigfiles: parsed values from configfiles: %s' % configfile_values)

        for opt_dest, val in configfile_values.items():
            set_opt = False
            if not hasattr(self.options, opt_dest):
                self.log.debug('parseconfigfiles: adding new option %s with value %s' % (opt_dest, val))
                set_opt = True
            else:
                if hasattr(self.options, '_action_taken') and self.options._action_taken.get(opt_dest, None):
                    # value set through take_action. do not modify by configfile
                    self.log.debug('parseconfigfiles: option %s already found in _action_taken' % (opt_dest))
                else:
                    self.log.debug('parseconfigfiles: option %s not found in _action_taken, setting to %s' %
                                   (opt_dest, val))
                    set_opt = True
            if set_opt:
                setattr(self.options, opt_dest, val)
                if hasattr(self.options, '_action_taken'):
                    self.options._action_taken[opt_dest] = True

    def make_options_option_name_and_destination(self, prefix, key):
        """Make the options option name"""
        if prefix == '':
            name = key
        else:
            name = "".join([prefix, self.OPTIONNAME_PREFIX_SEPARATOR, key])

        # dest : replace '-' with '_'
        dest = name.replace('-', '_')

        return name, dest

    def _get_options_by_property(self, prop_type, prop_value):
        """Return all options with property type equal to value"""
        if prop_type not in self.PROCESSED_OPTIONS_PROPERTIES:
            self.log.raiseException('Invalid prop_type %s for PROCESSED_OPTIONS_PROPERTIES %s' %
                                    (prop_type, self.PROCESSED_OPTIONS_PROPERTIES))
        prop_idx = self.PROCESSED_OPTIONS_PROPERTIES.index(prop_type)
        # get all options with prop_type
        options = {}
        for key in [dest for dest, props in self.processed_options.items() if props[prop_idx] == prop_value]:
            options[key] = getattr(self.options, key, None)  # None? isn't there always a default

        return options

    def get_options_by_prefix(self, prefix):
        """Get all options that set with prefix. Return a dict. The keys are stripped of the prefix."""
        offset = 0
        if prefix:
            offset = len(prefix) + len(self.OPTIONNAME_PREFIX_SEPARATOR)

        prefix_dict = {}
        for dest, value in self._get_options_by_property('prefix', prefix).items():
            new_dest = dest[offset:]
            prefix_dict[new_dest] = value
        return prefix_dict

    def get_options_by_section(self, section):
        """Get all options from section. Return a dict."""
        return self._get_options_by_property('section_name', section)

    def postprocess(self):
        """Some additional processing"""
        pass

    def validate(self):
        """Final step, allows for validating the options and/or args"""
        pass

    def dict_by_prefix(self, merge_empty_prefix=False):
        """Break the options dict by prefix; return nested dict.
            :param merge_empty_prefix : boolean (default False) also (try to) merge the empty
                                        prefix in the root of the dict. If there is a non-prefixed optionname
                                        that matches a prefix, it will be rejected and error will be logged.
        """
        subdict = {}

        prefix_idx = self.PROCESSED_OPTIONS_PROPERTIES.index('prefix')
        for prefix in nub([props[prefix_idx] for props in self.processed_options.values()]):
            subdict[prefix] = self.get_options_by_prefix(prefix)

        if merge_empty_prefix and '' in subdict:
            self.log.debug("dict_by_prefix: merge_empty_prefix set")
            for opt, val in subdict[''].items():
                if opt in subdict:
                    self.log.error("dict_by_prefix: non-prefixed option %s conflicts with prefix of same name." % opt)
                else:
                    subdict[opt] = val

        self.log.debug("dict_by_prefix: subdict %s" % subdict)
        return subdict

    def generate_cmd_line(self, ignore=None, add_default=None):
        """Create the commandline options that would create the current self.options.
           The result is sorted on the destination names.

            :param ignore : regex on destination
            :param add_default : print value that are equal to default
        """
        if ignore is not None:
            self.log.debug("generate_cmd_line ignore %s" % ignore)
            ignore = re.compile(ignore)
        else:
            self.log.debug("generate_cmd_line no ignore")

        args = []
        opt_dests = sorted(self.options.__dict__)

        for opt_dest in opt_dests:
            # help is store_or_None, but is not a processed option, so skip it
            if opt_dest in ExtOption.EXTOPTION_HELP:
                continue

            opt_value = self.options.__dict__[opt_dest]
            # this is the action as parsed by the class, not the actual action set in option
            # (eg action store_or_None is shown here as store_or_None, not as callback)
            typ = self.processed_options[opt_dest][self.PROCESSED_OPTIONS_PROPERTIES.index('type')]
            default = self.processed_options[opt_dest][self.PROCESSED_OPTIONS_PROPERTIES.index('default')]
            action = self.processed_options[opt_dest][self.PROCESSED_OPTIONS_PROPERTIES.index('action')]
            opt_name = self.processed_options[opt_dest][self.PROCESSED_OPTIONS_PROPERTIES.index('opt_name')]

            if ignore is not None and ignore.search(opt_dest):
                self.log.debug("generate_cmd_line adding %s value %s matches ignore. Not adding to args." %
                               (opt_name, opt_value))
                continue

            if opt_value == default:
                # do nothing
                # except for store_or_None and friends
                msg = ''
                if not (add_default or action in ('store_or_None',)):
                    msg = ' Not adding to args.'
                self.log.debug("generate_cmd_line adding %s value %s default found.%s" %
                               (opt_name, opt_value, msg))
                if not (add_default or action in ('store_or_None',)):
                    continue

            if opt_value is None:
                # do nothing
                self.log.debug("generate_cmd_line adding %s value %s. None found. not adding to args." %
                               (opt_name, opt_value))
                continue

            if action in ExtOption.EXTOPTION_STORE_OR:
                if opt_value == default:
                    self.log.debug("generate_cmd_line %s adding %s (value is default value %s)" %
                                   (action, opt_name, opt_value))
                    args.append("--%s" % (opt_name))
                else:
                    self.log.debug("generate_cmd_line %s adding %s non-default value %s" %
                                   (action, opt_name, opt_value))
                    if typ in ExtOption.TYPE_STRLIST:
                        sep, _, _ = what_str_list_tuple(typ)
                        args.append("--%s=%s" % (opt_name, shell_quote(sep.join(opt_value))))
                    else:
                        args.append("--%s=%s" % (opt_name, shell_quote(opt_value)))
            elif action in ("store_true", "store_false",) + ExtOption.EXTOPTION_LOG:
                # not default!
                self.log.debug("generate_cmd_line adding %s value %s. store action found" %
                               (opt_name, opt_value))
                if (action in ('store_true',) + ExtOption.EXTOPTION_LOG and default is True and opt_value is False) or \
                   (action in ('store_false',) and default is False and opt_value is True):
                    if hasattr(self.parser.option_class, 'ENABLE') and hasattr(self.parser.option_class, 'DISABLE'):
                        args.append("--%s-%s" % (self.parser.option_class.DISABLE, opt_name))
                    else:
                        self.log.error(("generate_cmd_line: %s : can't set inverse of default %s with action %s "
                                        "with missing ENABLE/DISABLE in option_class") %
                                       (opt_name, default, action))
                else:
                    if opt_value == default and ((action in ('store_true',) +
                                                  ExtOption.EXTOPTION_LOG and default is False) or
                                                 (action in ('store_false',) and default is True)):
                        if hasattr(self.parser.option_class, 'ENABLE') and \
                           hasattr(self.parser.option_class, 'DISABLE'):
                            args.append("--%s-%s" % (self.parser.option_class.DISABLE, opt_name))
                        else:
                            self.log.debug(("generate_cmd_line: %s : action %s can only set to inverse of default %s "
                                            "and current value is default. Not adding to args.") %
                                           (opt_name, action, default))
                    else:
                        args.append("--%s" % opt_name)
            elif action in ("add", "add_first", "add_flex"):
                if default is not None:
                    if action == 'add_flex' and default:
                        for ind, elem in enumerate(opt_value):
                            if elem == default[0] and opt_value[ind:ind + len(default)] == default:
                                empty = get_empty_add_flex(opt_value, self=self)
                                # TODO: this will only work for tuples and lists
                                opt_value = opt_value[:ind] + type(opt_value)([empty]) + opt_value[ind + len(default):]
                                # only the first occurence
                                break
                    elif hasattr(opt_value, '__neg__'):
                        if action == 'add_first':
                            opt_value = opt_value + -default
                        else:
                            opt_value = -default + opt_value
                    elif hasattr(opt_value, '__getslice__'):
                        if action == 'add_first':
                            opt_value = opt_value[:-len(default)]
                        else:
                            opt_value = opt_value[len(default):]

                if typ in ExtOption.TYPE_STRLIST:
                    sep, klass, helpsep = what_str_list_tuple(typ)
                    restype = '%s-separated %s' % (helpsep, klass.__name__)
                    value = sep.join(opt_value)
                else:
                    restype = 'string'
                    value = opt_value

                if not opt_value:
                    # empty strings, empty lists, 0
                    self.log.debug('generate_cmd_line no value left, skipping.')
                    continue

                self.log.debug("generate_cmd_line adding %s value %s. %s action, return as %s" %
                               (opt_name, opt_value, action, restype))

                args.append("--%s=%s" % (opt_name, shell_quote(value)))
            elif typ in ExtOption.TYPE_STRLIST:
                sep, _, _ = what_str_list_tuple(typ)
                args.append("--%s=%s" % (opt_name, shell_quote(sep.join(opt_value))))
            elif action in ("append",):
                # add multiple times
                self.log.debug("generate_cmd_line adding %s value %s. append action, return as multiple args" %
                               (opt_name, opt_value))
                args.extend(["--%s=%s" % (opt_name, shell_quote(v)) for v in opt_value])
            elif action in ("regex",):
                self.log.debug("generate_cmd_line adding %s regex pattern %s" % (opt_name, opt_value.pattern))
                args.append("--%s=%s" % (opt_name, shell_quote(opt_value.pattern)))
            else:
                self.log.debug("generate_cmd_line adding %s value %s" % (opt_name, opt_value))
                args.append("--%s=%s" % (opt_name, shell_quote(opt_value)))

        self.log.debug("commandline args %s" % args)
        return args


class SimpleOptionParser(ExtOptionParser):
    DESCRIPTION_DOCSTRING = True


class SimpleOption(GeneralOption):
    PARSER = SimpleOptionParser
    SETROOTLOGGER = True

    def __init__(self, go_dict=None, descr=None, short_groupdescr=None, long_groupdescr=None, config_files=None):
        """Initialisation
        :param go_dict : General Option option dict
        :param short_descr : short description of main options
        :param long_descr : longer description of main options
        :param config_files : list of configfiles to read options from

        a general options dict has as key the long option name, and is followed by a list/tuple
        mandatory are 4 elements : option help, type, action, default
        a 5th element is optional and is the short help name (if any)

        the generated help will include the docstring
        """
        self.go_dict = go_dict
        if short_groupdescr is None:
            short_groupdescr = 'Main options'
        if long_groupdescr is None:
            long_groupdescr = ''
        self.descr = [short_groupdescr, long_groupdescr]

        kwargs = {
            'go_prefixloggername': True,
            'go_mainbeforedefault': True,
        }
        if config_files is not None:
            kwargs['go_configfiles'] = config_files

        super(SimpleOption, self).__init__(**kwargs)

        if descr is not None:
            # TODO: as there is no easy/clean way to access the version of the vsc-base package,
            # this is equivalent to a warning
            self.log.deprecated('SimpleOption descr argument', '2.5.0', '3.0.0')

    def main_options(self):
        if self.go_dict is not None:
            prefix = None
            self.add_group_parser(self.go_dict, self.descr, prefix=prefix)


def simple_option(go_dict=None, descr=None, short_groupdescr=None, long_groupdescr=None, config_files=None):
    """A function that returns a single level GeneralOption option parser

    :param go_dict : General Option option dict
    :param short_descr : short description of main options
    :param long_descr : longer description of main options
    :param config_files : list of configfiles to read options from

    a general options dict has as key the long option name, and is followed by a list/tuple
    mandatory are 4 elements : option help, type, action, default
    a 5th element is optional and is the short help name (if any)

    the generated help will include the docstring
    """
    return SimpleOption(go_dict=go_dict, descr=descr, short_groupdescr=short_groupdescr,
                        long_groupdescr=long_groupdescr, config_files=config_files)
