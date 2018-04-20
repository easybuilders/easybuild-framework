from vsc.utils import fancylogger

from easybuild.tools.config import build_option
from easybuild.tools.config import CONT_TYPE_SINGULARITY, CONT_TYPE_DOCKER
from easybuild.tools.build_log import EasyBuildError
from .singularity import singularity as singularity_containerize
from .docker import docker_containerize

_log = fancylogger.getLogger('tools.containers')  # pylint: disable=C0103


def containerize(easyconfigs, eb_go=None):
    """
    Generate container recipe + (optionally) image
    """
    _log.experimental("support for generating container recipes and images (--containerize/-C)")

    container_type = build_option('container_type')
    if container_type == CONT_TYPE_SINGULARITY:
        singularity_containerize(easyconfigs)
    elif container_type == CONT_TYPE_DOCKER:
        docker_containerize(easyconfigs, eb_go)
    else:
        raise EasyBuildError("Unknown container type specified: %s", container_type)
