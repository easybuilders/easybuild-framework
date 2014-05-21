# #
# Copyright 2009-2014 Ghent University
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
@author: Fotis Georgatos (University of Luxembourg)
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
    graph_errors.append("Failed to import graphviz: try yum install graphviz-python, or apt-get install python-pygraphviz")

from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.config import build_option
from easybuild.tools.filetools import det_common_path_prefix, run_cmd, write_file
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.modules import modules_tool
from easybuild.tools.ordereddict import OrderedDict
from easybuild.framework.easyconfig.easyconfig import det_full_module_name, process_easyconfig, robot_find_easyconfig

_log = fancylogger.getLogger('easyconfig.tools', fname=False)


def skip_available(easyconfigs, testing=False):
    """Skip building easyconfigs for which a module is already available."""
    avail_modules = modules_tool().available()
    easyconfigs, check_easyconfigs = [], easyconfigs
    for ec in check_easyconfigs:
        module = ec['module']
        if module in avail_modules:
            msg = "%s is already installed (module found), skipping" % module
            print_msg(msg, log=_log, silent=testing)
            _log.info(msg)
        else:
            _log.debug("%s is not installed yet, so retaining it" % module)
            easyconfigs.append(ec)
    return easyconfigs


def find_resolved_modules(unprocessed, avail_modules):
    """
    Find easyconfigs in 1st argument which can be fully resolved using modules specified in 2nd argument
    """
    ordered_ecs = []
    new_avail_modules = avail_modules[:]
    new_unprocessed = []

    for ec in unprocessed:
        new_ec = ec.copy()
        new_ec['dependencies'] = [d for d in new_ec['dependencies'] if not det_full_module_name(d) in new_avail_modules]

        if len(new_ec['dependencies']) == 0:
            _log.debug("Adding easyconfig %s to final list" % new_ec['spec'])
            ordered_ecs.append(new_ec)
            new_avail_modules.append(ec['module'])

        else:
            new_unprocessed.append(new_ec)

    return ordered_ecs, new_unprocessed, new_avail_modules


def resolve_dependencies(unprocessed, build_specs=None, retain_all_deps=False):
    """
    Work through the list of easyconfigs to determine an optimal order
    @param unprocessed: list of easyconfigs
    @param build_specs: dictionary specifying build specifications (e.g. version, toolchain, ...)
    """

    robot = build_option('robot_path')

    retain_all_deps = build_option('retain_all_deps') or retain_all_deps
    if retain_all_deps:
        # assume that no modules are available when forced, to retain all dependencies
        avail_modules = []
        _log.info("Forcing all dependencies to be retained.")
    else:
        # Get a list of all available modules (format: [(name, installversion), ...])
        avail_modules = modules_tool().available()

        if len(avail_modules) == 0:
            _log.warning("No installed modules. Your MODULEPATH is probably incomplete: %s" % os.getenv('MODULEPATH'))

    ordered_ecs = []
    # all available modules can be used for resolving dependencies except those that will be installed
    being_installed = [p['module'] for p in unprocessed]
    avail_modules = [m for m in avail_modules if not m in being_installed]

    _log.debug('unprocessed before resolving deps: %s' % unprocessed)

    # resolve all dependencies, put a safeguard in place to avoid an infinite loop (shouldn't occur though)
    irresolvable = []
    loopcnt = 0
    maxloopcnt = 10000
    while unprocessed:
        # make sure this stops, we really don't want to get stuck in an infinite loop
        loopcnt += 1
        if loopcnt > maxloopcnt:
            tup = (maxloopcnt, unprocessed, irresolvable)
            msg = "Maximum loop cnt %s reached, so quitting (unprocessed: %s, irresolvable: %s)" % tup
            _log.error(msg)

        # first try resolving dependencies without using external dependencies
        last_processed_count = -1
        while len(avail_modules) > last_processed_count:
            last_processed_count = len(avail_modules)
            more_ecs, unprocessed, avail_modules = find_resolved_modules(unprocessed, avail_modules)
            for ec in more_ecs:
                if not ec['module'] in [x['module'] for x in ordered_ecs]:
                    ordered_ecs.append(ec)

        # robot: look for existing dependencies, add them
        if robot and unprocessed:

            being_installed = [det_full_module_name(p['ec'], eb_ns=True) for p in unprocessed]

            additional = []
            for i, entry in enumerate(unprocessed):
                # do not choose an entry that is being installed in the current run
                # if they depend, you probably want to rebuild them using the new dependency
                deps = entry['dependencies']
                candidates = [d for d in deps if not det_full_module_name(d, eb_ns=True) in being_installed]
                if len(candidates) > 0:
                    cand_dep = candidates[0]
                    # find easyconfig, might not find any
                    _log.debug("Looking for easyconfig for %s" % str(cand_dep))
                    # note: robot_find_easyconfig may return None
                    path = robot_find_easyconfig(robot, cand_dep['name'], det_full_ec_version(cand_dep))

                    if path is None:
                        # no easyconfig found for dependency, add to list of irresolvable dependencies
                        if cand_dep not in irresolvable:
                            _log.debug("Irresolvable dependency found: %s" % cand_dep)
                            irresolvable.append(cand_dep)
                        # remove irresolvable dependency from list of dependencies so we can continue
                        entry['dependencies'].remove(cand_dep)
                    else:
                        _log.info("Robot: resolving dependency %s with %s" % (cand_dep, path))
                        # build specs should not be passed down to resolved dependencies,
                        # to avoid that e.g. --try-toolchain trickles down into the used toolchain itself
                        processed_ecs = process_easyconfig(path, validate=not retain_all_deps)

                        # ensure that selected easyconfig provides required dependency
                        mods = [det_full_module_name(spec['ec']) for spec in processed_ecs]
                        dep_mod_name = det_full_module_name(cand_dep)
                        if not dep_mod_name in mods:
                            tup = (path, dep_mod_name, mods)
                            _log.error("easyconfig file %s does not contain module %s (mods: %s)" % tup)

                        for ec in processed_ecs:
                            if not ec in unprocessed + additional:
                                additional.append(ec)
                                _log.debug("Added %s as dependency of %s" % (ec, entry))
                else:
                    mod_name = det_full_module_name(entry['ec'], eb_ns=True)
                    _log.debug("No more candidate dependencies to resolve for %s" % mod_name)

            # add additional (new) easyconfigs to list of stuff to process
            unprocessed.extend(additional)

        elif not robot:
            # no use in continuing if robot is not enabled, dependencies won't be resolved anyway
            irresolvable = [dep for x in unprocessed for dep in x['dependencies']]
            break

    if irresolvable:
        irresolvable_mod_deps = [(det_full_module_name(dep, eb_ns=True), dep) for dep in irresolvable]
        _log.error('Irresolvable dependencies encountered: %s' % irresolvable_mod_deps)

    _log.info("Dependency resolution complete, building as follows:\n%s" % ordered_ecs)
    return ordered_ecs


