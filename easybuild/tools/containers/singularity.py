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
Support for generating singularity container recipes and creating container images

:author: Shahzeb Siddiqui (Pfizer)
:author: Kenneth Hoste (HPC-UGent)
:author: Mohamed Abidi (Bright Computing)
"""
import os

from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import CONT_IMAGE_FORMAT_EXT3, CONT_IMAGE_FORMAT_SANDBOX, CONT_IMAGE_FORMAT_SQUASHFS
from easybuild.tools.config import build_option, container_path
from easybuild.tools.filetools import remove_file, which
from easybuild.tools.run import run_cmd
from easybuild.tools.containers.base import ContainerGenerator


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


class SingularityContainer(ContainerGenerator):

    TOOLS = {'singularity': '2.4', 'sudo': None}

    RECIPE_FILE_NAME = 'Singularity'

    def resolve_template(self):
        return SINGULARITY_TEMPLATE

    def resolve_template_data(self):

        base_specs = parse_container_base(self.container_base)

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
                    self.log.debug("Extension for base container image to use is OK: %s", image_ext)
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
        for ec in self.easyconfigs:
            for osdep in ec['ec']['osdependencies']:
                if isinstance(osdep, basestring):
                    install_os_deps += "yum install -y %s\n" % osdep
                # tuple entry indicates multiple options
                elif isinstance(osdep, tuple):
                    install_os_deps += "yum --skip-broken -y install %s\n" % ' '.join(osdep)
                else:
                    raise EasyBuildError("Unknown format of OS dependency specification encountered: %s", osdep)

        # module names to load in container environment
        mod_names = [e['ec'].full_mod_name for e in self.easyconfigs]

        # adding all the regions for writing the  Singularity definition file
        return {
            'bootstrap': bootstrap_agent,
            'from': bootstrap_from,
            'install_os_deps': install_os_deps,
            'easyconfigs': ' '.join(os.path.basename(e['spec']) for e in self.easyconfigs),
            'mod_names': ' '.join(mod_names),
        }

    def build_image(self, recipe_path):

        cont_path = container_path()
        def_file = os.path.basename(recipe_path)

        # use --imagename if specified, otherwise derive based on filename of recipe
        img_name = self.img_name
        if img_name is None:
            # definition file Singularity.<app>-<version, container name <app>-<version>.<img|simg>
            img_name = def_file.split('.', 1)[1]

        cmd_opts = ''

        image_format = self.image_format

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
                raise EasyBuildError("Container image already exists at %s, not overwriting it without --force",
                                     img_path)

        # resolve full path to 'singularity' binary, since it may not be available via $PATH under sudo...
        singularity = which('singularity')
        cmd_env = ''

        singularity_tmpdir = self.tmpdir
        if singularity_tmpdir:
            cmd_env += 'SINGULARITY_TMPDIR=%s' % singularity_tmpdir

        cmd = ' '.join(['sudo', cmd_env, singularity, 'build', cmd_opts, img_path, recipe_path])
        print_msg("Running '%s', you may need to enter your 'sudo' password..." % cmd)
        run_cmd(cmd, stream_output=True)
        print_msg("Singularity image created at %s" % img_path, log=self.log)


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
