import os
import re

from easybuild.tools.module_naming_scheme import ModuleNamingScheme
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version

class ThematicMNS(ModuleNamingScheme):
    """Class implementing the thematic module naming scheme."""

    REQUIRED_KEYS = ['name', 'version', 'versionsuffix', 'toolchain', 'moduleclass']

    def det_full_module_name(self, ec):
        """
        Determine full module name from given easyconfig, according to the thematic module naming scheme.

        @param ec: dict-like object with easyconfig parameter values (e.g. 'name', 'version', etc.)

        @return: string representing full module name, e.g.: 'biology/ABySS/1.3.4-goolf-1.4.10'
        """
        
        return os.path.join(ec['moduleclass'], ec['name'], det_full_ec_version(ec))

# Maybe, can be usefull to still have the moduleclass when using module list (since it supports regex)
#    def det_short_module_name(self, ec):
#        """
#        Determine short module name, i.e. the name under which modules will be exposed to users.
#        Examples: GCC/4.8.3, OpenMPI/1.6.5, OpenBLAS/0.2.9, HPL/2.1, Python/2.7.5
#        """
#        return os.path.join(ec['name'], det_full_ec_version(ec))

    def is_short_modname_for(self, short_modname, name):
        """
        Determine whether the specified (short) module name is a module for software with the specified name.
        Default implementation checks via a strict regex pattern, and assumes short module names are of the form:
        <name>/<version>[-<toolchain>]
        """
        
        modname_regex = re.compile('^\S+/%s/\S+$' % re.escape(name))
        res = bool(modname_regex.match(short_modname))

        tup = (short_modname, name, modname_regex.pattern, res)
        self.log.debug("Checking whether '%s' is a module name for software with name '%s' via regex %s: %s" % tup)

        return res

