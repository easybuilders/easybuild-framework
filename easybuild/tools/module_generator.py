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
@author: Fotis Georgatos (Uni.Lu)
"""
import glob
import os
import string
import sys
import tempfile
from vsc.utils import fancylogger
from vsc.utils.missing import get_subclasses

from easybuild.tools import config, module_naming_scheme
from easybuild.tools.filetools import mkdir
from easybuild.tools.module_naming_scheme import ModuleNamingScheme
from easybuild.tools.module_naming_scheme.easybuild_module_naming_scheme import EasyBuildModuleNamingScheme
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.utilities import import_available_modules, quote_str


_log = fancylogger.getLogger('module_generator', fname=False)

# general module class
GENERAL_CLASS = 'all'

# suffix for devel module filename
DEVEL_MODULE_SUFFIX = '-easybuild-devel'


class ModuleGenerator(object):
    """
    Class for generating module files.
    """
    def __init__(self, application, fake=False):
        self.app = application
        self.fake = fake
        self.filename = None
        self.tmpdir = None

    def create_files(self):
        """
        Creates the absolute filename for the module.
        """
        module_path = config.install_path('mod')

        # Fake mode: set installpath to temporary dir
        if self.fake:
            self.tmpdir = tempfile.mkdtemp()
            _log.debug("Fake mode: using %s (instead of %s)" % (self.tmpdir, module_path))
            module_path = self.tmpdir

        # Real file goes in 'all' category
        self.filename = os.path.join(module_path, GENERAL_CLASS, det_full_module_name(self.app.cfg))

        # Make symlink in moduleclass category
        classPathFile = os.path.join(module_path, self.app.cfg['moduleclass'], det_full_module_name(self.app.cfg))

        # Create directories and links
        for path in [os.path.dirname(x) for x in [self.filename, classPathFile]]:
            mkdir(path, parents=True)

        # Make a symlink from classpathFile to self.filename
        try:
            # remove symlink if its there (even if it's broken)
            if os.path.lexists(classPathFile):
                os.remove(classPathFile)
            # remove module file if it's there (it'll be recreated), see Application.make_module
            if os.path.exists(self.filename):
                os.remove(self.filename)
            os.symlink(self.filename, classPathFile)
        except OSError, err:
            _log.exception("Failed to create symlink from %s to %s: %s" % (classPathFile, self.filename, err))

        return os.path.join(module_path, GENERAL_CLASS)

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
            lines.append("conflict    %s\n" % self.app.name)

        txt = '\n'.join(lines) % {
            'name': self.app.name,
            'version': self.app.version,
            'description': description,
            'installdir': self.app.installdir,
        }

        return txt

    def load_module(self, mod_name, recursive_unload=False):
        """
        Generate load statements for module.
        """
        if recursive_unload:
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

    def set_environment(self, key, value):
        """
        Generate setenv statement for the given key/value pair.
        """
        # quotes are needed, to ensure smooth working of EBDEVEL* modulefiles
        return 'setenv\t%s\t\t%s\n' % (key, quote_str(value))

    def set_fake(self, fake):
        """Determine whether this ModuleGenerator instance should generate fake modules."""
        _log.debug("Updating fake for this ModuleGenerator instance to %s (was %s)" % (fake, self.fake))
        self.fake = fake

    def is_fake(self):
        """Return whether this ModuleGenerator instance generates fake modules or not."""
        return self.fake


def avail_module_naming_schemes():
    """
    Returns a list of available module naming schemes.
    """
    mns_attr = 'AVAIL_MODULE_NAMING_SCHEMES'
    if not hasattr(module_naming_scheme, mns_attr):
        # all subclasses of ModuleNamingScheme available in the easybuild.tools.module_naming_scheme namespace are eligible
        import_available_modules('easybuild.tools.module_naming_scheme')

        # construct name-to-class dict of available module naming scheme
        avail_mnss = dict([(x.__name__, x) for x in get_subclasses(ModuleNamingScheme)])

        # cache dict of available module naming scheme in module constant
        setattr(module_naming_scheme, mns_attr, avail_mnss)
        return avail_mnss
    else:
        return getattr(module_naming_scheme, mns_attr)


def get_custom_module_naming_scheme():
    """
    Get custom module naming scheme as specified in configuration.
    """
    avail_mnss = avail_module_naming_schemes()
    _log.debug("List of available module naming schemes: %s" % avail_mnss.keys())
    sel_mns = config.get_module_naming_scheme()
    if sel_mns in avail_mnss:
        return avail_mnss[sel_mns]()
    else:
        _log.error("Selected module naming scheme %s could not be found in %s" % (sel_mns, avail_mnss.keys()))


def is_valid_module_name(mod_name):
    """Check whether the specified value is a valid module name."""
    # module name must be a string
    if not isinstance(mod_name, basestring):
        _log.warning("Wrong type for module name %s (%s), should be a string" % (mod_name, type(mod_name)))
        return False
    # module name must be relative path
    elif mod_name.startswith(os.path.sep):
        _log.warning("Module name (%s) should be a relative file path" % mod_name)
        return False
    # module name should not be empty
    elif not len(mod_name) > 0:
        _log.warning("Module name (%s) should have length > 0." % mod_name)
        return False
    else:
        # check whether filename only contains printable characters
        # (except for carriage-control characters \r, \x0b and \xoc)
        invalid_chars = [x for x in mod_name if not x in string.printable[:-3]]
        if len(invalid_chars) > 0:
            _log.warning("Module name %s contains invalid characters: %s" % (mod_name, invalid_chars))
            return False
    _log.debug("Module name %s validated" % mod_name)
    return True


def det_full_module_name(ec, eb_ns=False):
    """
    Determine full module name by selected module naming scheme, based on supplied easyconfig.
    Returns a string representing the module name, e.g. 'GCC/4.6.3', 'Python/2.7.5-ictce-4.1.13',
    with the following requirements:
        - module name is specified as a relative path
        - string representing module name has length > 0
        - module name only contains printable characters (string.printable, except carriage-control chars)
    """
    _log.debug("Determining module name for %s (eb_ns: %s)" % (ec, eb_ns))
    if eb_ns:
        # return module name under EasyBuild module naming scheme
        mod_name = EasyBuildModuleNamingScheme().det_full_module_name(ec)
    else:
        mod_name = get_custom_module_naming_scheme().det_full_module_name(ec)

    if not is_valid_module_name(mod_name):
        _log.error("%s is not a valid module name" % str(mod_name))
    else:
        _log.debug("Obtained module name %s" % mod_name)

    return mod_name

def det_devel_module_filename(ec):
    """Determine devel module filename."""
    return det_full_module_name(ec).replace(os.path.sep, '-') + DEVEL_MODULE_SUFFIX
