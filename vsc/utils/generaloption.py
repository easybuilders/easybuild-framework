#
#
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
#

"""
A class that can be used to generated options to python scripts in a general way.

@author: Stijn De Weirdt (Ghent University)
@author: Jens Timmerman (Ghent University)
"""

import ConfigParser
import copy
import inspect
import operator
import os
import re
import StringIO
import sys
import textwrap
from optparse import OptionParser, OptionGroup, Option, Values, BadOptionError, SUPPRESS_USAGE, OptionValueError
from optparse import SUPPRESS_HELP as nohelp  # supported in optparse of python v2.4
from optparse import _ as _gettext  # this is gettext normally
from vsc.utils.dateandtime import date_parser, datetime_parser
from vsc.utils.fancylogger import getLogger, setLogLevel
from vsc.utils.missing import shell_quote


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
            except:
                # do nothing
                pass

    if cols is not None:
        os.environ['COLUMNS'] = "%s" % cols


def check_str_list_tuple(option, opt, value):
    """
    check function for strlist and strtuple type
        assumes value is comma-separated list
        returns list or tuple of strings
    """
    split = value.split(',')
    if option.type == 'strlist':
        return split
    elif option.type == 'strtuple':
        return tuple(split)
    else:
        err = _("check_strlist_strtuple: unsupported type %s" % option.type)
        raise OptionValueError(err)


class ExtOption(Option):
    """Extended options class
        - enable/disable support

       Actions:
         - shorthelp : hook for shortend help messages
         - store_debuglog : turns on fancylogger debugloglevel
            - also: 'store_infolog', 'store_warninglog'
         - extend : extend default list (or create new one if is None)
         - date : convert into datetime.date
         - datetime : convert into datetime.datetime
         - regex: compile str in regexp
         - store_or_None
           - set default to None if no option passed,
           - set to default if option without value passed,
           - set to value if option with value passed
    """
    EXTEND_SEPARATOR = ','

    ENABLE = 'enable'  # do nothing
    DISABLE = 'disable'  # inverse action

    EXTOPTION_EXTRA_OPTIONS = ('extend', 'date', 'datetime', 'regex',)
    EXTOPTION_STORE_OR = ('store_or_None',)  # callback type
    EXTOPTION_LOG = ('store_debuglog', 'store_infolog', 'store_warninglog',)

    # shorthelp has no extra arguments
    ACTIONS = Option.ACTIONS + EXTOPTION_EXTRA_OPTIONS + EXTOPTION_STORE_OR + EXTOPTION_LOG + ('shorthelp',)
    STORE_ACTIONS = Option.STORE_ACTIONS + EXTOPTION_EXTRA_OPTIONS + EXTOPTION_LOG + ('store_or_None',)
    TYPED_ACTIONS = Option.TYPED_ACTIONS + EXTOPTION_EXTRA_OPTIONS + EXTOPTION_STORE_OR
    ALWAYS_TYPED_ACTIONS = Option.ALWAYS_TYPED_ACTIONS + EXTOPTION_EXTRA_OPTIONS

    TYPE_CHECKER = dict([('strlist', check_str_list_tuple),
                         ('strtuple', check_str_list_tuple),
                         ] + Option.TYPE_CHECKER.items())
    TYPES = tuple(['strlist', 'strtuple'] + list(Option.TYPES))

    def _set_attrs(self, attrs):
        """overwrite _set_attrs to allow store_or callbacks"""
        Option._set_attrs(self, attrs)
        if self.action in self.EXTOPTION_STORE_OR:
            setattr(self, 'store_or', self.action)

            def store_or(option, opt_str, value, parser, *args, **kwargs):
                """Callback for supporting options with optional values."""
                # see http://stackoverflow.com/questions/1229146/parsing-empty-options-in-python
                # ugly code, optparse is crap
                if parser.rargs and not parser.rargs[0].startswith('-'):
                    val = parser.rargs[0]
                    parser.rargs.pop(0)
                else:
                    val = kwargs.get('orig_default', None)

                setattr(parser.values, option.dest, val)

            # without the following, --x=y doesn't work; only --x y
            self.nargs = 0  # allow 0 args, will also use 0 args
            if self.type is None:
                # set to not None, for takes_value to return True
                self.type = 'string'

            self.callback = store_or
            self.callback_kwargs = {'orig_default': copy.deepcopy(self.default),
                                    }
            self.action = 'callback'  # act as callback
            if self.store_or == 'store_or_None':
                self.default = None
            else:
                raise ValueError("_set_attrs: unknown store_or %s" % self.store_or)

    def take_action(self, action, dest, opt, value, values, parser):
        """Extended take_action"""
        orig_action = action  # keep copy

        if action == 'shorthelp':
            parser.print_shorthelp()
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

            if orig_action in ('store_debuglog', 'store_infolog', 'store_warninglog') and action == 'store_true':
                setLogLevel(orig_action.split('_')[1][:-3].upper())

            Option.take_action(self, action, dest, opt, value, values, parser)
        elif action in self.EXTOPTION_EXTRA_OPTIONS:
            if action == "extend":
                # comma separated list convert in list
                lvalue = value.split(self.EXTEND_SEPARATOR)
                values.ensure_value(dest, []).extend(lvalue)
            elif action == "date":
                lvalue = date_parser(value)
                setattr(values, dest, lvalue)
            elif action == "datetime":
                lvalue = datetime_parser(value)
                setattr(values, dest, lvalue)
            elif action == "regex":
                lvalue = re.compile(r'' + value)
                setattr(values, dest, lvalue)
            else:
                raise(Exception("Unknown extended option action %s (known: %s)" %
                                (action, self.EXTOPTION_EXTRA_OPTIONS)))
        else:
            Option.take_action(self, action, dest, opt, value, values, parser)

        # set flag to mark as passed by action (ie not by default)
        # - distinguish from setting default value through option
        if hasattr(values, '_action_taken'):
            values._action_taken[dest] = True


