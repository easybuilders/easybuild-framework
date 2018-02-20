##
# Copyright 2009-2018 Ghent University
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
##
"""
Command line options for eb

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Toon Willems (Ghent University)
:author: Ward Poelmans (Ghent University)
:author: Damian Alvarez (Forschungszentrum Juelich GmbH)
"""
import copy
import glob
import os
import re
import shutil
import sys
import tempfile
import pwd
import vsc.utils.generaloption
from distutils.version import LooseVersion
from vsc.utils import fancylogger
from vsc.utils.fancylogger import setLogLevel
from vsc.utils.generaloption import GeneralOption
from vsc.utils.missing import nub

import easybuild.tools.environment as env
from easybuild.framework.easyblock import MODULE_ONLY_STEPS, SOURCE_STEP, EasyBlock
from easybuild.framework.easyconfig import EASYCONFIGS_PKG_SUBDIR
from easybuild.framework.easyconfig.easyconfig import HAVE_AUTOPEP8
from easybuild.framework.easyconfig.format.pyheaderconfigobj import build_easyconfig_constants_dict
from easybuild.framework.easyconfig.tools import get_paths_for
from easybuild.tools import build_log, run  # build_log should always stay there, to ensure EasyBuildLog
from easybuild.tools.build_log import DEVEL_LOG_LEVEL, EasyBuildError, print_warning, raise_easybuilderror
from easybuild.tools.config import DEFAULT_ALLOW_LOADED_MODULES, DEFAULT_FORCE_DOWNLOAD, DEFAULT_JOB_BACKEND
from easybuild.tools.config import DEFAULT_LOGFILE_FORMAT, DEFAULT_MAX_FAIL_RATIO_PERMS, DEFAULT_MNS
from easybuild.tools.config import DEFAULT_MODULE_SYNTAX, DEFAULT_MODULES_TOOL, DEFAULT_MODULECLASSES
from easybuild.tools.config import DEFAULT_PATH_SUBDIRS, DEFAULT_PKG_RELEASE, DEFAULT_PKG_TOOL, DEFAULT_PKG_TYPE
from easybuild.tools.config import DEFAULT_PNS, DEFAULT_PREFIX, DEFAULT_REPOSITORY, EBROOT_ENV_VAR_ACTIONS
from easybuild.tools.config import ERROR, IGNORE, FORCE_DOWNLOAD_CHOICES, LOADED_MODULES_ACTIONS, WARN
from easybuild.tools.config import get_pretend_installpath, mk_full_default_path
from easybuild.tools.configobj import ConfigObj, ConfigObjError
from easybuild.tools.docs import FORMAT_TXT, FORMAT_RST
from easybuild.tools.docs import avail_cfgfile_constants, avail_easyconfig_constants, avail_easyconfig_licenses
from easybuild.tools.docs import avail_toolchain_opts, avail_easyconfig_params, avail_easyconfig_templates
from easybuild.tools.docs import list_easyblocks, list_toolchains
from easybuild.tools.environment import restore_env, unset_env_vars
from easybuild.tools.filetools import CHECKSUM_TYPE_SHA256, CHECKSUM_TYPES, mkdir
from easybuild.tools.github import GITHUB_EB_MAIN, GITHUB_EASYCONFIGS_REPO, HAVE_GITHUB_API, HAVE_KEYRING
from easybuild.tools.github import fetch_github_token
from easybuild.tools.hooks import KNOWN_HOOKS
from easybuild.tools.include import include_easyblocks, include_module_naming_schemes, include_toolchains
from easybuild.tools.job.backend import avail_job_backends
from easybuild.tools.modules import avail_modules_tools
from easybuild.tools.module_generator import ModuleGeneratorLua, avail_module_generators
from easybuild.tools.module_naming_scheme import GENERAL_CLASS
from easybuild.tools.module_naming_scheme.utilities import avail_module_naming_schemes
from easybuild.tools.modules import Lmod
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.run import run_cmd
from easybuild.tools.package.utilities import avail_package_naming_schemes
from easybuild.tools.toolchain.compiler import DEFAULT_OPT_LEVEL, OPTARCH_MAP_CHAR, OPTARCH_SEP, Compiler
from easybuild.tools.toolchain.utilities import search_toolchain
from easybuild.tools.repository.repository import avail_repositories
from easybuild.tools.version import this_is_easybuild

try:
    from humanfriendly.terminal import terminal_supports_colors
except ImportError:
    # provide an approximation that should work in most cases
    def terminal_supports_colors(stream):
        try:
            return os.isatty(stream.fileno())
        except Exception:
            # in case of errors do not bother and just return the safe default
            return False

# monkey patch shell_quote in vsc.utils.generaloption, used by generate_cmd_line,
# to fix known issue, cfr. https://github.com/hpcugent/vsc-base/issues/152;
# inspired by https://github.com/hpcugent/vsc-base/pull/151
# this fixes https://github.com/easybuilders/easybuild-framework/issues/1438
# proper fix would be to implement a serialiser for command line options
def eb_shell_quote(token):
    """
    Wrap provided token in single quotes (to escape space and characters with special meaning in a shell),
    so it can be used in a shell command. This results in token that is not expanded/interpolated by the shell.
    """
    # first, strip off double quotes that may wrap the entire value,
    # we don't want to wrap single quotes around a double-quoted value
    token = str(token).strip('"')
    # escape any non-escaped single quotes, and wrap entire token in single quotes
    return "'%s'" % re.sub(r"(?<!\\)'", r"\'", token)

vsc.utils.generaloption.shell_quote = eb_shell_quote


CONFIG_ENV_VAR_PREFIX = 'EASYBUILD'

XDG_CONFIG_HOME = os.environ.get('XDG_CONFIG_HOME', os.path.join(os.path.expanduser('~'), ".config"))
XDG_CONFIG_DIRS = os.environ.get('XDG_CONFIG_DIRS', '/etc').split(os.pathsep)
DEFAULT_SYS_CFGFILES = [f for d in XDG_CONFIG_DIRS for f in sorted(glob.glob(os.path.join(d, 'easybuild.d', '*.cfg')))]
DEFAULT_USER_CFGFILE = os.path.join(XDG_CONFIG_HOME, 'easybuild', 'config.cfg')


_log = fancylogger.getLogger('options', fname=False)


def cleanup_and_exit(tmpdir):
    """
    Clean up temporary directory and exit.

    :param tmpdir: path to temporary directory to clean up
    """
    try:
        shutil.rmtree(tmpdir)
    except OSError as err:
        raise EasyBuildError("Failed to clean up temporary directory %s: %s", tmpdir, err)

    sys.exit(0)

def pretty_print_opts(opts_dict):
    """
    Pretty print options dict.

    :param opts_dict: dictionary with option names as keys, and (value, location) tuples as values
    """

    # rewrite option names/values a bit for pretty printing
    for opt in sorted(opts_dict):
        opt_val, loc = opts_dict[opt]

        if opt_val == '':
            opt_val = "''"
        elif isinstance(opt_val, list):
            opt_val = ', '.join(opt_val)

        opts_dict[opt] = (opt_val, loc)

    # determine max width or option names
    nwopt = max([len(opt) for opt in opts_dict])

    # header
    lines = [
        '#',
        "# Current EasyBuild configuration",
        "# (C: command line argument, D: default value, E: environment variable, F: configuration file)",
        '#',
    ]

    # add one line per retained option
    for opt in sorted(opts_dict):
        opt_val, loc = opts_dict[opt]
        lines.append("{0:<{nwopt}} ({1:}) = {2:}".format(opt, loc, opt_val, nwopt=nwopt))

    print '\n'.join(lines)


