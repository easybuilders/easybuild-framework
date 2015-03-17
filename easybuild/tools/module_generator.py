# #
# Copyright 2009-2015 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
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

    def __init__(self, application, fake=False):
        """ModuleGenerator constructor."""
        self.app = application
        self.fake = fake
        self.tmpdir = None
        self.filename = None
        self.class_mod_file = None
        self.module_path = None
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

    def prepare(self, mod_symlink_paths):
        """
        Creates the absolute filename for the module.
        """
        mod_path_suffix = build_option('suffix_modules_path')
        full_mod_name = '%s%s' % (self.app.full_mod_name, self.MODULE_FILE_EXTENSION)
        # module file goes in general moduleclass category
        self.filename = os.path.join(self.module_path, mod_path_suffix, full_mod_name)
        # make symlink in moduleclass category
        self.class_mod_files = [os.path.join(self.module_path, p, full_mod_name) for p in mod_symlink_paths]

        # create directories and links
        for path in [os.path.dirname(x) for x in [self.filename] + self.class_mod_files]:
            mkdir(path, parents=True)

        # remove module file if it's there (it'll be recreated), see Application.make_module
        if os.path.exists(self.filename):
            os.remove(self.filename)

        return os.path.join(self.module_path, mod_path_suffix)

    def create_symlinks(self):
        """Create moduleclass symlink(s) to actual module file."""
        try:
            # remove symlink if its there (even if it's broken)
            for class_mod_file in self.class_mod_files:
                if os.path.lexists(class_mod_file):
                    os.remove(class_mod_file)
                os.symlink(self.filename, class_mod_file)
        except OSError, err:
            self.log.error("Failed to create symlinks from %s to %s: %s" % (self.class_mod_files, self.filename, err))

    def is_fake(self):
        """Return whether this ModuleGeneratorTcl instance generates fake modules or not."""
        return self.fake

    def set_fake(self, fake):
        """Determine whether this ModuleGeneratorTcl instance should generate fake modules."""
        self.log.debug("Updating fake for this ModuleGeneratorTcl instance to %s (was %s)" % (fake, self.fake))
        self.fake = fake
        # fake mode: set installpath to temporary dir
        if self.fake:
            self.tmpdir = tempfile.mkdtemp()
            self.log.debug("Fake mode: using %s (instead of %s)" % (self.tmpdir, self.module_path))
            self.module_path = self.tmpdir
        else:
            self.module_path = install_path('mod')

    def module_header(self):
        """Return module header string."""
        raise NotImplementedError

    def comment(self, msg):
        """Return string containing given message as a comment."""
        raise NotImplementedError


