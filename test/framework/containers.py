# #
# Copyright 2018-2021 Ghent University
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
Unit tests for easybuild/tools/containers.py

@author: Kenneth Hoste (Ghent University)
"""
import os
import re
import stat
import sys
from test.framework.utilities import EnhancedTestCase, TestLoaderFiltered
from unittest import TextTestRunner

from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import adjust_permissions, mkdir, read_file, remove_file, which, write_file


MOCKED_SINGULARITY = """#!/bin/bash
if [[ $1 == '--version' ]]; then
    echo "%(version)s"
else
    echo "singularity was called with arguments: $@"
    # actually create image file using 'touch'
    echo "$@"
    echo $#
    if [[ $# -eq 3 ]]; then
      img=$2
    elif [[ $# -eq 4 ]]; then
      img=$3
    else
      echo "Don't know how to extract container image location" >&2
      exit 1
    fi
    touch $img
fi
"""

MOCKED_DOCKER = """#!/bin/bash
echo "docker was called with arguments: $@"
if [[ "$1" == '--version' ]]; then
    echo "Docker version 18.03.1-ce, build 9ee9f40"
else
    echo "$@"
    echo $#
fi
"""


class ContainersTest(EnhancedTestCase):
    """Tests for containers support"""

    def run_main(self, args, raise_error=True):
        """Helper function to run main with arguments specified in 'args' and return stdout/stderr."""
        self.mock_stdout(True)
        self.mock_stderr(True)
        self.eb_main(args, raise_error=raise_error, verbose=True, do_build=True)
        stdout = self.get_stdout().strip()
        stderr = self.get_stderr().strip()
        self.mock_stdout(False)
        self.mock_stderr(False)

        return stdout, stderr

    def check_regexs(self, regexs, stdout):
        """Helper function to check output of stdout."""
        for regex in regexs:
            regex = re.compile(regex, re.M)
            self.assertTrue(regex.search(stdout), "Pattern '%s' found in: %s" % (regex.pattern, stdout))

    def test_end2end_singularity_recipe_config(self):
        """End-to-end test for --containerize (recipe only), using --container-config."""
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')

        containerpath = os.path.join(self.test_prefix, 'containers')
        os.environ['EASYBUILD_CONTAINERPATH'] = containerpath
        # --containerpath must be an existing directory (this is done to avoid misconfiguration)
        mkdir(containerpath)

        test_container_recipe = os.path.join(self.test_prefix, 'containers', 'Singularity.toy-0.0')

        args = [
            toy_ec,
            '--containerize',
            '--experimental',
        ]

        args.extend(['--container-config', 'osversion=7.6.1810'])
        error_pattern = r"Keyword 'bootstrap' is required in container base config"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.run_main, args, raise_error=True)

        args.extend(['--container-config', 'bootstrap=foobar'])
        error_pattern = r"Unknown value specified for 'bootstrap' keyword: foobar \(known: arch, busybox, debootstrap, "
        self.assertErrorRegex(EasyBuildError, error_pattern, self.run_main, args, raise_error=True)

        # default mirror URL for yum bootstrap agent uses ${OSVERSION}, so 'osversion' must be specified too
        args.extend(['--container-config', 'bootstrap=yum'])
        error_pattern = "Keyword 'osversion' is required in container base config when '%{OSVERSION}' is used"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.run_main, args, raise_error=True)

        args[-1] = 'bootstrap=yum,osversion=7.6.1810'
        stdout, stderr = self.run_main(args, raise_error=True)

        txt = read_file(test_container_recipe)
        expected = '\n'.join([
            "Bootstrap: yum",
            "OSVersion: 7.6.1810",
            "MirrorURL: http://mirror.centos.org/centos-%{OSVERSION}/%{OSVERSION}/os/x86_64/",
            "Include: yum",
            '\n',
        ])
        self.assertTrue(txt.startswith(expected), "Container recipe starts with '%s':\n\n%s" % (expected, txt))

        # when installing from scratch, a bunch of OS packages are installed too
        pkgs = ['epel-release', 'python', 'setuptools', 'Lmod', r'gcc-c\+\+', 'make', 'patch', 'tar']
        for pkg in pkgs:
            regex = re.compile(r"^yum install .*%s" % pkg, re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))

        pip_patterns = [
            # EasyBuild is installed with pip by default
            "pip install easybuild",
        ]
        post_commands_patterns = [
            # easybuild user is added if it doesn't exist yet
            r"id easybuild \|\| useradd easybuild",
            # /app and /scratch are created (if missing) by default
            r"if \[ ! -d /app \]; then mkdir -p /app",
            r"if \[ ! -d /scratch \]; then mkdir -p /scratch",
        ]
        eb_pattern = r"eb toy-0.0.eb --robot\s*$"
        for pattern in pip_patterns + post_commands_patterns + [eb_pattern]:
            regex = re.compile('^' + pattern, re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))

        remove_file(test_container_recipe)

        # can also specify a custom mirror URL
        args[-1] += ',mirrorurl=https://example.com'
        stdout, stderr = self.run_main(args, raise_error=True)

        txt = read_file(test_container_recipe)
        expected = '\n'.join([
            "Bootstrap: yum",
            "OSVersion: 7.6.1810",
            "MirrorURL: https://example.com",
            "Include: yum",
            '\n',
        ])
        self.assertTrue(txt.startswith(expected), "Container recipe starts with '%s':\n\n%s" % (expected, txt))

        remove_file(test_container_recipe)

        # osversion is not required when %{OSVERSION} is nost used in mirror URL
        args[-1] = 'bootstrap=yum,mirrorurl=https://example.com,include=test123'
        stdout, stderr = self.run_main(args, raise_error=True)

        txt = read_file(test_container_recipe)
        expected = '\n'.join([
            "Bootstrap: yum",
            "MirrorURL: https://example.com",
            "Include: test123",
            '\n',
        ])
        self.assertTrue(txt.startswith(expected), "Container recipe starts with '%s':\n\n%s" % (expected, txt))

        # also check with image-based bootstrap agent, which requires 'from'
        test_cases = [
            ('docker', 'test'),
            ('localimage', 'test.simg'),
            ('library', 'sylabsed/examples/lolcow:latest'),
            ('shub', 'test'),
        ]
        error_pattern = "Keyword 'from' is required in container base config when using bootstrap agent"
        for (bootstrap, from_spec) in test_cases:
            args[-1] = 'bootstrap=%s' % bootstrap
            self.assertErrorRegex(EasyBuildError, error_pattern, self.run_main, args, raise_error=True)

            args[-1] += ',from=%s' % from_spec
            remove_file(test_container_recipe)
            stdout, stderr = self.run_main(args, raise_error=True)

            txt = read_file(test_container_recipe)
            expected = '\n'.join([
                "Bootstrap: %s" % bootstrap,
                "From: %s" % from_spec,
                '',
            ])
            self.assertTrue(txt.startswith(expected), "Container recipe starts with '%s':\n\n%s" % (expected, txt))

            # no OS packages are installed by default when starting from an existing image
            self.assertFalse("yum install" in txt)

            for pattern in pip_patterns + post_commands_patterns + [eb_pattern]:
                regex = re.compile('^' + pattern, re.M)
                self.assertTrue(regex.search(txt), "Pattern '%s' found in: %s" % (regex.pattern, txt))

        remove_file(test_container_recipe)

        # commands to install EasyBuild can be customized via 'eb_install' keyword
        args[-1] = 'bootstrap=yum,osversion=7.6.1810,install_eb=easy_install easybuild'
        stdout, stderr = self.run_main(args, raise_error=True)
        txt = read_file(test_container_recipe)

        for pattern in pip_patterns:
            regex = re.compile('^' + pattern, re.M)
            self.assertFalse(regex.search(txt), "Pattern '%s' should not be found in: %s" % (regex.pattern, txt))

        for pattern in ["easy_install easybuild", eb_pattern]:
            regex = re.compile('^' + pattern, re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' should be found in: %s" % (regex.pattern, txt))

        remove_file(test_container_recipe)

        # post commands be be customized via 'post_commands' keyword
        args[-1] = 'bootstrap=yum,osversion=7.6.1810,post_commands=id easybuild'
        stdout, stderr = self.run_main(args, raise_error=True)
        txt = read_file(test_container_recipe)

        for pattern in post_commands_patterns:
            regex = re.compile('^' + pattern, re.M)
            self.assertFalse(regex.search(txt), "Pattern '%s' should not be found in: %s" % (regex.pattern, txt))

        for pattern in ["id easybuild", eb_pattern]:
            regex = re.compile('^' + pattern, re.M)
            self.assertTrue(regex.search(txt), "Pattern '%s' should be found in: %s" % (regex.pattern, txt))

        remove_file(test_container_recipe)

        # options can be passed to 'eb' command in recipe via 'eb_args' keyword
        args[-1] = 'bootstrap=yum,osversion=7.6.1810,eb_args=--debug -l'
        stdout, stderr = self.run_main(args, raise_error=True)
        txt = read_file(test_container_recipe)

        regex = re.compile(r"^eb toy-0.0.eb --robot --debug -l", re.M)
        self.assertTrue(regex.search(txt), "Pattern '%s' should be found in: %s" % (regex.pattern, txt))

    def test_end2end_singularity_image(self):
        """End-to-end test for --containerize (recipe + image)."""
        topdir = os.path.dirname(os.path.abspath(__file__))
        toy_ec = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        containerpath = os.path.join(self.test_prefix, 'containers')
        os.environ['EASYBUILD_CONTAINERPATH'] = containerpath
        # --containerpath must be an existing directory (this is done to avoid misconfiguration)
        mkdir(containerpath)

        test_img = os.path.join(self.test_prefix, 'test123.img')
        write_file(test_img, '')

        args = [
            toy_ec,
            '-C',  # equivalent with --containerize
            '--experimental',
            '--container-config=bootstrap=localimage,from=%s' % test_img,
            '--container-build-image',
        ]

        if which('singularity') is None:
            error_pattern = "singularity with version 2.4 or higher not found on your system."
            self.assertErrorRegex(EasyBuildError, error_pattern, self.eb_main, args, raise_error=True)

        # install mocked versions of 'sudo' and 'singularity' commands
        singularity = os.path.join(self.test_prefix, 'bin', 'singularity')
        write_file(singularity, '')  # placeholder
        adjust_permissions(singularity, stat.S_IXUSR, add=True)

        sudo = os.path.join(self.test_prefix, 'bin', 'sudo')
        write_file(sudo, '#!/bin/bash\necho "running command \'$@\' with sudo..."\neval "$@"\n')
        adjust_permissions(sudo, stat.S_IXUSR, add=True)

        os.environ['PATH'] = os.path.pathsep.join([os.path.join(self.test_prefix, 'bin'), os.getenv('PATH')])

        for (version, ext) in [('2.4.0', 'simg'), ('3.1.0', 'sif')]:
            write_file(singularity, MOCKED_SINGULARITY % {'version': version})

            stdout, stderr = self.run_main(args)
            self.assertFalse(stderr)
            regexs = [
                r"^== singularity tool found at %s/bin/singularity" % self.test_prefix,
                r"^== singularity version '%s' is 2.4 or higher ... OK" % version,
                r"^== Singularity definition file created at %s/containers/Singularity\.toy-0.0" % self.test_prefix,
                r"^== Running 'sudo\s*\S*/singularity build\s*/.* /.*', you may need to enter your 'sudo' password...",
                r"^== Singularity image created at %s/containers/toy-0.0\.%s" % (self.test_prefix, ext),
            ]
            self.check_regexs(regexs, stdout)

            self.assertTrue(os.path.exists(os.path.join(containerpath, 'toy-0.0.%s' % ext)))

            remove_file(os.path.join(containerpath, 'Singularity.toy-0.0'))

        # check use of --container-image-format & --container-image-name
        write_file(singularity, MOCKED_SINGULARITY % {'version': '2.4.0'})
        args.extend([
            "--container-image-format=ext3",
            "--container-image-name=foo-bar",
        ])
        stdout, stderr = self.run_main(args)
        self.assertFalse(stderr)
        regexs = [
            r"^== singularity tool found at %s/bin/singularity" % self.test_prefix,
            r"^== singularity version '2.4.0' is 2.4 or higher ... OK",
            r"^== Singularity definition file created at %s/containers/Singularity\.foo-bar" % self.test_prefix,
            r"^== Running 'sudo\s*\S*/singularity build --writable /.* /.*', you may need to enter .*",
            r"^== Singularity image created at %s/containers/foo-bar\.img$" % self.test_prefix,
        ]
        self.check_regexs(regexs, stdout)

        cont_img = os.path.join(containerpath, 'foo-bar.img')
        self.assertTrue(os.path.exists(cont_img))

        remove_file(os.path.join(containerpath, 'Singularity.foo-bar'))

        # test again with container image already existing

        error_pattern = "Container image already exists at %s, not overwriting it without --force" % cont_img
        self.mock_stdout(True)
        self.assertErrorRegex(EasyBuildError, error_pattern, self.run_main, args, raise_error=True)
        self.mock_stdout(False)

        args.append('--force')
        stdout, stderr = self.run_main(args)
        self.assertFalse(stderr)
        regexs.extend([
            "WARNING: overwriting existing container image at %s due to --force" % cont_img,
        ])
        self.check_regexs(regexs, stdout)
        self.assertTrue(os.path.exists(cont_img))

        # also check behaviour under --extended-dry-run
        args.append('--extended-dry-run')
        stdout, stderr = self.run_main(args)
        self.assertFalse(stderr)
        self.check_regexs(regexs, stdout)

        # test use of --container-tmpdir
        args.append('--container-tmpdir=%s' % self.test_prefix)
        stdout, stderr = self.run_main(args)
        self.assertFalse(stderr)
        regexs[-3] = r"^== Running 'sudo\s*SINGULARITY_TMPDIR=%s \S*/singularity build .*" % self.test_prefix
        self.check_regexs(regexs, stdout)

    def test_end2end_dockerfile(self):
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')

        containerpath = os.path.join(self.test_prefix, 'containers')
        os.environ['EASYBUILD_CONTAINERPATH'] = containerpath
        # --containerpath must be an existing directory (this is done to avoid misconfiguration)
        mkdir(containerpath)

        base_args = [
            toy_ec,
            '--containerize',
            '--container-type=docker',
            '--experimental',
        ]

        error_pattern = "Unsupported container config 'not-supported'"
        self.assertErrorRegex(EasyBuildError,
                              error_pattern,
                              self.run_main,
                              base_args + ['--container-config=not-supported'],
                              raise_error=True)

        for cont_base in ['ubuntu:16.04', 'centos:7']:
            stdout, stderr = self.run_main(base_args + ['--container-config=%s' % cont_base])
            self.assertFalse(stderr)
            regexs = ["^== Dockerfile definition file created at %s/containers/Dockerfile.toy-0.0" % self.test_prefix]
            self.check_regexs(regexs, stdout)
            remove_file(os.path.join(self.test_prefix, 'containers', 'Dockerfile.toy-0.0'))

        self.run_main(base_args + ['--container-config=centos:7'])

        error_pattern = "Container recipe at %s/containers/Dockerfile.toy-0.0 already exists, " \
                        "not overwriting it without --force" % self.test_prefix
        self.assertErrorRegex(EasyBuildError,
                              error_pattern,
                              self.run_main,
                              base_args + ['--container-config=centos:7'],
                              raise_error=True)

        remove_file(os.path.join(self.test_prefix, 'containers', 'Dockerfile.toy-0.0'))

        base_args.insert(1, os.path.join(test_ecs, 'g', 'GCC', 'GCC-4.9.2.eb'))
        self.run_main(base_args + ['--container-config=ubuntu:16.04'])
        def_file = read_file(os.path.join(self.test_prefix, 'containers', 'Dockerfile.toy-0.0'))
        regexs = [
            "FROM ubuntu:16.04",
            "eb toy-0.0.eb GCC-4.9.2.eb",
            "module load toy/0.0 GCC/4.9.2",
        ]
        self.check_regexs(regexs, def_file)

        # there should be no leading/trailing whitespace included
        for pattern in [r'^\s+', r'\s+$']:
            regex = re.compile(pattern)
            self.assertFalse(regex.search(def_file), "Pattern '%s' should *not* be found in: %s" % (pattern, def_file))

    def test_end2end_docker_image(self):

        topdir = os.path.dirname(os.path.abspath(__file__))
        toy_ec = os.path.join(topdir, 'easyconfigs', 'test_ecs', 't', 'toy', 'toy-0.0.eb')

        containerpath = os.path.join(self.test_prefix, 'containers')
        os.environ['EASYBUILD_CONTAINERPATH'] = containerpath
        # --containerpath must be an existing directory (this is done to avoid misconfiguration)
        mkdir(containerpath)

        args = [
            toy_ec,
            '-C',  # equivalent with --containerize
            '--experimental',
            '--container-type=docker',
            '--container-config=ubuntu:16.04',
            '--container-build-image',
        ]

        if not which('docker'):
            error_pattern = "docker not found on your system."
            self.assertErrorRegex(EasyBuildError, error_pattern, self.run_main, args, raise_error=True)

        # install mocked versions of 'sudo' and 'docker' commands
        docker = os.path.join(self.test_prefix, 'bin', 'docker')
        write_file(docker, MOCKED_DOCKER)
        adjust_permissions(docker, stat.S_IXUSR, add=True)

        sudo = os.path.join(self.test_prefix, 'bin', 'sudo')
        write_file(sudo, '#!/bin/bash\necho "running command \'$@\' with sudo..."\neval "$@"\n')
        adjust_permissions(sudo, stat.S_IXUSR, add=True)

        os.environ['PATH'] = os.path.pathsep.join([os.path.join(self.test_prefix, 'bin'), os.getenv('PATH')])

        stdout, stderr = self.run_main(args)
        self.assertFalse(stderr)
        regexs = [
            r"^== docker tool found at %s/bin/docker" % self.test_prefix,
            r"^== Dockerfile definition file created at %s/containers/Dockerfile\.toy-0.0" % self.test_prefix,
            r"^== Running 'sudo docker build -f .* -t .* \.', you may need to enter your 'sudo' password...",
            r"^== Docker image created at toy-0.0:latest",
        ]
        self.check_regexs(regexs, stdout)

        args.extend(['--force', '--extended-dry-run'])
        stdout, stderr = self.run_main(args)
        self.assertFalse(stderr)
        self.check_regexs(regexs, stdout)

    def test_container_config_template_recipe(self):
        """Test use of --container-config and --container-template-recipe."""
        tmpl_path = os.path.join(self.test_prefix, 'tmpl.txt')
        tmpl_txt = '\n'.join([
            "# this is just a test",
            "bootstrap: %(bootstrap)s",
            "from: %(from)s",
            '',
            '%%post',
            "eb %(easyconfigs)s --robot --debug -l",
        ])
        write_file(tmpl_path, tmpl_txt)
        args = [
            '--experimental',
            '--containerize',
            '--container-template-recipe=%s' % tmpl_path,
            'toy-0.0.eb',
        ]
        error_pattern = "--container-config must be specified!"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.run_main, args)

        args.extend(['--container-config', 'bootstrap=localimage,from=foobar'])
        stdout, stderr = self.run_main(args)

        self.assertFalse(stderr)
        regex = re.compile("^== Singularity definition file created at .*/containers/Singularity.toy-0.0$")
        self.assertTrue(regex.match(stdout), "Stdout matches pattern '%s': %s" % (regex.pattern, stdout))

        expected = '\n'.join([
            "# this is just a test",
            "bootstrap: localimage",
            "from: foobar",
            "",
            "%post",
            "eb toy-0.0.eb --robot --debug -l",
        ])
        cont_recipe = read_file(os.path.join(self.test_prefix, 'containers', 'Singularity.toy-0.0'))
        self.assertEqual(cont_recipe, expected)


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(ContainersTest, sys.argv[1:])


if __name__ == '__main__':
    res = TextTestRunner(verbosity=1).run(suite())
    sys.exit(len(res.failures))
