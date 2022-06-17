# #
# Copyright 2009-2022 Ghent University
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
# #
"""
Support for generating docker container recipes and creating container images

:author Mohamed Abidi (Bright Computing)
"""
import os
import tempfile

from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import DOCKER_BASE_IMAGE_CENTOS, DOCKER_BASE_IMAGE_UBUNTU
from easybuild.tools.containers.base import ContainerGenerator
from easybuild.tools.containers.utils import det_os_deps
from easybuild.tools.filetools import remove_dir
from easybuild.tools.module_naming_scheme.easybuild_mns import EasyBuildMNS
from easybuild.tools.run import run_cmd


DOCKER_TMPL_HEADER = """\
FROM %(container_config)s
LABEL maintainer=easybuild@lists.ugent.be
"""

DOCKER_INSTALL_EASYBUILD = """\
RUN pip3 install -U pip setuptools && \\
    hash -r pip3&& \\
    pip3 install -U easybuild

RUN mkdir /app && \\
    mkdir /scratch && \\
    mkdir /scratch/tmp && \\
    useradd -m -s /bin/bash easybuild && \\
    chown easybuild:easybuild -R /app && \\
    chown easybuild:easybuild -R /scratch
"""

DOCKER_TMPL_FOOTER = """\
USER easybuild

RUN set -x && \\
    . /usr/share/lmod/lmod/init/sh && \\
    eb --robot %(eb_opts)s --installpath=/app/ --prefix=/scratch --tmpdir=/scratch/tmp

RUN touch ${HOME}/.bashrc && \\
    echo '' >> ${HOME}/.bashrc && \\
    echo '# Added by easybuild docker packaging' >> ${HOME}/.bashrc && \\
    echo 'source /usr/share/lmod/lmod/init/bash' >> ${HOME}/.bashrc && \\
    echo 'module use %(init_modulepath)s' >> ${HOME}/.bashrc && \\
    echo 'module load %(mod_names)s' >> ${HOME}/.bashrc

CMD ["/bin/bash", "-l"]
"""

DOCKER_UBUNTU2004_INSTALL_DEPS = """\
RUN apt-get update && \\
    DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-pip lmod \\
        curl wget git bzip2 gzip tar zip unzip xz-utils \\
        patch automake git debianutils \\
        g++ libdata-dump-perl libthread-queue-any-perl libssl-dev

RUN OS_DEPS='%(os_deps)s' && \\
    for dep in ${OS_DEPS}; do apt-get -qq install ${dep} || true; done
"""

DOCKER_CENTOS7_INSTALL_DEPS = """\
RUN yum install -y epel-release && \\
    yum install -y python3 python3-pip Lmod curl wget git \\
        bzip2 gzip tar zip unzip xz \\
        patch make git which \\
        gcc-c++ perl-Data-Dumper perl-Thread-Queue openssl-dev

RUN OS_DEPS='%(os_deps)s' && \\
    test -n "${OS_DEPS}" && \\
    yum --skip-broken install -y "${OS_DEPS}" || true
"""

DOCKER_OS_INSTALL_DEPS_TMPLS = {
    DOCKER_BASE_IMAGE_UBUNTU: DOCKER_UBUNTU2004_INSTALL_DEPS,
    DOCKER_BASE_IMAGE_CENTOS: DOCKER_CENTOS7_INSTALL_DEPS,
}


class DockerContainer(ContainerGenerator):

    TOOLS = {'docker': None, 'sudo': None}

    RECIPE_FILE_NAME = 'Dockerfile'

    def resolve_template(self):
        """Return template container recipe."""

        if self.container_template_recipe:
            raise EasyBuildError("--container-template-recipe is not supported yet for Docker container images!")

        if self.container_config:
            return '\n\n'.join([
                DOCKER_TMPL_HEADER % {'container_config': self.container_config},
                DOCKER_OS_INSTALL_DEPS_TMPLS[self.container_config],
                DOCKER_INSTALL_EASYBUILD,
                DOCKER_TMPL_FOOTER,
            ])
        else:
            raise EasyBuildError("--container--config is required for Docker container images!")

    def resolve_template_data(self):
        """Return template data for container recipe."""

        os_deps = det_os_deps(self.easyconfigs)

        ec = self.easyconfigs[-1]['ec']

        # We are using the default MNS inside the container
        docker_mns = EasyBuildMNS()

        init_modulepath = os.path.join("/app/modules/all", *docker_mns.det_init_modulepaths(ec))

        mod_names = [docker_mns.det_full_module_name(e['ec']) for e in self.easyconfigs]

        eb_opts = [os.path.basename(e['spec']) for e in self.easyconfigs]

        return {
            'os_deps': ' '.join(os_deps),
            'eb_opts': ' '.join(eb_opts),
            'init_modulepath': init_modulepath,
            'mod_names': ' '.join(mod_names),
        }

    def validate(self):
        """Perform validation of specified container configuration."""
        if self.container_config not in DOCKER_OS_INSTALL_DEPS_TMPLS.keys():
            raise EasyBuildError("Unsupported container config '%s'" % self.container_config)
        super(DockerContainer, self).validate()

    def build_image(self, dockerfile):
        ec = self.easyconfigs[-1]['ec']

        module_name = self.mns.det_full_module_name(ec)

        tempdir = tempfile.mkdtemp(prefix='easybuild-docker')
        container_name = self.img_name or "%s:latest" % module_name.replace('/', '-')
        docker_cmd = ' '.join(['sudo', 'docker', 'build', '-f', dockerfile, '-t', container_name, '.'])

        print_msg("Running '%s', you may need to enter your 'sudo' password..." % docker_cmd)
        run_cmd(docker_cmd, path=tempdir, stream_output=True)
        print_msg("Docker image created at %s" % container_name, log=self.log)

        remove_dir(tempdir)