def print_dry_run(easyconfigs, short=False, build_specs=None):
    """
    Print dry run information
    @param easyconfigs: list of easyconfig files
    @param short: print short output (use a variable for the common prefix)
    @param build_specs: dictionary specifying build specifications (e.g. version, toolchain, ...)
    """
    lines = []
    if build_option('robot_path') is None:
        lines.append("Dry run: printing build status of easyconfigs")
        all_specs = easyconfigs
    else:
        lines.append("Dry run: printing build status of easyconfigs and dependencies")
        all_specs = resolve_dependencies(easyconfigs, build_specs=build_specs, retain_all_deps=True)

    unbuilt_specs = skip_available(all_specs, testing=True)
    dry_run_fmt = " * [%1s] %s (module: %s)"  # markdown compatible (list of items with checkboxes in front)

    var_name = 'CFGS'
    common_prefix = det_common_path_prefix([spec['spec'] for spec in all_specs])
    # only allow short if common prefix is long enough
    short = short and common_prefix is not None and len(common_prefix) > len(var_name) * 2
    for spec in all_specs:
        if spec in unbuilt_specs:
            ans = ' '
        else:
            ans = 'x'
        mod = det_full_module_name(spec['ec'])

        if short:
            item = os.path.join('$%s' % var_name, spec['spec'][len(common_prefix) + 1:])
        else:
            item = spec['spec']
        lines.append(dry_run_fmt % (ans, item, mod))

    if short:
        # insert after 'Dry run:' message
        lines.insert(1, "%s=%s" % (var_name, common_prefix))
    silent = build_option('silent')
    print_msg('\n'.join(lines), log=_log, silent=silent, prefix=False)


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
        if omit_versions:
            return spec['name']
        else:
            return det_full_module_name(spec)

    # enhance list of specs
    for spec in specs:
        spec['module'] = mk_node_name(spec['ec'])
        spec['unresolved_deps'] = [mk_node_name(s) for s in spec['unresolved_deps']]

    # build directed graph
    dgr = digraph()
    dgr.add_nodes([spec['module'] for spec in specs])
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
        errors = "\n".join(graph_errors)
        msg = "An optional Python packages required to generate dependency graphs is missing: %s" % errors
        _log.error("%s\nerr: %s" % (msg, err))


def get_paths_for(subdir="easyconfigs", robot_path=None):
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
    (out, ec) = run_cmd("which eb", simple=False, log_all=False, log_ok=False)
    if ec:
        _log.warning("eb not found (%s), failed to determine installation prefix" % out)
    else:
        # eb should reside in <install_prefix>/bin/eb
        install_prefix = os.path.dirname(os.path.dirname(out))
        path_list.append(install_prefix)
        _log.debug("Also considering installation prefix %s..." % install_prefix)

    # look for desired subdirs
    for path in path_list:
        path = os.path.join(path, "easybuild", subdir)
        _log.debug("Looking for easybuild/%s in path %s" % (subdir, path))
        try:
            if os.path.exists(path):
                paths.append(os.path.abspath(path))
                _log.debug("Added %s to list of paths for easybuild/%s" % (path, subdir))
        except OSError, err:
            raise EasyBuildError(str(err))

    return paths


def stats_to_str(stats):
    """
    Pretty print build statistics to string.
    """
    if not isinstance(stats, (OrderedDict, dict)):
        _log.error("Can only pretty print build stats in dictionary form, not of type %s" % type(stats))

    txt = "{\n"

    pref = "    "

    def tostr(x):
        if isinstance(x, basestring):
            return "'%s'" % x
        else:
            return str(x)

    for (k, v) in stats.items():
        txt += "%s%s: %s,\n" % (pref, tostr(k), tostr(v))

    txt += "}"
    return txt
