# #
# Copyright 2009-2013 Ghent University
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
import sys
import tempfile
from vsc import fancylogger
from vsc.utils.missing import get_subclasses

from easybuild.tools import config
from easybuild.tools.module_naming_scheme import ModuleNamingScheme
from easybuild.tools.utilities import quote_str


_log = fancylogger.getLogger('module_generator', fname=False)

# general module class
GENERAL_CLASS = 'all'


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
        self.filename = os.path.join(module_path, GENERAL_CLASS, *det_full_module_name(self.app.cfg))

        # Make symlink in moduleclass category
        classPathFile = os.path.join(module_path, self.app.cfg['moduleclass'], *det_full_module_name(self.app.cfg))

        # Create directories and links
        for directory in [os.path.dirname(x) for x in [self.filename, classPathFile]]:
            if not os.path.isdir(directory):
                try:
                    os.makedirs(directory)
                except OSError, err:
                    _log.exception("Couldn't make directory %s: %s" % (directory, err))

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

        txt = '\n'.join([
            "#%%Module",  # double % to escape!
            "",
            "proc ModulesHelp { } {",
            "    puts stderr {   %(description)s",
            "    }",
            "}",
            "",
            "module-whatis {%(description)s}",
            "",
            "set root    %(installdir)s",
            "",
        ]) % {'description': description, 'installdir': self.app.installdir}

        if self.app.cfg['moduleloadnoconflict']:
            txt += '\n'.join([
                "if { ![is-loaded %(name)s/%(version)s] } {",
                "    if { [is-loaded %(name)s] } {",
                "        module unload %(name)s",
                "    }",
                "}",
                "",
        ]) % {'name': self.app.name, 'version': self.app.version}

        elif conflict:
            txt += "\nconflict    %s\n" % self.app.name

        return txt

    def load_module(self, mod_name):
        """
        Generate load statements for module.
        """
        return '\n'.join([
            "",
            "if { ![is-loaded %(mod_name)s] } {",
            "    module load %(mod_name)s",
            "}",
            "",
        ]) % {'mod_name': mod_name}

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


def det_full_ec_version(ec):
    """
    Determine exact install version, based on supplied easyconfig.
    e.g. 1.2.3-goalf-1.1.0-no-OFED or 1.2.3 (for dummy toolchains)
    """

    ecver = None

    # determine main install version based on toolchain
    if ec['toolchain']['name'] == 'dummy':
        ecver = ec['version']
    else:
        ecver = "%s-%s-%s" % (ec['version'], ec['toolchain']['name'], ec['toolchain']['version'])

    # prepend/append version prefix/suffix
    ecver = ''.join([x for x in [ec.get('versionprefix', ''), ecver, ec['versionsuffix']] if x])

    return ecver


def avail_module_naming_schemes():
    """
    Returns a list of available module naming schemes.
    """
    # all subclasses of ModuleNamingScheme available in the easybuild.tools.module_naming_scheme namespace are eligible
    avail_mnss = {}
    for path in sys.path:
        for mod in glob.glob(os.path.join(path, 'easybuild', 'tools', 'module_naming_scheme', '*.py')):
            if not mod.endswith('__init__.py'):
                mns_name = mod.split(os.path.sep)[-1].split('.')[0]
                mns_path = "easybuild.tools.module_naming_scheme.%s" % mns_name
                _log.debug("importing module %s..." % mns_path)
                mns_mod = __import__(mns_path, globals(), locals(), [''])
                # add subclasses by imported module to also include classes in modules that were added dynamically
                # e.g. during unit testing
                avail_mnss.update(dict([(x.__name__, x) for x in get_subclasses(mns_mod.ModuleNamingScheme)]))
    return avail_mnss


def get_custom_module_naming_scheme():
    """
    Get custom module naming scheme as specified in configuration.
    """
    avail_mnss = avail_module_naming_schemes()
    _log.debug("List of available module naming schemes: %s" % avail_mnss.keys())
    module_naming_scheme = config.get_module_naming_scheme()
    if module_naming_scheme in avail_mnss:
        return avail_mnss[module_naming_scheme]()
    else:
        _log.error("Custom module naming scheme %s could not be found!" % module_naming_scheme)


def det_full_module_name(ec):
    """
    Determine full module name by selected module naming scheme, based on supplied easyconfig.
    Returns a tuple with the module name parts, e.g. ('GCC', '4.6.3'), ('Python', '2.7.5-ictce-4.1.13')

    If a KeyError occurs when determining the module name, e.g. because the information supplied for dependencies
    is insufficient, an attempt is made to locate and parse an easyconfig file, and do another attempt.
    """
    try:
        return get_custom_module_naming_scheme().det_full_module_name(ec)
    except KeyError, err:
        _log.debug("KeyError occured (%s), will attempt to find a matching easyconfig file and retry." % err)
        _log.error("BOOM! Not implemented yet.")