def use_color(colorize, stream=sys.stdout):
    """
    Return ``True`` or ``False`` depending on whether ANSI color
    escapes are to be used when printing to `stream`.

    The `colorize` argument can take the three values
    ``fancylogger.Colorize.AUTO``/``.ALWAYS``/``.NEVER``,
    see the ``--color`` option for their meaning.
    """
    # turn color=auto/yes/no into a boolean value
    if colorize == fancylogger.Colorize.AUTO:
        return terminal_supports_colors(stream)
    elif colorize == fancylogger.Colorize.ALWAYS:
        return True
    else:
        assert colorize == fancylogger.Colorize.NEVER, \
            "Argument `colorize` must be one of: %s" % ', '.join(fancylogger.Colorize)
        return False


class EasyBuildOptions(GeneralOption):
    """Easybuild generaloption class"""
    VERSION = this_is_easybuild()

    DEFAULT_LOGLEVEL = 'INFO'
    DEFAULT_CONFIGFILES = DEFAULT_SYS_CFGFILES[:]
    if os.path.exists(DEFAULT_USER_CFGFILE):
        DEFAULT_CONFIGFILES.append(DEFAULT_USER_CFGFILE)

    ALLOPTSMANDATORY = False  # allow more than one argument
    CONFIGFILES_RAISE_MISSING = True  # don't allow non-existing config files to be specified

    def __init__(self, *args, **kwargs):
        """Constructor."""

        self.with_include = kwargs.pop('with_include', True)

        self.default_repositorypath = [mk_full_default_path('repositorypath')]
        self.default_robot_paths = get_paths_for(subdir=EASYCONFIGS_PKG_SUBDIR, robot_path=None) or []

        # set up constants to seed into config files parser, by section
        self.go_cfg_constants = {
            self.DEFAULTSECT: {
                'DEFAULT_REPOSITORYPATH': (self.default_repositorypath[0],
                                           "Default easyconfigs repository path"),
                'DEFAULT_ROBOT_PATHS': (os.pathsep.join(self.default_robot_paths),
                                        "List of default robot paths ('%s'-separated)" % os.pathsep),
                'USER': (pwd.getpwuid(os.geteuid()).pw_name,
                         "Current username, translated uid from password file"),
                'HOME': (os.path.expanduser('~'),
                         "Current user's home directory, expanded '~'")
            }
        }

        # update or define go_configfiles_initenv in named arguments to pass to parent constructor
        go_cfg_initenv = kwargs.setdefault('go_configfiles_initenv', {})
        for section, constants in self.go_cfg_constants.items():
            constants = dict([(name, value) for (name, (value, _)) in constants.items()])
            go_cfg_initenv.setdefault(section, {}).update(constants)

        super(EasyBuildOptions, self).__init__(*args, **kwargs)

    def basic_options(self):
        """basic runtime options"""
        all_stops = [x[0] for x in EasyBlock.get_steps()]
        strictness_options = [IGNORE, WARN, ERROR]

        descr = ("Basic options", "Basic runtime options for EasyBuild.")

        opts = OrderedDict({
            'dry-run': ("Print build overview incl. dependencies (full paths)", None, 'store_true', False),
            'dry-run-short': ("Print build overview incl. dependencies (short paths)", None, 'store_true', False, 'D'),
            'extended-dry-run': ("Print build environment and (expected) build procedure that will be performed",
                                 None, 'store_true', False, 'x'),
            'extended-dry-run-ignore-errors': ("Ignore errors that occur during dry run", None, 'store_true', True),
            'force': ("Force to rebuild software even if it's already installed (i.e. if it can be found as module), "
                      "and skipping check for OS dependencies", None, 'store_true', False, 'f'),
            'job': ("Submit the build as a job", None, 'store_true', False),
            'logtostdout': ("Redirect main log to stdout", None, 'store_true', False, 'l'),
            'only-blocks': ("Only build listed blocks", 'strlist', 'extend', None, 'b', {'metavar': 'BLOCKS'}),
            'rebuild': ("Rebuild software, even if module already exists (don't skip OS dependencies checks)",
                        None, 'store_true', False),
            'robot': ("Enable dependency resolution, using easyconfigs in specified paths",
                      'pathlist', 'store_or_None', [], 'r', {'metavar': 'PATH[%sPATH]' % os.pathsep}),
            'robot-paths': ("Additional paths to consider by robot for easyconfigs (--robot paths get priority)",
                            'pathlist', 'add_flex', self.default_robot_paths, {'metavar': 'PATH[%sPATH]' % os.pathsep}),
            'search-paths': ("Additional locations to consider in --search (next to --robot and --robot-paths paths)",
                             'pathlist', 'store_or_None', [], {'metavar': 'PATH[%sPATH]' % os.pathsep}),
            'skip': ("Skip existing software (useful for installing additional packages)",
                     None, 'store_true', False, 'k'),
            'stop': ("Stop the installation after certain step",
                     'choice', 'store_or_None', SOURCE_STEP, 's', all_stops),
            'strict': ("Set strictness level", 'choice', 'store', WARN, strictness_options),
        })

        self.log.debug("basic_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def software_options(self):
        # software build options
        descr = ("Software search and build options",
                 ("Specify software search and build options: EasyBuild will search for a "
                  "matching easyconfig and build it. When called with the try prefix "
                  "(i.e. --try-X ), EasyBuild will search for a matching easyconfig "
                  "and if none are found, try to generate one based on a close matching one "
                  "(NOTE: --try-X is best effort, it might produce wrong builds!)")
                 )

        opts = OrderedDict({
            'amend': (("Specify additional search and build parameters (can be used multiple times); "
                       "for example: versionprefix=foo or patches=one.patch,two.patch)"),
                      None, 'append', None, {'metavar': 'VAR=VALUE[,VALUE]'}),
            'software': ("Search and build software with given name and version",
                         'strlist', 'extend', None, {'metavar': 'NAME,VERSION'}),
            'software-name': ("Search and build software with given name",
                              None, 'store', None, {'metavar': 'NAME'}),
            'software-version': ("Search and build software with given version",
                                 None, 'store', None, {'metavar': 'VERSION'}),
            'toolchain': ("Search and build with given toolchain (name and version)",
                          'strlist', 'extend', None, {'metavar': 'NAME,VERSION'}),
            'toolchain-name': ("Search and build with given toolchain name",
                               None, 'store', None, {'metavar': 'NAME'}),
            'toolchain-version': ("Search and build with given toolchain version",
                                  None, 'store', None, {'metavar': 'VERSION'}),
        })

        longopts = opts.keys()
        for longopt in longopts:
            hlp = opts[longopt][0]
            hlp = "Try to %s (USE WITH CARE!)" % (hlp[0].lower() + hlp[1:])
            opts["try-%s" % longopt] = (hlp,) + opts[longopt][1:]

        self.log.debug("software_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def override_options(self):
        # override options
        descr = ("Override options", "Override default EasyBuild behavior.")

        opts = OrderedDict({
            'add-dummy-to-minimal-toolchains': ("Include dummy in minimal toolchain searches", None, 'store_true', False),
            'allow-loaded-modules': ("List of software names for which to allow loaded modules in initial environment",
                                     'strlist', 'store', DEFAULT_ALLOW_LOADED_MODULES),
            'allow-modules-tool-mismatch': ("Allow mismatch of modules tool and definition of 'module' function",
                                            None, 'store_true', False),
            'allow-use-as-root-and-accept-consequences': ("Allow using of EasyBuild as root (NOT RECOMMENDED!)",
                                                          None, 'store_true', False),
            'backup-modules': ("Back up an existing module file, if any. Only works when using --module-only",
                               None, 'store_true', None),  # default None to allow auto-enabling if not disabled
            'check-ebroot-env-vars': ("Action to take when defined $EBROOT* environment variables are found "
                                      "for which there is no matching loaded module; "
                                      "supported values: %s" % ', '.join(EBROOT_ENV_VAR_ACTIONS), None, 'store', WARN),
            'cleanup-builddir': ("Cleanup build dir after successful installation.", None, 'store_true', True),
            'cleanup-tmpdir': ("Cleanup tmp dir after successful run.", None, 'store_true', True),
            'color': ("Colorize output", 'choice', 'store', fancylogger.Colorize.AUTO, fancylogger.Colorize,
                      {'metavar':'WHEN'}),
            'consider-archived-easyconfigs': ("Also consider archived easyconfigs", None, 'store_true', False),
            'debug-lmod': ("Run Lmod modules tool commands in debug module", None, 'store_true', False),
            'default-opt-level': ("Specify default optimisation level", 'choice', 'store', DEFAULT_OPT_LEVEL,
                                  Compiler.COMPILER_OPT_FLAGS),
            'deprecated': ("Run pretending to be (future) version, to test removal of deprecated code.",
                           None, 'store', None),
            'detect-loaded-modules': ("Detect loaded EasyBuild-generated modules, act accordingly; "
                                      "supported values: %s" % ', '.join(LOADED_MODULES_ACTIONS), None, 'store', WARN),
            'devel': ("Enable including of development log messages", None, 'store_true', False),
            'download-timeout': ("Timeout for initiating downloads (in seconds)", float, 'store', None),
            'dump-autopep8': ("Reformat easyconfigs using autopep8 when dumping them", None, 'store_true', False),
            'easyblock': ("easyblock to use for processing the spec file or dumping the options",
                          None, 'store', None, 'e', {'metavar': 'CLASS'}),
            'enforce-checksums': ("Enforce availability of checksums for all sources/patches, so they can be verified",
                                  None, 'store_true', False),
            'experimental': ("Allow experimental code (with behaviour that can be changed/removed at any given time).",
                             None, 'store_true', False),
            'extra-modules': ("List of extra modules to load after setting up the build environment",
                              'strlist', 'extend', None),
            'filter-deps': ("List of dependencies that you do *not* want to install with EasyBuild, "
                            "because equivalent OS packages are installed. (e.g. --filter-deps=zlib,ncurses)",
                            'strlist', 'extend', None),
            'filter-env-vars': ("List of names of environment variables that should *not* be defined/updated by "
                                "module files generated by EasyBuild", 'strlist', 'extend', None),
            'fixed-installdir-naming-scheme': ("Use fixed naming scheme for installation directories", None,
                                               'store_true', False),
            'force-download': ("Force re-downloading of sources and/or patches, "
                               "even if they are available already in source path",
                                'choice', 'store_or_None', DEFAULT_FORCE_DOWNLOAD, FORCE_DOWNLOAD_CHOICES),
            'group': ("Group to be used for software installations (only verified, not set)", None, 'store', None),
            'group-writable-installdir': ("Enable group write permissions on installation directory after installation",
                                          None, 'store_true', False),
            'hidden': ("Install 'hidden' module file(s) by prefixing their version with '.'", None, 'store_true', False),
            'hide-deps': ("Comma separated list of dependencies that you want automatically hidden, "
                          "(e.g. --hide-deps=zlib,ncurses)", 'strlist', 'extend', None),
            'hide-toolchains': ("Comma separated list of toolchains that you want automatically hidden, "
                                "(e.g. --hide-toolchains=GCCcore)", 'strlist', 'extend', None),
            'ignore-checksums': ("Ignore failing checksum verification", None, 'store_true', False),
            'ignore-osdeps': ("Ignore any listed OS dependencies", None, 'store_true', False),
            'install-latest-eb-release': ("Install latest known version of easybuild", None, 'store_true', False),
            'max-fail-ratio-adjust-permissions': ("Maximum ratio for failures to allow when adjusting permissions",
                                                  'float', 'store', DEFAULT_MAX_FAIL_RATIO_PERMS),
            'minimal-toolchains': ("Use minimal toolchain when resolving dependencies", None, 'store_true', False),
            'module-only': ("Only generate module file(s); skip all steps except for %s" % ', '.join(MODULE_ONLY_STEPS),
                            None, 'store_true', False),
            'mpi-cmd-template': ("Template for MPI commands (template keys: %(nr_ranks)s, %(cmd)s)",
                                 None, 'store', None),
            'mpi-tests': ("Run MPI tests (when relevant)", None, 'store_true', True),
            'optarch': ("Set architecture optimization, overriding native architecture optimizations",
                        None, 'store', None),
            'output-format': ("Set output format", 'choice', 'store', FORMAT_TXT, [FORMAT_TXT, FORMAT_RST]),
            'parallel': ("Specify (maximum) level of parallellism used during build procedure",
                         'int', 'store', None),
            'pretend': (("Does the build/installation in a test directory located in $HOME/easybuildinstall"),
                        None, 'store_true', False, 'p'),
            'read-only-installdir': ("Set read-only permissions on installation directory after installation",
                                     None, 'store_true', False),
            'rpath': ("Enable use of RPATH for linking with libraries", None, 'store_true', False),
            'rpath-filter': ("List of regex patterns to use for filtering out RPATH paths", 'strlist', 'store', None),
            'set-default-module': ("Set the generated module as default", None, 'store_true', False),
            'set-gid-bit': ("Set group ID bit on newly created directories", None, 'store_true', False),
            'sticky-bit': ("Set sticky bit on newly created directories", None, 'store_true', False),
            'skip-test-cases': ("Skip running test cases", None, 'store_true', False, 't'),
            'trace': ("Provide more information in output to stdout on progress", None, 'store_true', False, 'T'),
            'umask': ("umask to use (e.g. '022'); non-user write permissions on install directories are removed",
                      None, 'store', None),
            'update-modules-tool-cache': ("Update modules tool cache file(s) after generating module file",
                                          None, 'store_true', False),
            'use-ccache': ("Enable use of ccache to speed up compilation, with specified cache dir",
                           str, 'store', False, {'metavar': "PATH"}),
            'use-f90cache': ("Enable use of f90cache to speed up compilation, with specified cache dir",
                             str, 'store', False, {'metavar': "PATH"}),
            'use-existing-modules': ("Use existing modules when resolving dependencies with minimal toolchains",
                                     None, 'store_true', False),
            'verify-easyconfig-filenames': ("Verify whether filename of specified easyconfigs matches with contents",
                                            None, 'store_true', False),
            'zip-logs': ("Zip logs that are copied to install directory, using specified command",
                         None, 'store_or_None', 'gzip'),

        })

        self.log.debug("override_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def config_options(self):
        # config options
        descr = ("Configuration options", "Configure EasyBuild behavior.")

        opts = OrderedDict({
            'avail-module-naming-schemes': ("Show all supported module naming schemes",
                                            None, 'store_true', False,),
            'avail-modules-tools': ("Show all supported module tools",
                                    None, "store_true", False,),
            'avail-repositories': ("Show all repository types (incl. non-usable)",
                                   None, "store_true", False,),
            'buildpath': ("Temporary build path", None, 'store', mk_full_default_path('buildpath')),
            'external-modules-metadata': ("List of files specifying metadata for external modules (INI format)",
                                          'strlist', 'store', None),
            'hooks': ("Location of Python module with hook implementations", 'str', 'store', None),
            'ignore-dirs': ("Directory names to ignore when searching for files/dirs",
                            'strlist', 'store', ['.git', '.svn']),
            'include-easyblocks': ("Location(s) of extra or customized easyblocks", 'strlist', 'store', []),
            'include-module-naming-schemes': ("Location(s) of extra or customized module naming schemes",
                                              'strlist', 'store', []),
            'include-toolchains': ("Location(s) of extra or customized toolchains or toolchain components",
                                   'strlist', 'store', []),
            'installpath': ("Install path for software and modules",
                            None, 'store', mk_full_default_path('installpath')),
            'installpath-modules': ("Install path for modules (if None, combine --installpath and --subdir-modules)",
                                    None, 'store', None),
            'installpath-software': ("Install path for software (if None, combine --installpath and --subdir-software)",
                                     None, 'store', None),
            'job-backend': ("Backend to use for submitting jobs", 'choice', 'store',
                            DEFAULT_JOB_BACKEND, sorted(avail_job_backends().keys())),
            # purposely take a copy for the default logfile format
            'logfile-format': ("Directory name and format of the log file",
                               'strtuple', 'store', DEFAULT_LOGFILE_FORMAT[:], {'metavar': 'DIR,FORMAT'}),
            'module-naming-scheme': ("Module naming scheme to use", None, 'store', DEFAULT_MNS),
            'module-syntax': ("Syntax to be used for module files", 'choice', 'store', DEFAULT_MODULE_SYNTAX,
                              sorted(avail_module_generators().keys())),
            'moduleclasses': (("Extend supported module classes "
                               "(For more info on the default classes, use --show-default-moduleclasses)"),
                              'strlist', 'extend', [x[0] for x in DEFAULT_MODULECLASSES]),
            'modules-footer': ("Path to file containing footer to be added to all generated module files",
                               None, 'store_or_None', None, {'metavar': "PATH"}),
            'modules-header': ("Path to file containing header to be added to all generated module files",
                               None, 'store_or_None', None, {'metavar': "PATH"}),
            'modules-tool': ("Modules tool to use",
                             'choice', 'store', DEFAULT_MODULES_TOOL, sorted(avail_modules_tools().keys())),
            'packagepath': ("The destination path for the packages built by package-tool",
                             None, 'store', mk_full_default_path('packagepath')),
            'package-naming-scheme': ("Packaging naming scheme choice",
                                      'choice', 'store', DEFAULT_PNS, sorted(avail_package_naming_schemes().keys())),
            'prefix': (("Change prefix for buildpath, installpath, sourcepath and repositorypath "
                        "(used prefix for defaults %s)" % DEFAULT_PREFIX),
                       None, 'store', None),
            'recursive-module-unload': ("Enable generating of modules that unload recursively.",
                                        None, 'store_true', False),
            'repository': ("Repository type, using repositorypath",
                           'choice', 'store', DEFAULT_REPOSITORY, sorted(avail_repositories().keys())),
            'repositorypath': (("Repository path, used by repository "
                                "(is passed as list of arguments to create the repository instance). "
                                "For more info, use --avail-repositories."),
                               'strlist', 'store', self.default_repositorypath),
            'sourcepath': ("Path(s) to where sources should be downloaded (string, colon-separated)",
                           None, 'store', mk_full_default_path('sourcepath')),
            'subdir-modules': ("Installpath subdir for modules", None, 'store', DEFAULT_PATH_SUBDIRS['subdir_modules']),
            'subdir-software': ("Installpath subdir for software",
                                None, 'store', DEFAULT_PATH_SUBDIRS['subdir_software']),
            'subdir-user-modules': ("Base path of user-specific modules relative to their $HOME", None, 'store', None),
            'suffix-modules-path': ("Suffix for module files install path", None, 'store', GENERAL_CLASS),
            # this one is sort of an exception, it's something jobscripts can set,
            # has no real meaning for regular eb usage
            'testoutput': ("Path to where a job should place the output (to be set within jobscript)",
                           None, 'store', None),
            'tmp-logdir': ("Log directory where temporary log files are stored", None, 'store', None),
            'tmpdir': ('Directory to use for temporary storage', None, 'store', None),
        })

        self.log.debug("config_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def informative_options(self):
        # informative options
        descr = ("Informative options", "Obtain information about EasyBuild.")

        opts = OrderedDict({
            'avail-cfgfile-constants': ("Show all constants that can be used in configuration files",
                                        None, 'store_true', False),
            'avail-easyconfig-constants': ("Show all constants that can be used in easyconfigs",
                                           None, 'store_true', False),
            'avail-easyconfig-licenses': ("Show all license constants that can be used in easyconfigs",
                                          None, 'store_true', False),
            'avail-easyconfig-params': (("Show all easyconfig parameters (include "
                                         "easyblock-specific ones by using -e)"),
                                        None, 'store_true', False, 'a'),
            'avail-easyconfig-templates': (("Show all template names and template constants "
                                            "that can be used in easyconfigs."),
                                           None, 'store_true', False),
            'avail-hooks': ("Show list of known hooks", None, 'store_true', False),
            'avail-toolchain-opts': ("Show options for toolchain", 'str', 'store', None),
            'check-conflicts': ("Check for version conflicts in dependency graphs", None, 'store_true', False),
            'dep-graph': ("Create dependency graph", None, 'store', None, {'metavar': 'depgraph.<ext>'}),
            'dump-env-script': ("Dump source script to set up build environment based on toolchain/dependencies",
                                None, 'store_true', False),
            'last-log': ("Print location to EasyBuild log file of last (failed) session", None, 'store_true', False),
            'list-easyblocks': ("Show list of available easyblocks",
                                'choice', 'store_or_None', 'simple', ['simple', 'detailed']),
            'list-installed-software': ("Show list of installed software", 'choice', 'store_or_None', 'simple',
                                        ['simple', 'detailed']),
            'list-software': ("Show list of supported software", 'choice', 'store_or_None', 'simple',
                              ['simple', 'detailed']),
            'list-toolchains': ("Show list of known toolchains",
                                None, 'store_true', False),
            'search': ("Search for easyconfig files in the robot search path, print full paths",
                       None, 'store', None, {'metavar': 'REGEX'}),
            'search-filename': ("Search for easyconfig files in the robot search path, print only filenames",
                                None, 'store', None, {'metavar': 'REGEX'}),
            'search-short': ("Search for easyconfig files in the robot search path, print short paths",
                             None, 'store', None, 'S', {'metavar': 'REGEX'}),
            'show-config': ("Show current EasyBuild configuration (only non-default + selected settings)",
                            None, 'store_true', False),
            'show-full-config': ("Show current EasyBuild configuration (all settings)", None, 'store_true', False),
            'show-default-configfiles': ("Show list of default config files", None, 'store_true', False),
            'show-default-moduleclasses': ("Show default module classes with description",
                                           None, 'store_true', False),
            'terse': ("Terse output (machine-readable)", None, 'store_true', False),
        })

        self.log.debug("informative_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def github_options(self):
        """GitHub integration configuration options."""
        descr = ("GitHub integration options", "Integration with GitHub")

        opts = OrderedDict({
            'check-github': ("Check status of GitHub integration, and report back", None, 'store_true', False),
            'check-style': ("Run a style check on the given easyconfigs", None, 'store_true', False),
            'cleanup-easyconfigs': ("Clean up easyconfig files for pull request", None, 'store_true', True),
            'dump-test-report': ("Dump test report to specified path", None, 'store_or_None', 'test_report.md'),
            'from-pr': ("Obtain easyconfigs from specified PR", int, 'store', None, {'metavar': 'PR#'}),
            'git-working-dirs-path': ("Path to Git working directories for EasyBuild repositories", str, 'store', None),
            'github-user': ("GitHub username", str, 'store', None),
            'github-org': ("GitHub organization", str, 'store', None),
            'install-github-token': ("Install GitHub token (requires --github-user)", None, 'store_true', False),
            'merge-pr': ("Merge pull request", int, 'store', None, {'metavar': 'PR#'}),
            'new-pr': ("Open a new pull request", None, 'store_true', False),
            'pr-branch-name': ("Branch name to use for new PRs; '<timestamp>_new_pr_<name><version>' if unspecified",
                               str, 'store', None),
            'pr-commit-msg': ("Commit message for new/updated pull request created with --new-pr", str, 'store', None),
            'pr-descr': ("Description for new pull request created with --new-pr", str, 'store', None),
            'pr-target-account': ("Target account for new PRs", str, 'store', GITHUB_EB_MAIN),
            'pr-target-branch': ("Target branch for new PRs", str, 'store', 'develop'),
            'pr-target-repo': ("Target repository for new/updating PRs", str, 'store', GITHUB_EASYCONFIGS_REPO),
            'pr-title': ("Title for new pull request created with --new-pr", str, 'store', None),
            'preview-pr': ("Preview a new pull request", None, 'store_true', False),
            'review-pr': ("Review specified pull request", int, 'store', None, {'metavar': 'PR#'}),
            'test-report-env-filter': ("Regex used to filter out variables in environment dump of test report",
                                       None, 'regex', None),
            'update-pr': ("Update an existing pull request", int, 'store', None, {'metavar': 'PR#'}),
            'upload-test-report': ("Upload full test report as a gist on GitHub", None, 'store_true', False, 'u'),
        })

        self.log.debug("github_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def regtest_options(self):
        """Regression test configuration options."""
        descr = ("Regression test options", "Run and control an EasyBuild regression test.")

        opts = OrderedDict({
            'aggregate-regtest': ("Collect all the xmls inside the given directory and generate a single file",
                                  None, 'store', None, {'metavar': 'DIR'}),
            'regtest': ("Enable regression test mode",
                        None, 'store_true', False),
            'regtest-output-dir': ("Set output directory for test-run",
                                   None, 'store', None, {'metavar': 'DIR'}),
            'sequential': ("Specify this option if you want to prevent parallel build",
                           None, 'store_true', False),
        })

        self.log.debug("regtest_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def package_options(self):
        # package-related options
        descr = ("Package options", "Control packaging performed by EasyBuild.")

        opts = OrderedDict({
            'package': ("Enabling packaging", None, 'store_true', False),
            'package-tool': ("Packaging tool to use", None, 'store', DEFAULT_PKG_TOOL),
            'package-tool-options': ("Extra options for packaging tool", None, 'store', ''),
            'package-type': ("Type of package to generate", None, 'store', DEFAULT_PKG_TYPE),
            'package-release': ("Package release iteration number", None, 'store', DEFAULT_PKG_RELEASE),
        })

        self.log.debug("package_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr)

    def easyconfig_options(self):
        # easyconfig options (to be passed to easyconfig instance)
        descr = ("Options for Easyconfigs", "Options to be passed to all Easyconfig.")

        opts = OrderedDict({
            'inject-checksums': ("Inject checksums of specified type for sources/patches into easyconfig file(s)",
                                 'choice', 'store_or_None', CHECKSUM_TYPE_SHA256, CHECKSUM_TYPES),
        })
        self.log.debug("easyconfig_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr, prefix='')

    def job_options(self):
        """Option related to --job."""
        descr = ("Options for job backend", "Options for job backend (only relevant when --job is used)")

        opts = OrderedDict({
            'backend-config': ("Configuration file for job backend", None, 'store', None),
            'cores': ("Number of cores to request per job", 'int', 'store', None),
            'max-walltime': ("Maximum walltime for jobs (in hours)", 'int', 'store', 24),
            'output-dir': ("Output directory for jobs (default: current directory)", None, 'store', os.getcwd()),
            'polling-interval': ("Interval between polls for status of jobs (in seconds)", float, 'store', 30.0),
            'target-resource': ("Target resource for jobs", None, 'store', None),
        })

        self.log.debug("job_options: descr %s opts %s", descr, opts)
        self.add_group_parser(opts, descr, prefix='job')

    def easyblock_options(self):
        # easyblock options (to be passed to easyblock instance)
        descr = ("Options for Easyblocks", "Options to be passed to all Easyblocks.")

        opts = None
        self.log.debug("easyblock_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr, prefix='easyblock')

    def unittest_options(self):
        # unittest options
        descr = ("Unittest options", "Options dedicated to unittesting (experts only).")

        opts = OrderedDict({
            'file': ("Log to this file in unittest mode", None, 'store', None),
        })

        self.log.debug("unittest_options: descr %s opts %s" % (descr, opts))
        self.add_group_parser(opts, descr, prefix='unittest')

    def validate(self):
        """Additional validation of options"""
        error_msgs = []

        for opt in ['software', 'try-software', 'toolchain', 'try-toolchain']:
            val = getattr(self.options, opt.replace('-', '_'))
            if val and len(val) != 2:
                msg = "--%s requires NAME,VERSION (given %s)" % (opt, ','.join(val))
                error_msgs.append(msg)

        if self.options.umask:
            umask_regex = re.compile('^[0-7]{3}$')
            if not umask_regex.match(self.options.umask):
                msg = "--umask value should be 3 digits (0-7) (regex pattern '%s')" % umask_regex.pattern
                error_msgs.append(msg)

        # subdir options must be relative
        for typ in ['modules', 'software']:
            subdir_opt = 'subdir_%s' % typ
            val = getattr(self.options, subdir_opt)
            if os.path.isabs(getattr(self.options, subdir_opt)):
                msg = "Configuration option '%s' must specify a *relative* path (use 'installpath-%s' instead?): '%s'"
                msg = msg % (subdir_opt, typ, val)
                error_msgs.append(msg)

        # specified module naming scheme must be a known one
        avail_mnss = avail_module_naming_schemes()
        if self.options.module_naming_scheme and self.options.module_naming_scheme not in avail_mnss:
            msg = "Selected module naming scheme '%s' is unknown: %s" % (self.options.module_naming_scheme, avail_mnss)
            error_msgs.append(msg)

        if error_msgs:
            raise EasyBuildError("Found problems validating the options: %s", '\n'.join(error_msgs))

    def postprocess(self):
        """Do some postprocessing, in particular print stuff"""
        build_log.EXPERIMENTAL = self.options.experimental

        # enable devel logging
        if self.options.devel:
            setLogLevel(DEVEL_LOG_LEVEL)

        # set strictness of run module
        if self.options.strict:
            run.strictness = self.options.strict

        # override current version of EasyBuild with version specified to --deprecated
        if self.options.deprecated:
            build_log.CURRENT_VERSION = LooseVersion(self.options.deprecated)

        # log to specified value of --unittest-file
        if self.options.unittest_file:
            fancylogger.logToFile(self.options.unittest_file, max_bytes=0)

        # set tmpdir
        self.tmpdir = set_tmpdir(self.options.tmpdir)

        # take --include options into account (unless instructed otherwise)
        if self.with_include:
            self._postprocess_include()

        # prepare for --list/--avail
        if any([self.options.avail_easyconfig_params, self.options.avail_easyconfig_templates,
                self.options.list_easyblocks, self.options.list_toolchains, self.options.avail_cfgfile_constants,
                self.options.avail_easyconfig_constants, self.options.avail_easyconfig_licenses,
                self.options.avail_repositories, self.options.show_default_moduleclasses,
                self.options.avail_modules_tools, self.options.avail_module_naming_schemes,
                self.options.show_default_configfiles, self.options.avail_toolchain_opts,
                self.options.avail_hooks,
                ]):
            build_easyconfig_constants_dict()  # runs the easyconfig constants sanity check
            self._postprocess_list_avail()

        # fail early if required dependencies for functionality requiring using GitHub API are not available:
        if self.options.from_pr or self.options.upload_test_report:
            if not HAVE_GITHUB_API:
                raise EasyBuildError("Required support for using GitHub API is not available (see warnings).")

        if self.options.module_syntax == ModuleGeneratorLua.SYNTAX and self.options.modules_tool != Lmod.__name__:
            error_msg = "Generating Lua module files requires Lmod as modules tool; "
            mod_syntaxes = ', '.join(sorted(avail_module_generators().keys()))
            error_msg += "use --module-syntax to specify a different module syntax to use (%s)" % mod_syntaxes
            raise EasyBuildError(error_msg)

        # check whether specified action --detect-loaded-modules is valid
        if self.options.detect_loaded_modules not in LOADED_MODULES_ACTIONS:
            raise EasyBuildError("Unknown action specified to --detect-loaded-modules: %s (known values: %s)",
                                 self.options.detect_loaded_modules, ', '.join(LOADED_MODULES_ACTIONS))

        # make sure a GitHub token is available when it's required
        if self.options.upload_test_report:
            if not HAVE_KEYRING:
                raise EasyBuildError("Python 'keyring' module required for obtaining GitHub token is not available.")
            if self.options.github_user is None:
                raise EasyBuildError("No GitHub user name provided, required for fetching GitHub token.")
            token = fetch_github_token(self.options.github_user)
            if token is None:
                raise EasyBuildError("Failed to obtain required GitHub token for user '%s'", self.options.github_user)

        # make sure autopep8 is available when it needs to be
        if self.options.dump_autopep8:
            if not HAVE_AUTOPEP8:
                raise EasyBuildError("Python 'autopep8' module required to reformat dumped easyconfigs as requested")

        # imply --terse for --last-log to avoid extra output that gets in the way
        if self.options.last_log:
            self.options.terse = True

        # auto-enable --backup-modules with --skip and --module-only, unless it was hard disabled
        if (self.options.module_only or self.options.skip) and self.options.backup_modules is None:
            self.log.debug("Auto-enabling --backup-modules because of --module-only or --skip")
            self.options.backup_modules = True

        # make sure --optarch has a valid format, but do it only if we are not going to submit jobs. Otherwise it gets
        # processed twice and fails when trying to parse a dictionary as if it was a string
        if self.options.optarch and not self.options.job:
            self._postprocess_optarch()

        # handle configuration options that affect other configuration options
        self._postprocess_config()

        # show current configuration and exit, if requested
        if self.options.show_config or self.options.show_full_config:
            self.show_config()
            cleanup_and_exit(self.tmpdir)

    def _postprocess_optarch(self):
        """Postprocess --optarch option."""
        optarch_parts = self.options.optarch.split(OPTARCH_SEP)

        # we expect to find a ':' in every entry in optarch, in case optarch is specified on a per-compiler basis
        n_parts = len(optarch_parts)
        map_char_cnts = [p.count(OPTARCH_MAP_CHAR) for p in optarch_parts]
        if (n_parts > 1 and any(c != 1 for c in map_char_cnts)) or (n_parts == 1 and map_char_cnts[0] > 1):
            raise EasyBuildError("The optarch option has an incorrect syntax: %s", self.options.optarch)
        else:
            # if there are options for different compilers, we set up a dict
            if OPTARCH_MAP_CHAR in optarch_parts[0]:
                optarch_dict = {}
                for compiler, compiler_opt in [p.split(OPTARCH_MAP_CHAR) for p in optarch_parts]:
                    if compiler in optarch_dict:
                        raise EasyBuildError("The optarch option contains duplicated entries for compiler %s: %s",
                                             compiler, self.options.optarch)
                    else:
                        optarch_dict[compiler] = compiler_opt
                self.options.optarch = optarch_dict
                self.log.info("Transforming optarch into a dict: %s", self.options.optarch)
            # if optarch is not in mapping format, we do nothing and just keep the string
            else:
                self.log.info("Keeping optarch raw: %s", self.options.optarch)

    def _postprocess_include(self):
        """Postprocess --include options."""
        # set up included easyblocks, module naming schemes and toolchains/toolchain components
        if self.options.include_easyblocks:
            include_easyblocks(self.tmpdir, self.options.include_easyblocks)

        if self.options.include_module_naming_schemes:
            include_module_naming_schemes(self.tmpdir, self.options.include_module_naming_schemes)

        if self.options.include_toolchains:
            include_toolchains(self.tmpdir, self.options.include_toolchains)

    def _postprocess_config(self):
        """Postprocessing of configuration options"""
        if self.options.prefix is not None:
            # prefix applies to all paths, and repository has to be reinitialised to take new repositorypath in account
            # in the legacy-style configuration, repository is initialised in configuration file itself
            for dest in ['installpath', 'buildpath', 'sourcepath', 'repository', 'repositorypath', 'packagepath']:
                if not self.options._action_taken.get(dest, False):
                    if dest == 'repository':
                        setattr(self.options, dest, DEFAULT_REPOSITORY)
                    elif dest == 'repositorypath':
                        repositorypath = [mk_full_default_path(dest, prefix=self.options.prefix)]
                        setattr(self.options, dest, repositorypath)
                        self.go_cfg_constants[self.DEFAULTSECT]['DEFAULT_REPOSITORYPATH'] = repositorypath
                    else:
                        setattr(self.options, dest, mk_full_default_path(dest, prefix=self.options.prefix))
                    # LEGACY this line is here for oldstyle config reasons
                    self.options._action_taken[dest] = True

        if self.options.pretend:
            self.options.installpath = get_pretend_installpath()

        if self.options.robot is not None:
            # paths specified to --robot have preference over --robot-paths
            # keep both values in sync if robot is enabled, which implies enabling dependency resolver
            self.options.robot_paths = [os.path.abspath(path) for path in self.options.robot + self.options.robot_paths]
            self.options.robot = self.options.robot_paths

        # Update the search_paths (if any) to absolute paths
        if self.options.search_paths is not None:
            self.options.search_paths = [os.path.abspath(path) for path in self.options.search_paths]

    def _postprocess_list_avail(self):
        """Create all the additional info that can be requested (exit at the end)"""
        msg = ''

        # dump supported configuration file constants
        if self.options.avail_cfgfile_constants:
            msg += avail_cfgfile_constants(self.go_cfg_constants, self.options.output_format)

        # dump possible easyconfig params
        if self.options.avail_easyconfig_params:
            msg += avail_easyconfig_params(self.options.easyblock, self.options.output_format)

        # dump easyconfig template options
        if self.options.avail_easyconfig_templates:
            msg += avail_easyconfig_templates(self.options.output_format)

        # dump easyconfig constant options
        if self.options.avail_easyconfig_constants:
            msg += avail_easyconfig_constants(self.options.output_format)

        # dump easyconfig license options
        if self.options.avail_easyconfig_licenses:
            msg += avail_easyconfig_licenses(self.options.output_format)

        # dump available easyblocks
        if self.options.list_easyblocks:
            msg += list_easyblocks(self.options.list_easyblocks, self.options.output_format)

        # dump known toolchains
        if self.options.list_toolchains:
            msg += list_toolchains(self.options.output_format)

        # dump known toolchain options
        if self.options.avail_toolchain_opts:
            msg += avail_toolchain_opts(self.options.avail_toolchain_opts, self.options.output_format)

        # dump known repository types
        if self.options.avail_repositories:
            msg += self.avail_repositories()

        # dump supported modules tools
        if self.options.avail_modules_tools:
            msg += self.avail_list('modules tools', avail_modules_tools())

        # dump supported module naming schemes
        if self.options.avail_module_naming_schemes:
            msg += self.avail_list('module naming schemes', avail_module_naming_schemes())

        # dump default list of config files that are considered
        if self.options.show_default_configfiles:
            msg += self.show_default_configfiles()

        # dump default moduleclasses with description
        if self.options.show_default_moduleclasses:
            msg += self.show_default_moduleclasses()

        if self.options.avail_hooks:
            msg += self.avail_list('hooks (in order of execution)', KNOWN_HOOKS)

        if self.options.unittest_file:
            self.log.info(msg)
        else:
            print msg

        # cleanup tmpdir and exit
        cleanup_and_exit(self.tmpdir)

    def avail_repositories(self):
        """Show list of known repository types."""
        repopath_defaults = self.default_repositorypath
        all_repos = avail_repositories(check_useable=False)
        usable_repos = avail_repositories(check_useable=True).keys()

        indent = ' ' * 2
        txt = ['All avaliable repository types']
        repos = sorted(all_repos.keys())
        for repo in repos:
            if repo in usable_repos:
                missing = ''
            else:
                missing = ' (*not usable*, something is missing (e.g. a required Python module))'
            if repo in repopath_defaults:
                default = ' (default arguments: %s)' % ', '.join(repopath_defaults[repo])
            else:
                default = ' (no default arguments)'

            txt.append("%s* %s%s%s" % (indent, repo, default, missing))
            txt.append("%s%s" % (indent * 3, all_repos[repo].DESCRIPTION))

        return "\n".join(txt)

    def avail_list(self, name, items):
        """Show list of available values passed by argument."""
        return "List of supported %s:\n\t%s" % (name, '\n\t'.join(items))

    def show_default_configfiles(self):
        """Show list of default config files."""
        xdg_config_home = os.environ.get('XDG_CONFIG_HOME', '(not set)')
        xdg_config_dirs = os.environ.get('XDG_CONFIG_DIRS', '(not set)')
        system_cfg_glob_paths = os.path.join('{' + ', '.join(XDG_CONFIG_DIRS) + '}', 'easybuild.d', '*.cfg')
        found_cfgfile_cnt = len(self.DEFAULT_CONFIGFILES)
        found_cfgfile_list = ', '.join(self.DEFAULT_CONFIGFILES) or '(none)'
        lines = [
            "Default list of configuration files:",
            '',
            "[with $XDG_CONFIG_HOME: %s, $XDG_CONFIG_DIRS: %s]" % (xdg_config_home, xdg_config_dirs),
            '',
            "* user-level: %s" % os.path.join('${XDG_CONFIG_HOME:-$HOME/.config}', 'easybuild', 'config.cfg'),
            "  -> %s => %s" % (DEFAULT_USER_CFGFILE, ('not found', 'found')[os.path.exists(DEFAULT_USER_CFGFILE)]),
            "* system-level: %s" % os.path.join('${XDG_CONFIG_DIRS:-/etc}', 'easybuild.d', '*.cfg'),
            "  -> %s => %s" % (system_cfg_glob_paths, ', '.join(DEFAULT_SYS_CFGFILES) or "(no matches)"),
            '',
            "Default list of existing configuration files (%d): %s" % (found_cfgfile_cnt, found_cfgfile_list),
        ]
        return '\n'.join(lines)

    def show_default_moduleclasses(self):
        """Show list of default moduleclasses and description."""
        lines = ["Default available module classes:", '']
        maxlen = max([len(x[0]) for x in DEFAULT_MODULECLASSES]) + 1  # at least 1 space
        for name, descr in DEFAULT_MODULECLASSES:
            lines.append("\t%s:%s%s" % (name, (" " * (maxlen - len(name))), descr))
        return '\n'.join(lines)

    def show_config(self):
        """Show specified EasyBuild configuration, relative to default EasyBuild configuration."""
        # keep copy of original environment, so we can restore it later
        orig_env = copy.deepcopy(os.environ)

        # options that should never/always be printed
        ignore_opts = ['show_config', 'show_full_config']
        include_opts = ['buildpath', 'installpath', 'repositorypath', 'robot_paths', 'sourcepath']
        cmdline_opts_dict = self.dict_by_prefix()

        def reparse_cfg(args=None, withcfg=True):
            """
            Utility function to reparse EasyBuild configuration.
            :param args: command line arguments to pass to configuration parser
            :param withcfg: whether or not to also consider configuration files
            :return: dictionary with parsed configuration options, by option group
            """
            if args is None:
                args = []
            cfg = EasyBuildOptions(go_args=args, go_useconfigfiles=withcfg, envvar_prefix=CONFIG_ENV_VAR_PREFIX,
                                   with_include=False)

            return cfg.dict_by_prefix()

        def det_location(opt, prefix=''):
            """Determine location where option was defined."""
            cur_opt_val = cmdline_opts_dict[prefix][opt]

            if cur_opt_val == default_opts_dict[prefix][opt]:
                loc = 'D'  # default value
            elif cur_opt_val == cfgfile_opts_dict[prefix][opt]:
                loc = 'F'  # config file
            elif cur_opt_val == env_opts_dict[prefix][opt]:
                loc = 'E'  # environment variable
            else:
                loc = 'C'  # command line option

            return loc

        # modify environment such that no $EASYBUILD_* environment variables are defined
        unset_env_vars([v for v in os.environ if v.startswith(CONFIG_ENV_VAR_PREFIX)], verbose=False)
        no_eb_env = copy.deepcopy(os.environ)

        default_opts_dict = reparse_cfg(withcfg=False)
        cfgfile_opts_dict = reparse_cfg()

        restore_env(orig_env)
        env_opts_dict = reparse_cfg()

        # options relevant to config files should always be passed,
        # but we need to figure out first where these options were defined...
        args = []
        opts_dict = {}
        for opt in ['configfiles', 'ignoreconfigfiles']:
            # add option to list of arguments to pass when figuring out configuration level for all options
            opt_val = getattr(self.options, opt)
            if opt_val:
                args.append('--%s=%s' % (opt, ','.join(opt_val or [])))

            # keep track of location where this option was defined
            is_default = opt_val == default_opts_dict[''][opt]
            if self.options.show_full_config or opt in include_opts or not is_default:
                opts_dict[opt] = (opt_val, det_location(opt))

        # determine option dicts by selectively disabling configuration levels (but enable use configfiles)
        restore_env(no_eb_env)
        cfgfile_opts_dict = reparse_cfg(args=args)

        restore_env(orig_env)
        env_opts_dict = reparse_cfg(args=args)

        # construct options dict to pretty print
        for prefix in sorted(default_opts_dict):
            for opt in sorted(default_opts_dict[prefix]):
                cur_opt_val = cmdline_opts_dict[prefix][opt]

                if opt in ignore_opts or opt in opts_dict:
                    continue

                is_default = cur_opt_val == default_opts_dict[prefix][opt]
                if self.options.show_full_config or opt in include_opts or not is_default:
                    loc = det_location(opt, prefix=prefix)
                    opt = opt.replace('_', '-')
                    if prefix:
                        opt = '%s-%s' % (prefix, opt)

                    opts_dict[opt] = (cur_opt_val, loc)

        pretty_print_opts(opts_dict)


def parse_options(args=None, with_include=True):
    """wrapper function for option parsing"""
    if os.environ.get('DEBUG_EASYBUILD_OPTIONS', '0').lower() in ('1', 'true', 'yes', 'y'):
        # very early debug, to debug the generaloption itself
        fancylogger.logToScreen(enable=True)
        fancylogger.setLogLevel('DEBUG')

    usage = "%prog [options] easyconfig [...]"
    description = ("Builds software based on easyconfig (or parse a directory).\n"
                   "Provide one or more easyconfigs or directories, use -H or --help more information.")

    try:
        eb_go = EasyBuildOptions(usage=usage, description=description, prog='eb', envvar_prefix=CONFIG_ENV_VAR_PREFIX,
                                 go_args=args, error_env_options=True, error_env_option_method=raise_easybuilderror,
                                 with_include=with_include)
    except Exception as err:
        raise EasyBuildError("Failed to parse configuration options: %s" % err)

    return eb_go


def process_software_build_specs(options):
    """
    Create a dictionary with specified software build options.
    The options arguments should be a parsed option list (as delivered by parse_options(args).options)
    """

    try_to_generate = False
    build_specs = {}
    logger = fancylogger.getLogger()

    # regular options: don't try to generate easyconfig, and search
    opts_map = {
        'name': options.software_name,
        'version': options.software_version,
        'toolchain_name': options.toolchain_name,
        'toolchain_version': options.toolchain_version,
    }

    # try options: enable optional generation of easyconfig
    try_opts_map = {
        'name': options.try_software_name,
        'version': options.try_software_version,
        'toolchain_name': options.try_toolchain_name,
        'toolchain_version': options.try_toolchain_version,
    }

    # process easy options
    for (key, opt) in opts_map.items():
        if opt:
            build_specs[key] = opt
            # remove this key from the dict of try-options (overruled)
            try_opts_map.pop(key)

    for (key, opt) in try_opts_map.items():
        if opt:
            build_specs[key] = opt
            # only when a try option is set do we enable generating easyconfigs
            try_to_generate = True

    # process --(try-)software/toolchain
    for opt in ['software', 'toolchain']:
        val = getattr(options, opt)
        tryval = getattr(options, 'try_%s' % opt)
        if val or tryval:
            if val and tryval:
                logger.warning("Ignoring --try-%(opt)s, only using --%(opt)s specification" % {'opt': opt})
            elif tryval:
                try_to_generate = True
            val = val or tryval  # --try-X value is overridden by --X
            key_prefix = ''
            if opt == 'toolchain':
                key_prefix = 'toolchain_'
            build_specs.update({
                '%sname' % key_prefix: val[0],
                '%sversion' % key_prefix: val[1],
            })

    # provide both toolchain and toolchain_name/toolchain_version keys
    if 'toolchain_name' in build_specs:
        build_specs['toolchain'] = {
            'name': build_specs['toolchain_name'],
            'version': build_specs.get('toolchain_version', None),
        }

    # process --amend and --try-amend
    if options.amend or options.try_amend:

        amends = []
        if options.amend:
            amends += options.amend
            if options.try_amend:
                logger.warning("Ignoring options passed via --try-amend, only using those passed via --amend.")
        elif options.try_amend:
            amends += options.try_amend
            try_to_generate = True

        for amend_spec in amends:
            # e.g., 'foo=bar=baz' => foo = 'bar=baz'
            param = amend_spec.split('=')[0]
            value = '='.join(amend_spec.split('=')[1:])
            # support list values by splitting on ',' if its there
            # e.g., 'foo=bar,baz' => foo = ['bar', 'baz']
            if ',' in value:
                value = value.split(',')
            build_specs.update({param: value})

    return (try_to_generate, build_specs)


def parse_external_modules_metadata(cfgs):
    """
    Parse metadata for external modules.

    :param cfgs: list of config files providing metadata for external modules
    :return: parsed metadata for external modules
    """

    # use external modules metadata configuration files that are available by default, unless others are specified
    if not cfgs:
        # we expect to find *external_modules_metadata.cfg files in etc/
        topdir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        cfgs = glob.glob(os.path.join(topdir, 'etc', '*external_modules_metadata.cfg'))

        if cfgs:
            _log.info("Using default external modules metadata cfg files: %s", cfgs)
        else:
            _log.info("No default external modules metadata found")

    # leave external_modules_metadata untouched if no files are provided
    if not cfgs:
        _log.debug("No metadata provided for external modules.")
        return {}

    parsed_metadata = ConfigObj()
    for cfg in cfgs:
        if os.path.isfile(cfg):
            _log.debug("Parsing %s with external modules metadata", cfg)
            try:
                parsed_metadata.merge(ConfigObj(cfg))
            except ConfigObjError as err:
                raise EasyBuildError("Failed to parse %s with external modules metadata: %s", cfg, err)
        else:
            raise EasyBuildError("Specified path for file with external modules metadata does not exist: %s", cfg)

    # make sure name/version values are always lists, make sure they're equal length
    for mod, entry in parsed_metadata.items():
        for key in ['name', 'version']:
            if isinstance(entry.get(key), basestring):
                entry[key] = [entry[key]]
                _log.debug("Transformed external module metadata value %s for %s into a single-value list: %s",
                           key, mod, entry[key])

        # if both names and versions are available, lists must be of same length
        names, versions = entry.get('name'), entry.get('version')
        if names is not None and versions is not None and len(names) != len(versions):
            raise EasyBuildError("Different length for lists of names/versions in metadata for external module %s: "
                                 "names: %s; versions: %s", mod, names, versions)

    _log.debug("External modules metadata: %s", parsed_metadata)
    return parsed_metadata


def set_tmpdir(tmpdir=None, raise_error=False):
    """Set temporary directory to be used by tempfile and others."""
    try:
        if tmpdir is not None:
            if not os.path.exists(tmpdir):
                os.makedirs(tmpdir)
            current_tmpdir = tempfile.mkdtemp(prefix='eb-', dir=tmpdir)
        else:
            # use tempfile default parent dir
            current_tmpdir = tempfile.mkdtemp(prefix='eb-')
    except OSError, err:
        raise EasyBuildError("Failed to create temporary directory (tmpdir: %s): %s", tmpdir, err)

    # avoid having special characters like '[' and ']' in the tmpdir pathname,
    # it is known to cause problems (e.g., with Python install tools, CUDA's nvcc, etc.);
    # only common characteris like alphanumeric, '_', '-', '.' and '/' are retained; others are converted to 'X'
    special_chars_regex = r'[^\w/.-]'
    if re.search(special_chars_regex, current_tmpdir):
        current_tmpdir = re.sub(special_chars_regex, 'X', current_tmpdir)
        _log.info("Detected special characters in path to temporary directory, replacing them to avoid trouble: %s")
        try:
            os.makedirs(current_tmpdir)
        except OSError as err:
            raise EasyBuildError("Failed to create path to temporary directory %s: %s", current_tmpdir, err)

    _log.info("Temporary directory used in this EasyBuild run: %s" % current_tmpdir)

    for var in ['TMPDIR', 'TEMP', 'TMP']:
        env.setvar(var, current_tmpdir, verbose=False)

    # reset to make sure tempfile picks up new temporary directory to use
    tempfile.tempdir = None

    # test if temporary directory allows to execute files, warn if it doesn't
    try:
        fd, tmptest_file = tempfile.mkstemp()
        os.close(fd)
        os.chmod(tmptest_file, 0700)
        if not run_cmd(tmptest_file, simple=True, log_ok=False, regexp=False, force_in_dry_run=True, trace=False):
            msg = "The temporary directory (%s) does not allow to execute files. " % tempfile.gettempdir()
            msg += "This can cause problems in the build process, consider using --tmpdir."
            if raise_error:
                raise EasyBuildError(msg)
            else:
                _log.warning(msg)
        else:
            _log.debug("Temporary directory %s allows to execute files, good!" % tempfile.gettempdir())
        os.remove(tmptest_file)

    except OSError, err:
        raise EasyBuildError("Failed to test whether temporary directory allows to execute files: %s", err)

    return current_tmpdir
