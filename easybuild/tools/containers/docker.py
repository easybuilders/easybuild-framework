import os
import shutil
import tempfile
import operator

from vsc.utils import fancylogger

from easybuild.framework.easyconfig.easyconfig import ActiveMNS
from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import build_option, container_path
from easybuild.tools.config import DOCKER_BASE_IMAGE_UBUNTU, DOCKER_BASE_IMAGE_CENTOS, DEFAULT_DOCKER_BASE_IMAGE
from easybuild.tools.filetools import which, write_file
from easybuild.tools.run import run_cmd

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

RUN yum --skip-broken install -y %(os_deps)s || true

RUN mkdir /app && \\
    mkdir /scratch && \\
    mkdir /scratch/tmp && \\
    useradd -m -s /bin/bash easybuild && \\
    chown easybuild:easybuild -R /app && \\
    chown easybuild:easybuild -R /scratch

USER easybuild

RUN set -x &&  \\
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


def check_docker_containerize():
    docker_container_base = build_option('container_base') or DEFAULT_DOCKER_BASE_IMAGE

    if docker_container_base not in [DOCKER_BASE_IMAGE_UBUNTU, DOCKER_BASE_IMAGE_CENTOS]:
        raise EasyBuildError("Unsupported container base image '%s'" % docker_container_base)

    # NOTE: no need to have docker and tools for just Dockerfile generation.
    if not build_option('container_build_image'):
        return

    docker_path = which('docker')
    if not docker_path:
        raise EasyBuildError("docker executable not found.")
    _log.debug("found docker executable '%s'" % docker_path)

    sudo_path = which('sudo')
    if not sudo_path:
        raise EasyBuildError("sudo not found.")

    try:
        run_cmd("sudo docker --version")
    except Exception:
        raise EasyBuildError("Error getting docker version")


def _det_os_deps(easyconfigs):
    res = []
    _os_deps = reduce(operator.add, [obj['ec']['osdependencies'] for obj in easyconfigs], [])
    for os_dep in _os_deps:
        if isinstance(os_dep, basestring):
            res.append(os_dep)
        elif isinstance(os_dep, tuple):
            res.extend(os_dep)
    return res


def generate_dockerfile(easyconfigs, container_base, eb_go):
    os_deps = _det_os_deps(easyconfigs)

    module_naming_scheme = ActiveMNS()

    ec = easyconfigs[-1]['ec']

    init_modulepath = os.path.join("/app/modules/all", *module_naming_scheme.det_init_modulepaths(ec))

    mod_names = [e['ec'].full_mod_name for e in easyconfigs]

    eb_opts = [eb_opt for eb_opt in eb_go.generate_cmd_line()
               if not eb_opt.startswith('--container') and eb_opt not in ['--ignore-osdeps', '--experimental']]
    eb_opts.extend(eb_go.args)

    tmpl = _DOCKER_TMPLS[container_base]
    content = tmpl % {
        'os_deps': ' '.join(os_deps),
        'eb_opts': ' '.join(eb_opts),
        'init_modulepath': init_modulepath,
        'mod_names': ' '.join(mod_names),
    }

    cont_path = container_path()

    img_name = build_option('container_image_name')
    if img_name:
        file_label = os.path.splitext(img_name)[0]
    else:
        file_label = mod_names[0].replace('/', '-')

    dockerfile = os.path.join(cont_path, 'Dockerfile.%s' % file_label)
    if os.path.exists(dockerfile):
        if build_option('force'):
            print_msg("WARNING: overwriting existing Dockerfile at %s due to --force" % dockerfile)
        else:
            raise EasyBuildError("Dockerfile at %s already exists, not overwriting it without --force", dockerfile)

    write_file(dockerfile, content)

    return dockerfile


def build_docker_image(easyconfigs, dockerfile):
    ec = easyconfigs[-1]['ec']

    module_naming_scheme = ActiveMNS()
    module_name = module_naming_scheme.det_full_module_name(ec)

    tempdir = tempfile.mkdtemp(prefix='easybuild-docker')
    container_name = build_option('container_image_name') or "%s:latest" % module_name
    docker_cmd = ' '.join(['sudo', 'docker', 'build', '-f', dockerfile, '-t', container_name, '.'])
    run_cmd(docker_cmd, path=tempdir)

    shutil.rmtree(tempdir)


def docker_containerize(easyconfigs, eb_go):

    check_docker_containerize()

    # Generate dockerfile
    container_base = build_option('container_base') or DEFAULT_DOCKER_BASE_IMAGE
    dockerfile = generate_dockerfile(easyconfigs, container_base, eb_go)

    # Build image if requested
    if build_option('container_build_image'):
        build_docker_image(easyconfigs, dockerfile)
