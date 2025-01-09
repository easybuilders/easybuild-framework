#!/usr/bin/env python
##
# Copyright 2021-2025 Alexander Grund
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
##
"""
Find Python dependencies for a given Python package after loading dependencies specified in an EasyConfig.
This is intended for writing or updating PythonBundle EasyConfigs:
    1. Create a EasyConfig with at least 'Python' as a dependency.
       When updating to a new toolchain it is a good idea to reduce the dependencies to a minimum
       as e.g. the new "Python" module might have different packages included.
    2. Run this script
    3. For each dependency found by this script search existing EasyConfigs for ones providing that Python package.
       E.g many are contained in Python-bundle-PyPI. Some can be updated from an earlier toolchain.
    4. Add those EasyConfigs as dependencies to your new EasyConfig.
    5. Rerun this script so it takes the newly provided packages into account.
       You can do steps 3-5 iteratively adding EasyConfig-dependencies one-by-one.
    6. Finally you copy the packages found by this script as "exts_list" into the new EasyConfig.
       You usually want the list printed as "in install order", the format is already suitable to be copied as-is.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from contextlib import contextmanager
from pprint import pprint
try:
    import pkg_resources
except ImportError as e:
    print(f'pkg_resources could not be imported: {e}\nYou might need to install setuptools!')
    sys.exit(1)

try:
    from packaging.utils import canonicalize_name
except ImportError:
    _canonicalize_regex = re.compile(r"[-_.]+")

    def canonicalize_name(name):
        """Fallback if the import doesn't work with same behavior."""
        return _canonicalize_regex.sub("-", name).lower()


@contextmanager
def temporary_directory(*args, **kwargs):
    """Resource wrapper over tempfile.mkdtemp"""
    name = tempfile.mkdtemp(*args, **kwargs)
    try:
        yield name
    finally:
        shutil.rmtree(name)


def extract_pkg_name(package_spec):
    """Get the package name from a specification such as 'package>=3.42'"""
    return re.split('<|>|=|~', package_spec, 1)[0]


def can_run(cmd, *arguments):
    """Check if the given cmd and argument can be run successfully"""
    try:
        return subprocess.call([cmd, *arguments], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) == 0
    except (subprocess.CalledProcessError, OSError):
        return False


def run_cmd(arguments, action_desc, capture_stderr=True, **kwargs):
    """Run the command and return the return code and output"""
    extra_args = kwargs or {}
    if sys.version_info[0] >= 3:
        extra_args['universal_newlines'] = True
    stderr = subprocess.STDOUT if capture_stderr else subprocess.PIPE
    p = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=stderr, **extra_args)
    out, err = p.communicate()
    if p.returncode != 0:
        if err:
            err = "\nSTDERR:\n" + err
        raise RuntimeError(f'Failed to {action_desc}: {out}{err}')
    return out


def run_in_venv(cmd, venv_path, action_desc):
    """Run the given command in the virtualenv at the given path"""
    cmd = f'source {venv_path}/bin/activate && {cmd}'
    return run_cmd(cmd, action_desc, shell=True, executable='/bin/bash')


def get_dep_tree(package_spec, verbose):
    """Get the dep-tree for installing the given Python package spec"""
    package_name = extract_pkg_name(package_spec)
    with temporary_directory(suffix=package_name + '-deps') as tmp_dir:
        # prevent pip from (ab)using $HOME/.cache/pip
        os.environ['XDG_CACHE_HOME'] = os.path.join(tmp_dir, 'pip-cache')
        venv_dir = os.path.join(tmp_dir, 'venv')
        if verbose:
            print('Creating virtualenv at ' + venv_dir)
        run_cmd([sys.executable, '-m', 'venv', '--system-site-packages', venv_dir], action_desc='create virtualenv')
        if verbose:
            print('Updating pip in virtualenv')
        run_in_venv('pip install --upgrade pip', venv_dir, action_desc='update pip')
        if verbose:
            print(f'Installing {package_spec} into virtualenv')
        out = run_in_venv(f'pip install "{package_spec}"', venv_dir, action_desc='install ' + package_spec)
        print(f'{package_spec} installed: {out}')
        # install pipdeptree, figure out dependency tree for installed package
        run_in_venv('pip install pipdeptree', venv_dir, action_desc='install pipdeptree')
        dep_tree = run_in_venv(f'pipdeptree -j -p "{package_name}"',
                               venv_dir, action_desc='collect dependencies')
    return json.loads(dep_tree)


def find_deps(pkgs, dep_tree):
    """Recursively resolve dependencies of the given package(s) and return them"""
    MAX_PACKAGES = 1000
    res = []
    next_pkgs = set(pkgs)
    # Don't check any package multiple times to avoid infinite recursion
    seen_pkgs = set()
    count = 0
    while next_pkgs:
        cur_pkgs = next_pkgs - seen_pkgs
        seen_pkgs.update(cur_pkgs)
        next_pkgs = set()
        for orig_pkg in cur_pkgs:
            count += 1
            if count > MAX_PACKAGES:
                raise RuntimeError(f"Aborting after checking {MAX_PACKAGES} packages. Possibly cycle detected!")
            pkg = canonicalize_name(orig_pkg)
            matching_entries = [entry for entry in dep_tree
                                if pkg in (entry['package']['package_name'], entry['package']['key'])]
            if not matching_entries:
                matching_entries = [entry for entry in dep_tree
                                    if orig_pkg in (entry['package']['package_name'], entry['package']['key'])]
            if not matching_entries:
                raise RuntimeError(f"Found no installed package for '{pkg}' in {dep_tree}")
            if len(matching_entries) > 1:
                raise RuntimeError(f"Found multiple installed packages for '{pkg}' in {dep_tree}")
            entry = matching_entries[0]
            res.append(entry['package'])
            # Add dependencies to list of packages to check next
            # Could call this function recursively but that might exceed the max recursion depth
            next_pkgs.update(dep['package_name'] for dep in entry['dependencies'])
    return res


