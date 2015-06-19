


"""
Default implementation of the EasyBuild packaging naming scheme

@author: Rob Schmidt (Ottawa Hospital Research Institute)
@author: Kenneth Hoste (Ghent University)
"""

from easybuild.tools.package.packaging_naming_scheme.pns import PackagingNamingScheme


class EasyBuildPNS(PackagingNamingScheme):
    """Class implmenting the default EasyBuild packaging naming scheme."""

    REQUIRED_KEYS = ['name', 'version', 'versionsuffix', 'toolchain']

    def name(self, ec):
        name_template = "eb-%(name)s-%(version)s-%(toolchain)s"
        pkg_name = name_template % {
            'toolchain' : self._toolchain(ec),
            'version': '-'.join([x for x in [ec.get('versionprefix', ''), ec['version'], ec['versionsuffix'].lstrip('-')] if x]),
            'name' : ec.name,
        }
        return pkg_name

    def _toolchain(self, ec):
        toolchain_template = "%(toolchain_name)s-%(toolchain_version)s"
        pkg_toolchain = toolchain_template % {
            'toolchain_name': ec.toolchain.name,
            'toolchain_version': ec.toolchain.version,
        }
        return pkg_toolchain


    def version(self, ec):
        return ec['version']

        

    def release(self):
        return 1

