# Copyright 2017-2019 Ghent University
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
from distutils.version import LooseVersion
import os
import re

from easybuild.tools.build_log import EasyBuildError, print_msg, print_warning
from easybuild.tools.config import CONT_IMAGE_FORMAT_EXT3, CONT_IMAGE_FORMAT_SANDBOX
from easybuild.tools.config import CONT_IMAGE_FORMAT_SIF, CONT_IMAGE_FORMAT_SQUASHFS
from easybuild.tools.config import build_option, container_path
from easybuild.tools.filetools import read_file, remove_file, which
from easybuild.tools.run import run_cmd
from easybuild.tools.containers.base import ContainerGenerator


ARCH = 'arch'  # Arch Linux
BUSYBOX = 'busybox'  # BusyBox Linux
DEBOOTSTRAP = 'debootstrap'  # apt-based systems like Ubuntu/Debian
DOCKER = 'docker'  # image hosted on Docker Hub
LIBRARY = 'library'  # Sylabs Container Library
LOCALIMAGE = 'localimage'  # local image file
SHUB = 'shub'  # image hosted on Singularity Hub
YUM = 'yum'  # yum-based systems like CentOS
ZYPPER = 'zypper'  # zypper-based systems like openSUSE

# valid bootstrap agents for 'bootstrap' keyword in --container-base-config
SINGULARITY_BOOTSTRAP_AGENTS = [ARCH, BUSYBOX, DEBOOTSTRAP, DOCKER, LIBRARY, LOCALIMAGE, SHUB, YUM, ZYPPER]

# valid bootstrap agents for --container-base-image value
SINGULARITY_BOOTSTRAP_AGENTS_IMAGE = [DOCKER, LIBRARY, LOCALIMAGE, SHUB]

SINGULARITY_INCLUDE_DEFAULTS = {
    YUM: 'yum',
    ZYPPER: 'zypper',
}

SINGULARITY_MIRRORURL_DEFAULTS = {
    BUSYBOX: 'https://www.busybox.net/downloads/binaries/%{OSVERSION}/busybox-x86_64',
    DEBOOTSTRAP: 'http://us.archive.ubuntu.com/ubuntu/',
    YUM: 'http://mirror.centos.org/centos-%{OSVERSION}/%{OSVERSION}/os/x86_64/',
    ZYPPER: 'http://download.opensuse.org/distribution/leap/%{OSVERSION}/repo/oss/',
}

