


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
            'toolchain' : self.toolchain(ec),
            'version': '-'.join([x for x in [ec.get('versionprefix', ''), ec['version'], ec['versionsuffix'].lstrip('-')] if x]),
            'name' : eb.name,
    }

    def _toolchain(self, eb):
        toolchain_template = "%(toolchain_name)s-%(toolchain_version)s"
        pkg_toolchain = toolchain_template % {
            'toolchain_name': eb.toolchain.name,
            'toolchain_version': eb.toolchain.version,
        }


    def version(self, eb):
        return eb.cfg['version']

        

    def release(self):
        return 1

