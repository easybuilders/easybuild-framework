"""
This describes the easyconfig format versions 2.X

This is a mix between version 1 and configparser-style configuration
"""

from distutils.version import LooseVersion

from easybuild.framework.easyconfig.format.format import EasyConfigFormat


class FormatTwoZero(EasyConfigFormat):
    """Simple extension of FormatOne with configparser blocks
        Deprecates setting version and toolchain/toolchain version in FormatOne
    """
    VERSION = LooseVersion('2.0')

    def check_docstring(self):
        """Verify docstring"""
        # TODO check for @author and/or @maintainer
