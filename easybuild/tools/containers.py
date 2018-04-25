# Copyright 2017-2018 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# https://github.com/easybuilders/easybuild
#
# EasyBuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
#
"""
Support for generating container recipes and creating container images

:author: Shahzeb Siddiqui (Pfizer)
:author: Kenneth Hoste (HPC-UGent)
"""
import os
from distutils.version import LooseVersion
from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import CONT_IMAGE_FORMAT_EXT3, CONT_IMAGE_FORMAT_SANDBOX, CONT_IMAGE_FORMAT_SQUASHFS
from easybuild.tools.config import CONT_TYPE_SINGULARITY
from easybuild.tools.config import build_option, container_path
from easybuild.tools.filetools import mkdir, remove_file, which, write_file
from easybuild.tools.run import run_cmd


DOCKER = 'docker'
LOCALIMAGE = 'localimage'
SHUB = 'shub'
SINGULARITY_BOOTSTRAP_TYPES = [DOCKER, LOCALIMAGE, SHUB]


SINGULARITY_TEMPLATE = """
Bootstrap: %(bootstrap)s
From: %(from)s

%%post
%(install_os_deps)s

# upgrade easybuild package automatically to latest version
pip install -U easybuild

# change to 'easybuild' user
su - easybuild

eb %(easyconfigs)s --robot --installpath=/app/ --prefix=/scratch --tmpdir=/scratch/tmp

# exit from 'easybuild' user
exit

# cleanup
rm -rf /scratch/tmp/* /scratch/build /scratch/sources /scratch/ebfiles_repo

%%runscript
eval "$@"

%%environment
source /etc/profile
module use /app/modules/all
module load %(mod_names)s

%%labels

"""


_log = fancylogger.getLogger('tools.containers')  # pylint: disable=C0103


def parse_container_base(base):
    """Parse value passed to --container-base option."""
    if base:
        base_specs = base.split(':')
        if len(base_specs) > 3 or len(base_specs) <= 1:
            error_msg = '\n'.join([
                "Invalid format for --container-base, must be one of the following:",
                '',
                "--container-base localimage:/path/to/image",
                "--container-base shub:<image>:<tag>",
                "--container-base docker:<image>:<tag>",
            ])
            raise EasyBuildError(error_msg)
    else:
        raise EasyBuildError("--container-base must be specified")

    # first argument to --container-base is the Singularity bootstrap agent (localimage, shub, docker)
    bootstrap_agent = base_specs[0]

    # check bootstrap type value and ensure it is localimage, shub, docker
    if bootstrap_agent not in SINGULARITY_BOOTSTRAP_TYPES:
        known_bootstrap_agents = ', '.join(SINGULARITY_BOOTSTRAP_TYPES)
        raise EasyBuildError("Bootstrap agent in container base spec must be one of: %s" % known_bootstrap_agents)

    res = {'bootstrap_agent': bootstrap_agent}

    for idx, base_spec in enumerate(base_specs[1:]):
        res.update({'arg%d' % (idx + 1): base_spec})

    return res


def generate_singularity_recipe(easyconfigs, container_base):
    """Main function to Singularity definition file and image."""

    cont_path = container_path()

    # make sure location to write container recipes & images exists
    mkdir(cont_path, parents=True)

    base_specs = parse_container_base(container_base)

    # extracting application name,version, version suffix, toolchain name, toolchain version from
    # easyconfig class

    bootstrap_agent = base_specs['bootstrap_agent']

    base_image, base_image_tag = None, None

    # with localimage it only takes 2 arguments. --container-base localimage:/path/to/image
    # checking if path to image is valid and verify image extension is '.img' or '.simg'
    if base_specs['bootstrap_agent'] == LOCALIMAGE:
        base_image = base_specs['arg1']
        if os.path.exists(base_image):
            # get the extension of container image
            image_ext = os.path.splitext(base_image)[1]
            if image_ext == '.img' or image_ext == '.simg':
                _log.debug("Extension for base container image to use is OK: %s", image_ext)
            else:
                raise EasyBuildError("Invalid image extension '%s' must be .img or .simg", image_ext)
        else:
            raise EasyBuildError("Singularity base image at specified path does not exist: %s", base_image)

    # otherwise, bootstrap agent is 'docker' or 'shub'
    # format --container-base {docker|shub}:<image>:<tag>
    else:
        base_image = base_specs['arg1']
        # image tag is optional
        base_image_tag = base_specs.get('arg2', None)

    bootstrap_from = base_image
    if base_image_tag:
        bootstrap_from += ':' + base_image_tag

    # if there is osdependencies in easyconfig then add them to Singularity recipe
    install_os_deps = ''
    for ec in easyconfigs:
        for osdep in ec['ec']['osdependencies']:
            if isinstance(osdep, basestring):
                install_os_deps += "yum install -y %s\n" % osdep
            # tuple entry indicates multiple options
            elif isinstance(osdep, tuple):
                install_os_deps += "yum --skip-broken -y install %s\n" % ' '.join(osdep)
            else:
                raise EasyBuildError("Unknown format of OS dependency specification encountered: %s", osdep)

    # module names to load in container environment
    mod_names = [e['ec'].full_mod_name for e in easyconfigs]

    # name of Singularity definition file
    img_name = build_option('container_image_name')
    if img_name:
        def_file_label = os.path.splitext(img_name)[0]
    else:
        def_file_label = mod_names[0].replace('/', '-')

    def_file = 'Singularity.%s' % def_file_label

    # adding all the regions for writing the  Singularity definition file
    content = SINGULARITY_TEMPLATE % {
        'bootstrap': bootstrap_agent,
        'from': bootstrap_from,
        'install_os_deps': install_os_deps,
        'easyconfigs': ' '.join(os.path.basename(e['spec']) for e in easyconfigs),
        'mod_names': ' '.join(mod_names),
    }
    def_path = os.path.join(cont_path, def_file)

    if os.path.exists(def_path):
        if build_option('force'):
            print_msg("WARNING: overwriting existing container recipe at %s due to --force" % def_path)
        else:
            raise EasyBuildError("Container recipe at %s already exists, not overwriting it without --force", def_path)

    write_file(def_path, content)
    print_msg("Singularity definition file created at %s" % def_path, log=_log)

    return def_path


