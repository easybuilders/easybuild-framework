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
Generating module files.

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Fotis Georgatos (Uni.Lu, NTUA)
:author: Damian Alvarez (Forschungszentrum Juelich GmbH)
"""
import os
import re
import sys
import tempfile
from distutils.version import LooseVersion
from textwrap import wrap
from vsc.utils import fancylogger
from vsc.utils.missing import get_subclasses

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option, get_module_syntax, install_path
from easybuild.tools.filetools import convert_name, mkdir, read_file, remove_file, resolve_path, symlink, write_file
from easybuild.tools.modules import ROOT_ENV_VAR_NAME_PREFIX, modules_tool
from easybuild.tools.utilities import quote_str


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


def dependencies_for(mod_name, modtool, depth=sys.maxint):
    """
    Obtain a list of dependencies for the given module, determined recursively, up to a specified depth (optionally)
    :param depth: recursion depth (default is sys.maxint, which should be equivalent to infinite recursion depth)
    """
    mod_filepath = modtool.modulefile_path(mod_name)
    modtxt = read_file(mod_filepath)
    loadregex = module_load_regex(mod_filepath)
    mods = loadregex.findall(modtxt)

    if depth > 0:
        # recursively determine dependencies for these dependency modules, until depth is non-positive
        moddeps = [dependencies_for(mod, modtool, depth=depth - 1) for mod in mods]
    else:
        # ignore any deeper dependencies
        moddeps = []

    # add dependencies of dependency modules only if they're not there yet
    for moddepdeps in moddeps:
        for dep in moddepdeps:
            if not dep in mods:
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

    # a single level of indentation
    INDENTATION = ' ' * 4

    def __init__(self, application, fake=False):
        """ModuleGenerator constructor."""
        self.app = application
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.fake_mod_path = tempfile.mkdtemp()

    def append_paths(self, key, paths, allow_abs=False, expand_relpaths=True):
        """
        Generate append-path statements for the given list of paths.

        :param key: environment variable to append paths to
        :param paths: list of paths to append
        :param allow_abs: allow providing of absolute paths
        :param expand_relpaths: expand relative paths into absolute paths (by prefixing install dir)
        """
        return self.update_paths(key, paths, prepend=False, allow_abs=allow_abs, expand_relpaths=expand_relpaths)

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

        except OSError, err:
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

    def prepend_paths(self, key, paths, allow_abs=False, expand_relpaths=True):
        """
        Generate prepend-path statements for the given list of paths.

        :param key: environment variable to append paths to
        :param paths: list of paths to append
        :param allow_abs: allow providing of absolute paths
        :param expand_relpaths: expand relative paths into absolute paths (by prefixing install dir)
        """
        return self.update_paths(key, paths, prepend=True, allow_abs=allow_abs, expand_relpaths=expand_relpaths)

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

    def conditional_statement(self, condition, body, negative=False, else_body=None):
        """
        Return formatted conditional statement, with given condition and body.

        :param condition: string containing the statement for the if condition (in correct syntax)
        :param body: (multiline) string with if body (in correct syntax, without indentation)
        :param negative: boolean indicating whether the condition should be negated
        :param else_body: optional body for 'else' part
        """
        raise NotImplementedError

    def get_description(self, conflict=True):
        """
        Generate a description.
        """
        raise NotImplementedError

    def getenv_cmd(self, envvar):
        """
        Return module-syntax specific code to get value of specific environment variable.
        """
        raise NotImplementedError

    def load_module(self, mod_name, recursive_unload=False, unload_modules=None):
        """
        Generate load statement for specified module.

        :param mod_name: name of module to generate load statement for
        :param recursive_unload: boolean indicating whether the 'load' statement should be reverted on unload
        :param unload_modules: name(s) of module to unload first
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

    def set_as_default(self, module_folder_path, module_version):
        """
        Set generated module as default module

        :param module_folder_path: module folder path, e.g. $HOME/easybuild/modules/all/Bison
        :param module_version: module version, e.g. 3.0.4
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

    def use(self, paths, prefix=None, guarded=False):
        """
        Generate module use statements for given list of module paths.
        :param paths: list of module path extensions to generate use statements for; paths will be quoted
        :param prefix: optional path prefix; not quoted, i.e., can be a statement
        :param guarded: use statements will be guarded to only apply if path exists
        """
        raise NotImplementedError

    def _generate_extension_list(self):
        """
        Generate a string with a comma-separated list of extensions.
        """
        exts_list = self.app.cfg['exts_list']
        extensions = ', '.join(sorted(['-'.join(ext[:2]) for ext in exts_list], key=str.lower))

        return extensions

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

        # Extensions (if any)
        extensions = self._generate_extension_list()
        lines.extend(self._generate_section("Included extensions", '\n'.join(wrap(extensions, 78))))

        return '\n'.join(lines)

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
                "Homepage: %s" % self.app.cfg['homepage']
            ]
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

    LOAD_REGEX = r"^\s*module\s+load\s+(\S+)"
    LOAD_TEMPLATE = "module load %(mod_name)s"

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

    def conditional_statement(self, condition, body, negative=False, else_body=None):
        """
        Return formatted conditional statement, with given condition and body.

        :param condition: string containing the statement for the if condition (in correct syntax)
        :param body: (multiline) string with if body (in correct syntax, without indentation)
        :param negative: boolean indicating whether the condition should be negated
        :param else_body: optional body for 'else' part
        """
        if negative:
            lines = ["if { ![ %s ] } {" % condition]
        else:
            lines = ["if { [ %s ] } {" % condition]

        for line in body.split('\n'):
            lines.append(self.INDENTATION + line)

        if else_body is None:
            lines.extend(['}', ''])
        else:
            lines.append('} else {')
            for line in else_body.split('\n'):
                lines.append(self.INDENTATION + line)
            lines.extend(['}', ''])

        return '\n'.join(lines)

    def get_description(self, conflict=True):
        """
        Generate a description.
        """
        txt = '\n'.join([
            "proc ModulesHelp { } {",
            "    puts stderr {%s" % re.sub('([{}\[\]])', r'\\\1', self._generate_help_text()),
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
            cond_unload = self.conditional_statement("is-loaded %(name)s", "module unload %(name)s")
            lines.extend(['', self.conditional_statement("is-loaded %(name)s/%(version)s", cond_unload, negative=True)])

        elif conflict:
            # conflict on 'name' part of module name (excluding version part at the end)
            # examples:
            # - 'conflict GCC' for 'GCC/4.8.3'
            # - 'conflict Core/GCC' for 'Core/GCC/4.8.2'
            # - 'conflict Compiler/GCC/4.8.2/OpenMPI' for 'Compiler/GCC/4.8.2/OpenMPI/1.6.4'
            lines.extend(['', "conflict %s" % os.path.dirname(self.app.short_mod_name)])

        whatis_lines = ["module-whatis {%s}" % re.sub('([{}\[\]])', r'\\\1', l) for l in self._generate_whatis_lines()]
        txt += '\n'.join([''] + lines + ['']) % {
            'name': self.app.name,
            'version': self.app.version,
            'whatis_lines': '\n'.join(whatis_lines),
            'installdir': self.app.installdir,
        }

        return txt

    def getenv_cmd(self, envvar):
        """
        Return module-syntax specific code to get value of specific environment variable.
        """
        return '$env(%s)' % envvar

    def load_module(self, mod_name, recursive_unload=False, unload_modules=None):
        """
        Generate load statement for specified module.

        :param mod_name: name of module to generate load statement for
        :param recursive_unload: boolean indicating whether the 'load' statement should be reverted on unload
        :param unload_module: name(s) of module to unload first
        """
        body = []
        if unload_modules:
            body.extend([self.unload_module(m).strip() for m in unload_modules])
        body.append(self.LOAD_TEMPLATE)

        if build_option('recursive_mod_unload') or recursive_unload:
            # not wrapping the 'module load' with an is-loaded guard ensures recursive unloading;
            # when "module unload" is called on the module in which the dependency "module load" is present,
            # it will get translated to "module unload"
            load_statement = body + ['']
        else:
            load_statement = [self.conditional_statement("is-loaded %(mod_name)s", '\n'.join(body), negative=True)]

        return '\n'.join([''] + load_statement) % {'mod_name': mod_name}

    def msg_on_load(self, msg):
        """
        Add a message that should be printed when loading the module.
        """
        # escape any (non-escaped) characters with special meaning by prefixing them with a backslash
        msg = re.sub(r'((?<!\\)[%s])'% ''.join(self.CHARS_TO_ESCAPE), r'\\\1', msg)
        print_cmd = "puts stderr %s" % quote_str(msg)
        return '\n'.join(['', self.conditional_statement("module-info mode load", print_cmd)])

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

        if isinstance(paths, basestring):
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
        return 'set-alias\t%s\t\t%s\n' % (key, quote_str(value))

    def set_as_default(self, module_folder_path, module_version):
        """
        Create a .version file inside the package module folder in order to set the default version for TMod

        :param module_folder_path: module folder path, e.g. $HOME/easybuild/modules/all/Bison
        :param module_version: module version, e.g. 3.0.4
        """
        txt = self.MODULE_SHEBANG + '\n'
        txt += 'set ModulesVersion %s\n' % module_version

        # write the file no matter what
        write_file(os.path.join(module_folder_path, '.version'), txt)

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
                val = quote_str(os.path.join('$root', value))
            else:
                val = '"$root"'
        else:
            val = quote_str(value)
        return 'setenv\t%s\t\t%s\n' % (key, val)

    def swap_module(self, mod_name_out, mod_name_in, guarded=True):
        """
        Generate swap statement for specified module names.

        :param mod_name_out: name of module to unload (swap out)
        :param mod_name_in: name of module to load (swap in)
        :param guarded: guard 'swap' statement, fall back to 'load' if module being swapped out is not loaded
        """
        body = "module swap %s %s" % (mod_name_out, mod_name_in)
        if guarded:
            alt_body = self.LOAD_TEMPLATE % {'mod_name': mod_name_in}
            swap_statement = [self.conditional_statement("is-loaded %s" % mod_name_out, body, else_body=alt_body)]
        else:
            swap_statement = [body, '']

        return '\n'.join([''] + swap_statement)

    def unload_module(self, mod_name):
        """
        Generate unload statement for specified module.

        :param mod_name: name of module to generate unload statement for
        """
        return '\n'.join(['', "module unload %s" % mod_name])

    def use(self, paths, prefix=None, guarded=False):
        """
        Generate module use statements for given list of module paths.
        :param paths: list of module path extensions to generate use statements for; paths will be quoted
        :param prefix: optional path prefix; not quoted, i.e., can be a statement
        :param guarded: use statements will be guarded to only apply if path exists
        """
        use_statements = []
        for path in paths:
            quoted_path = quote_str(path)
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

    LOAD_REGEX = r'^\s*load\("(\S+)"'
    LOAD_TEMPLATE = 'load("%(mod_name)s")'

    PATH_JOIN_TEMPLATE = 'pathJoin(root, "%s")'
    UPDATE_PATH_TEMPLATE = '%s_path("%s", %s)'

    START_STR = '[==['
    END_STR = ']==]'

    def check_group(self, group, error_msg=None):
        """
        Generate a check of the software group and the current user, and refuse to load the module if the user don't
        belong to the group

        :param group: string with the group name
        :param error_msg: error message to print for users outside that group
        """
        lmod_version = os.environ.get('LMOD_VERSION', 'NOT_FOUND')
        min_lmod_version = '6.0.8'

        if lmod_version != 'NOT_FOUND' and LooseVersion(lmod_version) >= LooseVersion(min_lmod_version):
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

    def conditional_statement(self, condition, body, negative=False, else_body=None):
        """
        Return formatted conditional statement, with given condition and body.

        :param condition: string containing the statement for the if condition (in correct syntax)
        :param body: (multiline) string with if body (in correct syntax, without indentation)
        :param negative: boolean indicating whether the condition should be negated
        :param else_body: optional body for 'else' part
        """
        if negative:
            lines = ["if not %s then" % condition]
        else:
            lines = ["if %s then" % condition]

        for line in body.split('\n'):
            lines.append(self.INDENTATION + line)

        if else_body is None:
            lines.extend(['end', ''])
        else:
            lines.append('else')
            for line in else_body.split('\n'):
                lines.append(self.INDENTATION + line)
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

        txt += '\n'.join([''] + lines + ['']) % {
            'name': self.app.name,
            'version': self.app.version,
            'whatis_lines': '\n'.join(whatis_lines),
            'installdir': self.app.installdir,
            'homepage': self.app.cfg['homepage'],
        }

        return txt

    def getenv_cmd(self, envvar):
        """
        Return module-syntax specific code to get value of specific environment variable.
        """
        return 'os.getenv("%s")' % envvar

    def load_module(self, mod_name, recursive_unload=False, unload_modules=None):
        """
        Generate load statement for specified module.

        :param mod_name: name of module to generate load statement for
        :param recursive_unload: boolean indicating whether the 'load' statement should be reverted on unload
        :param unload_modules: name(s) of module to unload first
        """
        body = []
        if unload_modules:
            body.extend([self.unload_module(m).strip() for m in unload_modules])
        body.append(self.LOAD_TEMPLATE)

        if build_option('recursive_mod_unload') or recursive_unload:
            # wrapping the 'module load' with an 'is-loaded or mode == unload'
            # guard ensures recursive unloading while avoiding load storms,
            # when "module unload" is called on the module in which the
            # depedency "module load" is present, it will get translated
            # to "module unload"
            # see also http://lmod.readthedocs.io/en/latest/210_load_storms.html
            load_guard = 'isloaded("%(mod_name)s") or mode() == "unload"'
        else:
            load_guard = 'isloaded("%(mod_name)s")'
        load_statement = [self.conditional_statement(load_guard, '\n'.join(body), negative=True)]

        return '\n'.join([''] + load_statement) % {'mod_name': mod_name}

    def msg_on_load(self, msg):
        """
        Add a message that should be printed when loading the module.
        """
        # take into account possible newlines in messages by using [==...==] (requires Lmod 5.8)
        stmt = 'io.stderr:write(%s%s%s)' % (self.START_STR, self.check_str(msg), self.END_STR)
        return '\n' + self.conditional_statement('mode() == "load"', stmt)

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

        if isinstance(paths, basestring):
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

    def set_as_default(self, module_folder_path, module_version):
        """
        Create a symlink named 'default' inside the package's module folder in order to set the default module version

        :param module_folder_path: module folder path, e.g. $HOME/easybuild/modules/all/Bison
        :param module_version: module version, e.g. 3.0.4
        """
        default_filepath = os.path.join(module_folder_path, 'default')

        if os.path.islink(default_filepath):
            link_target = resolve_path(default_filepath)
            remove_file(default_filepath)
            self.log.info("Removed default version marking from %s.", link_target)
        elif os.path.exists(default_filepath):
            raise EasyBuildError('Found an unexpected file named default in dir %s' % module_folder_path)

        symlink(module_version + self.MODULE_FILE_EXTENSION, default_filepath, use_abspath_source=False)
        self.log.info("Module default version file written to point to %s", default_filepath)

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
        body = 'swap("%s", "%s")' % (mod_name_out, mod_name_in)
        if guarded:
            alt_body = self.LOAD_TEMPLATE % {'mod_name': mod_name_in}
            swap_statement = [self.conditional_statement('isloaded("%s")' % mod_name_out, body, else_body=alt_body)]
        else:
            swap_statement = [body, '']

        return '\n'.join([''] + swap_statement)

    def unload_module(self, mod_name):
        """
        Generate unload statement for specified module.

        :param mod_name: name of module to generate unload statement for
        """
        return '\n'.join(['', 'unload("%s")' % mod_name])

    def use(self, paths, prefix=None, guarded=False):
        """
        Generate module use statements for given list of module paths.
        :param paths: list of module path extensions to generate use statements for; paths will be quoted
        :param prefix: optional path prefix; not quoted, i.e., can be a statement
        :param guarded: use statements will be guarded to only apply if path exists
        """
        use_statements = []
        for path in paths:
            quoted_path = quote_str(path)
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
