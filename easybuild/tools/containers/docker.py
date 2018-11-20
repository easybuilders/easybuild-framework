# #
# Copyright 2009-2018 Ghent University
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
from easybuild.tools.filetools import rmtree2
from easybuild.tools.run import run_cmd


DOCKER_TMPL_HEADER = """\
FROM %(container_base)s
LABEL maintainer=easybuild@lists.ugent.be
"""

DOCKER_INSTALL_EASYBUILD = """\
RUN pip install -U pip setuptools && \\
    hash -r pip && \\
    pip install -U easybuild

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
    eb %(eb_opts)s --installpath=/app/ --prefix=/scratch --tmpdir=/scratch/tmp

RUN touch ${HOME}/.profile && \\
    echo '\\n# Added by easybuild docker packaging' >> ${HOME}/.profile && \\
    echo 'source /usr/share/lmod/lmod/init/bash' >> ${HOME}/.profile && \\
    echo 'module use %(init_modulepath)s' >> ${HOME}/.profile && \\
    echo 'module load %(mod_names)s' >> ${HOME}/.profile

CMD ["/bin/bash", "-l"]
"""

DOCKER_UBUNTU1604_INSTALL_DEPS = """\
RUN apt-get update && \\
    apt-get install -y python python-pip lmod curl wget

RUN OS_DEPS='%(os_deps)s' && \\
    test -n "${OS_DEPS}" && \\
    for dep in ${OS_DEPS}; do apt-get -qq install ${dep} || true; done
"""

DOCKER_CENTOS7_INSTALL_DEPS = """\
RUN yum install -y epel-release && \\
    yum install -y python python-pip Lmod curl wget git

RUN OS_DEPS='%(os_deps)s' && \\
    test -n "${OS_DEPS}" && \\
    yum --skip-broken install -y "${OS_DEPS}" || true
"""

DOCKER_OS_INSTALL_DEPS_TMPLS = {
    DOCKER_BASE_IMAGE_UBUNTU: DOCKER_UBUNTU1604_INSTALL_DEPS,
    DOCKER_BASE_IMAGE_CENTOS: DOCKER_CENTOS7_INSTALL_DEPS,
}


class DockerContainer(ContainerGenerator):

    TOOLS = {'docker': None, 'sudo': None}

    RECIPE_FILE_NAME = 'Dockerfile'

    def resolve_template(self):
        return "\n\n".join([
            DOCKER_TMPL_HEADER % {'container_base': self.container_base},
            DOCKER_OS_INSTALL_DEPS_TMPLS[self.container_base],
            DOCKER_INSTALL_EASYBUILD,
            DOCKER_TMPL_FOOTER,
        ])

    def resolve_template_data(self):
        os_deps = det_os_deps(self.easyconfigs)

        ec = self.easyconfigs[-1]['ec']

        init_modulepath = os.path.join("/app/modules/all", *self.mns.det_init_modulepaths(ec))

        mod_names = [ec['ec'].full_mod_name for ec in self.easyconfigs]

        eb_opts = [os.path.basename(ec['spec']) for ec in self.easyconfigs]

        return {
            'os_deps': ' '.join(os_deps),
            'eb_opts': ' '.join(eb_opts),
            'init_modulepath': init_modulepath,
            'mod_names': ' '.join(mod_names),
        }

    def validate(self):
        if self.container_base not in DOCKER_OS_INSTALL_DEPS_TMPLS.keys():
            raise EasyBuildError("Unsupported container base image '%s'" % self.container_base)
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

        rmtree2(tempdir)
