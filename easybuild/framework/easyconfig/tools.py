# #
# Copyright 2009-2015 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
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

import os
import sys
from vsc.utils import fancylogger

# optional Python packages, these might be missing
# failing imports are just ignored
# a NameError should be catched where these are used

# PyGraph (used for generating dependency graphs)
graph_errors = []
try:
    from pygraph.classes.digraph import digraph
except ImportError, err:
    graph_errors.append("Failed to import pygraph-core: try easy_install python-graph-core")

try:
    import pygraph.readwrite.dot as dot
except ImportError, err:
    graph_errors.append("Failed to import pygraph-dot: try easy_install python-graph-dot")

# graphviz (used for creating dependency graph images)
try:
    sys.path.append('..')
    sys.path.append('/usr/lib/graphviz/python/')
    sys.path.append('/usr/lib64/graphviz/python/')
    import gv
except ImportError, err:
    graph_errors.append("Failed to import graphviz: try yum install graphviz-python,"
                        "or apt-get install python-pygraphviz,"
                        "or brew install graphviz --with-bindings")

from easybuild.framework.easyconfig import EASYCONFIGS_PKG_SUBDIR
from easybuild.framework.easyconfig.easyconfig import ActiveMNS
from easybuild.framework.easyconfig.easyconfig import process_easyconfig
from easybuild.framework.easyconfig.easyconfig import robot_find_easyconfig
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option
from easybuild.tools.filetools import find_easyconfigs, which, write_file
from easybuild.tools.github import fetch_easyconfigs_from_pr
from easybuild.tools.modules import modules_tool
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.utilities import quote_str
from easybuild.tools.toolchain.utilities import search_toolchain
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
import tempfile

_log = fancylogger.getLogger('easyconfig.tools', fname=False)


def skip_available(easyconfigs):
    """Skip building easyconfigs for existing modules."""
    modtool = modules_tool()
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


def find_resolved_modules(unprocessed, avail_modules, retain_all_deps=False):
    """
    Find easyconfigs in 1st argument which can be fully resolved using modules specified in 2nd argument
    """
    ordered_ecs = []
    new_avail_modules = avail_modules[:]
    new_unprocessed = []
    modtool = modules_tool()

    for ec in unprocessed:
        new_ec = ec.copy()
        deps = []
        for dep in new_ec['dependencies']:
            full_mod_name = dep.get('full_mod_name', None)
            if full_mod_name is None:
                full_mod_name = ActiveMNS().det_full_module_name(dep)

            dep_resolved = full_mod_name in new_avail_modules
            if not retain_all_deps:
                # hidden modules need special care, since they may not be included in list of available modules
                dep_resolved |= dep['hidden'] and modtool.exist([full_mod_name])[0]

            if not dep_resolved:
                # treat external modules as resolved when retain_all_deps is enabled (e.g., under --dry-run),
                # since no corresponding easyconfig can be found for them
                if retain_all_deps and dep.get('external_module', False):
                    _log.debug("Treating dependency marked as external dependency as resolved: %s", dep)
                else:
                    # no module available (yet) => retain dependency as one to be resolved
                    deps.append(dep)

        new_ec['dependencies'] = deps

        if len(new_ec['dependencies']) == 0:
            _log.debug("Adding easyconfig %s to final list" % new_ec['spec'])
            ordered_ecs.append(new_ec)
            new_avail_modules.append(ec['full_mod_name'])

        else:
            new_unprocessed.append(new_ec)

    return ordered_ecs, new_unprocessed, new_avail_modules