def build_singularity_image(def_path):
    """Build Singularity container image by calling out to 'singularity' (requires admin privileges!)."""

    cont_path = container_path()
    def_file = os.path.basename(def_path)

    # use --imagename if specified, otherwise derive based on filename of recipe
    img_name = build_option('container_image_name')
    if img_name is None:
        # definition file Singularity.<app>-<version, container name <app>-<version>.<img|simg>
        img_name = def_file.split('.', 1)[1]

    cmd_opts = ''

    image_format = build_option('container_image_format')

    # squashfs image format (default for Singularity)
    if image_format in [None, CONT_IMAGE_FORMAT_SQUASHFS]:
        img_path = os.path.join(cont_path, img_name + '.simg')

    # ext3 image format, creating as writable container
    elif image_format == CONT_IMAGE_FORMAT_EXT3:
        img_path = os.path.join(cont_path, img_name + '.img')
        cmd_opts = '--writable'

    # sandbox image format, creates as a directory but acts like a container
    elif image_format == CONT_IMAGE_FORMAT_SANDBOX:
        img_path = os.path.join(cont_path, img_name)
        cmd_opts = '--sandbox'

    else:
        raise EasyBuildError("Unknown container image format specified for Singularity: %s" % image_format)

    if os.path.exists(img_path):
        if build_option('force'):
            print_msg("WARNING: overwriting existing container image at %s due to --force" % img_path)
            remove_file(img_path)
        else:
            raise EasyBuildError("Container image already exists at %s, not overwriting it without --force", img_path)

    # resolve full path to 'singularity' binary, since it may not be available via $PATH under sudo...
    singularity = which('singularity')
    cmd_env = ''

    singularity_tmpdir = build_option('container_tmpdir')
    if singularity_tmpdir:
        cmd_env += 'SINGULARITY_TMPDIR=%s' % singularity_tmpdir

    cmd = ' '.join(['sudo', cmd_env, singularity, 'build', cmd_opts, img_path, def_path])
    print_msg("Running '%s', you may need to enter your 'sudo' password..." % cmd)
    run_cmd(cmd, stream_output=True)
    print_msg("Singularity image created at %s" % img_path, log=_log)


def check_singularity():
    """Check whether Singularity can be used (if it's needed)."""
    # if we're going to build a container image, we'll need a sufficiently recent version of Singularity available
    # (and otherwise we don't really care if Singularity is not available)

    if build_option('container_build_image'):
        path_to_singularity_cmd = which('singularity')
        if path_to_singularity_cmd:
            print_msg("Singularity tool found at %s" % path_to_singularity_cmd)
            out, ec = run_cmd("singularity --version", simple=False, trace=False, force_in_dry_run=True)
            if ec:
                raise EasyBuildError("Failed to determine Singularity version: %s" % out)
            else:
                # singularity version format for 2.3.1 and higher is x.y-dist
                singularity_version = out.strip().split('-')[0]

            if LooseVersion(singularity_version) < LooseVersion('2.4'):
                raise EasyBuildError("Please upgrade singularity instance to version 2.4 or higher")
            else:
                print_msg("Singularity version '%s' is 2.4 or higher ... OK" % singularity_version)
        else:
            raise EasyBuildError("Singularity not found in your system")


def singularity(easyconfigs, container_base=None):
    """
    Create Singularity definition file and (optionally) image
    """
    check_singularity()

    if container_base is None:
        container_base = build_option('container_base')

    def_path = generate_singularity_recipe(easyconfigs, container_base)

    # also build container image, if requested (requires sudo!)
    if build_option('container_build_image'):
        build_singularity_image(def_path)


def containerize(easyconfigs):
    """
    Generate container recipe + (optionally) image
    """
    _log.experimental("support for generating container recipes and images (--containerize/-C)")

    container_type = build_option('container_type')
    if container_type == CONT_TYPE_SINGULARITY:
        singularity(easyconfigs)
    else:
        raise EasyBuildError("Unknown container type specified: %s", container_type)