SINGULARITY_TEMPLATE = """
Bootstrap: %(bootstrap)s
%(bootstrap_config)s

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

    @staticmethod
    def singularity_version():
        """Get Singularity version."""
        version_cmd = "singularity --version"
        out, ec = run_cmd(version_cmd, simple=False, trace=False, force_in_dry_run=True)
        if ec:
            raise EasyBuildError("Error running '%s': %s for tool {1} with output: {2}" % (version_cmd, out))

        res = re.search(r"\d+\.\d+(\.\d+)?", out.strip())
        if not res:
            raise EasyBuildError("Error parsing Singularity version: %s" % out)

        return res.group(0)

    def resolve_template(self):
        """Return template container recipe."""
        if self.container_template_recipe:
            template = read_file(self.container_template_recipe)
        else:
            template = SINGULARITY_TEMPLATE

        return template

    def resolve_template_data_base_config(self):
        """Return template data for container recipe based on what is passed to --container-base-config."""

        template_data = {}

        base_config_known_keys = [
            # bootstrap agent to use
            # see https://www.sylabs.io/guides/latest/user-guide/definition_files.html#header
            'bootstrap',
            # argument for bootstrap agents; only valid for: docker, library, localimage, shub
            'from',
            # list of additional OS packages to include; only valid with debootstrap, yum, zypper
            'include',
            # URI to use to download OS; only valid with busybox, debootstrap, yum, zypper
            'mirrorurl',
            # OS 'version' to use; only valid with busybox, debootstrap, yum, zypper
            # only required if value for %(mirrorurl)s contains %{OSVERSION}s
            'osversion',
        ]

        # configuration for base container is assumed to have <key>=<value>[,<key>=<value>] format
        config_items = self.container_base_config.split(',')
        for item in config_items:
            key, value = item.split('=', 1)
            if key in base_config_known_keys:
                template_data[key] = value
            else:
                raise EasyBuildError("Unknown key for base container configuration: %s", key)

        # make sure correct bootstrap agent is specified
        bootstrap = template_data.get('bootstrap')
        if bootstrap:
            if bootstrap not in SINGULARITY_BOOTSTRAP_AGENTS:
                raise EasyBuildError("Unknown value specified for 'bootstrap' keyword: %s (known: %s)",
                                     bootstrap, ', '.join(SINGULARITY_BOOTSTRAP_AGENTS))
        else:
            raise EasyBuildError("Keyword 'bootstrap' is required in container base config")

        # make sure 'from' is specified when required
        if bootstrap in SINGULARITY_BOOTSTRAP_AGENTS_IMAGE and template_data.get('from') is None:
            raise EasyBuildError("Keyword 'from' is required in container base config when using bootstrap agent '%s'",
                                 bootstrap)

        # use default value for mirror URI if none was specified
        if bootstrap in SINGULARITY_MIRRORURL_DEFAULTS and template_data.get('mirrorurl') is None:
            template_data['mirrorurl'] = SINGULARITY_MIRRORURL_DEFAULTS[bootstrap]

        # check whether OS version is specified if required
        mirrorurl = template_data.get('mirrorurl')
        if mirrorurl and '%{OSVERSION}' in mirrorurl and template_data.get('osversion') is None:
            raise EasyBuildError("Keyword 'osversion' is required in container base config when '%%{OSVERSION}' "
                                 "is used in mirror URI: %s", mirrorurl)

        # use default value for list of included OS packages if nothing else was specified
        if bootstrap in SINGULARITY_INCLUDE_DEFAULTS and template_data.get('include') is None:
            template_data['include'] = SINGULARITY_INCLUDE_DEFAULTS[bootstrap]

        return template_data

    def resolve_template_data_base_image(self):
        """Return template data for container recipe based on what is passed to --container-base-image."""
        base_specs = parse_container_base_image(self.container_base_image)

        # extracting application name,version, version suffix, toolchain name, toolchain version from
        # easyconfig class

        bootstrap_agent = base_specs['bootstrap_agent']

        base_image, base_image_tag = None, None

        # with localimage it only takes 2 arguments. --container-base-image localimage:/path/to/image
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

        # otherwise, bootstrap agent is 'docker', 'library' or 'shub'
        # format --container-base-image {docker|library|shub}:<image>:<tag>
        else:
            base_image = base_specs['arg1']
            # image tag is optional
            base_image_tag = base_specs.get('arg2', None)

        bootstrap_from = base_image
        if base_image_tag:
            bootstrap_from += ':' + base_image_tag

        return {
            'bootstrap': bootstrap_agent,
            'from': bootstrap_from,
        }

    def resolve_template_data(self):
        """Return template data for container recipe."""

        template_data = {}

        if self.container_base_image:
            if self.container_base_config:
                print_warning("--container-base-config is ignored when --container-base-image is also specified!")

            template_data.update(self.resolve_template_data_base_image())

        elif self.container_base_config:
            template_data.update(self.resolve_template_data_base_config())

        else:
            raise EasyBuildError("Either --container-base-config or --container-base-image must be specified!")

        # puzzle together specs for bootstrap agent
        bootstrap_config_lines = []
        for key in ['From', 'OSVersion', 'MirrorURL', 'Include']:
            if key.lower() in template_data:
                bootstrap_config_lines.append('%s: %s' % (key, template_data[key.lower()]))
        template_data['bootstrap_config'] = '\n'.join(bootstrap_config_lines)

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

        template_data['install_os_deps'] = install_os_deps

        # module names to load in container environment
        mod_names = [e['ec'].full_mod_name for e in self.easyconfigs]
        template_data['mod_names'] = ' '.join(mod_names)

        template_data['easyconfigs'] = ' '.join(os.path.basename(e['spec']) for e in self.easyconfigs)

        return template_data

    def build_image(self, recipe_path):
        """Build container image by calling out to 'sudo singularity build'."""

        cont_path = container_path()
        def_file = os.path.basename(recipe_path)

        # use --imagename if specified, otherwise derive based on filename of recipe
        img_name = self.img_name
        if img_name is None:
            # definition file Singularity.<app>-<version, container name <app>-<version>.<img|simg>
            img_name = def_file.split('.', 1)[1]

        cmd_opts = ''

        image_format = self.image_format

        singularity_version = self.singularity_version()

        # squashfs image format (default for Singularity)
        if image_format in [None, CONT_IMAGE_FORMAT_SQUASHFS, CONT_IMAGE_FORMAT_SIF]:
            if LooseVersion(singularity_version) > LooseVersion('3.0'):
                ext = '.sif'
            else:
                ext = '.simg'
            img_path = os.path.join(cont_path, img_name + ext)

        # ext3 image format, creating as writable container
        elif image_format == CONT_IMAGE_FORMAT_EXT3:
            if LooseVersion(singularity_version) > LooseVersion('3.0'):
                raise EasyBuildError("ext3 image format is only supported with Singularity 2.x (found Singularity %s)",
                                     singularity_version)
            else:
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


def parse_container_base_image(base):
    """Parse value passed to --container-base-image option."""
    if base:
        base_specs = base.split(':')
        if len(base_specs) > 3 or len(base_specs) <= 1:
            error_msg = '\n'.join([
                "Invalid format for --container-base-image, must be one of the following:",
                '',
                "--container-base-image library:<entity>/<collection>/<container>:<tag>",
                "--container-base-image localimage:/path/to/image",
                "--container-base-image shub:<registry>/<username>/<container-name>:<tag>@digest",
                "--container-base-image docker:<registry>/<namespace>/<container>:<tag>@<digest>",
            ])
            raise EasyBuildError(error_msg)
    else:
        raise EasyBuildError("--container-base-image must be specified")

    # first argument to --container-base-image is the Singularity bootstrap agent (library, localimage, shub, docker)
    bootstrap_agent = base_specs[0]

    # check bootstrap type value and ensure it is library, localimage, shub, docker
    if bootstrap_agent not in SINGULARITY_BOOTSTRAP_AGENTS_IMAGE:
        known_bootstrap_agents = ', '.join(SINGULARITY_BOOTSTRAP_AGENTS_IMAGE)
        raise EasyBuildError("Bootstrap agent in container base image spec must be one of: %s" % known_bootstrap_agents)

    res = {'bootstrap_agent': bootstrap_agent}

    for idx, base_spec in enumerate(base_specs[1:]):
        res.update({'arg%d' % (idx + 1): base_spec})

    return res
