# Copyright 2017-2021 Ghent University
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

from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import CONT_IMAGE_FORMAT_EXT3, CONT_IMAGE_FORMAT_SANDBOX
from easybuild.tools.config import CONT_IMAGE_FORMAT_SIF, CONT_IMAGE_FORMAT_SQUASHFS
from easybuild.tools.config import build_option, container_path
from easybuild.tools.containers.base import ContainerGenerator
from easybuild.tools.filetools import read_file, remove_file, which
from easybuild.tools.run import run_cmd
from easybuild.tools.py2vs3 import string_type


ARCH = 'arch'  # Arch Linux
BUSYBOX = 'busybox'  # BusyBox Linux
DEBOOTSTRAP = 'debootstrap'  # apt-based systems like Ubuntu/Debian
DOCKER = 'docker'  # image hosted on Docker Hub
LIBRARY = 'library'  # Sylabs Container Library
LOCALIMAGE = 'localimage'  # local image file
SHUB = 'shub'  # image hosted on Singularity Hub
YUM = 'yum'  # yum-based systems like CentOS
ZYPPER = 'zypper'  # zypper-based systems like openSUSE

# 'distro' bootstrap agents (starting from scratch, not from existing image)
SINGULARITY_BOOTSTRAP_AGENTS_DISTRO = [ARCH, BUSYBOX, DEBOOTSTRAP, YUM, ZYPPER]

# 'image' bootstrap agents (starting from an existing image)
SINGULARITY_BOOTSTRAP_AGENTS_IMAGE = [DOCKER, LIBRARY, LOCALIMAGE, SHUB]

# valid bootstrap agents for 'bootstrap' keyword in --container-config
SINGULARITY_BOOTSTRAP_AGENTS = sorted(SINGULARITY_BOOTSTRAP_AGENTS_DISTRO + SINGULARITY_BOOTSTRAP_AGENTS_IMAGE)

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

%(install_eb)s

%(post_commands)s

# install Lmod RC file
cat > /etc/lmodrc.lua << EOF
scDescriptT = {
  {
    ["dir"]       = "/app/lmodcache",
    ["timestamp"] = "/app/lmodcache/timestamp",
  },
}
EOF

# switch to 'easybuild' user for following commands
# quotes around EOF delimiter are important to ensure environment variables are not expanded prematurely!
su - easybuild << 'EOF'

# verbose commands, exit on first error
set -ve

# configure EasyBuild

# use /scratch as general prefix, used for sources, build directories, etc.
export EASYBUILD_PREFIX=/scratch

# also use /scratch for temporary directories
export EASYBUILD_TMPDIR=/scratch/tmp

# download sources to /scratch/sources, but also consider files located in /tmp/easybuild/sources;
# that way, source files that can not be downloaded can be seeded in
export EASYBUILD_SOURCEPATH=/scratch/sources:/tmp/easybuild/sources

# install software & modules into /app
export EASYBUILD_INSTALLPATH=/app

# use EasyBuild to install specified software
eb %(easyconfigs)s --robot %(eb_args)s

# update Lmod cache
mkdir -p /app/lmodcache
$LMOD_DIR/update_lmod_system_cache_files -d /app/lmodcache -t /app/lmodcache/timestamp /app/modules/all

# end of set of commands to run as 'easybuild' user
EOF