def get_toolchain_hierarchy(parent_toolchain):
    # Grab all possible subtoolchains
    _, all_tc_classes = search_toolchain('')
    subtoolchains = dict((tc_class.NAME, getattr(tc_class, 'SUBTOOLCHAIN', None)) for tc_class in all_tc_classes)
    # The parent is the first element in the list
    toolchain_list = [parent_toolchain]
    current = parent_toolchain
    while True:
        # Get the next subtoolchain
        if subtoolchains[current['name']]:
            # Grab the easyconfig of the current toolchain and search the dependencies for a version of the subtoolchain
            path = robot_find_easyconfig(current['name'],current['version'])
            if path is None:
                raise EasyBuildError("Could not find easyconfig for toolchain %s " % current)
            # Parse the easyconfig
            parsed_ec = process_easyconfig(path)[0]
            # Search the dependencies for the version of the subtoolchain
            dep_tcs = [dep_toolchain['toolchain'] for dep_toolchain in parsed_ec['dependencies']
                                           if dep_toolchain['toolchain']['name'] == subtoolchains[current['name']]]
            # Check we have a unique version and add it to the list
            unique_versions = set([dep_tc['version'] for dep_tc in dep_tcs])

            if len(unique_versions) == 1:
                toolchain_list += [dep_tcs[0]]
            elif len(unique_versions) == 0:
                # Check if we have dummy toolchain
                if subtoolchains[current['name']] == DUMMY_TOOLCHAIN_NAME:
                    toolchain_list += [{'name': DUMMY_TOOLCHAIN_NAME, 'version': ''}]
                    break
                else:
                    _log.info("Your toolchain hierarchy is not fully populated!")
                    EasyBuildError("No version found for subtoolchain %s in dependencies of %s"
                                   % (subtoolchains[current], current))
            else:
                raise EasyBuildError("Multiple versions of %s found in dependencies of toolchain %s"
                                     % (subtoolchains[current], current))
            current = dep_tcs[0]
        else:
            break
    _log.info("Found toolchain hierarchy %s", toolchain_list)

    return toolchain_list

def refresh_dependencies(initial_dependencies,altered_dep):
    """
    Refresh derived arguments in a dependency
    @param initial_dependencies: initial dependency list
    @param altered_dep: The dependency to be refreshed
    """
    if altered_dep['toolchain']['name'] == DUMMY_TOOLCHAIN_NAME:
        altered_dep['toolchain']['dummy'] = True
    # Update module name
    altered_dep['short_mod_name'] = ActiveMNS().det_short_module_name(altered_dep)
    altered_dep['full_mod_name'] = ActiveMNS().det_full_module_name(altered_dep)

    # Now replace the dependency in the list
    new_dependencies = []
    for d in initial_dependencies:
        if d['name'] == altered_dep['name']:
            new_dependencies += [altered_dep]
        else:
            new_dependencies += [d]
    return new_dependencies

def deep_refresh_dependencies(ec,altered_dep):
    """
    Deep refresh derived arguments in a dependency
    @param ec: the original easyconifg instance
    @param altered_dep: The dependency to be refreshed

    """
    new_ec = ec.copy()

    # Change all the various places the dependencies can appear
    for key in ['dependencies',
                'hiddendependencies',
                'unresolved_deps',
                'builddependencies'
                ]:
        if new_ec[key]:
            new_ec[key] = refresh_dependencies(new_ec[key],altered_dep)
    for key in ['dependencies',
                'hiddendependencies',
                'builddependencies'
                ]:
        if new_ec['ec'][key]:
            new_ec['ec'][key] = refresh_dependencies(new_ec['ec'][key],altered_dep)

    return new_ec

