# #
# Copyright 2009-2022 Ghent University
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
Generating module files.

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Fotis Georgatos (Uni.Lu, NTUA)
:author: Damian Alvarez (Forschungszentrum Juelich GmbH)
"""
import copy
import os
import re
import tempfile
from contextlib import contextmanager
from distutils.version import LooseVersion
from textwrap import wrap

from easybuild.base import fancylogger
from easybuild.tools.build_log import EasyBuildError, print_warning
from easybuild.tools.config import build_option, get_module_syntax, install_path
from easybuild.tools.filetools import convert_name, mkdir, read_file, remove_file, resolve_path, symlink, write_file
from easybuild.tools.modules import ROOT_ENV_VAR_NAME_PREFIX, EnvironmentModulesC, Lmod, modules_tool
from easybuild.tools.py2vs3 import string_type
from easybuild.tools.utilities import get_subclasses, quote_str


_log = fancylogger.getLogger('module_generator', fname=False)


def avail_module_generators():
    """
    Return all known module syntaxes.
    """
    return dict([(k.SYNTAX, k) for k in get_subclasses(ModuleGenerator)])


def module_generator(app, fake=False):
    """
    Return ModuleGenerator instance that matches the selected module file syntax to be used
    """
    module_syntax = get_module_syntax()
    available_mod_gens = avail_module_generators()

    if module_syntax not in available_mod_gens:
        raise EasyBuildError("No module generator available for specified syntax '%s' (available: %s)",
                             module_syntax, available_mod_gens)

    module_generator_class = available_mod_gens[module_syntax]
    return module_generator_class(app, fake=fake)


def module_load_regex(modfilepath):
    """
    Return the correct (compiled) regex to extract dependencies, depending on the module file type (Lua vs Tcl)
    """
    if modfilepath.endswith(ModuleGeneratorLua.MODULE_FILE_EXTENSION):
        regex = ModuleGeneratorLua.LOAD_REGEX
    else:
        regex = ModuleGeneratorTcl.LOAD_REGEX
    return re.compile(regex, re.M)


def dependencies_for(mod_name, modtool, depth=None):
    """
    Obtain a list of dependencies for the given module, determined recursively, up to a specified depth (optionally)
    :param depth: recursion depth (default is None, which corresponds to infinite recursion depth)
    """
    mod_filepath = modtool.modulefile_path(mod_name)
    modtxt = read_file(mod_filepath)
    loadregex = module_load_regex(mod_filepath)
    mods = loadregex.findall(modtxt)

    if depth is None or depth > 0:
        if depth and depth > 0:
            depth = depth - 1
        # recursively determine dependencies for these dependency modules, until depth is non-positive
        moddeps = [dependencies_for(mod, modtool, depth=depth) for mod in mods]
    else:
        # ignore any deeper dependencies
        moddeps = []

    # add dependencies of dependency modules only if they're not there yet
    for moddepdeps in moddeps:
        for dep in moddepdeps:
            if dep not in mods:
                mods.append(dep)

    return mods


class ModuleGenerator(object):
    """
    Class for generating module files.
    """
    SYNTAX = None

    # chars we want to escape in the generated modulefiles
    CHARS_TO_ESCAPE = None

    MODULE_FILE_EXTENSION = None
    MODULE_SHEBANG = None
    DOT_MODULERC = '.modulerc'

    # a single level of indentation
    INDENTATION = ' ' * 4

    def __init__(self, application, fake=False):
        """ModuleGenerator constructor."""
        self.app = application
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.fake_mod_path = tempfile.mkdtemp()

        self.modules_tool = modules_tool()
        self.added_paths_per_key = None

    @contextmanager
    def start_module_creation(self):
        """
        Prepares creating a module and returns the file header (shebang) if any including the newline

        Meant to be used in a with statement:
            with generator.start_module_creation() as txt:
                # Write txt
        """
        if self.added_paths_per_key is not None:
            raise EasyBuildError('Module creation already in process. '
                                 'You cannot create multiple modules at the same time!')
        # Mapping of keys/env vars to paths already added
        self.added_paths_per_key = dict()
        txt = self.MODULE_SHEBANG
        if txt:
            txt += '\n'
        try:
            yield txt
        finally:
            self.added_paths_per_key = None

    def create_symlinks(self, mod_symlink_paths, fake=False):
        """Create moduleclass symlink(s) to actual module file."""
        mod_filepath = self.get_module_filepath(fake=fake)
        class_mod_files = [self.get_module_filepath(fake=fake, mod_path_suffix=p) for p in mod_symlink_paths]
        try:
            for class_mod_file in class_mod_files:
                # remove symlink if its there (even if it's broken)
                if os.path.lexists(class_mod_file):
                    self.log.debug("Removing existing symlink %s", class_mod_file)
                    os.remove(class_mod_file)

                mkdir(os.path.dirname(class_mod_file), parents=True)
                os.symlink(mod_filepath, class_mod_file)

        except OSError as err:
            raise EasyBuildError("Failed to create symlinks from %s to %s: %s", class_mod_files, mod_filepath, err)

    def define_env_var(self, env_var):
        """
        Determine whether environment variable with specified name should be defined or not.

        :param env_var: name of environment variable to check
        """
        return env_var not in (build_option('filter_env_vars') or [])

    def get_module_filepath(self, fake=False, mod_path_suffix=None):
        """Return path to module file."""
        mod_path = self.get_modules_path(fake=fake, mod_path_suffix=mod_path_suffix)
        full_mod_name = self.app.full_mod_name + self.MODULE_FILE_EXTENSION
        return os.path.join(mod_path, full_mod_name)

    def get_modules_path(self, fake=False, mod_path_suffix=None):
        """Return path to directory where module files should be generated in."""
        mod_path = install_path('mod')
        if fake:
            self.log.debug("Fake mode: using %s (instead of %s)" % (self.fake_mod_path, mod_path))
            mod_path = self.fake_mod_path

        if mod_path_suffix is None:
            mod_path_suffix = build_option('suffix_modules_path')

        return os.path.join(mod_path, mod_path_suffix)

    def _filter_paths(self, key, paths):
        """Filter out paths already added to key and return the remaining ones"""
        if self.added_paths_per_key is None:
            # For compatibility this is only a warning for now and we don't filter any paths
            print_warning('Module creation has not been started. Call start_module_creation first!')
            return paths

        added_paths = self.added_paths_per_key.setdefault(key, set())
        # paths can be a string
        if isinstance(paths, string_type):
            if paths in added_paths:
                filtered_paths = None
            else:
                added_paths.add(paths)
                filtered_paths = paths
        else:
            # Coerce any iterable/generator into a list
            if not isinstance(paths, list):
                paths = list(paths)
            filtered_paths = [x for x in paths if x not in added_paths and not added_paths.add(x)]
        if filtered_paths != paths:
            removed_paths = paths if filtered_paths is None else [x for x in paths if x not in filtered_paths]
            print_warning("Suppressed adding the following path(s) to $%s of the module as they were already added: %s",
                          key, removed_paths,
                          log=self.log)
            if not filtered_paths:
                filtered_paths = None
        return filtered_paths

    def append_paths(self, key, paths, allow_abs=False, expand_relpaths=True):
        """
        Generate append-path statements for the given list of paths.

        :param key: environment variable to append paths to
        :param paths: list of paths to append
        :param allow_abs: allow providing of absolute paths
        :param expand_relpaths: expand relative paths into absolute paths (by prefixing install dir)
        """
        paths = self._filter_paths(key, paths)
        if paths is None:
            return ''
        return self.update_paths(key, paths, prepend=False, allow_abs=allow_abs, expand_relpaths=expand_relpaths)

    def prepend_paths(self, key, paths, allow_abs=False, expand_relpaths=True):
        """
        Generate prepend-path statements for the given list of paths.

        :param key: environment variable to append paths to
        :param paths: list of paths to append
        :param allow_abs: allow providing of absolute paths
        :param expand_relpaths: expand relative paths into absolute paths (by prefixing install dir)
        """
        paths = self._filter_paths(key, paths)
        if paths is None:
            return ''
        return self.update_paths(key, paths, prepend=True, allow_abs=allow_abs, expand_relpaths=expand_relpaths)

    def _modulerc_check_module_version(self, module_version):
        """
        Check value type & contents of specified module-version spec.

        :param module_version: specs for module-version statement (dict with 'modname', 'sym_version' & 'version' keys)
        :return: True if spec is OK
        """
        res = False
        if module_version:
            if isinstance(module_version, dict):
                expected_keys = ['modname', 'sym_version', 'version']
                if sorted(module_version.keys()) == expected_keys:
                    res = True
                else:
                    raise EasyBuildError("Incorrect module_version spec, expected keys: %s", expected_keys)
            else:
                raise EasyBuildError("Incorrect module_version value type: %s", type(module_version))

        return res

    def _write_modulerc_file(self, modulerc_path, modulerc_txt, wrapped_mod_name=None):
        """
        Write modulerc file with specified contents.

        :param modulerc_path: location of .modulerc file to write
        :param modulerc_txt: contents of .modulerc file
        :param wrapped_mod_name: name of module file for which a wrapper is defined in the .modulerc file (if any)
        """
        # Lmod 6.x requires that module being wrapped is in same location as .modulerc file...
        if wrapped_mod_name is not None:
            if isinstance(self.modules_tool, Lmod) and LooseVersion(self.modules_tool.version) < LooseVersion('7.0'):
                mod_dir = os.path.dirname(modulerc_path)

                # need to consider existing module file in both Tcl (no extension) & Lua (.lua extension) syntax...
                wrapped_mod_fp = os.path.join(mod_dir, os.path.basename(wrapped_mod_name))
                wrapped_mod_exists = os.path.exists(wrapped_mod_fp)
                if not wrapped_mod_exists and self.MODULE_FILE_EXTENSION:
                    wrapped_mod_exists = os.path.exists(wrapped_mod_fp + self.MODULE_FILE_EXTENSION)

                if not wrapped_mod_exists:
                    error_msg = "Expected module file %s not found; " % wrapped_mod_fp
                    error_msg += "Lmod 6.x requires that .modulerc and wrapped module file are in same directory!"
                    raise EasyBuildError(error_msg)

        if os.path.exists(modulerc_path):
            curr_modulerc = read_file(modulerc_path)

            # get rid of Tcl shebang line if modulerc file already exists and already contains Tcl shebang line
            tcl_shebang = ModuleGeneratorTcl.MODULE_SHEBANG
            if modulerc_txt.startswith(tcl_shebang) and curr_modulerc.startswith(tcl_shebang):
                modulerc_txt = '\n'.join(modulerc_txt.split('\n')[1:])

            # check whether specified contents is already contained in current modulerc file;
            # if so, we don't need to update the existing modulerc at all...
            # if it's not, we need to append to existing modulerc file
            if modulerc_txt.strip() not in curr_modulerc:

                # if current contents doesn't end with a newline, prefix text being appended with a newline
                if not curr_modulerc.endswith('\n'):
                    modulerc_txt = '\n' + modulerc_txt

                write_file(modulerc_path, modulerc_txt, append=True, backup=True)
        else:
            write_file(modulerc_path, modulerc_txt)

    def modulerc(self, module_version=None, filepath=None, modulerc_txt=None):
        """
        Generate contents of .modulerc file, in Tcl syntax (compatible with all module tools, incl. Lmod).
        If 'filepath' is specified, the .modulerc file will be written as well.

        :param module_version: specs for module-version statement (dict with 'modname', 'sym_version' & 'version' keys)
        :param filepath: location where .modulerc file should be written to
        :param modulerc_txt: contents of .modulerc to use
        :return: contents of .modulerc file
        """
        if modulerc_txt is None:

            self.log.info("Generating .modulerc contents in Tcl syntax (args: module_version: %s", module_version)
            modulerc = [ModuleGeneratorTcl.MODULE_SHEBANG]

            if self._modulerc_check_module_version(module_version):

                module_version_statement = "module-version %(modname)s %(sym_version)s"

                # for Environment Modules we need to guard the module-version statement,
                # to avoid "Duplicate version symbol" warning messages where EasyBuild trips over,
                # which occur because the .modulerc is parsed twice
                # "module-info version <arg>" returns its argument if that argument is not a symbolic version (yet),
                # and returns the corresponding real version in case the argument is an existing symbolic version
                # cfr. https://sourceforge.net/p/modules/mailman/message/33399425/
                if self.modules_tool.__class__ == EnvironmentModulesC:

                    keys = ['modname', 'sym_version', 'version']
                    modname, sym_version, version = [module_version[key] for key in keys]

                    # determine module name with symbolic version
                    if version in modname:
                        # take a copy so we don't modify original value
                        module_version = copy.copy(module_version)
                        module_version['sym_modname'] = modname.replace(version, sym_version)
                    else:
                        raise EasyBuildError("Version '%s' does not appear in module name '%s'", version, modname)

                    module_version_statement = '\n'.join([
                        'if {"%(sym_modname)s" eq [module-info version %(sym_modname)s]} {',
                        ' ' * 4 + module_version_statement,
                        "}",
                    ])

                modulerc.append(module_version_statement % module_version)

            modulerc_txt = '\n'.join(modulerc)

        if filepath:
            self.log.info("Writing %s with contents:\n%s", filepath, modulerc_txt)
            self._write_modulerc_file(filepath, modulerc_txt, wrapped_mod_name=module_version['modname'])

        return modulerc_txt

    def is_loaded(self, mod_names):
        """
        Generate (list of) expression(s) to check whether specified module(s) is (are) loaded.

        :param mod_names: (list of) module name(s) to check load status for
        """
        if isinstance(mod_names, string_type):
            res = self.IS_LOADED_TEMPLATE % mod_names
        else:
            res = [self.IS_LOADED_TEMPLATE % m for m in mod_names]

        return res

    def det_installdir(self, modfile):
        """
        Determine installation directory used by given module file
        """
        res = None

        modtxt = read_file(modfile)
        root_regex = re.compile(self.INSTALLDIR_REGEX, re.M)
        match = root_regex.search(modtxt)
        if match:
            res = match.group('installdir')

        return res

    # From this point on just not implemented methods

    def check_group(self, group, error_msg=None):
        """
        Generate a check of the software group and the current user, and refuse to load the module if the user don't
        belong to the group

        :param group: string with the group name
        :param error_msg: error message to print for users outside that group
        """
        raise NotImplementedError

    def comment(self, msg):
        """Return given string formatted as a comment."""
        raise NotImplementedError

    def check_version(self, minimal_version_maj, minimal_version_min, minimal_version_patch='0'):
        """
        Check the minimal version of the modules tool in the module file
        :param minimal_version_maj: the major version to check
        :param minimal_version_min: the minor version to check
        :param minimal_version_patch: the patch version to check
        """
        raise NotImplementedError

    def conditional_statement(self, conditions, body, negative=False, else_body=None, indent=True,
                              cond_or=False, cond_tmpl=None):
        """
        Return formatted conditional statement, with given condition and body.

        :param conditions: (list of) string(s) containing the statement(s) for the if condition (in correct syntax)
        :param body: (multiline) string with if body (in correct syntax, without indentation)
        :param negative: boolean indicating whether the (individual) condition(s) should be negated
        :param else_body: optional body for 'else' part
        :param indent: indent if/else body
        :param cond_or: combine multiple conditions using 'or' (default is to combine with 'and')
        :param cond_tmpl: template for condition expression (default: '%s')
        """
        raise NotImplementedError

    def get_description(self, conflict=True):
        """
        Generate a description.
        """
        raise NotImplementedError

    def getenv_cmd(self, envvar, default=None):
        """
        Return module-syntax specific code to get value of specific environment variable.
        """
        raise NotImplementedError

    def load_module(self, mod_name, recursive_unload=False, depends_on=False, unload_modules=None, multi_dep_mods=None):
        """
        Generate load statement for specified module.

        :param mod_name: name of module to generate load statement for
        :param recursive_unload: boolean indicating whether the 'load' statement should be reverted on unload
        :param depends_on: use depends_on statements rather than (guarded) load statements
        :param unload_modules: name(s) of module to unload first
        :param multi_dep_mods: list of module names in multi_deps context, to use for guarding load statement
        """
        raise NotImplementedError

    def msg_on_load(self, msg):
        """
        Add a message that should be printed when loading the module.
        """
        raise NotImplementedError

    def set_alias(self, key, value):
        """
        Generate set-alias statement in modulefile for the given key/value pair.
        """
        raise NotImplementedError

    def set_as_default(self, module_dir_path, module_version, mod_symlink_paths=None):
        """
        Set generated module as default module

        :param module_dir_path: module directory path, e.g. $HOME/easybuild/modules/all/Bison
        :param module_version: module version, e.g. 3.0.4
        :param mod_symlink_paths: list of paths in which symlinks to module files must be created
        """
        raise NotImplementedError

    def set_environment(self, key, value, relpath=False):
        """
        Generate a quoted setenv statement for the given key/value pair.

        :param key: name of environment variable to define
        :param value: value to define environment variable with
        :param relpath: value is path relative to installation prefix
        """
        raise NotImplementedError

    def swap_module(self, mod_name_out, mod_name_in, guarded=True):
        """
        Generate swap statement for specified module names.

        :param mod_name_out: name of module to unload (swap out)
        :param mod_name_in: name of module to load (swap in)
        :param guarded: guard 'swap' statement, fall back to 'load' if module being swapped out is not loaded
        """
        raise NotImplementedError

    def unload_module(self, mod_name):
        """
        Generate unload statement for specified module.

        :param mod_name: name of module to generate unload statement for
        """
        raise NotImplementedError

    def update_paths(self, key, paths, prepend=True, allow_abs=False, expand_relpaths=True):
        """
        Generate prepend-path or append-path statements for the given list of paths.

        :param key: environment variable to prepend/append paths to
        :param paths: list of paths to prepend
        :param prepend: whether to prepend (True) or append (False) paths
        :param allow_abs: allow providing of absolute paths
        :param expand_relpaths: expand relative paths into absolute paths (by prefixing install dir)
        """
        raise NotImplementedError

    def _det_user_modpath_common(self, user_modpath):
        """
        Helper function for det_user_modpath.
        """
        # Check for occurences of {RUNTIME_ENV::SOME_ENV_VAR}
        # SOME_ENV_VAR will be expanded at module load time.
        runtime_env_re = re.compile(r'{RUNTIME_ENV::(\w+)}')
        sub_paths = []
        expanded_user_modpath = []
        for sub_path in re.split(os.path.sep, user_modpath):
            matched_re = runtime_env_re.match(sub_path)
            if matched_re:
                if sub_paths:
                    path = quote_str(os.path.join(*sub_paths))
                    expanded_user_modpath.extend([path])
                    sub_paths = []
                expanded_user_modpath.extend([self.getenv_cmd(matched_re.group(1))])
            else:
                sub_paths.append(sub_path)
        if sub_paths:
            expanded_user_modpath.extend([quote_str(os.path.join(*sub_paths))])

        # if a mod_path_suffix is being used, we should respect it
        mod_path_suffix = build_option('suffix_modules_path')
        if mod_path_suffix:
            expanded_user_modpath.extend([quote_str(mod_path_suffix)])

        return expanded_user_modpath

    def det_user_modpath(self, user_modpath):
        """
        Determine user-specific modules subdirectory, to be used in 'use' statements
        (cfr. implementation of use() method).
        """
        raise NotImplementedError

    def use(self, paths, prefix=None, guarded=False, user_modpath=None):
        """
        Generate module use statements for given list of module paths.
        :param paths: list of module path extensions to generate use statements for; paths will be quoted
        :param prefix: optional path prefix; not quoted, i.e., can be a statement
        :param guarded: use statements will be guarded to only apply if path exists
        :param user_modpath: user-specific modules subdirectory to include in use statements
        """
        raise NotImplementedError

    def _generate_extension_list(self):
        """
        Generate a string with a comma-separated list of extensions.
        """
        # We need only name and version, so don't resolve templates
        exts_list = self.app.cfg.get_ref('exts_list')
        extensions = ', '.join(sorted(['-'.join(ext[:2]) for ext in exts_list], key=str.lower))

        return extensions

    def _generate_extensions_list(self):
        """
        Generate a list of all extensions in name/version format
        """
        exts_list = self.app.cfg['exts_list']
        # the format is extension_name/extension_version
        exts_ver_list = []
        for ext in exts_list:
            if isinstance(ext, tuple):
                exts_ver_list.append('%s/%s' % (ext[0], ext[1]))
            elif isinstance(ext, string_type):
                exts_ver_list.append(ext)

        return sorted(exts_ver_list, key=str.lower)

    def _generate_help_text(self):
        """
        Generate syntax-independent help text used for `module help`.
        """

        # General package description (mandatory)
        lines = self._generate_section('Description', self.app.cfg['description'], strip=True)

        # Package usage instructions (optional)
        lines.extend(self._generate_section('Usage', self.app.cfg['usage'], strip=True))

        # Examples (optional)
        lines.extend(self._generate_section('Examples', self.app.cfg['examples'], strip=True))

        # Citing (optional)
        lines.extend(self._generate_section('Citing', self.app.cfg['citing'], strip=True))

        # Additional information: homepage + (if available) doc paths/urls, upstream/site contact
        lines.extend(self._generate_section("More information", " - Homepage: %s" % self.app.cfg['homepage']))

        docpaths = self.app.cfg['docpaths'] or []
        docurls = self.app.cfg['docurls'] or []
        if docpaths or docurls:
            root_envvar = ROOT_ENV_VAR_NAME_PREFIX + convert_name(self.app.name, upper=True)
            lines.extend([" - Documentation:"])
            lines.extend(["    - $%s/%s" % (root_envvar, path) for path in docpaths])
            lines.extend(["    - %s" % url for url in docurls])

        for contacts_type in ['upstream', 'site']:
            contacts = self.app.cfg['%s_contacts' % contacts_type]
            if contacts:
                if isinstance(contacts, list):
                    lines.append(" - %s contacts:" % contacts_type.capitalize())
                    lines.extend(["    - %s" % contact for contact in contacts])
                else:
                    lines.append(" - %s contact: %s" % (contacts_type.capitalize(), contacts))

        # Multi deps (if any)
        multi_deps = self._generate_multi_deps_list()
        if multi_deps:
            compatible_modules_txt = '\n'.join([
                "This module is compatible with the following modules, one of each line is required:",
            ] + ['* %s' % d for d in multi_deps])
            lines.extend(self._generate_section("Compatible modules", compatible_modules_txt))

        # Extensions (if any)
        extensions = self._generate_extension_list()
        lines.extend(self._generate_section("Included extensions", '\n'.join(wrap(extensions, 78))))

        return '\n'.join(lines)

    def _generate_multi_deps_list(self):
        """
        Generate a string with a comma-separated list of multi_deps.
        """
        multi_deps = []
        if self.app.cfg['multi_deps']:
            for key in sorted(self.app.cfg['multi_deps'].keys()):
                mod_list = []
                txt = ''
                vlist = self.app.cfg['multi_deps'].get(key)
                for idx in range(len(vlist)):
                    for deplist in self.app.cfg.multi_deps:
                        for dep in deplist:
                            if dep['name'] == key and dep['version'] == vlist[idx]:
                                modname = dep['short_mod_name']
                                # indicate which version is loaded by default (unless that's disabled)
                                if idx == 0 and self.app.cfg['multi_deps_load_default']:
                                    modname += ' (default)'
                                mod_list.append(modname)
                txt += ', '.join(mod_list)
                multi_deps.append(txt)

        return multi_deps

    def _generate_section(self, sec_name, sec_txt, strip=False):
        """
        Generate section with given name and contents.
        """
        res = []
        if sec_txt:
            if strip:
                sec_txt = sec_txt.strip()
            res = ['', '', sec_name, '=' * len(sec_name), sec_txt]
        return res

    def _generate_whatis_lines(self):
        """
        Generate a list of entries used for `module whatis`.
        """
        whatis = self.app.cfg['whatis']
        if whatis is None:
            # default: include 'whatis' statements with description, homepage, and extensions (if any)
            whatis = [
                "Description: %s" % self.app.cfg['description'],
                "Homepage: %s" % self.app.cfg['homepage'],
                "URL: %s" % self.app.cfg['homepage'],
            ]

            multi_deps = self._generate_multi_deps_list()
            if multi_deps:
                whatis.append("Compatible modules: %s" % ', '.join(multi_deps))

            extensions = self._generate_extension_list()
            if extensions:
                whatis.append("Extensions: %s" % extensions)

        return whatis


class ModuleGeneratorTcl(ModuleGenerator):
    """
    Class for generating Tcl module files.
    """
    SYNTAX = 'Tcl'
    MODULE_FILE_EXTENSION = ''  # no suffix for Tcl module files
    MODULE_SHEBANG = '#%Module'
    CHARS_TO_ESCAPE = ['$']

    INSTALLDIR_REGEX = r"^set root\s+(?P<installdir>.*)"
    LOAD_REGEX = r"^\s*(?:module\s+load|depends-on)\s+(\S+)"
    LOAD_TEMPLATE = "module load %(mod_name)s"
    LOAD_TEMPLATE_DEPENDS_ON = "depends-on %(mod_name)s"
    IS_LOADED_TEMPLATE = 'is-loaded %s'

    def check_group(self, group, error_msg=None):
        """
        Generate a check of the software group and the current user, and refuse to load the module if the user don't
        belong to the group

        :param group: string with the group name
        :param error_msg: error message to print for users outside that group
        """
        self.log.warning("Can't generate robust check in TCL modules for users belonging to group %s.", group)
        return ''

    def comment(self, msg):
        """Return string containing given message as a comment."""
        return "# %s\n" % msg

    def conditional_statement(self, conditions, body, negative=False, else_body=None, indent=True,
                              cond_or=False, cond_tmpl=None):
        """
        Return formatted conditional statement, with given condition and body.

        :param conditions: (list of) string(s) containing the statement(s) for the if condition (in correct syntax)
        :param body: (multiline) string with if body (in correct syntax, without indentation)
        :param negative: boolean indicating whether the (individual) condition(s) should be negated
        :param else_body: optional body for 'else' part
        :param indent: indent if/else body
        :param cond_or: combine multiple conditions using 'or' (default is to combine with 'and')
        :param cond_tmpl: template for condition expression (default: '%s')
        """
        if isinstance(conditions, string_type):
            conditions = [conditions]

        if cond_or:
            join_op = ' || '
        else:
            join_op = ' && '

        if negative:
            condition = join_op.join('![ %s ]' % c for c in conditions)
        else:
            condition = join_op.join('[ %s ]' % c for c in conditions)

        if cond_tmpl:
            condition = cond_tmpl % condition

        lines = ["if { %s } {" % condition]

        for line in body.split('\n'):
            if indent:
                line = self.INDENTATION + line
            lines.append(line)

        if else_body is None:
            lines.extend(['}', ''])
        else:
            lines.append('} else {')
            for line in else_body.split('\n'):
                if indent:
                    line = self.INDENTATION + line
                lines.append(line)
            lines.extend(['}', ''])

        return '\n'.join(lines)

    def get_description(self, conflict=True):
        """
        Generate a description.
        """
        txt = '\n'.join([
            "proc ModulesHelp { } {",
            "    puts stderr {%s" % re.sub(r'([{}\[\]])', r'\\\1', self._generate_help_text()),
            "    }",
            '}',
            '',
        ])

        lines = [
            '%(whatis_lines)s',
            '',
            "set root %(installdir)s",
        ]

        if self.app.cfg['moduleloadnoconflict']:
            cond_unload = self.conditional_statement(self.is_loaded('%(name)s'), "module unload %(name)s")
            lines.extend([
                '',
                self.conditional_statement(self.is_loaded('%(name)s/%(version)s'), cond_unload, negative=True),
            ])

        elif conflict:
            # conflict on 'name' part of module name (excluding version part at the end)
            # examples:
            # - 'conflict GCC' for 'GCC/4.8.3'
            # - 'conflict Core/GCC' for 'Core/GCC/4.8.2'
            # - 'conflict Compiler/GCC/4.8.2/OpenMPI' for 'Compiler/GCC/4.8.2/OpenMPI/1.6.4'
            lines.extend(['', "conflict %s" % os.path.dirname(self.app.short_mod_name)])

        whatis_lines = [
            "module-whatis {%s}" % re.sub(r'([{}\[\]])', r'\\\1', line)
            for line in self._generate_whatis_lines()
        ]
        txt += '\n'.join([''] + lines + ['']) % {
            'name': self.app.name,
            'version': self.app.version,
            'whatis_lines': '\n'.join(whatis_lines),
            'installdir': self.app.installdir,
        }

        return txt

    def getenv_cmd(self, envvar, default=None):
        """
        Return module-syntax specific code to get value of specific environment variable.
        """
        if default is None:
            cmd = '$::env(%s)' % envvar
        else:
            values = {
                'default': default,
                'envvar': '::env(%s)' % envvar,
            }
            cmd = '[if { [info exists %(envvar)s] } { concat $%(envvar)s } else { concat "%(default)s" } ]' % values
        return cmd

    def load_module(self, mod_name, recursive_unload=None, depends_on=False, unload_modules=None, multi_dep_mods=None):
        """
        Generate load statement for specified module.

        :param mod_name: name of module to generate load statement for
        :param recursive_unload: boolean indicating whether the 'load' statement should be reverted on unload
                                 (if None: enable if recursive_mod_unload build option or depends_on is True)
        :param depends_on: use depends_on statements rather than (guarded) load statements
        :param unload_modules: name(s) of module to unload first
        :param multi_dep_mods: list of module names in multi_deps context, to use for guarding load statement
        """
        body = []
        if unload_modules:
            body.extend([self.unload_module(m).strip() for m in unload_modules])
        load_template = self.LOAD_TEMPLATE
        # Lmod 7.6.1+ supports depends-on which does this most nicely:
        if build_option('mod_depends_on') or depends_on:
            if not self.modules_tool.supports_depends_on:
                raise EasyBuildError("depends-on statements in generated module are not supported by modules tool")
            load_template = self.LOAD_TEMPLATE_DEPENDS_ON

        body.append(load_template)

        depends_on = load_template == self.LOAD_TEMPLATE_DEPENDS_ON

        cond_tmpl = None

        if recursive_unload is None:
            recursive_unload = build_option('recursive_mod_unload') or depends_on

        if recursive_unload:
            # wrapping the 'module load' statement with an 'is-loaded or mode == unload'
            # guard ensures recursive unloading while avoiding load storms;
            # when "module unload" is called on the module in which the
            # dependency "module load" is present, it will get translated
            # to "module unload" (while the condition is left untouched)
            # see also http://lmod.readthedocs.io/en/latest/210_load_storms.html
            cond_tmpl = "[ module-info mode remove ] || %s"

        if depends_on:
            if multi_dep_mods and len(multi_dep_mods) > 1:
                parent_mod_name = os.path.dirname(mod_name)
                guard = self.is_loaded(multi_dep_mods[1:])
                if_body = load_template % {'mod_name': parent_mod_name}
                else_body = '\n'.join(body)
                load_statement = [
                    self.conditional_statement(guard, if_body, else_body=else_body, cond_tmpl=cond_tmpl, cond_or=True),
                ]
            else:
                load_statement = body + ['']
        else:
            if multi_dep_mods is None:
                # guard load statement with check to see whether module being loaded is already loaded
                # (this avoids load storms)
                cond_mod_names = '%(mod_name)s'
            else:
                cond_mod_names = multi_dep_mods

            # conditional load if one or more conditions are specified
            load_guards = self.is_loaded(cond_mod_names)
            body = '\n'.join(body)
            load_statement = [self.conditional_statement(load_guards, body, negative=True, cond_tmpl=cond_tmpl)]

        return '\n'.join([''] + load_statement) % {'mod_name': mod_name}

    def msg_on_load(self, msg):
        """
        Add a message that should be printed when loading the module.
        """
        # escape any (non-escaped) characters with special meaning by prefixing them with a backslash
        msg = re.sub(r'((?<!\\)[%s])' % ''.join(self.CHARS_TO_ESCAPE), r'\\\1', msg)
        print_cmd = "puts stderr %s" % quote_str(msg, tcl=True)
        return '\n'.join(['', self.conditional_statement("module-info mode load", print_cmd, indent=False)])

    def update_paths(self, key, paths, prepend=True, allow_abs=False, expand_relpaths=True):
        """
        Generate prepend-path or append-path statements for the given list of paths.

        :param key: environment variable to prepend/append paths to
        :param paths: list of paths to prepend
        :param prepend: whether to prepend (True) or append (False) paths
        :param allow_abs: allow providing of absolute paths
        :param expand_relpaths: expand relative paths into absolute paths (by prefixing install dir)
        """
        if prepend:
            update_type = 'prepend'
        else:
            update_type = 'append'

        if not self.define_env_var(key):
            self.log.info("Not including statement to %s environment variable $%s, as specified", update_type, key)
            return ''

        if isinstance(paths, string_type):
            self.log.debug("Wrapping %s into a list before using it to %s path %s", paths, update_type, key)
            paths = [paths]

        abspaths = []
        for path in paths:
            if os.path.isabs(path) and not allow_abs:
                raise EasyBuildError("Absolute path %s passed to update_paths which only expects relative paths.",
                                     path)
            elif not os.path.isabs(path):
                # prepend/append $root (= installdir) for (non-empty) relative paths
                if path:
                    if expand_relpaths:
                        abspaths.append(os.path.join('$root', path))
                    else:
                        abspaths.append(path)
                else:
                    abspaths.append('$root')
            else:
                abspaths.append(path)

        statements = ['%s-path\t%s\t\t%s\n' % (update_type, key, p) for p in abspaths]
        return ''.join(statements)

    def set_alias(self, key, value):
        """
        Generate set-alias statement in modulefile for the given key/value pair.
        """
        # quotes are needed, to ensure smooth working of EBDEVEL* modulefiles
        return 'set-alias\t%s\t\t%s\n' % (key, quote_str(value, tcl=True))

    def set_as_default(self, module_dir_path, module_version, mod_symlink_paths=None):
        """
        Create a .version file inside the package module folder in order to set the default version for TMod

        :param module_dir_path: module directory path, e.g. $HOME/easybuild/modules/all/Bison
        :param module_version: module version, e.g. 3.0.4
        :param mod_symlink_paths: list of paths in which symlinks to module files must be created
        """
        txt = self.MODULE_SHEBANG + '\n'
        txt += 'set ModulesVersion %s\n' % module_version

        # write the file no matter what
        dot_version_path = os.path.join(module_dir_path, '.version')
        write_file(dot_version_path, txt)

        # create symlink to .version file in class module folders
        if mod_symlink_paths is None:
            mod_symlink_paths = []

        module_dir_name = os.path.basename(module_dir_path)
        for mod_symlink_path in mod_symlink_paths:
            mod_symlink_dir = os.path.join(install_path('mod'), mod_symlink_path, module_dir_name)
            dot_version_link_path = os.path.join(mod_symlink_dir, '.version')
            if os.path.islink(dot_version_link_path):
                link_target = resolve_path(dot_version_link_path)
                remove_file(dot_version_link_path)
                self.log.info("Removed default version marking from %s.", link_target)
            elif os.path.exists(dot_version_link_path):
                raise EasyBuildError('Found an unexpected file named .version in dir %s', mod_symlink_dir)
            symlink(dot_version_path, dot_version_link_path, use_abspath_source=True)

    def set_environment(self, key, value, relpath=False):
        """
        Generate a quoted setenv statement for the given key/value pair.

        :param key: name of environment variable to define
        :param value: value to define environment variable with
        :param relpath: value is path relative to installation prefix
        """
        if not self.define_env_var(key):
            self.log.info("Not including statement to define environment variable $%s, as specified", key)
            return ''

        # quotes are needed, to ensure smooth working of EBDEVEL* modulefiles
        if relpath:
            if value:
                val = quote_str(os.path.join('$root', value), tcl=True)
            else:
                val = '"$root"'
        else:
            val = quote_str(value, tcl=True)
        return 'setenv\t%s\t\t%s\n' % (key, val)

    def swap_module(self, mod_name_out, mod_name_in, guarded=True):
        """
        Generate swap statement for specified module names.

        :param mod_name_out: name of module to unload (swap out)
        :param mod_name_in: name of module to load (swap in)
        :param guarded: guard 'swap' statement, fall back to 'load' if module being swapped out is not loaded
        """
        # In Modules 4.2.3+ a 2-argument swap 'module swap foo foo/X.Y.Z' will fail as the unloaded 'foo'
        # means all 'foo' modules conflict and 'foo/X.Y.Z' will not load.  A 1-argument swap like
        # 'module swap foo/X.Y.Z' will unload any currently loaded 'foo' without it becoming conflicting
        # and successfully load the new module.
        # See: https://modules.readthedocs.io/en/latest/NEWS.html#modules-4-2-3-2019-03-23
        body = "module swap %s" % (mod_name_in)
        if guarded:
            alt_body = self.LOAD_TEMPLATE % {'mod_name': mod_name_in}
            swap_statement = [self.conditional_statement(self.is_loaded(mod_name_out), body, else_body=alt_body)]
        else:
            swap_statement = [body, '']

        return '\n'.join([''] + swap_statement)

    def unload_module(self, mod_name):
        """
        Generate unload statement for specified module.

        :param mod_name: name of module to generate unload statement for
        """
        return '\n'.join(['', "module unload %s" % mod_name])

    def det_user_modpath(self, user_modpath):
        """
        Determine user-specific modules subdirectory, to be used in 'use' statements
        (cfr. implementation of use() method).
        """
        if user_modpath:
            user_modpath = ' '.join(self._det_user_modpath_common(user_modpath))

        return user_modpath

    def use(self, paths, prefix=None, guarded=False, user_modpath=None):
        """
        Generate module use statements for given list of module paths.
        :param paths: list of module path extensions to generate use statements for; paths will be quoted
        :param prefix: optional path prefix; not quoted, i.e., can be a statement
        :param guarded: use statements will be guarded to only apply if path exists
        :param user_modpath: user-specific modules subdirectory to include in use statements
        """
        user_modpath = self.det_user_modpath(user_modpath)
        use_statements = []
        for path in paths:
            quoted_path = quote_str(path, tcl=True)
            if user_modpath:
                quoted_path = '[ file join %s %s ]' % (user_modpath, quoted_path)
            if prefix:
                full_path = '[ file join %s %s ]' % (prefix, quoted_path)
            else:
                full_path = quoted_path
            if guarded:
                cond_statement = self.conditional_statement('file isdirectory %s' % full_path,
                                                            'module use %s' % full_path)
                use_statements.append(cond_statement)
            else:
                use_statements.append("module use %s\n" % full_path)
        return ''.join(use_statements)


class ModuleGeneratorLua(ModuleGenerator):
    """
    Class for generating Lua module files.
    """
    SYNTAX = 'Lua'
    MODULE_FILE_EXTENSION = '.lua'
    MODULE_SHEBANG = ''  # no 'shebang' in Lua module files
    CHARS_TO_ESCAPE = []

    INSTALLDIR_REGEX = r'^local root\s+=\s+"(?P<installdir>.*)"'
    LOAD_REGEX = r'^\s*(?:load|depends_on)\("(\S+)"'
    LOAD_TEMPLATE = 'load("%(mod_name)s")'
    LOAD_TEMPLATE_DEPENDS_ON = 'depends_on("%(mod_name)s")'
    IS_LOADED_TEMPLATE = 'isloaded("%s")'

    PATH_JOIN_TEMPLATE = 'pathJoin(root, "%s")'
    UPDATE_PATH_TEMPLATE = '%s_path("%s", %s)'

    START_STR = '[==['
    END_STR = ']==]'

    def __init__(self, *args, **kwargs):
        """ModuleGeneratorLua constructor."""
        super(ModuleGeneratorLua, self).__init__(*args, **kwargs)

        if self.modules_tool:
            if self.modules_tool.version and LooseVersion(self.modules_tool.version) >= LooseVersion('7.7.38'):
                self.DOT_MODULERC = '.modulerc.lua'

    def check_version(self, minimal_version_maj, minimal_version_min, minimal_version_patch='0'):
        """
        Check the minimal version of the moduletool in the module file
        :param minimal_version_maj: the major version to check
        :param minimal_version_min: the minor version to check
        :param minimal_version_patch: the patch version to check
        """
        lmod_version_check_expr = 'convertToCanonical(LmodVersion()) >= convertToCanonical("%(maj)s.%(min)s.%(patch)s")'
        return lmod_version_check_expr % {
            'maj': minimal_version_maj,
            'min': minimal_version_min,
            'patch': minimal_version_patch,
        }

    def check_group(self, group, error_msg=None):
        """
        Generate a check of the software group and the current user, and refuse to load the module if the user don't
        belong to the group

        :param group: string with the group name
        :param error_msg: error message to print for users outside that group
        """
        lmod_version = self.modules_tool.version
        min_lmod_version = '6.0.8'

        if LooseVersion(lmod_version) >= LooseVersion(min_lmod_version):
            if error_msg is None:
                error_msg = "You are not part of '%s' group of users that have access to this software; " % group
                error_msg += "Please consult with user support how to become a member of this group"

            error_msg = 'LmodError("' + error_msg + '")'
            res = self.conditional_statement('userInGroup("%s")' % group, error_msg, negative=True)
        else:
            warn_msg = "Can't generate robust check in Lua modules for users belonging to group %s. "
            warn_msg += "Lmod version not recent enough (%s), should be >= %s"
            self.log.warning(warn_msg, group, lmod_version, min_lmod_version)
            res = ''

        return res

    def check_str(self, txt):
        """Check whether provided string has any unwanted substrings in it."""
        if self.START_STR in txt or self.END_STR in txt:
            raise EasyBuildError("Found unwanted '%s' or '%s' in: %s", self.START_STR, self.END_STR, txt)
        else:
            return txt

    def comment(self, msg):
        """Return string containing given message as a comment."""
        return "-- %s\n" % msg

    def conditional_statement(self, conditions, body, negative=False, else_body=None, indent=True,
                              cond_or=False, cond_tmpl=None):
        """
        Return formatted conditional statement, with given condition and body.

        :param conditions: (list of) string(s) containing the statement(s) for the if condition (in correct syntax)
        :param body: (multiline) string with if body (in correct syntax, without indentation)
        :param negative: boolean indicating whether the (individual) condition(s) should be negated
        :param else_body: optional body for 'else' part
        :param indent: indent if/else body
        :param cond_or: combine multiple conditions using 'or' (default is to combine with 'and')
        :param cond_tmpl: template for condition expression (default: '%s')
        """
        if isinstance(conditions, string_type):
            conditions = [conditions]

        if cond_or:
            join_op = ' or '
        else:
            join_op = ' and '

        if negative:
            condition = join_op.join('not ( %s )' % c for c in conditions)
        else:
            condition = join_op.join(conditions)

        if cond_tmpl:
            condition = cond_tmpl % condition

        lines = ["if %s then" % condition]

        for line in body.split('\n'):
            if indent:
                line = self.INDENTATION + line
            lines.append(line)

        if else_body is None:
            lines.extend(['end', ''])
        else:
            lines.append('else')
            for line in else_body.split('\n'):
                if indent:
                    line = self.INDENTATION + line
                lines.append(line)
            lines.extend(['end', ''])

        return '\n'.join(lines)

    def get_description(self, conflict=True):
        """
        Generate a description.
        """
        txt = '\n'.join([
            'help(%s%s' % (self.START_STR, self.check_str(self._generate_help_text())),
            '%s)' % self.END_STR,
            '',
        ])

        lines = [
            "%(whatis_lines)s",
            '',
            'local root = "%(installdir)s"',
        ]

        if self.app.cfg['moduleloadnoconflict']:
            self.log.info("Nothing to do to ensure no conflicts can occur on load when using Lua modules files/Lmod")

        elif conflict:
            # conflict on 'name' part of module name (excluding version part at the end)
            lines.extend(['', 'conflict("%s")' % os.path.dirname(self.app.short_mod_name)])

        whatis_lines = []
        for line in self._generate_whatis_lines():
            whatis_lines.append("whatis(%s%s%s)" % (self.START_STR, self.check_str(line), self.END_STR))

        if build_option('module_extensions'):
            extensions_list = self._generate_extensions_list()

            if extensions_list:
                extensions_stmt = 'extensions("%s")' % ','.join(['%s' % x for x in extensions_list])
                # put this behind a Lmod version check as 'extensions' is only (well) supported since Lmod 8.2.8,
                # see https://lmod.readthedocs.io/en/latest/330_extensions.html#module-extensions and
                # https://github.com/TACC/Lmod/issues/428
                lines.extend(['', self.conditional_statement(self.check_version("8", "2", "8"), extensions_stmt)])

        txt += '\n'.join([''] + lines + ['']) % {
            'name': self.app.name,
            'version': self.app.version,
            'whatis_lines': '\n'.join(whatis_lines),
            'installdir': self.app.installdir,
            'homepage': self.app.cfg['homepage'],
        }

        return txt

    def getenv_cmd(self, envvar, default=None):
        """
        Return module-syntax specific code to get value of specific environment variable.
        """
        if default is None:
            cmd = 'os.getenv("%s")' % envvar
        else:
            cmd = 'os.getenv("%s") or "%s"' % (envvar, default)
        return cmd

    def load_module(self, mod_name, recursive_unload=None, depends_on=False, unload_modules=None, multi_dep_mods=None):
        """
        Generate load statement for specified module.

        :param mod_name: name of module to generate load statement for
        :param recursive_unload: boolean indicating whether the 'load' statement should be reverted on unload
                                 (if None: enable if recursive_mod_unload build option or depends_on is True)
        :param depends_on: use depends_on statements rather than (guarded) load statements
        :param unload_modules: name(s) of module to unload first
        :param multi_dep_mods: list of module names in multi_deps context, to use for guarding load statement
        """
        body = []
        if unload_modules:
            body.extend([self.unload_module(m).strip() for m in unload_modules])

        load_template = self.LOAD_TEMPLATE
        # Lmod 7.6+ supports depends_on which does this most nicely:
        if build_option('mod_depends_on') or depends_on:
            if not self.modules_tool.supports_depends_on:
                raise EasyBuildError("depends_on statements in generated module are not supported by modules tool")
            load_template = self.LOAD_TEMPLATE_DEPENDS_ON

        body.append(load_template)

        depends_on = load_template == self.LOAD_TEMPLATE_DEPENDS_ON

        cond_tmpl = None

        if recursive_unload is None:
            recursive_unload = build_option('recursive_mod_unload') or depends_on

        if recursive_unload:
            # wrapping the 'module load' statement with an 'is-loaded or mode == unload'
            # guard ensures recursive unloading while avoiding load storms;
            # when "module unload" is called on the module in which the
            # dependency "module load" is present, it will get translated
            # to "module unload" (while the condition is left untouched)
            # see also http://lmod.readthedocs.io/en/latest/210_load_storms.html
            cond_tmpl = 'mode() == "unload" or %s'

        if depends_on:
            if multi_dep_mods and len(multi_dep_mods) > 1:
                parent_mod_name = os.path.dirname(mod_name)
                guard = self.is_loaded(multi_dep_mods[1:])
                if_body = load_template % {'mod_name': parent_mod_name}
                else_body = '\n'.join(body)
                load_statement = [
                    self.conditional_statement(guard, if_body, else_body=else_body, cond_tmpl=cond_tmpl, cond_or=True),
                ]
            else:
                load_statement = body + ['']
        else:
            if multi_dep_mods is None:
                # guard load statement with check to see whether module being loaded is already loaded
                # (this avoids load storms)
                cond_mod_names = '%(mod_name)s'
            else:
                cond_mod_names = multi_dep_mods

            # conditional load if one or more conditions are specified
            load_guards = self.is_loaded(cond_mod_names)
            body = '\n'.join(body)
            load_statement = [self.conditional_statement(load_guards, body, negative=True, cond_tmpl=cond_tmpl)]

        return '\n'.join([''] + load_statement) % {'mod_name': mod_name}

    def msg_on_load(self, msg):
        """
        Add a message that should be printed when loading the module.
        """
        # take into account possible newlines in messages by using [==...==] (requires Lmod 5.8)
        stmt = 'io.stderr:write(%s%s%s)' % (self.START_STR, self.check_str(msg), self.END_STR)
        return '\n' + self.conditional_statement('mode() == "load"', stmt, indent=False)

    def modulerc(self, module_version=None, filepath=None, modulerc_txt=None):
        """
        Generate contents of .modulerc(.lua) file, in Lua syntax (but only if Lmod is recent enough, i.e. >= 7.7.38)

        :param module_version: specs for module-version statement (dict with 'modname', 'sym_version' & 'version' keys)
        :param filepath: location where .modulerc file should be written to
        :param modulerc_txt: contents of .modulerc to use
        :return: contents of .modulerc file
        """
        if modulerc_txt is None:
            lmod_ver = self.modules_tool.version
            min_ver = '7.7.38'

            if LooseVersion(lmod_ver) >= LooseVersion(min_ver):
                self.log.info("Found Lmod v%s >= v%s, so will generate .modulerc.lua in Lua syntax", lmod_ver, min_ver)

                modulerc = []

                if self._modulerc_check_module_version(module_version):
                    module_version_statement = 'module_version("%(modname)s", "%(sym_version)s")'
                    modulerc.append(module_version_statement % module_version)

                modulerc_txt = '\n'.join(modulerc)

            else:
                self.log.info("Lmod v%s < v%s, need to stick to Tcl syntax for .modulerc", lmod_ver, min_ver)

        return super(ModuleGeneratorLua, self).modulerc(module_version=module_version, filepath=filepath,
                                                        modulerc_txt=modulerc_txt)

    def update_paths(self, key, paths, prepend=True, allow_abs=False, expand_relpaths=True):
        """
        Generate prepend_path or append_path statements for the given list of paths

        :param key: environment variable to prepend/append paths to
        :param paths: list of paths to prepend/append
        :param prepend: whether to prepend (True) or append (False) paths
        :param allow_abs: allow providing of absolute paths
        :param expand_relpaths: expand relative paths into absolute paths (by prefixing install dir)
        """
        if prepend:
            update_type = 'prepend'
        else:
            update_type = 'append'

        if not self.define_env_var(key):
            self.log.info("Not including statement to %s environment variable $%s, as specified", update_type, key)
            return ''

        if isinstance(paths, string_type):
            self.log.debug("Wrapping %s into a list before using it to %s path %s", update_type, paths, key)
            paths = [paths]

        abspaths = []
        for path in paths:
            if os.path.isabs(path):
                if allow_abs:
                    abspaths.append(quote_str(path))
                else:
                    raise EasyBuildError("Absolute path %s passed to update_paths which only expects relative paths.",
                                         path)
            else:
                # use pathJoin for (non-empty) relative paths
                if path:
                    if expand_relpaths:
                        abspaths.append(self.PATH_JOIN_TEMPLATE % path)
                    else:
                        abspaths.append(quote_str(path))
                else:
                    abspaths.append('root')

        statements = [self.UPDATE_PATH_TEMPLATE % (update_type, key, p) for p in abspaths]
        statements.append('')
        return '\n'.join(statements)

    def set_alias(self, key, value):
        """
        Generate set-alias statement in modulefile for the given key/value pair.
        """
        # quotes are needed, to ensure smooth working of EBDEVEL* modulefiles
        return 'set_alias("%s", %s)\n' % (key, quote_str(value))

    def set_as_default(self, module_dir_path, module_version, mod_symlink_paths=None):
        """
        Create a symlink named 'default' inside the package's module folder in order to set the default module version

        :param module_dir_path: module directory path, e.g. $HOME/easybuild/modules/all/Bison
        :param module_version: module version, e.g. 3.0.4
        :param mod_symlink_paths: list of paths in which symlinks to module files must be created
        """
        def create_default_symlink(path):
            """Helper function to create 'default' symlink in specified directory."""
            default_filepath = os.path.join(path, 'default')

            if os.path.islink(default_filepath):
                link_target = resolve_path(default_filepath)
                remove_file(default_filepath)
                self.log.info("Removed default version marking from %s.", link_target)
            elif os.path.exists(default_filepath):
                raise EasyBuildError('Found an unexpected file named default in dir %s', module_dir_path)

            symlink(module_version + self.MODULE_FILE_EXTENSION, default_filepath, use_abspath_source=False)
            self.log.info("Module default version file written to point to %s", default_filepath)

        create_default_symlink(module_dir_path)

        # also create symlinks in class module folders
        if mod_symlink_paths is None:
            mod_symlink_paths = []

        for mod_symlink_path in mod_symlink_paths:
            mod_dir_name = os.path.basename(module_dir_path)
            mod_symlink_dir = os.path.join(install_path('mod'), mod_symlink_path, mod_dir_name)
            create_default_symlink(mod_symlink_dir)

    def set_environment(self, key, value, relpath=False):
        """
        Generate a quoted setenv statement for the given key/value pair.

        :param key: name of environment variable to define
        :param value: value to define environment variable with
        :param relpath: value is path relative to installation prefix
        """
        if not self.define_env_var(key):
            self.log.info("Not including statement to define environment variable $%s, as specified", key)
            return ''

        if relpath:
            if value:
                val = self.PATH_JOIN_TEMPLATE % value
            else:
                val = 'root'
        else:
            val = quote_str(value)
        return 'setenv("%s", %s)\n' % (key, val)

    def swap_module(self, mod_name_out, mod_name_in, guarded=True):
        """
        Generate swap statement for specified module names.

        :param mod_name_out: name of module to unload (swap out)
        :param mod_name_in: name of module to load (swap in)
        :param guarded: guard 'swap' statement, fall back to 'load' if module being swapped out is not loaded
        """
        body = '\n'.join([
            'unload("%s")' % mod_name_out,
            'load("%s")' % mod_name_in,
        ])
        if guarded:
            alt_body = self.LOAD_TEMPLATE % {'mod_name': mod_name_in}
            swap_statement = [self.conditional_statement(self.is_loaded(mod_name_out), body, else_body=alt_body)]
        else:
            swap_statement = [body, '']

        return '\n'.join([''] + swap_statement)

    def unload_module(self, mod_name):
        """
        Generate unload statement for specified module.

        :param mod_name: name of module to generate unload statement for
        """
        return '\n'.join(['', 'unload("%s")' % mod_name])

    def det_user_modpath(self, user_modpath):
        """
        Determine user-specific modules subdirectory, to be used in 'use' statements
        (cfr. implementations of use() method).
        """
        if user_modpath:
            user_modpath = ', '.join(self._det_user_modpath_common(user_modpath))

        return user_modpath

    def use(self, paths, prefix=None, guarded=False, user_modpath=None):
        """
        Generate module use statements for given list of module paths.
        :param paths: list of module path extensions to generate use statements for; paths will be quoted
        :param prefix: optional path prefix; not quoted, i.e., can be a statement
        :param guarded: use statements will be guarded to only apply if path exists
        :param user_modpath: user-specific modules subdirectory to include in use statements
        """
        user_modpath = self.det_user_modpath(user_modpath)
        use_statements = []
        for path in paths:
            quoted_path = quote_str(path)
            if user_modpath:
                quoted_path = 'pathJoin(%s, %s)' % (user_modpath, quoted_path)
            if prefix:
                full_path = 'pathJoin(%s, %s)' % (prefix, quoted_path)
            else:
                full_path = quoted_path

            prepend_modulepath = self.UPDATE_PATH_TEMPLATE % ('prepend', 'MODULEPATH', full_path)
            if guarded:
                cond_statement = self.conditional_statement('isDir(%s)' % full_path, prepend_modulepath)
                use_statements.append(cond_statement)
            else:
                use_statements.append(prepend_modulepath + '\n')
        return ''.join(use_statements)
