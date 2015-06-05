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
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option
from easybuild.tools.filetools import find_easyconfigs, which, write_file
from easybuild.tools.github import fetch_easyconfigs_from_pr
from easybuild.tools.modules import modules_tool
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.utilities import quote_str


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
