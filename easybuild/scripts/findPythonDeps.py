#!/usr/bin/env python

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pprint import pprint
try:
    import pkg_resources
except ImportError as e:
    print('pkg_resources could not be imported: %s\nYou might need to install setuptools!' % e)
    sys.exit(1)

try:
    from packaging.utils import canonicalize_name
except ImportError:
    _canonicalize_regex = re.compile(r"[-_.]+")

    def canonicalize_name(name):
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
    return re.split('<|>|=|~', args.package, 1)[0]


def can_run(cmd, argument):
    """Check if the given cmd and argument can be run successfully"""
    with open(os.devnull, 'w') as FNULL:
        try:
            return subprocess.call([cmd, argument], stdout=FNULL, stderr=subprocess.STDOUT) == 0
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
        raise RuntimeError('Failed to %s: %s%s' % (action_desc, out, err))
    return out


def run_in_venv(cmd, venv_path, action_desc):
    """Run the given command in the virtualenv at the given path"""
    cmd = 'source %s/bin/activate && %s' % (venv_path, cmd)
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
        run_cmd(['virtualenv', '--system-site-packages', venv_dir], action_desc='create virtualenv')
        if verbose:
            print('Updating pip in virtualenv')
        run_in_venv('pip install --upgrade pip', venv_dir, action_desc='update pip')
        if verbose:
            print('Installing %s into virtualenv' % package_spec)
        out = run_in_venv('pip install "%s"' % package_spec, venv_dir, action_desc='install ' + package_spec)
        print('%s installed: %s' % (package_spec, out))
        # install pipdeptree, figure out dependency tree for installed package
        run_in_venv('pip install pipdeptree', venv_dir, action_desc='install pipdeptree')
        dep_tree = run_in_venv('pipdeptree -j -p "%s"' % package_name,
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
                raise RuntimeError("Aborting after checking %s packages. Possibly cycle detected!" % MAX_PACKAGES)
            pkg = canonicalize_name(orig_pkg)
            matching_entries = [entry for entry in dep_tree
                                if pkg in (entry['package']['package_name'], entry['package']['key'])]
            if not matching_entries:
                matching_entries = [entry for entry in dep_tree
                                    if orig_pkg in (entry['package']['package_name'], entry['package']['key'])]
            if not matching_entries:
                raise RuntimeError("Found no installed package for '%s' in %s" % (pkg, dep_tree))
            if len(matching_entries) > 1:
                raise RuntimeError("Found multiple installed packages for '%s' in %s" % (pkg, dep_tree))
            entry = matching_entries[0]
            res.append((entry['package']['package_name'], entry['package']['installed_version']))
            # Add dependencies to list of packages to check next
            # Could call this function recursively but that might exceed the max recursion depth
            next_pkgs.update(dep['package_name'] for dep in entry['dependencies'])
    return res


def print_deps(package, verbose):
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
        if dep not in handled:
            handled.add(dep)
            if dep[0] in installed_modules:
                if verbose:
                    print("Skipping installed module '%s'" % dep[0])
            else:
                res.append(dep)

    print("List of dependencies in (likely) install order:")
    pprint(res, indent=4)
    print("Sorted list of dependencies:")
    pprint(sorted(res), indent=4)


examples = [
    'Example usage with EasyBuild (after installing dependency modules):',
    '\t' + sys.argv[0] + ' --ec TensorFlow-2.3.4.eb tensorflow==2.3.4',
    'Which is the same as:',
    '\t' + ' && '.join(['eb TensorFlow-2.3.4.eb --dump-env',
                        'source TensorFlow-2.3.4.env',
                        sys.argv[0] + ' tensorflow==2.3.4',
                        ]),
]
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
    excluded_dep = '(%s)' % os.path.basename(args.ec)
    missing_deps = [dep for dep in missing_dep_out.split('\n')
                    if dep.startswith('*') and excluded_dep not in dep
                    ]
    if missing_deps:
        print('You need to install all modules on which %s depends first!' % args.ec)
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

        cmd = "source %s/*.env && python %s '%s'" % (tmp_dir, sys.argv[0], args.package)
        if args.verbose:
            cmd += ' --verbose'
            print('Restarting script in new build environment')

        out = run_cmd(cmd, action_desc='Run in new environment', shell=True, executable='/bin/bash')
        print(out)
else:
    if not can_run('virtualenv', '--version'):
        print('Virtualenv not found or executable. ' +
              'Make sure it is installed (e.g. in the currently loaded Python module)!')
        sys.exit(1)
    if 'PIP_PREFIX' in os.environ:
        print("$PIP_PREFIX is set. Unsetting it as it doesn't work well with virtualenv.")
        del os.environ['PIP_PREFIX']
    print_deps(args.package, args.verbose)
