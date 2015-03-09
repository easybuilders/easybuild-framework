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
import tempfile
from vsc.utils import fancylogger

from easybuild.framework.easyconfig.easyconfig import ActiveMNS
from easybuild.tools import config
from easybuild.tools.config import build_option
from easybuild.tools.filetools import mkdir
from easybuild.tools.module_naming_scheme.utilities import det_hidden_modname
from easybuild.tools.utilities import quote_str


_log = fancylogger.getLogger('module_generator', fname=False)


class ModuleGenerator(object):
    """
    Class for generating module files.
    """

    # chars we want to escape in the generated modulefiles
    CHARS_TO_ESCAPE = ["$"]

    def __init__(self, application, fake=False):
        self.app = application
        self.fake = fake
        self.tmpdir = None
        self.filename = None
        self.class_mod_file = None
        self.module_path = None

    def prepare(self):
        """
        Creates the absolute filename for the module.
        """
        mod_path_suffix = build_option('suffix_modules_path')
        full_mod_name = self.app.full_mod_name
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
            _log.error("Failed to create symlinks from %s to %s: %s" % (self.class_mod_files, self.filename, err))

    def get_description(self, conflict=True):
        """
        Generate a description.
        """
        description = "%s - Homepage: %s" % (self.app.cfg['description'], self.app.cfg['homepage'])

        lines = [
            "#%%Module",  # double % to escape string formatting!
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

        txt = '\n'.join(lines) % {
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
            _log.info("Wrapping %s into a list before using it to prepend path %s" % (paths, key))
            paths = [paths]

        # make sure only relative paths are passed
        for i in xrange(len(paths)):
            if os.path.isabs(paths[i]) and not allow_abs:
                _log.error("Absolute path %s passed to prepend_paths which only expects relative paths." % paths[i])
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

    def set_fake(self, fake):
        """Determine whether this ModuleGenerator instance should generate fake modules."""
        _log.debug("Updating fake for this ModuleGenerator instance to %s (was %s)" % (fake, self.fake))
        self.fake = fake
        # fake mode: set installpath to temporary dir
        if self.fake:
            self.tmpdir = tempfile.mkdtemp()
            _log.debug("Fake mode: using %s (instead of %s)" % (self.tmpdir, self.module_path))
            self.module_path = self.tmpdir
        else:
            self.module_path = config.install_path('mod')

    def is_fake(self):
        """Return whether this ModuleGenerator instance generates fake modules or not."""
        return self.fake
