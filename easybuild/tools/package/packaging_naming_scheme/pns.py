
from vsc.utils import fancylogger

options = [ "package-naming-name-template", "package-naming-version-template", "package-naming-toolchain-template" ]

class PackagingNamingScheme(object):
    """Abstract class for package naming scheme"""


    def __init__(self, *args, **kwargs):
        """initialize logger."""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

    def name(self):
        """Return name of the package, by default would include name, version, toolchain"""

        
    def version(self):
        """The version in the version part of the package"""

    def release(self):
        """Just the release"""
        return 1