class PassThroughOptionParser(OptionParser):
    """
    "Pass-through" option parsing -- an OptionParser that ignores
    unknown options and lets them pile up in the leftover argument
    list.  Useful for programs that pass unknown options through
    to a sub-program.
    from http://www.koders.com/python/fid9DFF5006AF4F52BA6483C4F654E26E6A20DBC73C.aspx?s=add+one#L27
    """
    def __init__(self):
        OptionParser.__init__(self, add_help_option=False, usage=SUPPRESS_USAGE)

    def _process_long_opt(self, rargs, values):
        """Extend optparse code with catch of unknown long options error"""
        try:
            OptionParser._process_long_opt(self, rargs, values)
        except BadOptionError, err:
            self.largs.append(err.opt_str)

    def _process_short_opts(self, rargs, values):
        """Process the short options, pass unknown to largs"""
        # implementation from recent optparser
        arg = rargs.pop(0)
        stop = False
        i = 1
        for ch in arg[1:]:
            opt = "-" + ch
            option = self._short_opt.get(opt)
            i += 1  # we have consumed a character

            if not option:
                # don't fail here, just append to largs
                # raise BadOptionError(opt)
                self.largs.append(opt)
                return
            if option.takes_value():
                # Any characters left in arg?  Pretend they're the
                # next arg, and stop consuming characters of arg.
                if i < len(arg):
                    rargs.insert(0, arg[i:])
                    stop = True

                nargs = option.nargs
                if len(rargs) < nargs:
                    if nargs == 1:
                        self.error(_("%s option requires an argument") % opt)
                    else:
                        self.error(_("%s option requires %d arguments")
                                   % (opt, nargs))
                elif nargs == 1:
                    value = rargs.pop(0)
                else:
                    value = tuple(rargs[0:nargs])
                    del rargs[0:nargs]

            else:  # option doesn't take a value
                value = None

            option.process(opt, value, values, self)

            if stop:
                break


