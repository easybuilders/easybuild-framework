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
Dependency resolution functionality, a.k.a. robot.

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Toon Willems (Ghent University)
:author: Ward Poelmans (Ghent University)
"""
import copy
import os
import sys
from vsc.utils import fancylogger
from vsc.utils.missing import nub

from easybuild.framework.easyconfig.easyconfig import EASYCONFIGS_ARCHIVE_DIR, ActiveMNS, process_easyconfig
from easybuild.framework.easyconfig.easyconfig import robot_find_easyconfig, verify_easyconfig_filename
from easybuild.framework.easyconfig.tools import find_resolved_modules, skip_available
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option
from easybuild.tools.filetools import det_common_path_prefix, search_file
from easybuild.tools.module_naming_scheme.easybuild_mns import EasyBuildMNS
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version


_log = fancylogger.getLogger('tools.robot', fname=False)


def det_robot_path(robot_paths_option, tweaked_ecs_paths, pr_path, auto_robot=False):
    """Determine robot path."""
    robot_path = robot_paths_option[:]
    _log.info("Using robot path(s): %s" % robot_path)

    tweaked_ecs_path, tweaked_ecs_deps_path = None, None
    # paths to tweaked easyconfigs or easyconfigs downloaded from a PR have priority
    if tweaked_ecs_paths is not None:
        tweaked_ecs_path, tweaked_ecs_deps_path = tweaked_ecs_paths
        # easyconfigs listed on the command line (and tweaked) should be found first
        robot_path.insert(0, tweaked_ecs_path)
        # dependencies are always tweaked but we should only use them if there is no other option (so they come last)
        robot_path.append(tweaked_ecs_deps_path)
        _log.info("Prepended list of robot search paths with %s and appended with %s: %s", tweaked_ecs_path,
                  tweaked_ecs_deps_path, robot_path)
    if pr_path is not None:
        robot_path.append(pr_path)
        _log.info("Appended list of robot search paths with %s: %s" % (pr_path, robot_path))

    return robot_path


def check_conflicts(easyconfigs, modtool, check_inter_ec_conflicts=True):
    """
    Check for conflicts in dependency graphs for specified easyconfigs.

    :param easyconfigs: list of easyconfig files (EasyConfig instances) to check for conflicts
    :param modtool: ModulesTool instance to use
    :param check_inter_ec_conflicts: also check for conflicts between (dependencies of) listed easyconfigs
    :return: True if one or more conflicts were found, False otherwise
    """

    ordered_ecs = resolve_dependencies(easyconfigs, modtool, retain_all_deps=True)

    def mk_key(spec):
        """Create key for dictionary with all dependencies."""
        if 'ec' in spec:
            spec = spec['ec']

        return (spec['name'], det_full_ec_version(spec))

    # determine whether any 'wrappers' are involved
    wrapper_deps = {}
    for ec in ordered_ecs:
        # easyconfigs using ModuleRC install a 'wrapper' for their dependency
        # these need to be filtered out to avoid reporting false conflicts...
        if ec['ec']['easyblock'] == 'ModuleRC':
            wrapper_deps[mk_key(ec)] = mk_key(ec['ec']['dependencies'][0])

    def mk_dep_keys(deps):
        """Create keys for given list of dependencies."""
        res = []
        for dep in deps:
            # filter out dependencies marked as external module
            if not dep.get('external_module', False):
                key = mk_key(dep)
                # replace 'wrapper' dependencies with the dependency they're wrapping
                if key in wrapper_deps:
                    key = wrapper_deps[key]
                res.append(key)
        return res

    # construct a dictionary: (name, installver) tuple to (build) dependencies
    deps_for, dep_of = {}, {}
    for node in ordered_ecs:
        node_key = mk_key(node)

        # exclude external modules, since we can't check conflicts on them (we don't even know the software name)
        build_deps = mk_dep_keys(node['builddependencies'])
        deps = mk_dep_keys(node['ec'].all_dependencies)

        # separate runtime deps from build deps
        runtime_deps = [d for d in deps if d not in build_deps]

        deps_for[node_key] = (build_deps, runtime_deps)

        # keep track of reverse deps too
        for dep in deps:
            dep_of.setdefault(dep, set()).add(node_key)

    if check_inter_ec_conflicts:
        # add ghost entry that depends on each of the specified easyconfigs,
        # since we want to check for conflicts between specified easyconfigs too;
        # 'wrapper' easyconfigs are not included to avoid false conflicts being reported
        ec_keys = [k for k in [mk_key(e) for e in easyconfigs] if k not in wrapper_deps]
        deps_for[(None, None)] = ([], ec_keys)

    # iteratively expand list of dependencies
    last_deps_for = None
    while deps_for != last_deps_for:
        last_deps_for = copy.deepcopy(deps_for)
        # (Automake, _), [], [(Autoconf, _), (GCC, _)]
        for (key, (build_deps, runtime_deps)) in last_deps_for.items():
            # extend runtime dependencies with non-build dependencies of own runtime dependencies
            # Autoconf
            for dep in runtime_deps:
                # [], [M4, GCC]
                deps_for[key][1].extend([d for d in deps_for[dep][1]])

            # extend build dependencies with non-build dependencies of own build dependencies
            for dep in build_deps:
                deps_for[key][0].extend([d for d in deps_for[dep][1]])

            deps_for[key] = (sorted(nub(deps_for[key][0])), sorted(nub(deps_for[key][1])))

            # also track reverse deps (except for ghost entry)
            if key != (None, None):
                for dep in build_deps + runtime_deps:
                    dep_of.setdefault(dep, set()).add(key)

    def check_conflict(parent, dep1, dep2):
        """
        Check whether dependencies with given name/(install) version conflict with each other.

        :param parent: name & install version of 'parent' software
        :param dep1: name & install version of 1st dependency
        :param dep2: name & install version of 2nd dependency
        """
        # dependencies with the same name should have the exact same install version
        # if not => CONFLICT!
        conflict = dep1[0] == dep2[0] and dep1[1] != dep2[1]
        if conflict:
            vs_msg = "%s-%s vs %s-%s " % (dep1 + dep2)
            for dep in [dep1, dep2]:
                if dep in dep_of:
                    vs_msg += "\n\t%s-%s as dep of: " % dep + ', '.join('%s-%s' % d for d in sorted(dep_of[dep]))

            if parent[0] is None:
                sys.stderr.write("Conflict between (dependencies of) easyconfigs: %s\n" % vs_msg)
            else:
                specname = '%s-%s' % parent
                sys.stderr.write("Conflict found for dependencies of %s: %s\n" % (specname, vs_msg))

        return conflict

    # for each of the easyconfigs, check whether the dependencies (incl. build deps) contain any conflicts
    res = False
    for (key, (build_deps, runtime_deps)) in deps_for.items():
        # also check whether module itself clashes with any of its dependencies
        for i, dep1 in enumerate(build_deps + runtime_deps + [key]):
            for dep2 in (build_deps + runtime_deps)[i+1:]:
                # don't worry about conflicts between module itself and any of its build deps
                if dep1 != key or dep2 not in build_deps:
                    res |= check_conflict(key, dep1, dep2)

    return res


def dry_run(easyconfigs, modtool, short=False):
    """
    Compose dry run overview for supplied easyconfigs:
    * [ ] for unavailable
    * [x] for available
    * [F] for forced
    * [R] for rebuild
    :param easyconfigs: list of parsed easyconfigs (EasyConfig instances)
    :param modtool: ModulesTool instance to use
    :param short: use short format for overview: use a variable for common prefixes
    """
    lines = []
    if build_option('robot_path') is None:
        lines.append("Dry run: printing build status of easyconfigs")
        all_specs = easyconfigs
    else:
        lines.append("Dry run: printing build status of easyconfigs and dependencies")
        all_specs = resolve_dependencies(easyconfigs, modtool, retain_all_deps=True)

    unbuilt_specs = skip_available(all_specs, modtool)
    dry_run_fmt = " * [%1s] %s (module: %s)"  # markdown compatible (list of items with checkboxes in front)

    listed_ec_paths = [spec['spec'] for spec in easyconfigs]

    var_name = 'CFGS'
    common_prefix = det_common_path_prefix([spec['spec'] for spec in all_specs])
    # only allow short if common prefix is long enough
    short = short and common_prefix is not None and len(common_prefix) > len(var_name) * 2
    for spec in all_specs:
        if spec in unbuilt_specs:
            ans = ' '
        elif build_option('force') and spec['spec'] in listed_ec_paths:
            ans = 'F'
        elif build_option('rebuild') and spec['spec'] in listed_ec_paths:
            ans = 'R'
        else:
            ans = 'x'

        if spec['ec'].short_mod_name != spec['ec'].full_mod_name:
            mod = "%s | %s" % (spec['ec'].mod_subdir, spec['ec'].short_mod_name)
        else:
            mod = spec['ec'].full_mod_name

        if short:
            item = os.path.join('$%s' % var_name, spec['spec'][len(common_prefix) + 1:])
        else:
            item = spec['spec']
        lines.append(dry_run_fmt % (ans, item, mod))

    if short:
        # insert after 'Dry run:' message
        lines.insert(1, "%s=%s" % (var_name, common_prefix))
    return '\n'.join(lines)


def resolve_dependencies(easyconfigs, modtool, retain_all_deps=False):
    """
    Work through the list of easyconfigs to determine an optimal order
    :param easyconfigs: list of easyconfigs
    :param modtool: ModulesTool instance to use
    :param retain_all_deps: boolean indicating whether all dependencies must be retained, regardless of availability;
                            retain all deps when True, check matching build option when False
    """
    robot = build_option('robot_path')
    # retain all dependencies if specified by either the resp. build option or the dedicated named argument
    retain_all_deps = build_option('retain_all_deps') or retain_all_deps

    avail_modules = modtool.available()
    if retain_all_deps:
        # assume that no modules are available when forced, to retain all dependencies
        avail_modules = []
        _log.info("Forcing all dependencies to be retained.")
    else:
        if len(avail_modules) == 0:
            _log.warning("No installed modules. Your MODULEPATH is probably incomplete: %s" % os.getenv('MODULEPATH'))

    ordered_ecs = []
    # all available modules can be used for resolving dependencies except those that will be installed
    being_installed = [p['full_mod_name'] for p in easyconfigs]
    avail_modules = [m for m in avail_modules if not m in being_installed]

    _log.debug('easyconfigs before resolving deps: %s' % easyconfigs)

    # resolve all dependencies, put a safeguard in place to avoid an infinite loop (shouldn't occur though)
    irresolvable = []
    loopcnt = 0
    maxloopcnt = 10000
    while easyconfigs:
        # make sure this stops, we really don't want to get stuck in an infinite loop
        loopcnt += 1
        if loopcnt > maxloopcnt:
            raise EasyBuildError("Maximum loop cnt %s reached, so quitting (easyconfigs: %s, irresolvable: %s)",
                                 maxloopcnt, easyconfigs, irresolvable)

        # first try resolving dependencies without using external dependencies
        last_processed_count = -1
        while len(avail_modules) > last_processed_count:
            last_processed_count = len(avail_modules)
            res = find_resolved_modules(easyconfigs, avail_modules, modtool, retain_all_deps=retain_all_deps)
            resolved_ecs, easyconfigs, avail_modules = res
            ordered_ec_mod_names = [x['full_mod_name'] for x in ordered_ecs]
            for ec in resolved_ecs:
                # only add easyconfig if it's not included yet (based on module name)
                if not ec['full_mod_name'] in ordered_ec_mod_names:
                    ordered_ecs.append(ec)

        # dependencies marked as external modules should be resolved via available modules at this point
        missing_external_modules = [d['full_mod_name'] for ec in easyconfigs for d in ec['dependencies']
                                    if d.get('external_module', False)]
        if missing_external_modules:
            raise EasyBuildError("Missing modules for one or more dependencies marked as external modules: %s",
                                 missing_external_modules)

        # robot: look for existing dependencies, add them
        if robot and easyconfigs:

            # rely on EasyBuild module naming scheme when resolving dependencies, since we know that will
            # generate sensible module names that include the necessary information for the resolution to work
            # (name, version, toolchain, versionsuffix)
            being_installed = [EasyBuildMNS().det_full_module_name(p['ec']) for p in easyconfigs]

            additional = []
            for entry in easyconfigs:
                # do not choose an entry that is being installed in the current run
                # if they depend, you probably want to rebuild them using the new dependency
                deps = entry['dependencies']
                candidates = [d for d in deps if not EasyBuildMNS().det_full_module_name(d) in being_installed]
                if candidates:
                    cand_dep = candidates[0]
                    # find easyconfig, might not find any
                    _log.debug("Looking for easyconfig for %s" % str(cand_dep))
                    # note: robot_find_easyconfig may return None
                    path = robot_find_easyconfig(cand_dep['name'], det_full_ec_version(cand_dep))

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
                        hidden = cand_dep.get('hidden', False)
                        processed_ecs = process_easyconfig(path, validate=not retain_all_deps, hidden=hidden)

                        # ensure that selected easyconfig provides required dependency
                        verify_easyconfig_filename(path, cand_dep, parsed_ec=processed_ecs)

                        for ec in processed_ecs:
                            if not ec in easyconfigs + additional:
                                additional.append(ec)
                                _log.debug("Added %s as dependency of %s" % (ec, entry))
                else:
                    mod_name = EasyBuildMNS().det_full_module_name(entry['ec'])
                    _log.debug("No more candidate dependencies to resolve for %s" % mod_name)

            # add additional (new) easyconfigs to list of stuff to process
            easyconfigs.extend(additional)
            _log.debug("Unprocessed dependencies: %s", easyconfigs)

        elif not robot:
            # no use in continuing if robot is not enabled, dependencies won't be resolved anyway
            irresolvable = [dep for x in easyconfigs for dep in x['dependencies']]
            break

    if irresolvable:
        _log.warning("Irresolvable dependencies (details): %s" % irresolvable)
        irresolvable_mods_eb = [EasyBuildMNS().det_full_module_name(dep) for dep in irresolvable]
        _log.warning("Irresolvable dependencies (EasyBuild module names): %s" % ', '.join(irresolvable_mods_eb))
        irresolvable_mods = [ActiveMNS().det_full_module_name(dep) for dep in irresolvable]
        raise EasyBuildError("Irresolvable dependencies encountered: %s", ', '.join(irresolvable_mods))

    _log.info("Dependency resolution complete, building as follows: %s" % ordered_ecs)
    return ordered_ecs


def search_easyconfigs(query, short=False, filename_only=False, terse=False):
    """Search for easyconfigs, if a query is provided."""
    search_path = build_option('robot_path')
    if not search_path:
        search_path = [os.getcwd()]
    extra_search_paths = build_option('search_paths')
    if extra_search_paths:
        search_path.extend(extra_search_paths)

    ignore_dirs = build_option('ignore_dirs')

    # note: don't pass down 'filename_only' here, we need the full path to filter out archived easyconfigs
    var_defs, _hits = search_file(search_path, query, short=short, ignore_dirs=ignore_dirs, terse=terse,
                                  silent=True, filename_only=False)

     # filter out archived easyconfigs, these are handled separately
    hits, archived_hits = [], []
    for hit in _hits:
        if EASYCONFIGS_ARCHIVE_DIR in hit.split(os.path.sep):
            archived_hits.append(hit)
        else:
            hits.append(hit)

    # check whether only filenames should be printed
    if filename_only:
        hits = [os.path.basename(hit) for hit in hits]
        archived_hits = [os.path.basename(hit) for hit in archived_hits]

    # prepare output format
    if terse:
        lines, tmpl = [], '%s'
    else:
        lines = ['%s=%s' % var_def for var_def in var_defs]
        tmpl = ' * %s'

    # non-archived hits are shown first
    lines.extend(tmpl % hit for hit in hits)

    # also take into account archived hits
    if archived_hits:
        if build_option('consider_archived_easyconfigs'):
            if not terse:
                lines.extend(['', "Matching archived easyconfigs:", ''])
            lines.extend(tmpl % hit for hit in archived_hits)
        elif not terse:
            cnt = len(archived_hits)
            lines.extend([
                '',
                "Note: %d matching archived easyconfig(s) found, use --consider-archived-easyconfigs to see them" % cnt,
            ])

    print '\n'.join(lines)