class ModuleGeneratorTcl(ModuleGenerator):
    """
    Class for generating Tcl module files.
    """
    MODULE_FILE_EXTENSION = ''  # no suffix for Tcl module files
    SYNTAX = 'Tcl'
    CHARS_TO_ESCAPE = ["$"]

    LOAD_REGEX = r"^\s*module\s+load\s+(\S+)"
    LOAD_TEMPLATE = "module load %(mod_name)s"

    def module_header(self):
        """Return module header string."""
        return "#%Module\n"

    def comment(self, msg):
        """Return string containing given message as a comment."""
        return "# %s\n" % msg

    def get_description(self, conflict=True):
        """
        Generate a description.
        """
        description = "%s - Homepage: %s" % (self.app.cfg['description'], self.app.cfg['homepage'])

        lines = [
            "",
            "proc ModulesHelp { } {",
            "    puts stderr {   %(description)s",
            "    }",
            "}",
            "",
            "module-whatis {Description: %(description)s}",
            "",
            "set root    %(installdir)s",
            "",
        ]

        if self.app.cfg['moduleloadnoconflict']:
            lines.extend([
                "if { ![is-loaded %(name)s/%(version)s] } {",
                "    if { [is-loaded %(name)s] } {",
                "        module unload %(name)s",
                "    }",
                "}",
                "",
            ])

        elif conflict:
            # conflict on 'name' part of module name (excluding version part at the end)
            # examples:
            # - 'conflict GCC' for 'GCC/4.8.3'
            # - 'conflict Core/GCC' for 'Core/GCC/4.8.2'
            # - 'conflict Compiler/GCC/4.8.2/OpenMPI' for 'Compiler/GCC/4.8.2/OpenMPI/1.6.4'
            lines.append("conflict %s\n" % os.path.dirname(self.app.short_mod_name))

        txt = self.module_header()
        txt += '\n'.join(lines) % {
            'name': self.app.name,
            'version': self.app.version,
            'description': description,
            'installdir': self.app.installdir,
        }

        return txt

    def load_module(self, mod_name):
        """
        Generate load statements for module.
        """
        if build_option('recursive_mod_unload'):
            # not wrapping the 'module load' with an is-loaded guard ensures recursive unloading;
            # when "module unload" is called on the module in which the depedency "module load" is present,
            # it will get translated to "module unload"
            load_statement = ["module load %(mod_name)s"]
        else:
            load_statement = [
                "if { ![is-loaded %(mod_name)s] } {",
                "    %s" % self.LOAD_TEMPLATE,
                "}",
            ]
        return '\n'.join([""] + load_statement + [""]) % {'mod_name': mod_name}

    def unload_module(self, mod_name):
        """
        Generate unload statements for module.
        """
        return '\n'.join([
            "",
            "if { [is-loaded %(mod_name)s] } {",
            "    module unload %(mod_name)s",
            "}",
            "",
        ]) % {'mod_name': mod_name}

    def prepend_paths(self, key, paths, allow_abs=False):
        """
        Generate prepend-path statements for the given list of paths.
        """
        template = "prepend-path\t%s\t\t%s\n"

        if isinstance(paths, basestring):
            self.log.debug("Wrapping %s into a list before using it to prepend path %s" % (paths, key))
            paths = [paths]


        for i, path in enumerate(paths):
            if os.path.isabs(path) and not allow_abs:
                self.log.error("Absolute path %s passed to prepend_paths which only expects relative paths." % path)
            elif not os.path.isabs(path):
                # prepend $root (= installdir) for relative paths
                paths[i]="$root/%s" % path


        statements = [template % (key, p) for p in paths]
        return ''.join(statements)


    def use(self, paths):
        """
        Generate module use statements for given list of module paths.
        """
        use_statements = []
        for path in paths:
            use_statements.append("module use %s" % path)
        return '\n'.join(use_statements)

    def set_environment(self, key, value):
        """
        Generate setenv statement for the given key/value pair.
        """
        # quotes are needed, to ensure smooth working of EBDEVEL* modulefiles
        return 'setenv\t%s\t\t%s\n' % (key, quote_str(value))
    
    def msg_on_load(self, msg):
        """
        Add a message that should be printed when loading the module.
        """
        # escape any (non-escaped) characters with special meaning by prefixing them with a backslash
        msg = re.sub(r'((?<!\\)[%s])'% ''.join(self.CHARS_TO_ESCAPE), r'\\\1', msg)
        return '\n'.join([
            "",
            "if [ module-info mode load ] {",
            '        puts stderr     "%s"' % msg,
            "}",
            "",
        ])
    
    def add_tcl_footer(self, tcltxt):
        """
        Append whatever Tcl code you want to your modulefile
        """
        return tcltxt

    def set_alias(self, key, value):
        """
        Generate set-alias statement in modulefile for the given key/value pair.
        """
        # quotes are needed, to ensure smooth working of EBDEVEL* modulefiles
        return 'set-alias\t%s\t\t%s\n' % (key, quote_str(value))


