# #
# Copyright 2009-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/easybuild
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

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Fotis Georgatos (Uni.Lu, NTUA)
"""
import os
import re
import sys
import tempfile
from vsc.utils import fancylogger
from vsc.utils.missing import get_subclasses

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option, get_module_syntax, install_path
from easybuild.tools.filetools import mkdir, read_file
from easybuild.tools.modules import modules_tool
from easybuild.tools.utilities import quote_str


_log = fancylogger.getLogger('module_generator', fname=False)


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

    def get_modules_path(self, fake=False, mod_path_suffix=None):
        """Return path to directory where module files should be generated in."""
        mod_path = install_path('mod')
        if fake:
            self.log.debug("Fake mode: using %s (instead of %s)" % (self.fake_mod_path, mod_path))
            mod_path = self.fake_mod_path

        if mod_path_suffix is None:
            mod_path_suffix = build_option('suffix_modules_path')

        return os.path.join(mod_path, mod_path_suffix)

    def get_module_filepath(self, fake=False, mod_path_suffix=None):
        """Return path to module file."""
        mod_path = self.get_modules_path(fake=fake, mod_path_suffix=mod_path_suffix)
        full_mod_name = self.app.full_mod_name + self.MODULE_FILE_EXTENSION
        return os.path.join(mod_path, full_mod_name)

    def prepare(self, fake=False):
        """
        Prepare for generating module file: Creates the absolute filename for the module.
        """
        mod_path = self.get_modules_path(fake=fake)
        # module file goes in general moduleclass category
        # make symlink in moduleclass category

        mod_filepath = self.get_module_filepath(fake=fake)
        mkdir(os.path.dirname(mod_filepath), parents=True)

        # remove module file if it's there (it'll be recreated), see EasyBlock.make_module
        if os.path.exists(mod_filepath) and not build_option('extended_dry_run'):
            self.log.debug("Removing existing module file %s", mod_filepath)
            os.remove(mod_filepath)

        return mod_path

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

    def comment(self, msg):
        """Return given string formatted as a comment."""
        raise NotImplementedError

    def conditional_statement(self, condition, body, negative=False, else_body=None):
        """
        Return formatted conditional statement, with given condition and body.

        @param condition: string containing the statement for the if condition (in correct syntax)
        @param body: (multiline) string with if body (in correct syntax, without indentation)
        @param negative: boolean indicating whether the condition should be negated
        @param else_body: optional body for 'else' part
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

        @param mod_name: name of module to generate load statement for
        @param recursive_unload: boolean indicating whether the 'load' statement should be reverted on unload
        @param unload_modules: name(s) of module to unload first
        """
        raise NotImplementedError

    def unload_module(self, mod_name):
        """
        Generate unload statement for specified module.

        @param mod_name: name of module to generate unload statement for
        """
        raise NotImplementedError

    def swap_module(self, mod_name_out, mod_name_in, guarded=True):
        """
        Generate swap statement for specified module names.

        @param mod_name_out: name of module to unload (swap out)
        @param mod_name_in: name of module to load (swap in)
        @param guarded: guard 'swap' statement, fall back to 'load' if module being swapped out is not loaded
        """
        raise NotImplementedError


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

    def comment(self, msg):
        """Return string containing given message as a comment."""
        return "# %s\n" % msg

    def conditional_statement(self, condition, body, negative=False, else_body=None):
        """
        Return formatted conditional statement, with given condition and body.

        @param condition: string containing the statement for the if condition (in correct syntax)
        @param body: (multiline) string with if body (in correct syntax, without indentation)
        @param negative: boolean indicating whether the condition should be negated
        @param else_body: optional body for 'else' part
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
        description = "%s - Homepage: %s" % (self.app.cfg['description'], self.app.cfg['homepage'])

        whatis = self.app.cfg['whatis']
        if whatis is None:
            # default: include single 'whatis' statement with description as contents
            whatis = ["Description: %s" % description]

        lines = [
            "proc ModulesHelp { } {",
            "    puts stderr { %(description)s",
            "    }",
            '}',
            '',
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

        txt = '\n'.join(lines + ['']) % {
            'name': self.app.name,
            'version': self.app.version,
            'description': description,
            'whatis_lines': '\n'.join(["module-whatis {%s}" % line for line in whatis]),
            'installdir': self.app.installdir,
        }

        return txt

    def load_module(self, mod_name, recursive_unload=False, unload_modules=None):
        """
        Generate load statement for specified module.

        @param mod_name: name of module to generate load statement for
        @param recursive_unload: boolean indicating whether the 'load' statement should be reverted on unload
        @param unload_module: name(s) of module to unload first
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

    def unload_module(self, mod_name):
        """
        Generate unload statement for specified module.

        @param mod_name: name of module to generate unload statement for
        """
        return '\n'.join(['', "module unload %s" % mod_name])

    def swap_module(self, mod_name_out, mod_name_in, guarded=True):
        """
        Generate swap statement for specified module names.

        @param mod_name_out: name of module to unload (swap out)
        @param mod_name_in: name of module to load (swap in)
        @param guarded: guard 'swap' statement, fall back to 'load' if module being swapped out is not loaded
        """
        body = "module swap %s %s" % (mod_name_out, mod_name_in)
        if guarded:
            alt_body = self.LOAD_TEMPLATE % {'mod_name': mod_name_in}
            swap_statement = [self.conditional_statement("is-loaded %s" % mod_name_out, body, else_body=alt_body)]
        else:
            swap_statement = [body, '']

        return '\n'.join([''] + swap_statement)

    def prepend_paths(self, key, paths, allow_abs=False, expand_relpaths=True):
        """
        Generate prepend-path statements for the given list of paths.

        @param key: environment variable to prepend paths to
        @param paths: list of paths to prepend
        @param allow_abs: allow providing of absolute paths
        @param expand_relpaths: expand relative paths into absolute paths (by prefixing install dir)
        """
        template = "prepend-path\t%s\t\t%s\n"

        if isinstance(paths, basestring):
            self.log.debug("Wrapping %s into a list before using it to prepend path %s" % (paths, key))
            paths = [paths]

        abspaths = []
        for path in paths:
            if os.path.isabs(path) and not allow_abs:
                raise EasyBuildError("Absolute path %s passed to prepend_paths which only expects relative paths.",
                                     path)
            elif not os.path.isabs(path):
                # prepend $root (= installdir) for (non-empty) relative paths
                if path:
                    if expand_relpaths:
                        abspaths.append(os.path.join('$root', path))
                    else:
                        abspaths.append(path)
                else:
                    abspaths.append('$root')
            else:
                abspaths.append(path)

        statements = [template % (key, p) for p in abspaths]
        return ''.join(statements)

    def use(self, paths, prefix=None, guarded=False):
        """
        Generate module use statements for given list of module paths.
        @param paths: list of module path extensions to generate use statements for; paths will be quoted
        @param prefix: optional path prefix; not quoted, i.e., can be a statement
        @param guarded: use statements will be guarded to only apply if path exists
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

    def set_environment(self, key, value, relpath=False):
        """
        Generate setenv statement for the given key/value pair.
        """
        # quotes are needed, to ensure smooth working of EBDEVEL* modulefiles
        if relpath:
            if value:
                val = quote_str(os.path.join('$root', value))
            else:
                val = '"$root"'
        else:
            val = quote_str(value)
        return 'setenv\t%s\t\t%s\n' % (key, val)

    def msg_on_load(self, msg):
        """
        Add a message that should be printed when loading the module.
        """
        # escape any (non-escaped) characters with special meaning by prefixing them with a backslash
        msg = re.sub(r'((?<!\\)[%s])'% ''.join(self.CHARS_TO_ESCAPE), r'\\\1', msg)
        print_cmd = "puts stderr %s" % quote_str(msg)
        return '\n'.join(['', self.conditional_statement("module-info mode load", print_cmd)])

    def set_alias(self, key, value):
        """
        Generate set-alias statement in modulefile for the given key/value pair.
        """
        # quotes are needed, to ensure smooth working of EBDEVEL* modulefiles
        return 'set-alias\t%s\t\t%s\n' % (key, quote_str(value))

    def getenv_cmd(self, envvar):
        """
        Return module-syntax specific code to get value of specific environment variable.
        """
        return '$env(%s)' % envvar


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
    PREPEND_PATH_TEMPLATE = 'prepend_path("%s", %s)'

    def __init__(self, *args, **kwargs):
        """ModuleGeneratorLua constructor."""
        super(ModuleGeneratorLua, self).__init__(*args, **kwargs)

    def comment(self, msg):
        """Return string containing given message as a comment."""
        return "-- %s\n" % msg

    def conditional_statement(self, condition, body, negative=False, else_body=None):
        """
        Return formatted conditional statement, with given condition and body.

        @param condition: string containing the statement for the if condition (in correct syntax)
        @param body: (multiline) string with if body (in correct syntax, without indentation)
        @param negative: boolean indicating whether the condition should be negated
        @param else_body: optional body for 'else' part
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

        description = "%s - Homepage: %s" % (self.app.cfg['description'], self.app.cfg['homepage'])

        whatis = self.app.cfg['whatis']
        if whatis is None:
            # default: include single 'whatis' statement with description as contents
            whatis = ["Description: %s" % description]

        lines = [
            "help([[%(description)s]])",
            '',
            "%(whatis_lines)s",
            '',
            'local root = "%(installdir)s"',
        ]

        if self.app.cfg['moduleloadnoconflict']:
            self.log.info("Nothing to do to ensure no conflicts can occur on load when using Lua modules files/Lmod")

        elif conflict:
            # conflict on 'name' part of module name (excluding version part at the end)
            lines.extend(['', 'conflict("%s")' % os.path.dirname(self.app.short_mod_name)])

        txt = '\n'.join(lines + ['']) % {
            'name': self.app.name,
            'version': self.app.version,
            'description': description,
            'whatis_lines': '\n'.join(["whatis([[%s]])" % line for line in whatis]),
            'installdir': self.app.installdir,
            'homepage': self.app.cfg['homepage'],
        }

        return txt

    def load_module(self, mod_name, recursive_unload=False, unload_modules=None):
        """
        Generate load statement for specified module.

        @param mod_name: name of module to generate load statement for
        @param recursive_unload: boolean indicating whether the 'load' statement should be reverted on unload
        @param unload_modules: name(s) of module to unload first
        """
        body = []
        if unload_modules:
            body.extend([self.unload_module(m).strip() for m in unload_modules])
        body.append(self.LOAD_TEMPLATE)

        if build_option('recursive_mod_unload') or recursive_unload:
            # not wrapping the 'module load' with an is-loaded guard ensures recursive unloading;
            # when "module unload" is called on the module in which the depedency "module load" is present,
            # it will get translated to "module unload"
            load_statement = body + ['']
        else:
            load_statement = [self.conditional_statement('isloaded("%(mod_name)s")', '\n'.join(body), negative=True)]

        return '\n'.join([''] + load_statement) % {'mod_name': mod_name}

    def unload_module(self, mod_name):
        """
        Generate unload statement for specified module.

        @param mod_name: name of module to generate unload statement for
        """
        return '\n'.join(['', 'unload("%s")' % mod_name])

    def swap_module(self, mod_name_out, mod_name_in, guarded=True):
        """
        Generate swap statement for specified module names.

        @param mod_name_out: name of module to unload (swap out)
        @param mod_name_in: name of module to load (swap in)
        @param guarded: guard 'swap' statement, fall back to 'load' if module being swapped out is not loaded
        """
        body = 'swap("%s", "%s")' % (mod_name_out, mod_name_in)
        if guarded:
            alt_body = self.LOAD_TEMPLATE % {'mod_name': mod_name_in}
            swap_statement = [self.conditional_statement('isloaded("%s")' % mod_name_out, body, else_body=alt_body)]
        else:
            swap_statement = [body, '']

        return '\n'.join([''] + swap_statement)

    def prepend_paths(self, key, paths, allow_abs=False, expand_relpaths=True):
        """
        Generate prepend-path statements for the given list of paths

        @param key: environment variable to prepend paths to
        @param paths: list of paths to prepend
        @param allow_abs: allow providing of absolute paths
        @param expand_relpaths: expand relative paths into absolute paths (by prefixing install dir)
        """
        if isinstance(paths, basestring):
            self.log.debug("Wrapping %s into a list before using it to prepend path %s", paths, key)
            paths = [paths]

        abspaths = []
        for path in paths:
            if os.path.isabs(path):
                if allow_abs:
                    abspaths.append(quote_str(path))
                else:
                    raise EasyBuildError("Absolute path %s passed to prepend_paths which only expects relative paths.",
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

        statements = [self.PREPEND_PATH_TEMPLATE % (key, p) for p in abspaths]
        statements.append('')
        return '\n'.join(statements)

    def use(self, paths, prefix=None, guarded=False):
        """
        Generate module use statements for given list of module paths.
        @param paths: list of module path extensions to generate use statements for; paths will be quoted
        @param prefix: optional path prefix; not quoted, i.e., can be a statement
        @param guarded: use statements will be guarded to only apply if path exists
        """
        use_statements = []
        for path in paths:
            quoted_path = quote_str(path)
            if prefix:
                full_path = 'pathJoin(%s, %s)' % (prefix, quoted_path)
            else:
                full_path = quoted_path
            if guarded:
                cond_statement = self.conditional_statement('isDir(%s)' % full_path,
                                                            self.PREPEND_PATH_TEMPLATE % ('MODULEPATH', full_path))
                use_statements.append(cond_statement)
            else:
                use_statements.append(self.PREPEND_PATH_TEMPLATE % ('MODULEPATH', full_path) + '\n')
        return ''.join(use_statements)

    def set_environment(self, key, value, relpath=False):
        """
        Generate a quoted setenv statement for the given key/value pair.
        """
        if relpath:
            if value:
                val = self.PATH_JOIN_TEMPLATE % value
            else:
                val = 'root'
        else:
            val = quote_str(value)
        return 'setenv("%s", %s)\n' % (key, val)

    def msg_on_load(self, msg):
        """
        Add a message that should be printed when loading the module.
        """
        return '\n'.join(['', self.conditional_statement('mode() == "load"', 'io.stderr:write("%s")' % msg)])

    def set_alias(self, key, value):
        """
        Generate set-alias statement in modulefile for the given key/value pair.
        """
        # quotes are needed, to ensure smooth working of EBDEVEL* modulefiles
        return 'set_alias("%s", %s)\n' % (key, quote_str(value))

    def getenv_cmd(self, envvar):
        """
        Return module-syntax specific code to get value of specific environment variable.
        """
        return 'os.getenv("%s")' % envvar


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
    @param depth: recursion depth (default is sys.maxint, which should be equivalent to infinite recursion depth)
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
