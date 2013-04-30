"""
The main easyconfig format class
"""
from distutils.version import LooseVersion

from vsc import fancylogger


class EasyConfigFormat(object):
    """EasyConfigFormat class"""
    VERSION = LooseVersion('0.0')

    def __init__(self):
        """Initialise the EasyConfigFormat class"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        if not len(self.VERSION) == 2:
            self.log.error('Invalid version number %s' % (self.VERSION))

        self.text = None  # text version of the

        self.header = None  # the header
        self.docstring = None  # the docstring
        self.cfg = None  # configuration data
        self.versions = None  # supported versions
        self.toolchains = None  # suported toolchains/toolchain versions

    def verify(self):
        """Verify the format"""
        self._check_docstring()

    def check_docstring(self):
        """Verify docstring placeholder. Do nothing by default."""
        pass

    def parse(self, txt):
        """Parse the txt according to this format. This is higly version specific"""
        self.log.error('parse needs implementation')

    def text(self):
        """Create text according to this format. This is higly version specific"""
        self.log.error('text needs implementation')