# cleanup, everything in /scratch is assumed to be temporary
rm -rf /scratch/*

%%runscript
eval "$@"

%%environment
# make sure that 'module' and 'ml' commands are defined
source /etc/profile
# increase threshold time for Lmod to write cache in $HOME (which we don't want to do)
export LMOD_SHORT_TIME=86400
# purge any modules that may be loaded outside container
module --force purge
# avoid picking up modules from outside of container
module unuse $MODULEPATH
# pick up modules installed in /app
module use /app/modules/all
# load module(s) corresponding to installed software
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

    def resolve_template_data_config(self):
        """Return template data for container recipe based on what is passed to --container-config."""

        template_data = {}

        config_known_keys = [
            # bootstrap agent to use
            # see https://www.sylabs.io/guides/latest/user-guide/definition_files.html#header
            'bootstrap',
            # additional arguments for 'eb' command
            'eb_args',
            # argument for bootstrap agents; only valid for: docker, library, localimage, shub
            'from',
            # list of additional OS packages to include; only valid with debootstrap, yum, zypper
            'include',
            # commands to install EasyBuild
            'install_eb',
            # URI to use to download OS; only valid with busybox, debootstrap, yum, zypper
            'mirrorurl',
            # OS 'version' to use; only valid with busybox, debootstrap, yum, zypper
            # only required if value for %(mirrorurl)s contains %{OSVERSION}s
            'osversion',
            # additional commands for 'post' section
            'post_commands',
        ]

        # configuration for base container is assumed to have <key>=<value>[,<key>=<value>] format
        config_items = self.container_config.split(',')
        for item in config_items:
            key, value = item.split('=', 1)
            if key in config_known_keys:
                template_data[key] = value
            else:
                raise EasyBuildError("Unknown key for container configuration: %s", key)

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

    def resolve_template_data(self):
        """Return template data for container recipe."""

        template_data = {}

        if self.container_config:
            template_data.update(self.resolve_template_data_config())
        else:
            raise EasyBuildError("--container-config must be specified!")

        # puzzle together specs for bootstrap agent
        bootstrap_config_lines = []
        for key in ['From', 'OSVersion', 'MirrorURL', 'Include']:
            if key.lower() in template_data:
                bootstrap_config_lines.append('%s: %s' % (key, template_data[key.lower()]))
        template_data['bootstrap_config'] = '\n'.join(bootstrap_config_lines)

        # basic tools & utilities to install in container image
        osdeps = []

        # install bunch of required/useful OS packages, but only when starting from scratch;
        # when starting from an existing image, the required OS packages are assumed to be installed already
        if template_data['bootstrap'] in SINGULARITY_BOOTSTRAP_AGENTS_DISTRO:
            osdeps.extend([
                # EPEL is required for installing Lmod & python-pip
                'epel-release',
                # EasyBuild requirements
                'python setuptools Lmod',
                # pip is used to install EasyBuild packages
                'python-pip',
                # useful utilities
                'bzip2 gzip tar zip unzip xz',  # extracting sources
                'curl wget',  # downloading
                'patch make',  # building
                'file git which',  # misc. tools
                # additional packages that EasyBuild relies on (for now)
                'gcc-c++',  # C/C++ components of GCC (gcc, g++)
                'perl-Data-Dumper',  # required for GCC build
                # required for Automake build, see https://github.com/easybuilders/easybuild-easyconfigs/issues/1822
                'perl-Thread-Queue',
                ('libibverbs-dev', 'libibverbs-devel', 'rdma-core-devel'),  # for OpenMPI
                ('openssl-devel', 'libssl-dev', 'libopenssl-devel'),  # for CMake, Python, ...
            ])

        # also include additional OS dependencies specified in easyconfigs
        for ec in self.easyconfigs:
            for osdep in ec['ec']['osdependencies']:
                if osdep not in osdeps:
                    osdeps.append(osdep)

        install_os_deps = []
        for osdep in osdeps:
            if isinstance(osdep, string_type):
                install_os_deps.append("yum install --quiet --assumeyes %s" % osdep)
            # tuple entry indicates multiple options
            elif isinstance(osdep, tuple):
                install_os_deps.append("yum --skip-broken --quiet --assumeyes install %s" % ' '.join(osdep))
            else:
                raise EasyBuildError("Unknown format of OS dependency specification encountered: %s", osdep)

        template_data['install_os_deps'] = '\n'.join(install_os_deps)

        # install (latest) EasyBuild in container image
        # use 'pip install', unless custom commands are specified via 'install_eb' keyword
        if 'install_eb' not in template_data:
            template_data['install_eb'] = '\n'.join([
                "# install EasyBuild using pip",
                # upgrade pip
                "pip install -U pip",
                "pip install easybuild",
            ])

        # if no custom value is specified for 'post_commands' keyword,
        # make sure 'easybuild' user exists and that installation prefix + scratch dir are in place
        if 'post_commands' not in template_data:
            template_data['post_commands'] = '\n'.join([
                "# create 'easybuild' user (if missing)",
                "id easybuild || useradd easybuild",
                '',
                "# create /app software installation prefix + /scratch sandbox directory",
                "if [ ! -d /app ]; then mkdir -p /app; chown easybuild:easybuild -R /app; fi",
                "if [ ! -d /scratch ]; then mkdir -p /scratch; chown easybuild:easybuild -R /scratch; fi",
            ])

        # use empty value for 'eb_args' keyword if nothing was specified
        if 'eb_args' not in template_data:
            template_data['eb_args'] = ''

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
