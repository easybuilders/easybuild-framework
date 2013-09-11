import os

from easybuild.tools.module_naming_scheme import ModuleNamingScheme


class TestModuleNamingScheme(ModuleNamingScheme):
    """Class implementing a simple module naming scheme for testing purposes."""

    def det_full_module_name(self, ec):
        """
        Determine full module name from given easyconfig, according to a simple testing module naming scheme.

        @param ec: dict-like object with easyconfig parameter values (e.g. 'name', 'version', etc.)

        @return: n-element tuple with full module name, e.g.: ('gzip', '1.5'), ('intel', 'intelmpi', 'gzip', '1.5')
        """
        if ec['toolchain']['name'] == 'goolf':
            mod_name = os.path.join('gnu', 'openmpi', ec['name'], ec['version'])
        elif ec['toolchain']['name'] == 'GCC':
            mod_name = os.path.join('gnu', ec['name'], ec['version'])
        elif ec['toolchain']['name'] == 'ictce':
            mod_name = os.path.join('intel', 'intelmpi', ec['name'], ec['version'])
        else:
            mod_name = os.path.join(ec['name'], ec['version'])
        return mod_name