class ModuleGeneratorLua(ModuleGenerator):
    """
    Class for generating Lua module files.
    """
    MODULE_FILE_EXTENSION = '.lua'
    SYNTAX = 'Lua'
    CHARS_TO_ESCAPE = ["%"]

    LOAD_REGEX = r'^\s*load\("(\S+)"'
    LOAD_TEMPLATE = 'load("%(mod_name)s")'

    def __init__(self, *args, **kwargs):
        """ModuleGeneratorLua constructor."""
        super(ModuleGeneratorLua, self).__init__(*args, **kwargs)

    def module_header(self):
        """Return module header string."""
        return ''

    def comment(self, msg):
        """Return string containing given message as a comment."""
        return " -- %s\n" % msg

    def get_description(self, conflict=True):
        """
        Generate a description.
        """

        description = "%s - Homepage: %s" % (self.app.cfg['description'], self.app.cfg['homepage'])

        lines = [
            "local pkg = {}",
            "help = [["
            "%(description)s"
            "]]",
            "whatis([[Name: %(name)s]])",
            "whatis([[Version: %(version)s]])",
            "whatis([[Description: %(description)s]])",
            "whatis([[Homepage: %(homepage)s]])"
            "whatis([[License: N/A ]])",
            "",
            "",
            'pkg.root="%(installdir)s"',
            "",
            ]

        txt = '\n'.join(lines) % {
            'name': self.app.name,
            'version': self.app.version,
            'description': description,
            'installdir': self.app.installdir,
            'homepage': self.app.cfg['homepage'],
        }

        return txt

    def load_module(self, mod_name):
        """
        Generate load statements for module.
        """
        if build_option('recursive_mod_unload'):
            # not wrapping the 'module load' with an is-loaded guard ensures recursive unloading;
            # when "module unload" is called on the module in which the depedency "module load" is present,
            # it will get translated to "module unload"
            load_statement = [LOAD_TEMPLATE]
        else:
            load_statement = [
                'if ( not isloaded("%(mod_name)s")) then',
                '  %s' % LOAD_TEMPLATE,
                'end',
            ]
        return '\n'.join([""] + load_statement + [""]) % {'mod_name': mod_name}

    def unload_module(self, mod_name):
        """
        Generate unload statements for module.
        """
        return '\n'.join([
            "",
            "if (isloaded(%(mod_name)s)) then",
            "    unload(%(mod_name)s)",
            "end",
            "",
        ]) % {'mod_name': mod_name}

    def prepend_paths(self, key, paths, allow_abs=False):
        """
        Generate prepend-path statements for the given list of paths.
        """
        template = 'prepend_path(%s,%s)\n'

        if isinstance(paths, basestring):
            self.log.debug("Wrapping %s into a list before using it to prepend path %s" % (paths, key))
            paths = [paths]

        for i, path in enumerate(paths):
            if os.path.isabs(path) and not allow_abs:
                self.log.error("Absolute path %s passed to prepend_paths which only expects relative paths." % path)
            elif not os.path.isabs(path):
                # use pathJoin(pkg.root, path) for relative paths
                paths[i]=' pathJoin(pkg.root,"%s")' % path

        statements = [template % (quote_str(key), p) for p in paths]
        return ''.join(statements)

    def use(self, paths):
        """
        Generate module use statements for given list of module paths.
        @param paths: list of module path extensions to generate use statements for
        """
        return '\n'.join(['use("%s")' % p for p in paths] + [''])

    def set_environment(self, key, value):
        """
        Generate a quoted setenv statement for the given key/value pair.
        """
        # setting of $EBDEVELFOO modulefile path in Tcl case uses string
        # interpolation available in Tcl, but not in Lua. Ie
        # setenv("FOO","pkg.root/somevar") where pkg.root and somevar are
        # variables cant be used. 
        return 'setenv("%s", %s)\n' % (key, quote_str(value))

    def set_environment_unquoted(self, key, unquotedvalue):
        """ Generate an unquoted setenv statement for the given key/value pair.
        """
        return 'setenv("%s",%s)\n' % (key, unquotedvalue)

    def msg_on_load(self, msg):
        """
        Add a message that should be printed when loading the module.
        """
        pass

    def add_tcl_footer(self, tcltxt):
        raise NotImplementedError

    def add_lua_footer(self,luatxt):
        """
        Append whatever Lua code you want to your modulefile
        """
        return luatxt

    def set_alias(self, key, value):
        """
        Generate set-alias statement in modulefile for the given key/value pair.
        """
        # quotes are needed, to ensure smooth working of EBDEVEL* modulefiles
        return 'setalias(%s,"%s")\n' % (key, quote_str(value))

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
        tup = (module_syntax, available_mod_gens)
        _log.error("No module generator available for specified syntax '%s' (available: %s)" % tup)

    module_generator_class = available_mod_gens[module_syntax]
    return module_generator_class(app, fake=fake)


def module_load_regex(modfilepath):
    """
    Return the correct (compiled) regex to extract dependencies, depending on the module file type (Lua vs Tcl)
    """
    if modfilepath.endswith('.lua'):
        regex = ModuleGeneratorLua.LOAD_REGEX
    else:
        regex = ModuleGeneratorTcl.LOAD_REGEX
    return re.compile(regex, re.M)


def dependencies_for(mod_name, depth=sys.maxint):
    """
    Obtain a list of dependencies for the given module, determined recursively, up to a specified depth (optionally)
    @param depth: recursion depth (default is sys.maxint, which should be equivalent to infinite recursion depth)
    """
    mod_filepath = modules_tool().modulefile_path(mod_name)
    modtxt = read_file(mod_filepath)
    loadregex = module_load_regex(mod_filepath)
    mods = loadregex.findall(modtxt)

    if depth > 0:
        # recursively determine dependencies for these dependency modules, until depth is non-positive
        moddeps = [dependencies_for(mod, depth=depth - 1) for mod in mods]
    else:
        # ignore any deeper dependencies
        moddeps = []

    # add dependencies of dependency modules only if they're not there yet
    for moddepdeps in moddeps:
        for dep in moddepdeps:
            if not dep in mods:
                mods.append(dep)

    return mods
