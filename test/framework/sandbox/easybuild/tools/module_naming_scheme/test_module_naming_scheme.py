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
            return ('gnu', 'openmpi', ec['name'], ec['version'])
        elif ec['toolchain']['name'] == 'GCC':
            return ('gnu', ec['name'], ec['version'])
        elif ec['toolchain']['name'] == 'ictce':
            return ('intel', 'intelmpi', ec['name'], ec['version'])
        else:
            return (ec['name'], ec['version'])
