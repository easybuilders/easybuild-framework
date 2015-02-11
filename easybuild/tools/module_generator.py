# #
# Copyright 2009-2014 Ghent University
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
import tempfile
from vsc.utils import fancylogger
from vsc.utils.missing import get_subclasses

from easybuild.framework.easyconfig.easyconfig import ActiveMNS
from easybuild.tools import config
from easybuild.tools.config import build_option, get_module_syntax
from easybuild.tools.filetools import mkdir
from easybuild.tools.modules import Lmod, modules_tool
from easybuild.tools.utilities import quote_str


MODULE_GENERATOR_CLASS_PREFIX = 'ModuleGenerator'


_log = fancylogger.getLogger('module_generator', fname=False)


class ModuleGenerator(object):
    """
    Class for generating module files.
    """

    # chars we want to escape in the generated modulefiles
    CHARS_TO_ESCAPE = ["$"]
    MODULE_SUFFIX = ''

    def __init__(self, application, fake=False):
        """ModuleGenerator constructor."""
        self.app = application
        self.fake = fake
        self.tmpdir = None
        self.filename = None
        self.class_mod_file = None
        self.module_path = None
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

    def prepare(self):
        """
        Creates the absolute filename for the module.
        """
        mod_path_suffix = build_option('suffix_modules_path')
        full_mod_name = '%s%s' % (self.app.full_mod_name, self.MODULE_SUFFIX)
        # module file goes in general moduleclass category
        self.filename = os.path.join(self.module_path, mod_path_suffix, full_mod_name)
        # make symlink in moduleclass category
        mod_symlink_paths = ActiveMNS().det_module_symlink_paths(self.app.cfg)
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
            self.module_path = config.install_path('mod')

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
                "    module load %(mod_name)s",
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
            self.log.info("Wrapping %s into a list before using it to prepend path %s" % (paths, key))
            paths = [paths]

        # make sure only relative paths are passed
        for i in xrange(len(paths)):
            if os.path.isabs(paths[i]) and not allow_abs:
                self.log.error("Absolute path %s passed to prepend_paths which only expects relative paths." % paths[i])
            elif not os.path.isabs(paths[i]):
                # prepend $root (= installdir) for relative paths
                paths[i] = "$root/%s" % paths[i]

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
        # nothing to do here, but this should fail in the context of generating Lua modules
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

    MODULE_SUFFIX = '.lua'

    def __init__(self, *args, **kwargs):
        """ModuleGeneratorLua constructor."""
        super(ModuleGeneratorLua, self).__init__(*args, **kwargs)

        # make sure Lmod is being used as a modules tool
        if not isinstance(modules_tool(), Lmod):
            self.log.error("Only Lmod can be used as modules tool when generating module files in Lua syntax.")

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
            "whatis([[Keywords: Not set]])",
            "",
            "",
            'pkg.root="%(installdir)s"',
            "",
            ]

        #@todo check if this is really needed, imho Lmod doesnt need this at all.
        if self.app.cfg['moduleloadnoconflict']:
            lines.extend([
             'if ( not isloaded("%(name)s/%(version)s")) then',
             '  load("%(name)s/%(version)s")',
             'end',
             ])

        elif conflict:
            # conflicts are not needed in lua module files, as Lmod's one name
            # rule and automatic swapping.
            pass

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
            load_statement = ['load("%(mod_name)s")']
        else:
            load_statement = [
                'if ( not isloaded("%(mod_name)s")) then',
                '  load("%(mod_name)s")',
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
            self.log.info("Wrapping %s into a list before using it to prepend path %s" % (paths, key))
            paths = [paths]

        # make sure only relative paths are passed
        for i in xrange(len(paths)):
            if os.path.isabs(paths[i]) and not allow_abs:
                self.log.error("Absolute path %s passed to prepend_paths which only expects relative paths." % paths[i])
            elif not os.path.isabs(paths[i]):
                # prepend $root (= installdir) for relative paths
                paths[i] = ' pathJoin(pkg.root,"%s")' % paths[i]

        statements = [template % (quote_str(key), p) for p in paths]
        return ''.join(statements)

    def use(self, paths):
        """
        Generate module use statements for given list of module paths.
        """
        use_statements = []
        for path in paths:
            use_statements.append('use("%s")' % path)
        return '\n'.join(use_statements)


    def set_environment(self, key, value):

        """
        Generate setenv statement for the given key/value pair.
        """
        # quotes are needed, to ensure smooth working of EBDEVEL* modulefiles
        return 'setenv("%s", %s)\n' % (key, quote_str(value))


    def msg_on_load(self, msg):
        """
        Add a message that should be printed when loading the module.
        """
        pass


    def add_tcl_footer(self, tcltxt):
        """
        Append whatever Tcl code you want to your modulefile
        """
    #@todo to pass or not to pass? this should fail in the context of generating Lua modules
        pass


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
    class_dict = {}
    for klass in get_subclasses(ModuleGenerator):
        class_name = klass.__name__
        if class_name.startswith(MODULE_GENERATOR_CLASS_PREFIX):
            syntax = class_name[len(MODULE_GENERATOR_CLASS_PREFIX):]
            class_dict.update({syntax: klass})
        else:
            tup = (MODULE_GENERATOR_CLASS_PREFIX, class_name)
            _log.error("Invalid name for ModuleGenerator subclass, should start with %s: %s" % tup)
    return class_dict


def module_generator(app, fake=False):
    """
    Return interface to modules tool (environment modules (C, Tcl), or Lmod)
    """
    module_syntax = get_module_syntax()
    module_generator_class = avail_module_generators().get(module_syntax)
    return module_generator_class(app, fake=fake)

def return_module_loadregex(modname):
    """
    Return the right regex depending on the module file type (Lua vs Tcl) in order for 
    to be able to figure out dependencies.
    """
    if (modules_tool().modulefile_path(modname).endswith('.lua')):
        loadregex = re.compile(r"^\s*load\(\"(\S+)\"", re.M)
    else:   `
        loadregex = re.compile(r"^\s*module\s+load\s+(\S+)", re.M)
    return loadregex

