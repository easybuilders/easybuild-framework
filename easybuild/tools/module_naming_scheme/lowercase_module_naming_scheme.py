import os
import re

from easybuild.tools.module_naming_scheme.mns import ModuleNamingScheme
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version

class LowercaseModuleNamingScheme(ModuleNamingScheme):
    """Class implementing a lowercase module naming scheme."""

    REQUIRED_KEYS = ['name', 'version', 'versionsuffix', 'toolchain']

    def det_full_module_name(self, ec):
        """
        Determine full module name from given easyconfig, according to the EasyBuild module naming scheme.
        :param ec: dict-like object with easyconfig parameter values (e.g. 'name', 'version', etc.)
        :return: string with full module name <name>/<installversion>, e.g.: 'gzip/1.5-goolf-1.4.10'
        """
        return os.path.join(ec['name'], det_full_ec_version(ec)).lower()

    def is_short_modname_for(self, short_modname, name):
        """
        Determine whether the specified (short) module name is a module for software with the specified name.
        Default implementation checks via a strict regex pattern, and assumes short module names are of the form:
            <name>/<version>[-<toolchain>]
        """
        modname_regex = re.compile('^%s(/\S+)?$' % re.escape(name.lower()))
        res = bool(modname_regex.match(short_modname))

        self.log.debug("Checking whether '%s' is a module name for software with name '%s' via regex %s: %s",
                       short_modname, name, modname_regex.pattern, res)

        return res
