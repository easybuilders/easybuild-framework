# Copyright 2014-2017 Ghent University
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
Support for generating Singularity definition files and creating Singularity images

:author: Shahzeb Siddiqui (Pfizer)
:author: Kenneth Hoste (HPC-UGent)
"""
import os
from distutils.version import LooseVersion
from vsc.utils import fancylogger

from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import CONT_IMAGE_FORMAT_EXT3, CONT_IMAGE_FORMAT_SANDBOX, CONT_IMAGE_FORMAT_SQUASHFS
from easybuild.tools.config import build_option, container_path, get_module_naming_scheme
from easybuild.tools.filetools import change_dir, which, write_file
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.run import run_cmd


CONT_TYPE_DOCKER = 'docker'
CONT_TYPE_SINGULARITY = 'singularity'

DOCKER = 'docker'
LOCALIMAGE = 'localimage'
SHUB = 'shub'
SINGULARITY_BOOTSTRAP_TYPES = [DOCKER, LOCALIMAGE, SHUB]


_log = fancylogger.getLogger('tools.containers')  # pylint: disable=C0103


def parse_container_base(base):
    """Sanity check for value passed to --container-base option."""
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
        res.update({'arg%d' % (idx + 1): base_specs[idx + 1]})

    return res


def generate_singularity_recipe(ordered_ecs, container_base):
    """Main function to Singularity definition file and image."""

    cont_path = container_path()

    # check if --containerpath is valid path and a directory
    if os.path.isdir(cont_path):
        _log.info("Path for container recipes & images: %s", cont_path)
    else:
        raise EasyBuildError("Location for container recipes & images is a non-existing directory: %s" % cont_path)

    base_specs = parse_container_base(container_base)

    # extracting application name,version, version suffix, toolchain name, toolchain version from
    # easyconfig class

    bootstrap_agent = base_specs['bootstrap_agent']

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

    # bootstrap from local image
    if bootstrap_agent == LOCALIMAGE:
        bootstrap_content = 'Bootstrap: ' + bootstrap_agent + '\n'
        bootstrap_content += 'From: ' + base_image + '\n'
    # default bootstrap is shub or docker
    else:
        bootstrap_content = 'BootStrap: ' + bootstrap_agent + '\n'
        if base_image_tag is None:
            bootstrap_content += 'From: ' + base_image  + '\n'
        else:
            bootstrap_content += 'From: ' + base_image + ':' + base_image_tag + '\n'

    post_content = '\n%post\n'

    # if there is osdependencies in easyconfig then add them to Singularity recipe
    osdeps = ordered_ecs[0]['ec']['osdependencies']
    if len(osdeps) > 0:
        # format: osdependencies = ['libibverbs-dev', 'libibverbs-devel', 'rdma-core-devel']
        if isinstance(osdeps[0], basestring):
            for os_package in osdeps:
                post_content += "yum install -y " + os_package + " || true \n"
        # format: osdependencies = [('libibverbs-dev', 'libibverbs-devel', 'rdma-core-devel')]
        else:
            for os_package in osdeps[0]:
                post_content += "yum install -y " + os_package + " || true \n"

   # upgrade easybuild package automatically in all Singularity builds
    post_content += "pip install -U easybuild \n"
    post_content += "su - easybuild \n"

    environment_content = '\n'.join([
        "%environment",
        "source /etc/profile",
    ])

    modulepath = '/app/modules/all'
    eb_name = ordered_ecs[0]['ec'].name
    eb_full_ver = det_full_ec_version(ordered_ecs[0]['ec'])

    # name of easyconfig to build
    easyconfig  = '%s-%s.eb' % (eb_name, eb_full_ver)
    # name of Singularity defintiion file
    def_file  = "Singularity.%s-%s" % (eb_name, eb_full_ver)

    ebfile = os.path.splitext(easyconfig)[0] + '.eb'
    post_content += "eb " + ebfile  + " --robot --installpath=/app/ --prefix=/scratch --tmpdir=/scratch/tmp\n"

    environment_content += "module use " +  modulepath + '\n'
    environment_content += "module load " + os.path.join(eb_name, eb_full_ver) + '\n'

    # cleaning up directories in container after build
    post_content += '\n'.join([
        'exit',
        "rm -rf /scratch/tmp/* /scratch/build /scratch/sources /scratch/ebfiles_repo",
    ])

    runscript_content = '\n'.join([
        "%runscript",
        'eval "$@"',
    ])

    label_content = "\n%labels \n"

    # adding all the regions for writing the  Singularity definition file
    content = bootstrap_content + post_content + runscript_content + environment_content + label_content
    def_path = os.path.join(cont_path, def_file)

    if os.path.exists(def_path) and not build_option('force'):
        raise EasyBuildError("%s already exists, not overwriting it without --force", def_path)

    write_file(def_path, content)

    print_msg("Singularity definition file created at %s" % def_path, log=_log)

    # also build container image, if requested (requires sudo!)
    if build_option('container_build_image'):

        # use --imagename if specified, otherwise derive based on filename of recipe
        cont_img = build_option('container_image_name')
        if cont_img is None:
            # definition file Singularity.<app>-<version, container name <app>-<version>.<img|simg>
            dot_idx = def_file.find('.')
            cont_img = def_file[dot_idx+1:]

        cont_img_cmd_opts = ''

        image_format = build_option('container_image_format')

        # squashfs image format (default for Singularity)
        if image_format in [None, CONT_IMAGE_FORMAT_SQUASHFS]:
            cont_img_path = os.path.join(cont_path, cont_img + '.simg')

        # ext3 image format, creating as writable container
        elif image_format == CONT_IMAGE_FORMAT_EXT3:
            cont_img_path = os.path.join(cont_path, cont_img + '.img')
            cont_img_cmd_opts = '--writeable'

        # sandbox image format, creates as a directory but acts like a container
        elif image_format == CONT_IMAGE_FORMAT_SANDBOX:
            cont_img_path = os.path.join(cont_path, cont_img)

        else:
            raise EasyBuildError("Unknown container image format specified for Singularity: %s" % image_format)

        if os.path.exists(cont_img_path):
            raise EasyBuildError("Container image already exists at " + cont_img_path)
        else:
            cont_img_cmd = "sudo singularity build %s --sandbox %s %s" % (cont_img_cmd_opts, cont_img_path, def_path)
            run_cmd(cont_img_cmd)
            print_msg("Singularity image created at %s" % cont_img_path, log=_log)


def singularity(ordered_ecs, container_base=None):
    """
    Create Singularity definition file and (optionally) image
    """
    if container_base is None:
        container_base = build_option('container_base')

    path_to_singularity_cmd = which('singularity')
    if path_to_singularity_cmd:
        print_msg("Singularity tool found at %s" % path_to_singularity_cmd)
        out, ec = run_cmd("singularity --version", simple=False)
        if ec:
            raise EasyBuildError("Failed to determine Singularity version: %s" % out)
        else:
            # singularity version format for 2.3.1 and higher is x.y-dist
            singularity_version = out.strip().split('-')[0]

    if build_option('container_build_image'):
        if not path_to_singularity_cmd:
            raise EasyBuildError("Singularity not found in your system")

        if LooseVersion(singularity_version) < LooseVersion('2.4'):
            raise EasyBuildError("Please upgrade singularity instance to version 2.4 or higher")
        else:
            print_msg("Singularity version '%s' is 2.4 or higher ... OK" % singularity_version)

    generate_singularity_recipe(ordered_ecs, container_base)
