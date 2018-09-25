# #
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
# #

"""
Easyconfig module that contains the default EasyConfig configuration parameters.

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Toon Willems (Ghent University)
"""
from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError


_log = fancylogger.getLogger('easyconfig.default', fname=False)

# constants for different categories of easyconfig parameters
# use tuples so we can sort them based on the numbers
HIDDEN = (-1, 'hidden')
MANDATORY = (0, 'mandatory')
CUSTOM = (1, 'easyblock-specific')
TOOLCHAIN = (2, 'toolchain')
BUILD = (3, 'build')
FILEMANAGEMENT = (4, 'file-management')
DEPENDENCIES = (5, 'dependencies')
LICENSE = (6, 'license')
EXTENSIONS = (7, 'extensions')
MODULES = (8, 'modules')
OTHER = (9, 'other')


# we use a tuple here so we can sort them based on the numbers
CATEGORY_NAMES = ['BUILD', 'CUSTOM', 'DEPENDENCIES', 'EXTENSIONS', 'FILEMANAGEMENT', 'HIDDEN',
                  'LICENSE', 'MANDATORY', 'MODULES', 'OTHER', 'TOOLCHAIN']
ALL_CATEGORIES = dict((name, eval(name)) for name in CATEGORY_NAMES)

# List of tuples. Each tuple has the following format (key, [default, help text, category])
DEFAULT_CONFIG = {
    # MANDATORY easyconfig parameters
    'description': [None, 'A short description of the software', MANDATORY],
    'homepage': [None, 'The homepage of the software', MANDATORY],
    'name': [None, "Name of software", MANDATORY],
    'toolchain': [None, 'Name and version of toolchain', MANDATORY],
    'version': [None, "Version of software", MANDATORY],
    # TODO not yet in MANDATORY_PARAMS, so not enforced (only enforced in v2)
    'software_license': [None, 'Software license', MANDATORY],
    'software_license_urls': [None, 'List of software license locations', MANDATORY],
    # TODO not yet in MANDATORY_PARAMS, so not enforced  (only enforced in v2)
    'docurls': [None, 'List of urls with documentation of the software (not necessarily on homepage)', MANDATORY],

    # TOOLCHAIN easyconfig parameters
    'onlytcmod': [False, ('Boolean/string to indicate if the toolchain should only load '
                          'the environment with module (True) or also set all other '
                          'variables (False) like compiler CC etc (if string: comma '
                          'separated list of variables that will be ignored).'), TOOLCHAIN],
    'toolchainopts': [None, 'Extra options for compilers', TOOLCHAIN],

    # BUILD easyconfig parameters
    'bitbucket_account': ['%(namelower)s', "Bitbucket account name to be used to resolve template values in source"
                                           " URLs", BUILD],
    'buildopts': ['', 'Extra options passed to make step (default already has -j X)', BUILD],
    'checksums': [[], "Checksums for sources and patches", BUILD],
    'configopts': ['', 'Extra options passed to configure (default already has --prefix)', BUILD],
    'easyblock': [None, "EasyBlock to use for building; if set to None, an easyblock is selected "
                        "based on the software name", BUILD],
    'easybuild_version': [None, "EasyBuild-version this spec-file was written for", BUILD],
    'github_account': ['%(namelower)s', "GitHub account name to be used to resolve template values in source URLs",
                       BUILD],
    'hidden': [False, "Install module file as 'hidden' by prefixing its version with '.'", BUILD],
    'installopts': ['', 'Extra options for installation', BUILD],
    'maxparallel': [None, 'Max degree of parallelism', BUILD],
    'parallel': [None, ('Degree of parallelism for e.g. make (default: based on the number of '
                        'cores, active cpuset and restrictions in ulimit)'), BUILD],
    'patches': [[], "List of patches to apply", BUILD],
    'prebuildopts': ['', 'Extra options pre-passed to build command.', BUILD],
    'preconfigopts': ['', 'Extra options pre-passed to configure.', BUILD],
    'preinstallopts': ['', 'Extra prefix options for installation.', BUILD],
    'postinstallcmds': [[], 'Commands to run after the install step.', BUILD],
    'runtest': [None, ('Indicates if a test should be run after make; should specify argument '
                       'after make (for e.g.,"test" for make test)'), BUILD],
    'sanity_check_commands': [[], ("format: [(name, options)] e.g. [('gzip','-h')]. "
                                   "Using a non-tuple is equivalent to (name, '-h')"), BUILD],
    'sanity_check_paths': [{}, ("List of files and directories to check "
                                "(format: {'files':<list>, 'dirs':<list>})"), BUILD],
    'skip': [False, "Skip existing software", BUILD],
    'skipsteps': [[], "Skip these steps", BUILD],
    'source_urls': [[], "List of URLs for source files", BUILD],
    'sources': [[], "List of source files", BUILD],
    'stop': [None, 'Keyword to halt the build process after a certain step.', BUILD],
    'tests': [[], ("List of test-scripts to run after install. A test script should return a "
                   "non-zero exit status to fail"), BUILD],
    'unpack_options': ['', "Extra options for unpacking source", BUILD],
    'unwanted_env_vars': [[], "List of environment variables that shouldn't be set during build", BUILD],
    'versionprefix': ['', ('Additional prefix for software version '
                           '(placed before version and toolchain name)'), BUILD],
    'versionsuffix': ['', 'Additional suffix for software version (placed after toolchain name)', BUILD],

    # FILEMANAGEMENT easyconfig parameters
    'buildininstalldir': [False, ('Boolean to build (True) or not build (False) in the installation directory'),
                          FILEMANAGEMENT],
    'cleanupoldbuild': [True, ('Boolean to remove (True) or backup (False) the previous build '
                               'directory with identical name or not.'), FILEMANAGEMENT],
    'cleanupoldinstall': [True, ('Boolean to remove (True) or backup (False) the previous install '
                                 'directory with identical name or not.'), FILEMANAGEMENT],
    'dontcreateinstalldir': [False, ('Boolean to create (False) or not create (True) the install directory'),
                             FILEMANAGEMENT],
    'keeppreviousinstall': [False, ('Boolean to keep the previous installation with identical '
                                    'name. Experts only!'), FILEMANAGEMENT],
    'keepsymlinks': [False, ('Boolean to determine whether symlinks are to be kept during copying '
                             'or if the content of the files pointed to should be copied'),
                     FILEMANAGEMENT],
    'start_dir': [None, ('Path to start the make in. If the path is absolute, use that path. '
                         'If not, this is added to the guessed path.'), FILEMANAGEMENT],

    # DEPENDENCIES easyconfig parameters
    'allow_system_deps': [[], "Allow listed system dependencies (format: (<name>, <version>))", DEPENDENCIES],
    'builddependencies': [[], "List of build dependencies", DEPENDENCIES],
    'dependencies': [[], "List of dependencies", DEPENDENCIES],
    'hiddendependencies': [[], "List of dependencies available as hidden modules", DEPENDENCIES],
    'osdependencies': [[], "OS dependencies that should be present on the system", DEPENDENCIES],

    # LICENSE easyconfig parameters
    'group': [None, "Name of the user group for which the software should be available; "
                    "format: string or 2-tuple with group name + custom error for users outside group", LICENSE],
    'key': [None, 'Key for installing software', LICENSE],
    'license_file': [None, 'License file for software', LICENSE],
    'license_server': [None, 'License server for software', LICENSE],
    'license_server_port': [None, 'Port for license server', LICENSE],

    # EXTENSIONS easyconfig parameters
    'exts_download_dep_fail': [False, "Fail if downloaded dependencies are detected for extensions", EXTENSIONS],
    'exts_classmap': [{}, "Map of extension name to class for handling build and installation.", EXTENSIONS],
    'exts_defaultclass': [None, "List of module for and name of the default extension class", EXTENSIONS],
    'exts_default_options': [{}, "List of default options for extensions", EXTENSIONS],
    'exts_filter': [None, ("Extension filter details: template for cmd and input to cmd "
                           "(templates for name, version and src)."), EXTENSIONS],
    'exts_list': [[], 'List with extensions added to the base installation', EXTENSIONS],

    # MODULES easyconfig parameters
    'allow_prepend_abs_path': [False, "Allow specifying absolute paths to prepend in modextrapaths", MODULES],
    'include_modpath_extensions': [True, "Include $MODULEPATH extensions specified by module naming scheme.", MODULES],
    'modaliases': [{}, "Aliases to be defined in module file", MODULES],
    'modextrapaths': [{}, "Extra paths to be prepended in module file", MODULES],
    'modextravars': [{}, "Extra environment variables to be added to module file", MODULES],
    'modloadmsg': [{}, "Message that should be printed when generated module is loaded", MODULES],
    'modluafooter': ["", "Footer to include in generated module file (Lua syntax)", MODULES],
    'modaltsoftname': [None, "Module name to use (rather than using software name", MODULES],
    'modtclfooter': ["", "Footer to include in generated module file (Tcl syntax)", MODULES],
    'moduleclass': ['base', 'Module class to be used for this software', MODULES],
    'moduleforceunload': [False, 'Force unload of all modules when loading the extension', MODULES],
    'moduleloadnoconflict': [False, "Don't check for conflicts, unload other versions instead ", MODULES],
    'module_depends_on': [False, 'Use depends_on (Lmod 7.6.1+) for dependencies in generated module '
                          '(implies recursive unloading of modules).', MODULES],
    'recursive_module_unload': [False, 'Recursive unload of all dependencies when unloading module', MODULES],

    # MODULES documentation easyconfig parameters
    #    (docurls is part of MANDATORY)
    'docpaths': [None, "List of paths for documentation relative to installation directory", MODULES],
    'examples': [None, "Free-form text with examples on using the software", MODULES],
    'site_contacts': [None, "String/list of strings with site contacts for the software", MODULES],
    'upstream_contacts': [None, "String/list of strings with upstream contact addresses "
                          "(e.g., support e-mail, mailing list, bugtracker)", MODULES],
    'usage': [None, "Usage instructions for the software", MODULES],
    'whatis': [None, "List of brief (one line) description entries for the software", MODULES],

    # OTHER easyconfig parameters
    'buildstats': [None, "A list of dicts with build statistics", OTHER],
}


def sorted_categories():
    """
    returns the categories in the correct order
    """
    categories = ALL_CATEGORIES.values()
    categories.sort(key=lambda c: c[0])
    return categories


def get_easyconfig_parameter_default(param):
    """Get default value for given easyconfig parameter."""
    if param not in DEFAULT_CONFIG:
        raise EasyBuildError("Unkown easyconfig parameter: %s (known: %s)", param, sorted(DEFAULT_CONFIG.keys()))
    else:
        _log.debug("Returning default value for easyconfig parameter %s: %s" % (param, DEFAULT_CONFIG[param][0]))
        return DEFAULT_CONFIG[param][0]
