"""A module to setup and use an ld wrapper to support RPATH"""

import os
import copy
import shutil
import stat
import tempfile
from vsc.utils import fancylogger
from easybuild.tools.filetools import adjust_permissions

_log = fancylogger.getLogger('tools.package')

orig_os_environ = copy.deepcopy(os.environ)
# RPATH is linux only
ld_wrapper_script_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "ld_wrapper.sh"))

DEBUG = True


def prepare_ld_wrapper():
    """
    Copy wrapper from framework for each iteration, a bit expensive, but might give flexibility
    """
    _log.debug("rpath: preparing ld wrapper script")
    wrapper_dir = tempfile.mkdtemp(prefix='eb-ldwrapper-')
    # copy wrapper script from framework
    wrapper_ld = os.path.join(wrapper_dir, "ld")
    wrapper_ld_gold = os.path.join(wrapper_dir, "ld.gold")
    shutil.copy(ld_wrapper_script_loc, wrapper_ld)
    shutil.copy(ld_wrapper_script_loc, wrapper_ld_gold)
    adjust_permissions(wrapper_ld, stat.S_IXUSR, add=True)
    adjust_permissions(wrapper_ld_gold, stat.S_IXUSR, add=True)

    # put wrapper script in PATH
    os.environ['PATH'] = os.pathsep.join([wrapper_dir] +
                                         [x for x in os.environ.get('PATH', '').split(os.pathsep) if len(x) > 0])

    os.environ['EB_LD_FLAG'] = "1"
    if DEBUG:
        os.environ['EB_LD_VERBOSE'] = 'true'


def teardown_ld_wrapper():
    """
    Return environment
    """
    os.environ = copy.deepcopy(orig_os_environ)


def check_rpath_support():
    """
    If there are any special checks we need to do to make sure this will work they should
    go here. Incuding whether experimental enabled to begin with.
    """

    _log.experimental("Support for setting RPATH for dependencies.")
