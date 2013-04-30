"""
This describes the easyconfig format version 1.X

This is the original pure python code, to be exec'ed rather then parsed
"""
from distutils.version import LooseVersion

from easybuild.framework.easyconfig.format.format import EasyConfigFormat


class FormatOne(EasyConfigFormat):
    """Simple extension of FormatOne with configparser blocks
        Deprecates setting version and toolchain/toolchain version in FormatOne
    """
    VERSION = LooseVersion('1.0')
