

from vsc.utils import fancylogger
from vsc.utils.missing import get_subclasses
from vsc.utils.patterns import Singleton
from easybuild.tools.config import get_package_naming_scheme
from easybuild.tools.build_log import EasyBuildError, print_error, print_msg
from easybuild.tools.package.packaging_naming_scheme.pns import PackagingNamingScheme
from easybuild.tools.utilities import import_available_modules

def avail_package_naming_scheme():
    '''
    Returns the list of valed naming schemes that are in the easybuild.package.package_naming_scheme namespace
    '''
    import_available_modules('easybuild.tools.package.packaging_naming_scheme')

    class_dict = dict([(x.__name__, x) for x in get_subclasses(PackagingNamingScheme)])

    return class_dict

class ActivePNS(object):
    """
    The wrapper class for Package Naming Schmese, follows the model of Module Naming Schemes, mostly
    """
    
    __metaclass__ = Singleton
    
    def __init__(self, *args, **kwargs):
        """Initialize logger and find available PNSes to load"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        avail_pns = avail_package_naming_scheme()
        sel_pns = get_package_naming_scheme()
        if sel_pns in avail_pns:
            self.pns = avail_pns[sel_pns]()
        else:
            raise EasyBuildError("Selected package naming scheme %s could not be found in %s",
                                    sel_pns, avail_pns.keys())

    def name(self, ec):
        name = self.pns.name(ec)
        return name

    def version(self, ec):
        version = self.pns.version(ec)
        return version

    def release(self, ec):
        release = self.pns.release()
        return release
