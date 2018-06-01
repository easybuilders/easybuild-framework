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
import shutil
import tempfile

from vsc.utils import fancylogger

from easybuild.framework.easyconfig.easyconfig import ActiveMNS
from easybuild.tools.build_log import print_msg
from easybuild.tools.config import build_option
from easybuild.tools.config import DOCKER_BASE_IMAGE_UBUNTU, DOCKER_BASE_IMAGE_CENTOS, DEFAULT_DOCKER_BASE_IMAGE
from easybuild.tools.run import run_cmd
from .base import ContainerGenerator
from .utils import det_os_deps

_log = fancylogger.getLogger('tools.containers.singularity')  # pylint: disable=C0103

DOCKER_UBUNTU1604_TMPL = """\
FROM ubuntu:16.04
LABEL maintainer=mohamed.abidi@brightcomputing.com

RUN apt-get update && \\
    apt-get install -y python python-pip lmod curl wget

RUN pip install -U pip setuptools && \\
    hash -r pip && \\
    pip install -U easybuild

RUN mkdir /app && \\
    mkdir /scratch && \\
    mkdir /scratch/tmp && \\
    useradd -m -s /bin/bash easybuild && \\
    chown easybuild:easybuild -R /app && \\
    chown easybuild:easybuild -R /scratch

RUN OS_DEPS='%(os_deps)s' && \\
    test -n "${OS_DEPS}" && \\
    for dep in ${OS_DEPS}; do apt-get -qq install ${dep} || true; done

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

DOCKER_CENTOS7_TMPL = """\
FROM centos:7
LABEL maintainer=mohamed.abidi@brightcomputing.com

RUN yum install -y epel-release && \\
    yum install -y python python-pip Lmod curl wget git

RUN pip install -U pip setuptools && \\
    hash -r pip && \\
    pip install -U easybuild

RUN OS_DEPS='%(os_deps)s' && \\
    test -n "${OS_DEPS}" && \\
    yum --skip-broken install -y "${OS_DEPS}" || true

RUN mkdir /app && \\
    mkdir /scratch && \\
    mkdir /scratch/tmp && \\
    useradd -m -s /bin/bash easybuild && \\
    chown easybuild:easybuild -R /app && \\
    chown easybuild:easybuild -R /scratch

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

_DOCKER_TMPLS = {
    DOCKER_BASE_IMAGE_UBUNTU: DOCKER_UBUNTU1604_TMPL,
    DOCKER_BASE_IMAGE_CENTOS: DOCKER_CENTOS7_TMPL,
}


class DockerContainer(ContainerGenerator):

    TOOLS = {'docker': '0.0', 'sudo': '0.0'}

    RECIPE_FILE_NAME = 'Dockerfile'

    def resolve_template(self):
        return _DOCKER_TMPLS[self._container_base or DEFAULT_DOCKER_BASE_IMAGE]

    def resolve_template_data(self):
        os_deps = det_os_deps(self._easyconfigs)

        module_naming_scheme = ActiveMNS()

        ec = self._easyconfigs[-1]['ec']

        init_modulepath = os.path.join("/app/modules/all", *module_naming_scheme.det_init_modulepaths(ec))

        mod_names = [e['ec'].full_mod_name for e in self._easyconfigs]

        eb_opts = [os.path.basename(ec['spec']) for ec in self._easyconfigs]

        return {
            'os_deps': ' '.join(os_deps),
            'eb_opts': ' '.join(eb_opts),
            'init_modulepath': init_modulepath,
            'mod_names': ' '.join(mod_names),
        }

    def build_image(self, dockerfile):
        ec = self._easyconfigs[-1]['ec']

        module_naming_scheme = ActiveMNS()
        module_name = module_naming_scheme.det_full_module_name(ec)

        tempdir = tempfile.mkdtemp(prefix='easybuild-docker')
        container_name = build_option('container_image_name') or "%s:latest" % module_name.replace('/', '-')
        docker_cmd = ' '.join(['sudo', 'docker', 'build', '-f', dockerfile, '-t', container_name, '.'])

        print_msg("Running '%s', you may need to enter your 'sudo' password..." % docker_cmd)
        run_cmd(docker_cmd, path=tempdir, stream_output=True)
        print_msg("Docker image created at %s" % container_name, log=_log)

        shutil.rmtree(tempdir)