class ExtOptionParser(OptionParser):
    """Make an option parser that limits the C{-h} / C{--shorthelp} to short opts only, C{-H} / C{--help} for all options

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

    def __init__(self, *args, **kwargs):
        self.log = getLogger(self.__class__.__name__)
        self.help_to_string = kwargs.pop('help_to_string', None)
        self.help_to_file = kwargs.pop('help_to_file', None)
        self.envvar_prefix = kwargs.pop('envvar_prefix', None)

        # py2.4 epilog compatibilty with py2.7 / optparse 1.5.3
        self.epilog = kwargs.pop('epilog', None)

        if not 'option_class' in kwargs:
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

    def set_description_docstring(self):
        """Try to find the main docstring and add it if description is not None"""
        stack = inspect.stack()[-1]
        try:
            docstr = stack[0].f_globals.get('__doc__', None)
        except:
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
                except:
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
            - class constant is used to avoid _taken_action as option in the __dict__
        """
        values = OptionParser.get_default_values(self)

        class ExtValues(self.VALUES_CLASS):
            _action_taken = {}

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

    def print_help(self, fh=None):
        """Intercept print to file to print to string and remove the ENABLE/DISABLE options from help"""
        if self.help_to_string:
            self.help_to_file = StringIO.StringIO()
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

        OptionParser.print_help(self, fh)

    def _add_help_option(self):
        """Add shorthelp and longhelp"""
        self.add_option("-%s" % self.shorthelp[0],
                        self.shorthelp[1],  # *self.shorthelp[1:], syntax error in Python 2.4
                        action="shorthelp",
                        help=_gettext("show short help message and exit"))
        self.add_option("-%s" % self.longhelp[0],
                        self.longhelp[1],  # *self.longhelp[1:], syntax error in Python 2.4
                        action="help",
                        help=_gettext("show full help message and exit"))

    def _get_args(self, args):
        """Prepend the options set through the environment"""
        regular_args = OptionParser._get_args(self, args)
        env_args = self.get_env_options()
        return env_args + regular_args  # prepend the environment options as longopts

    def get_env_options_prefix(self):
        """Return the prefix to use for options passed through the environment"""
        # sys.argv[0] or the prog= argument of the optionparser, strip possible extension
        if self.envvar_prefix is None:
            self.envvar_prefix = self.get_prog_name().rsplit('.', 1)[0].upper()
        return self.envvar_prefix

    def get_env_options(self):
        """Retrieve options from the environment: prefix_longopt.upper()"""
        env_long_opts = []
        if self.envvar_prefix is None:
            self.get_env_options_prefix()

        epilogprefixtxt = "All long option names can be passed as environment variables. "
        epilogprefixtxt += "Variable name is %(prefix)s_<LONGNAME> "
        epilogprefixtxt += "eg. --some-opt is same as setting %(prefix)s_SOME_OPT in the environment."
        self.epilog.append(epilogprefixtxt % {'prefix': self.envvar_prefix})

        for opt in self._get_all_options():
            if opt._long_opts is None:
                continue
            for lo in opt._long_opts:
                if len(lo) == 0:
                    continue
                env_opt_name = "%s_%s" % (self.envvar_prefix, lo.lstrip('-').replace('-', '_').upper())
                val = os.environ.get(env_opt_name, None)
                if not val is None:
                    if opt.action in opt.TYPED_ACTIONS:  # not all typed actions are mandatory, but let's assume so
                        env_long_opts.append("%s=%s" % (lo, val))
                    else:
                        # interpretation of values: 0/no/false means: don't set it
                        if not ("%s" % val).lower() in ("0", "no", "false",):
                            env_long_opts.append("%s" % lo)
                else:
                    self.log.debug("Environment variable %s is not set" % env_opt_name)

        self.log.debug("Environment variable options with prefix %s: %s" % (self.envvar_prefix, env_long_opts))
        return env_long_opts

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
        - go_loggername : name of logger, default classname
        - go_initbeforedefault : set the main options before the default ones

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
    CONFIGFILE_PARSER = ConfigParser.ConfigParser

    METAVAR_DEFAULT = True  # generate a default metavar
    METAVAR_MAP = None  # metvar, list of longopts map

    OPTIONGROUP_SORTED_OPTIONS = True

    PROCESSED_OPTIONS_PROPERTIES = ['type', 'default', 'action', 'opt_name', 'prefix', 'section_name']

    VERSION = None  # set the version (will add --version)

    DEFAULT_LOGLEVEL = None
    DEFAULT_CONFIGFILES = None
    DEFAULT_IGNORECONFIGFILES = None

    def __init__(self, **kwargs):
        go_args = kwargs.pop('go_args', None)
        self.no_system_exit = kwargs.pop('go_nosystemexit', None)  # unit test option
        self.use_configfiles = kwargs.pop('go_useconfigfiles', self.CONFIGFILES_USE)  # use or ignore config files
        self.configfiles = kwargs.pop('go_configfiles', self.CONFIGFILES_INIT)  # configfiles to parse
        prefixloggername = kwargs.pop('go_prefixloggername', False)  # name of logger is same as envvar prefix
        mainbeforedefault = kwargs.pop('go_mainbeforedefault', False)  # Set the main options before the default ones

        set_columns(kwargs.pop('go_columns', None))

        kwargs.update({
            'option_class': ExtOption,
            'usage': kwargs.get('usage', self.USAGE),
            'version': self.VERSION,
        })
        self.parser = self.PARSER(**kwargs)
        self.parser.allow_interspersed_args = self.INTERSPERSED

        self.configfile_parser = self.CONFIGFILE_PARSER()
        self.configfile_remainder = {}

        loggername = self.__class__.__name__
        if prefixloggername:
            prefix = self.parser.get_env_options_prefix()
            if prefix is not None and len(prefix) > 0:
                loggername = prefix.replace('.', '_')  # . indicate hierarchy in logging land

        self.log = getLogger(loggername)
        self.options = None
        self.args = None

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

        if not self.options is None:
            # None for eg usage/help
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
            'quiet': ("Enable info quiet/warning mode", None, "store_warninglog", False),
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
            'configfiles': ("Parse (additional) configfiles", None, "extend", self.DEFAULT_CONFIGFILES),
            'ignoreconfigfiles': ("Ignore configfiles", None, "extend", self.DEFAULT_IGNORECONFIGFILES),
        }
        descr = ['Configfile options', '']
        self.log.debug("Add configfiles options descr %s opts %s (no prefix)" % (descr, opts))
        self.add_group_parser(opts, descr, prefix=None)

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

    def make_option_metavar(self, longopt, details):
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

        @param opt_dict: options, with the form C{"long_opt" : value}.
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
        section_help = "(configfile section %s)" % (section_name)
        if description[1]:
            short_description = description[0]
            long_description = "%s %s" % (description[1], section_help)
        else:
            short_description = "%s %s" % (description[0], section_help)
            long_description = description[1]

        opt_grp = OptionGroup(self.parser, short_description, long_description)
        keys = opt_dict.keys()
        if self.OPTIONGROUP_SORTED_OPTIONS:
            keys.sort()  # alphabetical
        for key in keys:
            details = opt_dict[key]

            hlp = details[0]
            typ = details[1]
            action = details[2]
            default = details[3]
            # easy override default with otherdefault
            if key in otherdefaults:
                default = otherdefaults.get(key)

            extra_help = []
            if action in ("extend",) or typ in ('strlist', 'strtuple',):
                extra_help.append("type comma-separated list")
            elif typ is not None:
                extra_help.append("type %s" % typ)

            if default is not None:
                if len(str(default)) == 0:
                    extra_help.append("def ''")  # empty string
                elif action in ("extend",) or typ in ('strlist', 'strtuple',):
                    extra_help.append("def %s" % ','.join(default))
                else:
                    extra_help.append("def %s" % default)

            if len(extra_help) > 0:
                hlp += " (%s)" % ("; ".join(extra_help))

            opt_name, opt_dest = self.make_options_option_name_and_destination(prefix, key)

            args = ["--%s" % opt_name]

            # this has to match PROCESSED_OPTIONS_PROPERTIES
            self.processed_options[opt_dest] = [typ, default, action, opt_name, prefix, section_name]  # add longopt
            if not len(self.processed_options[opt_dest]) == len(self.PROCESSED_OPTIONS_PROPERTIES):
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
                    elif isinstance(extra_detail, (str,)) and len(extra_detail) == 1:
                        args.insert(0, "-%s" % extra_detail)
                    elif isinstance(extra_detail, (dict,)):
                        passed_kwargs.update(extra_detail)
                    else:
                        self.log.raiseException("add_group_parser: unknown extra detail %s" % extra_detail)

            # add help
            nameds['help'] = hlp

            if hasattr(self.parser.option_class, 'ENABLE') and hasattr(self.parser.option_class, 'DISABLE'):
                args.append("--%s-%s" % (self.parser.option_class.ENABLE, opt_name))
                args.append("--%s-%s" % (self.parser.option_class.DISABLE, opt_name))

            # force passed_kwargs as final nameds
            nameds.update(passed_kwargs)
            opt_grp.add_option(*args, **nameds)

        self.parser.add_option_group(opt_grp)

        # map between prefix and sectionnames
        prefix_section_names = self.config_prefix_sectionnames_map.setdefault(prefix, [])
        if not section_name in prefix_section_names:
            prefix_section_names.append(section_name)
            self.log.debug("Added prefix %s to list of sectionnames for %s" % (prefix, section_name))

    def default_parseoptions(self):
        """Return default options"""
        return sys.argv[1:]

    def parseoptions(self, options_list=None):
        """Parse the options"""
        if options_list is None:
            options_list = self.default_parseoptions()

        try:
            (self.options, self.args) = self.parser.parse_args(options_list)
        except SystemExit, err:
            if self.no_system_exit:
                try:
                    msg = err.message
                except:
                    # py2.4
                    msg = '_nomessage_'
                self.log.debug("parseoptions: no_system_exit set after parse_args err %s code %s" %
                               (msg, err.code))
                return
            else:
                sys.exit(err.code)

        # args should be empty, since everything is optional
        if len(self.args) > 1:
            self.log.debug("Found remaining args %s" % self.args)
            if self.ALLOPTSMANDATORY:
                self.parser.error("Invalid arguments args %s" % self.args)

        self.log.debug("Found options %s args %s" % (self.options, self.args))

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
                self.log.debug("parseconfigfiles: configfile %s will be ignored %s" % fn)
            else:
                configfiles.append(fn)

        try:
            parsed_files = self.configfile_parser.read(configfiles)
        except:
            self.log.raiseException("parseconfigfiles: problem during read")

        self.log.debug("parseconfigfiles: following files were parsed %s" % parsed_files)
        self.log.debug("parseconfigfiles: following files were NOT parsed %s" %
                       [x for x in configfiles if not x in parsed_files])
        self.log.debug("parseconfigfiles: sections (w/o DEFAULT) %s" % self.configfile_parser.sections())

        # walk through list of section names
        # - look for options set though config files
        configfile_values = {}
        configfile_options_default = {}
        configfile_cmdline = []
        configfile_cmdline_dest = []  # expected destinations

        # won't parse
        cfg_sections = self.config_prefix_sectionnames_map.values()  # without DEFAULT
        for section in cfg_sections:
            if not section in self.config_prefix_sectionnames_map.values():
                self.log.warning("parseconfigfiles: found section %s, won't be parsed" % section)
                continue

        # add any non-option related configfile data to configfile_remainder dict
        cfg_sections_flat = [name for section_names in cfg_sections for name in section_names]
        for section in self.configfile_parser.sections():
            if section not in cfg_sections_flat:
                self.log.debug("parseconfigfiles: found section %s, adding to remainder" % section)
                remainder = self.configfile_remainder.setdefault(section, {})
                # parse te remaining options, sections starting with 'raw_' as their name will be considered raw sections

                for opt, val in self.configfile_parser.items(section, raw=(section.startswith('raw_'))):
                    remainder[opt] = val

        # options are passed to the commandline option parser
        for prefix, section_names in self.config_prefix_sectionnames_map.items():
            for section in section_names:
                # default section is treated separate in ConfigParser
                if not (self.configfile_parser.has_section(section) or section.lower() == 'default'):
                    self.log.debug('parseconfigfiles: no section %s' % section)
                    continue

                for opt, val in self.configfile_parser.items(section):
                    self.log.debug('parseconfigfiles: section %s option %s val %s' % (section, opt, val))

                    opt_name, opt_dest = self.make_options_option_name_and_destination(prefix, opt)
                    actual_option = self.parser.get_option_by_long_name(opt_name)
                    if actual_option is None:
                        self.log.raiseException('parseconfigfiles: no option corresponding with dest %s' %
                                                opt_dest)

                    configfile_options_default[opt_dest] = actual_option.default

                    if actual_option.action in ('store_true', 'store_false',):
                        try:
                            newval = self.configfile_parser.getboolean(section, opt)
                            self.log.debug(('parseconfigfiles: getboolean for option %s value %s '
                                            'in section %s returned %s') % (opt, val, section, newval))
                        except:
                            self.log.raiseException(('parseconfigfiles: failed to getboolean for option %s value %s '
                                                     'in section %s') % (opt, val, section))
                        configfile_values[opt_dest] = newval
                    else:
                        configfile_cmdline_dest.append(opt_dest)
                        configfile_cmdline.append("--%s" % opt_name)
                        configfile_cmdline.append(val)

        # reparse
        self.log.debug('parseconfigfiles: going to parse options through cmdline %s' % configfile_cmdline)
        try:
            (parsed_configfile_options, parsed_configfile_args) = self.parser.parse_args(configfile_cmdline)
        except:
            self.log.raiseException('parseconfigfiles: failed to parse options through cmdline %s' %
                                    configfile_cmdline)

        if len(parsed_configfile_args) > 0:
            self.log.raiseException('parseconfigfiles: not all options were parsed: %s' % parsed_configfile_args)

        for opt_dest in configfile_cmdline_dest:
            try:
                configfile_values[opt_dest] = getattr(parsed_configfile_options, opt_dest)
            except:
                self.log.raiseException('parseconfigfiles: failed to retrieve dest %s from parsed_configfile_options' %
                                        opt_dest)

        self.log.debug('parseconfigfiles: parsed values from configfiles: %s' % configfile_values)

        for opt_dest, val in configfile_values.items():
            if not hasattr(self.options, opt_dest):
                self.log.debug('parseconfigfiles: added new option %s with value %s' % (opt_dest, val))
                setattr(self.options, opt_dest, val)
            else:
                if hasattr(self.options, '_action_taken') and self.options._action_taken.get(opt_dest, None):
                    # value set through take_action. do not modify by configfile
                    self.log.debug('parseconfigfiles: option %s found in _action_taken' % (opt_dest))
                    continue
                else:
                    self.log.debug('parseconfigfiles: option %s not found in _action_taken, setting to %s' %
                                   (opt_dest, val))
                    setattr(self.options, opt_dest, val)

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
        if not prop_type in self.PROCESSED_OPTIONS_PROPERTIES:
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
        prefix_dict = {}
        for dest, value in self._get_options_by_property('prefix', prefix).items():
            new_dest = dest[len(prefix) + len(self.OPTIONNAME_PREFIX_SEPARATOR):]
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

    def dict_by_prefix(self):
        """Break the options dict by prefix in sub-dict"""
        # TODO replace by _get_options_by_property code
        subdict = {}
        for k in self.options.__dict__.keys():
            levels = k.split(self.OPTIONNAME_PREFIX_SEPARATOR)
            lastlvl = subdict
            for lvl in levels[:-1]:  # 0 or more
                lastlvl.setdefault(lvl, {})
                lastlvl = lastlvl[lvl]
            lastlvl[levels[-1]] = self.options.__dict__[k]
        self.log.debug("Returned subdict %s" % subdict)
        return subdict

    def generate_cmd_line(self, ignore=None, add_default=None):
        """Create the commandline options that would create the current self.options
            opt_name is destination

            @param ignore : regex on destination
            @param add_default : print value that are equal to default
        """
        if ignore is not None:
            self.log.debug("generate_cmd_line ignore %s" % ignore)
            ignore = re.compile(ignore)
        else:
            self.log.debug("generate_cmd_line no ignore")

        args = []
        opt_dests = self.options.__dict__.keys()
        opt_dests.sort()

        for opt_dest in opt_dests:
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

            if action in ('store_or_None',):
                if opt_value == default:
                    self.log.debug("generate_cmd_line %s adding %s (value is default value %s)" %
                                   (action, opt_name, opt_value))
                    args.append("--%s" % (opt_name))
                else:
                    self.log.debug("generate_cmd_line %s adding %s non-default value %s" %
                                   (action, opt_name, opt_value))
                    args.append("--%s=%s" % (opt_name, shell_quote(opt_value)))
            elif action in ("store_true", "store_false", 'store_debuglog'):
                # not default!
                self.log.debug("generate_cmd_line adding %s value %s. store action found" %
                               (opt_name, opt_value))
                if (action in ('store_true', 'store_debuglog',) and default is True and opt_value is False) or \
                    (action in ('store_false',) and default is False and opt_value is True):
                    if hasattr(self.parser.option_class, 'ENABLE') and hasattr(self.parser.option_class, 'DISABLE'):
                        args.append("--%s-%s" % (self.parser.option_class.DISABLE, opt_name))
                    else:
                        self.log.error(("generate_cmd_line: %s : can't set inverse of default %s with action %s "
                                        "with missing ENABLE/DISABLE in option_class") %
                                       (opt_name, default, action))
                else:
                    if opt_value == default and ((action in ('store_true', 'store_debuglog',) and default is False)
                                                 or (action in ('store_false',) and default is True)):
                        if hasattr(self.parser.option_class, 'ENABLE') and \
                            hasattr(self.parser.option_class, 'DISABLE'):
                            args.append("--%s-%s" % (self.parser.option_class.DISABLE, opt_name))
                        else:
                            self.log.debug(("generate_cmd_line: %s : action %s can only set to inverse of default %s "
                                            "and current value is default. Not adding to args.") %
                                           (opt_name, action, default))
                    else:
                        args.append("--%s" % opt_name)
            elif action in ("extend",):
                # comma separated
                self.log.debug("generate_cmd_line adding %s value %s. extend action, return as comma-separated list" %
                               (opt_name, opt_value))

                if default is not None:
                    # remove these. if default is set, extend extends the default!
                    for def_el in default:
                        opt_value.remove(def_el)

                if len(opt_value) == 0:
                    self.log.debug('generate_cmd_line skipping.')
                    continue

                args.append("--%s=%s" % (opt_name, shell_quote(",".join(opt_value))))
            elif typ in ('strlist', 'strtuple',):
                args.append("--%s=%s" % (opt_name, shell_quote(",".join(opt_value))))
            elif action in ("append",):
                # add multiple times
                self.log.debug("generate_cmd_line adding %s value %s. append action, return as multiple args" %
                               (opt_name, opt_value))
                args.extend(["--%s=%s" % (opt_name, shell_quote(v)) for v in opt_value])
            else:
                self.log.debug("generate_cmd_line adding %s value %s" % (opt_name, opt_value))
                args.append("--%s=%s" % (opt_name, shell_quote(opt_value)))

        self.log.debug("commandline args %s" % args)
        return args


class SimpleOptionParser(ExtOptionParser):
    DESCRIPTION_DOCSTRING = True


class SimpleOption(GeneralOption):
    PARSER = SimpleOptionParser

    def __init__(self, go_dict=None, descr=None, short_groupdescr=None, long_groupdescr=None, config_files=None):
        """Initialisation
        @param go_dict : General Option option dict
        @param short_descr : short description of main options
        @param long_descr : longer description of main options
        @param config_files : list of configfiles to read options from

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

    def main_options(self):
        if self.go_dict is not None:
            prefix = None
            self.add_group_parser(self.go_dict, self.descr, prefix=prefix)


def simple_option(go_dict=None, descr=None, short_groupdescr=None, long_groupdescr=None, config_files=None):
    """A function that returns a single level GeneralOption option parser

    @param go_dict : General Option option dict
    @param short_descr : short description of main options
    @param long_descr : longer description of main options
    @param config_files : list of configfiles to read options from

    a general options dict has as key the long option name, and is followed by a list/tuple
    mandatory are 4 elements : option help, type, action, default
    a 5th element is optional and is the short help name (if any)

    the generated help will include the docstring
    """
    return SimpleOption(go_dict, descr, short_groupdescr, long_groupdescr, config_files)
