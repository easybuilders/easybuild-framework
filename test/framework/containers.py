# #
# Copyright 2018-2018 Ghent University
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
from easybuild.tools.containers.singularity import parse_container_base


MOCKED_SINGULARITY = """#!/bin/bash
if [[ $1 == '--version' ]]; then
    echo "2.4.0"
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

    def test_parse_container_base(self):
        """Test parse_container_base function."""

        for base_spec in [None, '']:
            self.assertErrorRegex(EasyBuildError, "--container-base must be specified", parse_container_base, base_spec)

        # format of base spec must be correct: <bootstrap_agent>:<arg> or <bootstrap_agent>:<arg1>:<arg2>
        error_regex = "Invalid format for --container-base"
        for base_spec in ['foo', 'foo:bar:baz:sjee']:
            self.assertErrorRegex(EasyBuildError, error_regex, parse_container_base, base_spec)

        # bootstrap agent must be known
        error_regex = "Bootstrap agent in container base spec must be one of: docker, localimage, shub"
        self.assertErrorRegex(EasyBuildError, error_regex, parse_container_base, 'foo:bar')

        # check parsing of 'localimage' base spec
        expected = {'bootstrap_agent': 'localimage', 'arg1': '/path/to/base.img'}
        self.assertEqual(parse_container_base('localimage:/path/to/base.img'), expected)

        # check parsing of 'docker' and 'shub' base spec (2nd argument, image tag, is optional)
        for agent in ['docker', 'shub']:
            expected = {'bootstrap_agent': agent, 'arg1': 'foo'}
            self.assertEqual(parse_container_base('%s:foo' % agent), expected)
            expected.update({'arg2': 'bar'})
            self.assertEqual(parse_container_base('%s:foo:bar' % agent), expected)

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

    def test_end2end_singularity_recipe(self):
        """End-to-end test for --containerize (recipe only)."""
        test_ecs = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'easyconfigs', 'test_ecs')
        toy_ec = os.path.join(test_ecs, 't', 'toy', 'toy-0.0.eb')

        containerpath = os.path.join(self.test_prefix, 'containers')
        os.environ['EASYBUILD_CONTAINERPATH'] = containerpath
        # --containerpath must be an existing directory (this is done to avoid misconfiguration)
        mkdir(containerpath)

        args = [
            toy_ec,
            '--containerize',
            '--experimental',
        ]

        error_pattern = "--container-base must be specified"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.run_main, args, raise_error=True)

        # generating Singularity definition file with 'docker' or 'shub' bootstrap agents always works,
        # i.e. image label is not verified, image tag can be anything
        for cont_base in ['docker:test123', 'docker:test123:foo', 'shub:test123', 'shub:test123:foo']:
            stdout, stderr = self.run_main(args + ['--container-base=%s' % cont_base])

            self.assertFalse(stderr)
            regexs = ["^== Singularity definition file created at %s/containers/Singularity.toy-0.0" % self.test_prefix]
            self.check_regexs(regexs, stdout)

            remove_file(os.path.join(self.test_prefix, 'containers', 'Singularity.toy-0.0'))

        args.append("--container-base=shub:test123")
        self.run_main(args)

        # existing definition file is not overwritten without use of --force
        error_pattern = "Container recipe at .* already exists, not overwriting it without --force"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.run_main, args, raise_error=True)

        stdout, stderr = self.run_main(args + ['--force'])
        self.assertFalse(stderr)
        regexs = [
            "^== WARNING: overwriting existing container recipe at .* due to --force",
            "^== Singularity definition file created at %s/containers/Singularity.toy-0.0" % self.test_prefix,
        ]
        self.check_regexs(regexs, stdout)

        remove_file(os.path.join(self.test_prefix, 'containers', 'Singularity.toy-0.0'))

        # add another easyconfig file to check if multiple easyconfigs are handled correctly
        args.insert(1, os.path.join(test_ecs, 'g', 'GCC', 'GCC-4.9.2.eb'))

        # with 'localimage' bootstrap agent, specified image must exist
        test_img = os.path.join(self.test_prefix, 'test123.img')
        args[-1] = "--container-base=localimage:%s" % test_img
        error_pattern = "Singularity base image at specified path does not exist"
        self.assertErrorRegex(EasyBuildError, error_pattern, self.run_main, args, raise_error=True)

        write_file(test_img, '')
        stdout, stderr = self.run_main(args)
        self.assertFalse(stderr)
        regexs = ["^== Singularity definition file created at %s/containers/Singularity.toy-0.0" % self.test_prefix]
        self.check_regexs(regexs, stdout)

        # check contents of generated recipe
        def_file = read_file(os.path.join(self.test_prefix, 'containers', 'Singularity.toy-0.0'))
        regexs = [
            "^Bootstrap: localimage$",
            "^From: %s$" % test_img,
            "^eb toy-0.0.eb GCC-4.9.2.eb",
            "module load toy/0.0 GCC/4.9.2$",
        ]
        self.check_regexs(regexs, def_file)

        # image extension must make sense when localimage is used
        for img_name in ['test123.foo', 'test123']:
            test_img = os.path.join(self.test_prefix, img_name)
            args[-1] = "--container-base=localimage:%s" % test_img
            write_file(test_img, '')
            error_pattern = "Invalid image extension '.*' must be \.img or \.simg"
            self.assertErrorRegex(EasyBuildError, error_pattern, self.run_main, args, raise_error=True)

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
            '--container-base=localimage:%s' % test_img,
            '--container-build-image',
        ]

        if which('singularity') is None:
            error_pattern = "singularity with version 2.4 or higher not found on your system."
            self.assertErrorRegex(EasyBuildError, error_pattern, self.eb_main, args, raise_error=True)

        # install mocked versions of 'sudo' and 'singularity' commands
        singularity = os.path.join(self.test_prefix, 'bin', 'singularity')
        write_file(singularity, MOCKED_SINGULARITY)
        adjust_permissions(singularity, stat.S_IXUSR, add=True)

        sudo = os.path.join(self.test_prefix, 'bin', 'sudo')
        write_file(sudo, '#!/bin/bash\necho "running command \'$@\' with sudo..."\neval "$@"\n')
        adjust_permissions(sudo, stat.S_IXUSR, add=True)

        os.environ['PATH'] = os.path.pathsep.join([os.path.join(self.test_prefix, 'bin'), os.getenv('PATH')])

        stdout, stderr = self.run_main(args)
        self.assertFalse(stderr)
        regexs = [
            "^== singularity tool found at %s/bin/singularity" % self.test_prefix,
            "^== singularity version '2.4.0' is 2.4 or higher ... OK",
            "^== Singularity definition file created at %s/containers/Singularity\.toy-0.0" % self.test_prefix,
            "^== Running 'sudo\s*\S*/singularity build\s*/.* /.*', you may need to enter your 'sudo' password...",
            "^== Singularity image created at %s/containers/toy-0.0\.simg" % self.test_prefix,
        ]
        self.check_regexs(regexs, stdout)

        self.assertTrue(os.path.exists(os.path.join(containerpath, 'toy-0.0.simg')))

        remove_file(os.path.join(containerpath, 'Singularity.toy-0.0'))

        # check use of --container-image-format & --container-image-name
        args.extend([
            "--container-image-format=ext3",
            "--container-image-name=foo-bar",
        ])
        stdout, stderr = self.run_main(args)
        self.assertFalse(stderr)
        regexs[-3] = "^== Singularity definition file created at %s/containers/Singularity\.foo-bar" % self.test_prefix
        regexs[-2] = "^== Running 'sudo\s*\S*/singularity build --writable /.* /.*', you may need to enter .*"
        regexs[-1] = "^== Singularity image created at %s/containers/foo-bar\.img$" % self.test_prefix
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
        regexs[-3] = "^== Running 'sudo\s*SINGULARITY_TMPDIR=%s \S*/singularity build .*" % self.test_prefix
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

        error_pattern = "Unsupported container base image 'not-supported'"
        self.assertErrorRegex(EasyBuildError,
                              error_pattern,
                              self.run_main,
                              base_args + ['--container-base=not-supported'],
                              raise_error=True)

        for cont_base in ['ubuntu:16.04', 'centos:7']:
            stdout, stderr = self.run_main(base_args + ['--container-base=%s' % cont_base])
            self.assertFalse(stderr)
            regexs = ["^== Dockerfile definition file created at %s/containers/Dockerfile.toy-0.0" % self.test_prefix]
            self.check_regexs(regexs, stdout)
            remove_file(os.path.join(self.test_prefix, 'containers', 'Dockerfile.toy-0.0'))

        self.run_main(base_args + ['--container-base=centos:7'])

        error_pattern = "Container recipe at %s/containers/Dockerfile.toy-0.0 already exists, " \
                        "not overwriting it without --force" % self.test_prefix
        self.assertErrorRegex(EasyBuildError,
                              error_pattern,
                              self.run_main,
                              base_args + ['--container-base=centos:7'],
                              raise_error=True)

        remove_file(os.path.join(self.test_prefix, 'containers', 'Dockerfile.toy-0.0'))

        base_args.insert(1, os.path.join(test_ecs, 'g', 'GCC', 'GCC-4.9.2.eb'))
        self.run_main(base_args + ['--container-base=ubuntu:16.04'])
        def_file = read_file(os.path.join(self.test_prefix, 'containers', 'Dockerfile.toy-0.0'))
        regexs = [
            "FROM ubuntu:16.04",
            "eb toy-0.0.eb GCC-4.9.2.eb",
            "module load toy/0.0 GCC/4.9.2",
        ]
        self.check_regexs(regexs, def_file)

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
            '--container-base=ubuntu:16.04',
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
            "^== docker tool found at %s/bin/docker" % self.test_prefix,
            "^== Dockerfile definition file created at %s/containers/Dockerfile\.toy-0.0" % self.test_prefix,
            "^== Running 'sudo docker build -f .* -t .* \.', you may need to enter your 'sudo' password...",
            "^== Docker image created at toy-0.0:latest",
        ]
        self.check_regexs(regexs, stdout)

        args.extend(['--force', '--extended-dry-run'])
        stdout, stderr = self.run_main(args)
        self.assertFalse(stderr)
        self.check_regexs(regexs, stdout)


def suite():
    """ returns all the testcases in this module """
    return TestLoaderFiltered().loadTestsFromTestCase(ContainersTest, sys.argv[1:])


if __name__ == '__main__':
    TextTestRunner(verbosity=1).run(suite())
