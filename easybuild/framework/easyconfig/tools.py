# #
# Copyright 2009-2016 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://www.vscentrum.be),
# Flemish Research Foundation (FWO) (http://www.fwo.be/en)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/easybuild
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
Easyconfig module that provides functionality for dealing with easyconfig (.eb) files,
alongside the EasyConfig class to represent parsed easyconfig files.

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
@author: Fotis Georgatos (Uni.Lu, NTUA)
@author: Ward Poelmans (Ghent University)
"""
import copy
import glob
import os
import re
import sys
import tempfile
from distutils.version import LooseVersion
from vsc.utils import fancylogger

from easybuild.framework.easyconfig import EASYCONFIGS_PKG_SUBDIR
from easybuild.framework.easyconfig.easyconfig import ActiveMNS, create_paths, get_easyblock_class, process_easyconfig
from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import build_option
from easybuild.tools.environment import restore_env
from easybuild.tools.filetools import find_easyconfigs, which, write_file
from easybuild.tools.github import fetch_easyconfigs_from_pr, download_repo
from easybuild.tools.modules import modules_tool
from easybuild.tools.multidiff import multidiff
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME
from easybuild.tools.utilities import only_if_module_is_available, quote_str
from easybuild.tools.version import VERSION as EASYBUILD_VERSION

# optional Python packages, these might be missing
# failing imports are just ignored
# a NameError should be caught where these are used

try:
    # PyGraph (used for generating dependency graphs)
    # https://pypi.python.org/pypi/python-graph-core
    from pygraph.classes.digraph import digraph
    # https://pypi.python.org/pypi/python-graph-dot
    import pygraph.readwrite.dot as dot
    # graphviz (used for creating dependency graph images)
    sys.path.append('..')
    sys.path.append('/usr/lib/graphviz/python/')
    sys.path.append('/usr/lib64/graphviz/python/')
    # https://pypi.python.org/pypi/pygraphviz
    # graphviz-python (yum) or python-pygraphviz (apt-get)
    # or brew install graphviz --with-bindings (OS X)
    import gv
except ImportError:
    pass

_log = fancylogger.getLogger('easyconfig.tools', fname=False)


def skip_available(easyconfigs, modtool):
    """Skip building easyconfigs for existing modules."""
    module_names = [ec['full_mod_name'] for ec in easyconfigs]
    modules_exist = modtool.exist(module_names)
    retained_easyconfigs = []
    for ec, mod_name, mod_exists in zip(easyconfigs, module_names, modules_exist):
        if mod_exists:
            _log.info("%s is already installed (module found), skipping" % mod_name)
        else:
            _log.debug("%s is not installed yet, so retaining it" % mod_name)
            retained_easyconfigs.append(ec)
    return retained_easyconfigs


def find_resolved_modules(easyconfigs, avail_modules, modtool, retain_all_deps=False):
    """
    Find easyconfigs in 1st argument which can be fully resolved using modules specified in 2nd argument

    @param easyconfigs: list of parsed easyconfigs
    @param avail_modules: list of available modules
    @param retain_all_deps: retain all dependencies, regardless of whether modules are available for them or not
    """
    ordered_ecs = []
    new_easyconfigs = []
    # copy, we don't want to modify the origin list of available modules
    avail_modules = avail_modules[:]
    _log.debug("Finding resolved modules for %s (available modules: %s)", easyconfigs, avail_modules)

    ec_mod_names = [ec['full_mod_name'] for ec in easyconfigs]
    for easyconfig in easyconfigs:
        new_ec = easyconfig.copy()
        deps = []
        for dep in new_ec['dependencies']:
            dep_mod_name = dep.get('full_mod_name', ActiveMNS().det_full_module_name(dep))

            # treat external modules as resolved when retain_all_deps is enabled (e.g., under --dry-run),
            # since no corresponding easyconfig can be found for them
            if retain_all_deps and dep.get('external_module', False):
                _log.debug("Treating dependency marked as external dependency as resolved: %s", dep_mod_name)

            elif retain_all_deps and dep_mod_name not in avail_modules:
                # if all dependencies should be retained, include dep unless it has been already
                _log.debug("Retaining new dep %s in 'retain all deps' mode", dep_mod_name)
                deps.append(dep)

            # retain dep if it is (still) in the list of easyconfigs
            elif dep_mod_name in ec_mod_names:
                _log.debug("Dep %s is (still) in list of easyconfigs, retaining it", dep_mod_name)
                deps.append(dep)

            # retain dep if corresponding module is not available yet;
            # fallback to checking with modtool.exist is required,
            # for hidden modules and external modules where module name may be partial
            elif dep_mod_name not in avail_modules and not modtool.exist([dep_mod_name], skip_avail=True)[0]:
                # no module available (yet) => retain dependency as one to be resolved
                _log.debug("No module available for dep %s, retaining it", dep)
                deps.append(dep)

        # update list of dependencies with only those unresolved
        new_ec['dependencies'] = deps

        # if all dependencies have been resolved, add module for this easyconfig in the list of available modules
        if not new_ec['dependencies']:
            _log.debug("Adding easyconfig %s to final list" % new_ec['spec'])
            ordered_ecs.append(new_ec)
            mod_name = easyconfig['full_mod_name']
            avail_modules.append(mod_name)
            # remove module name from list, so dependencies can be marked as resolved
            ec_mod_names.remove(mod_name)

        else:
            new_easyconfigs.append(new_ec)

    return ordered_ecs, new_easyconfigs, avail_modules


@only_if_module_is_available('pygraph.classes.digraph', pkgname='python-graph-core')
def dep_graph(filename, specs):
    """
    Create a dependency graph for the given easyconfigs.
    """
    # check whether module names are unique
    # if so, we can omit versions in the graph
    names = set()
    for spec in specs:
        names.add(spec['ec']['name'])
    omit_versions = len(names) == len(specs)

    def mk_node_name(spec):
        if spec.get('external_module', False):
            node_name = "%s (EXT)" % spec['full_mod_name']
        elif omit_versions:
            node_name = spec['name']
        else:
            node_name = ActiveMNS().det_full_module_name(spec)

        return node_name

    # enhance list of specs
    all_nodes = set()
    for spec in specs:
        spec['module'] = mk_node_name(spec['ec'])
        all_nodes.add(spec['module'])
        spec['ec'].all_dependencies = [mk_node_name(s) for s in spec['ec'].all_dependencies]
        all_nodes.update(spec['ec'].all_dependencies)
        
        # Get the build dependencies for each spec so we can distinguish them later
        spec['ec'].build_dependencies = [mk_node_name(s) for s in spec['ec']['builddependencies']]
        all_nodes.update(spec['ec'].build_dependencies)

    # build directed graph
    dgr = digraph()
    dgr.add_nodes(all_nodes)
    for spec in specs:
        for dep in spec['ec'].all_dependencies:
            dgr.add_edge((spec['module'], dep))
            if dep in spec['ec'].build_dependencies:
                dgr.add_edge_attributes((spec['module'], dep), attrs=[('style','dotted'), ('color','blue'), ('arrowhead','diamond')])

    _dep_graph_dump(dgr, filename)

    if not build_option('silent'):
        print "Wrote dependency graph for %d easyconfigs to %s" % (len(specs), filename)


@only_if_module_is_available('pygraph.readwrite.dot', pkgname='python-graph-dot')
def _dep_graph_dump(dgr, filename):
    """Dump dependency graph to file, in specified format."""
    # write to file
    dottxt = dot.write(dgr)
    if os.path.splitext(filename)[-1] == '.dot':
        # create .dot file
        write_file(filename, dottxt)
    else:
        _dep_graph_gv(dottxt, filename)


@only_if_module_is_available('gv', pkgname='graphviz')
def _dep_graph_gv(dottxt, filename):
    """Render dependency graph to file using graphviz."""
    # try and render graph in specified file format
    gvv = gv.readstring(dottxt)
    gv.layout(gvv, 'dot')
    gv.render(gvv, os.path.splitext(filename)[-1], filename)


def get_paths_for(subdir=EASYCONFIGS_PKG_SUBDIR, robot_path=None):
    """
    Return a list of absolute paths where the specified subdir can be found, determined by the PYTHONPATH
    """

    paths = []

    # primary search path is robot path
    path_list = []
    if isinstance(robot_path, list):
        path_list = robot_path[:]
    elif robot_path is not None:
        path_list = [robot_path]
    # consider Python search path, e.g. setuptools install path for easyconfigs
    path_list.extend(sys.path)

    # figure out installation prefix, e.g. distutils install path for easyconfigs
    eb_path = which('eb')
    if eb_path is None:
        _log.warning("'eb' not found in $PATH, failed to determine installation prefix")
    else:
        # eb should reside in <install_prefix>/bin/eb
        install_prefix = os.path.dirname(os.path.dirname(eb_path))
        path_list.append(install_prefix)
        _log.debug("Also considering installation prefix %s..." % install_prefix)

    # look for desired subdirs
    for path in path_list:
        path = os.path.join(path, "easybuild", subdir)
        _log.debug("Checking for easybuild/%s at %s" % (subdir, path))
        try:
            if os.path.exists(path):
                paths.append(os.path.abspath(path))
                _log.debug("Added %s to list of paths for easybuild/%s" % (path, subdir))
        except OSError, err:
            raise EasyBuildError(str(err))

    return paths


def alt_easyconfig_paths(tmpdir, tweaked_ecs=False, from_pr=False):
    """Obtain alternative paths for easyconfig files."""
    # path where tweaked easyconfigs will be placed
    tweaked_ecs_path = None
    if tweaked_ecs:
        tweaked_ecs_path = os.path.join(tmpdir, 'tweaked_easyconfigs')

    # path where files touched in PR will be downloaded to
    pr_path = None
    if from_pr:
        pr_path = os.path.join(tmpdir, "files_pr%s" % from_pr)

    return tweaked_ecs_path, pr_path


def det_easyconfig_paths(orig_paths):
    """
    Determine paths to easyconfig files.
    @param orig_paths: list of original easyconfig paths
    @return: list of paths to easyconfig files
    """
    from_pr = build_option('from_pr')
    robot_path = build_option('robot_path')

    # list of specified easyconfig files
    ec_files = orig_paths[:]

    if from_pr is not None:
        pr_files = fetch_easyconfigs_from_pr(from_pr)

        if ec_files:
            # replace paths for specified easyconfigs that are touched in PR
            for i, ec_file in enumerate(ec_files):
                for pr_file in pr_files:
                    if ec_file == os.path.basename(pr_file):
                        ec_files[i] = pr_file
        else:
            # if no easyconfigs are specified, use all the ones touched in the PR
            ec_files = [path for path in pr_files if path.endswith('.eb')]

    if ec_files and robot_path:
        # look for easyconfigs with relative paths in robot search path,
        # unless they were found at the given relative paths

        # determine which easyconfigs files need to be found, if any
        ecs_to_find = []
        for idx, ec_file in enumerate(ec_files):
            if ec_file == os.path.basename(ec_file) and not os.path.exists(ec_file):
                ecs_to_find.append((idx, ec_file))
        _log.debug("List of easyconfig files to find: %s" % ecs_to_find)

        # find missing easyconfigs by walking paths in robot search path
        for path in robot_path:
            _log.debug("Looking for missing easyconfig files (%d left) in %s..." % (len(ecs_to_find), path))
            for (subpath, dirnames, filenames) in os.walk(path, topdown=True):
                for idx, orig_path in ecs_to_find[:]:
                    if orig_path in filenames:
                        full_path = os.path.join(subpath, orig_path)
                        _log.info("Found %s in %s: %s" % (orig_path, path, full_path))
                        ec_files[idx] = full_path
                        # if file was found, stop looking for it (first hit wins)
                        ecs_to_find.remove((idx, orig_path))

                # stop os.walk insanity as soon as we have all we need (os.walk loop)
                if not ecs_to_find:
                    break

                # ignore subdirs specified to be ignored by replacing items in dirnames list used by os.walk
                dirnames[:] = [d for d in dirnames if d not in build_option('ignore_dirs')]

            # stop os.walk insanity as soon as we have all we need (outer loop)
            if not ecs_to_find:
                break

    return ec_files


def parse_easyconfigs(paths, validate=True):
    """
    Parse easyconfig files
    @params paths: paths to easyconfigs
    """
    easyconfigs = []
    generated_ecs = False
    for (path, generated) in paths:
        path = os.path.abspath(path)
        # keep track of whether any files were generated
        generated_ecs |= generated
        if not os.path.exists(path):
            raise EasyBuildError("Can't find path %s", path)
        try:
            ec_files = find_easyconfigs(path, ignore_dirs=build_option('ignore_dirs'))
            for ec_file in ec_files:
                # only pass build specs when not generating easyconfig files
                kwargs = {'validate': validate}
                if not build_option('try_to_generate'):
                    kwargs['build_specs'] = build_option('build_specs')
                ecs = process_easyconfig(ec_file, **kwargs)
                easyconfigs.extend(ecs)
        except IOError, err:
            raise EasyBuildError("Processing easyconfigs in path %s failed: %s", path, err)

    return easyconfigs, generated_ecs


def stats_to_str(stats):
    """
    Pretty print build statistics to string.
    """
    if not isinstance(stats, (OrderedDict, dict)):
        raise EasyBuildError("Can only pretty print build stats in dictionary form, not of type %s", type(stats))

    txt = "{\n"
    pref = "    "
    for (k, v) in stats.items():
        txt += "%s%s: %s,\n" % (pref, quote_str(k), quote_str(v))
    txt += "}"
    return txt


def find_related_easyconfigs(path, ec):
    """
    Find related easyconfigs for provided parsed easyconfig in specified path.

    A list of easyconfigs for the same software (name) is returned,
    matching the 1st criterion that yields a non-empty list.

    The following criteria are considered (in this order) next to common software version criterion, i.e.
    exact version match, a major/minor version match, a major version match, or no version match (in that order).

    (i)   matching versionsuffix and toolchain name/version
    (ii)  matching versionsuffix and toolchain name (any toolchain version)
    (iii) matching versionsuffix (any toolchain name/version)
    (iv)  matching toolchain name/version (any versionsuffix)
    (v)   matching toolchain name (any versionsuffix, toolchain version)
    (vi)  no extra requirements (any versionsuffix, toolchain name/version)

    If no related easyconfigs with a matching software name are found, an empty list is returned.
    """
    name = ec.name
    version = ec.version
    versionsuffix = ec['versionsuffix']
    toolchain_name = ec['toolchain']['name']
    toolchain_name_pattern = r'-%s-\S+' % toolchain_name
    toolchain_pattern = '-%s-%s' % (toolchain_name, ec['toolchain']['version'])
    if toolchain_name == DUMMY_TOOLCHAIN_NAME:
        toolchain_name_pattern = ''
        toolchain_pattern = ''

    potential_paths = [glob.glob(ec_path) for ec_path in create_paths(path, name, '*')]
    potential_paths = sum(potential_paths, [])  # flatten
    _log.debug("found these potential paths: %s" % potential_paths)

    parsed_version = LooseVersion(version).version
    version_patterns = [version]  # exact version match
    if len(parsed_version) >= 2:
        version_patterns.append(r'%s\.%s\.\w+' % tuple(parsed_version[:2]))  # major/minor version match
    if parsed_version != parsed_version[0]:
        version_patterns.append(r'%s\.[\d-]+\.\w+' % parsed_version[0])  # major version match
    version_patterns.append(r'[\w.]+')  # any version

    regexes = []
    for version_pattern in version_patterns:
        common_pattern = r'^\S+/%s-%s%%s\.eb$' % (re.escape(name), version_pattern)
        regexes.extend([
            common_pattern % (toolchain_pattern + versionsuffix),
            common_pattern % (toolchain_name_pattern + versionsuffix),
            common_pattern % (r'\S*%s' % versionsuffix),
            common_pattern % toolchain_pattern,
            common_pattern % toolchain_name_pattern,
            common_pattern % r'\S*',
        ])

    for regex in regexes:
        res = [p for p in potential_paths if re.match(regex, p)]
        if res:
            _log.debug("Related easyconfigs found using '%s': %s" % (regex, res))
            break
        else:
            _log.debug("No related easyconfigs in potential paths using '%s'" % regex)

    return sorted(res)


def review_pr(pr, colored=True, branch='develop'):
    """
    Print multi-diff overview between easyconfigs in specified PR and specified branch.
    @param pr: pull request number in easybuild-easyconfigs repo to review
    @param colored: boolean indicating whether a colored multi-diff should be generated
    @param branch: easybuild-easyconfigs branch to compare with
    """
    tmpdir = tempfile.mkdtemp()

    download_repo_path = download_repo(branch=branch, path=tmpdir)
    repo_path = os.path.join(download_repo_path, 'easybuild', 'easyconfigs')
    pr_files = [path for path in fetch_easyconfigs_from_pr(pr) if path.endswith('.eb')]

    lines = []
    ecs, _ = parse_easyconfigs([(fp, False) for fp in pr_files], validate=False)
    for ec in ecs:
        files = find_related_easyconfigs(repo_path, ec['ec'])
        _log.debug("File in PR#%s %s has these related easyconfigs: %s" % (pr, ec['spec'], files))
        if files:
            lines.append(multidiff(ec['spec'], files, colored=colored))
        else:
            lines.extend(['', "(no related easyconfigs found for %s)\n" % os.path.basename(ec['spec'])])

    return '\n'.join(lines)


def dump_env_script(easyconfigs):
    """
    Dump source scripts that set up build environment for specified easyconfigs.

    @param easyconfigs: list of easyconfigs to generate scripts for
    """
    ecs_and_script_paths = []
    for easyconfig in easyconfigs:
        script_path = '%s.env' % os.path.splitext(os.path.basename(easyconfig['spec']))[0]
        ecs_and_script_paths.append((easyconfig['ec'], script_path))

    # don't just overwrite existing scripts
    existing_scripts = [s for (_, s) in ecs_and_script_paths if os.path.exists(s)]
    if existing_scripts:
        if build_option('force'):
            _log.info("Found existing scripts, overwriting them: %s", ' '.join(existing_scripts))
        else:
            raise EasyBuildError("Script(s) already exists, not overwriting them (unless --force is used): %s",
                                 ' '.join(existing_scripts))

    orig_env = copy.deepcopy(os.environ)

    for ec, script_path in ecs_and_script_paths:
        # obtain EasyBlock instance
        app_class = get_easyblock_class(ec['easyblock'], name=ec['name'])
        app = app_class(ec)

        # mimic dry run, and keep quiet
        app.dry_run = app.silent = app.toolchain.dry_run = True

        # prepare build environment (in dry run mode)
        app.check_readiness_step()
        app.prepare_step(start_dir=False)

        # compose script
        ecfile = os.path.basename(ec.path)
        script_lines = [
            "#!/bin/bash",
            "# script to set up build environment as defined by EasyBuild v%s for %s" % (EASYBUILD_VERSION, ecfile),
            "# usage: source %s" % os.path.basename(script_path),
        ]

        script_lines.extend(['', "# toolchain & dependency modules"])
        if app.toolchain.modules:
            script_lines.extend(["module load %s" % mod for mod in app.toolchain.modules])
        else:
            script_lines.append("# (no modules loaded)")

        script_lines.extend(['', "# build environment"])
        if app.toolchain.vars:
            env_vars = sorted(app.toolchain.vars.items())
            script_lines.extend(["export %s='%s'" % (var, val.replace("'", "\\'")) for (var, val) in env_vars])
        else:
            script_lines.append("# (no build environment defined)")

        write_file(script_path, '\n'.join(script_lines))
        print_msg("Script to set up build environment for %s dumped to %s" % (ecfile, script_path), prefix=False)

        restore_env(orig_env)