def print_deps(package, verbose):
    """Print dependencies of the given package that are not installed yet in a format usable as 'exts_list'"""
    if verbose:
        print('Getting dep tree of ' + package)
    dep_tree = get_dep_tree(package, verbose)
    if verbose:
        print('Extracting dependencies of ' + package)
    deps = find_deps([extract_pkg_name(package)], dep_tree)

    installed_modules = {mod.project_name for mod in pkg_resources.working_set}
    if verbose:
        print("Installed modules: " + ', '.join(sorted(installed_modules)))

    # iterate over deps in reverse order, get rid of duplicates along the way
    # also filter out Python packages that are already installed in current environment
    res = []
    handled = set()
    for dep in reversed(deps):
        # Tuple as we need it for exts_list
        dep_entry = (dep['package_name'], dep['installed_version'])
        if dep_entry not in handled:
            handled.add(dep_entry)
            # Need to check for key and package_name as naming is not consistent. E.g.:
            # "PyQt5-sip":    'key': 'pyqt5-sip',    'package_name': 'PyQt5-sip'
            # "jupyter-core": 'key': 'jupyter-core', 'package_name': 'jupyter_core'
            if dep['key'] in installed_modules or dep['package_name'] in installed_modules:
                if verbose:
                    print(f"Skipping installed module '{dep['package_name']}'")
            else:
                res.append(dep_entry)

    print("List of dependencies in (likely) install order:")
    pprint(res, indent=4)
    print("Sorted list of dependencies:")
    pprint(sorted(res), indent=4)


def main():
    """Entrypoint of the script"""
    examples = textwrap.dedent(f"""
        Example usage with EasyBuild (after installing dependency modules):
            {sys.argv[0]} --ec TensorFlow-2.3.4.eb tensorflow==2.3.4
        Which is the same as:
            eb TensorFlow-2.3.4.eb --dump-env && source TensorFlow-2.3.4.env && {sys.argv[0]} tensorflow==2.3.4
        Using the '--ec' parameter is recommended as the latter requires manually updating the .env file
        after each change to the EasyConfig.
    """)
    parser = argparse.ArgumentParser(
        description='Find dependencies of Python packages by installing it in a temporary virtualenv. ',
        epilog='\n'.join(examples),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('package', metavar='python-pkg-spec',
                        help='Python package spec, e.g. tensorflow==2.3.4')
    parser.add_argument('--ec', metavar='easyconfig', help='EasyConfig to use as the build environment. '
                        'You need to have dependency modules installed already!')
    parser.add_argument('--verbose', help='Verbose output', action='store_true')
    args = parser.parse_args()

    if args.ec:
        if not can_run('eb', '--version'):
            print('EasyBuild not found or executable. Make sure it is in your $PATH when using --ec!')
            sys.exit(1)
        if args.verbose:
            print('Checking with EasyBuild for missing dependencies')
        missing_dep_out = run_cmd(['eb', args.ec, '--missing'],
                                  capture_stderr=False,
                                  action_desc='Get missing dependencies'
                                  )
        excluded_dep = f'({os.path.basename(args.ec)})'
        missing_deps = [dep for dep in missing_dep_out.split('\n')
                        if dep.startswith('*') and excluded_dep not in dep
                        ]
        if missing_deps:
            print(f'You need to install all modules on which {args.ec} depends first!')
            print('\n\t'.join(['Missing:'] + missing_deps))
            sys.exit(1)

        # If the --ec argument is a (relative) existing path make it absolute so we can find it after the chdir
        ec_arg = os.path.abspath(args.ec) if os.path.exists(args.ec) else args.ec
        with temporary_directory() as tmp_dir:
            old_dir = os.getcwd()
            os.chdir(tmp_dir)
            if args.verbose:
                print('Running EasyBuild to get build environment')
            run_cmd(['eb', ec_arg, '--dump-env', '--force'], action_desc='Dump build environment')
            os.chdir(old_dir)

            cmd = f"source {tmp_dir}/*.env && python {sys.argv[0]} '{args.package}'"
            if args.verbose:
                cmd += ' --verbose'
                print('Restarting script in new build environment')

            out = run_cmd(cmd, action_desc='Run in new environment', shell=True, executable='/bin/bash')
            print(out)
    else:
        if not can_run(sys.executable, '-m', 'venv', '-h'):
            print("'venv' module not found. This should be available in Python 3.3+.")
            sys.exit(1)
        if 'PIP_PREFIX' in os.environ:
            print("$PIP_PREFIX is set. Unsetting it as it doesn't work well with virtualenv.")
            del os.environ['PIP_PREFIX']
        os.environ['PYTHONNOUSERSITE'] = '1'
        print_deps(args.package, args.verbose)


if __name__ == "__main__":
    main()
