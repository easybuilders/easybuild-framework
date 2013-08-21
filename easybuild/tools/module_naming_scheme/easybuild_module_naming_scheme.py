from easybuild.tools.module_generator import det_full_ec_version
from easybuild.tools.module_naming_scheme import ModuleNamingScheme


class EasyBuildModuleNamingScheme(ModuleNamingScheme):
    """Class implementing the default EasyBuild module naming scheme."""

    def det_full_module_name(self, ec):
        """
        Determine full module name from given easyconfig, according to the EasyBuild module naming scheme.

        @param ec: dict-like object with easyconfig parameter values (e.g. 'name', 'version', etc.)

        @return: two-element tuple with full module name (<name>, <installversion>), e.g.: ('gzip', '1.5-goolf-1.4.10')
        """
        return (ec['name'], det_full_ec_version(ec))