def find_minimally_resolved_modules(unprocessed, avail_modules, retain_all_deps=False, use_any_existing_modules=True):
    """
    Find easyconfigs in 1st argument which can be fully resolved using modules specified in 2nd argument
    """
    ordered_ecs = []
    new_avail_modules = avail_modules[:]
    new_unprocessed = []
    modtool = modules_tool()

    for ec in unprocessed:
        new_ec = ec.copy()
        deps = []
        # Populate the toolchain hierarchy
        toolchains = get_toolchain_hierarchy(new_ec['ec']['toolchain'])
        for dep in new_ec['dependencies']:
            dep_resolved = False
            orig_dep = dep
            if dep['toolchain'] in toolchains:
                deptoolchains = toolchains[toolchains.index(dep['toolchain']):]
                if use_any_existing_modules:
                    # Only search for toolchains further down the chain
                    for tc in deptoolchains:
                        dep['toolchain'] = tc
                        full_mod_name = ActiveMNS().det_full_module_name(dep)
                        dep_resolved = full_mod_name in avail_modules
                        # hidden modules need special care, since they may not be included in list of available modules
                        if not retain_all_deps:
                            dep_resolved |= dep['hidden'] and modtool.exist([full_mod_name])[0]
                        if dep_resolved:
                            # Need to update the dependency in the original easyconfig
                            new_ec = deep_refresh_dependencies(new_ec,dep)
                            break
                if not dep_resolved:
                    # If we can't resolve it, we find the minimal easyconfig for the resolution and update the dependency
                    found_minimal_easyconfig = False
                    for tc in reversed(deptoolchains):
                        dep['toolchain'] = tc
                        eb_file = robot_find_easyconfig(dep['name'], det_full_ec_version(dep))
                        if eb_file is not None:
                            if dep['toolchain'] != orig_dep['toolchain']:
                                _log.info("Minimally resolving dependency %s of %s with %s" %
                                          (cand_dep, ec['name'], eb_file))
                            new_ec = deep_refresh_dependencies(new_ec, dep)
                            found_minimal_easyconfig = True
                            break
                    # Now check for the existence of the module of the dep
                    if found_minimal_easyconfig:
                        full_mod_name = ActiveMNS().det_full_module_name(dep)
                        dep_resolved = full_mod_name in avail_modules
                        if not retain_all_deps:
                            dep_resolved |= dep['hidden'] and modtool.exist([full_mod_name])[0]
                    else:
                        _log.debug("Irresolvable minimal dependency found: %s" % orig_dep)
            else:
                # in the case where the toolchain of a dependency is different to the parent toolchain we do nothing
                full_mod_name = dep.get('full_mod_name', None)
                if full_mod_name is None:
                    full_mod_name = ActiveMNS().det_full_module_name(dep)

                dep_resolved = full_mod_name in new_avail_modules
                if not retain_all_deps:
                    # hidden modules need special care, since they may not be included in list of available modules
                    dep_resolved |= dep['hidden'] and modtool.exist([full_mod_name])[0]

            if not dep_resolved:
                # treat external modules as resolved when retain_all_deps is enabled (e.g., under --dry-run),
                # since no corresponding easyconfig can be found for them
                if retain_all_deps and dep.get('external_module', False):
                    _log.debug("Treating dependency marked as external dependency as resolved: %s", dep)
                else:
                    # no module available (yet) => retain dependency as one to be resolved
                    deps.append(dep)

        new_ec['dependencies'] = deps

        if len(new_ec['dependencies']) == 0:
            minimal_dir = tempfile.mkdtemp(prefix='minimal-easyconfigs')
            newspec = os.path.join(minimal_dir, "%s-%s.eb" % (new_ec['ec']['name'], det_full_ec_version(new_ec['ec'])))
            _log.debug("Attempting dumping minimal easyconfig to %s and adding it to final list" % newspec)
            try:

                # only copy if the files are not the same file already (yes, it happens)
                if os.path.exists(newspec):
                    _log.debug("Not creating easyconfig file %s since file exists" % newspec)
                else:
                    oldspec = new_ec['spec']
                    new_ec['spec'] = newspec
                    new_ec['ec'].dump(newspec)
                    _log.info("Updating %s : %s is new minimal toolchain version" % (oldspec, new_ec['spec']))
                    ordered_ecs.append(new_ec)
                    _log.debug("Adding easyconfig %s to final list" % new_ec['spec'])
                    new_avail_modules.append(ec['full_mod_name'])
            except (IOError, OSError), err:
                print_error("Failed to create easyconfig %s: %s" % (newspec, err))
        else:
            new_unprocessed.append(new_ec)

    return ordered_ecs, new_unprocessed, new_avail_modules



def _dep_graph(fn, specs, silent=False):
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
        spec['unresolved_deps'] = [mk_node_name(s) for s in spec['unresolved_deps']]
        all_nodes.update(spec['unresolved_deps'])

    # build directed graph
    dgr = digraph()
    dgr.add_nodes(all_nodes)
    for spec in specs:
        for dep in spec['unresolved_deps']:
            dgr.add_edge((spec['module'], dep))

    # write to file
    dottxt = dot.write(dgr)
    if fn.endswith(".dot"):
        # create .dot file
        write_file(fn, dottxt)
    else:
        # try and render graph in specified file format
        gvv = gv.readstring(dottxt)
        gv.layout(gvv, 'dot')
        gv.render(gvv, fn.split('.')[-1], fn)

    if not silent:
        print "Wrote dependency graph for %d easyconfigs to %s" % (len(specs), fn)


def dep_graph(*args, **kwargs):
    try:
        _dep_graph(*args, **kwargs)
    except NameError, err:
        raise EasyBuildError("An optional Python packages required to generate dependency graphs is missing: %s, %s",
                             '\n'.join(graph_errors), err)


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


def parse_easyconfigs(paths):
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
                kwargs = {}
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
