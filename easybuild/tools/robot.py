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
Dependency resolution functionality, a.k.a. robot.

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
@author: Toon Willems (Ghent University)
@author: Ward Poelmans (Ghent University)
"""
import os
from easybuild import toolchains
from vsc.utils import fancylogger
from vsc.utils.missing import nub

from easybuild.framework.easyconfig.easyconfig import ActiveMNS, process_easyconfig, robot_find_easyconfig
from easybuild.framework.easyconfig.tools import find_resolved_modules, skip_available
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.config import build_option
from easybuild.tools.filetools import det_common_path_prefix, search_file
from easybuild.tools.module_naming_scheme.easybuild_mns import EasyBuildMNS
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.modules import modules_tool
from easybuild.tools.toolchain.utilities import search_toolchain
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME


_log = fancylogger.getLogger('tools.robot', fname=False)

def det_robot_path(robot_paths_option, tweaked_ecs_path, pr_path, auto_robot=False):
    """Determine robot path."""
    robot_path = robot_paths_option[:]
    _log.info("Using robot path(s): %s" % robot_path)

    # paths to tweaked easyconfigs or easyconfigs downloaded from a PR have priority
    if tweaked_ecs_path is not None:
        robot_path.insert(0, tweaked_ecs_path)
        _log.info("Prepended list of robot search paths with %s: %s" % (tweaked_ecs_path, robot_path))
    if pr_path is not None:
        robot_path.insert(0, pr_path)
        _log.info("Prepended list of robot search paths with %s: %s" % (pr_path, robot_path))

    return robot_path


def dry_run(easyconfigs, short=False):
    """
    Compose dry run overview for supplied easyconfigs ([ ] for unavailable, [x] for available, [F] for forced)
    @param easyconfigs: list of parsed easyconfigs (EasyConfig instances)
    @param short: use short format for overview: use a variable for common prefixes
    """
    lines = []
    if build_option('robot_path') is None:
        lines.append("Dry run: printing build status of easyconfigs")
        all_specs = easyconfigs
    else:
        lines.append("Dry run: printing build status of easyconfigs and dependencies")
        all_specs = minimally_resolve_dependencies(easyconfigs, retain_all_deps=True)

    unbuilt_specs = skip_available(all_specs)
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

def replace_toolchain_with_hierarchy(item_specs, parent, retain_all_deps, use_any_existing_modules, subtoolchains):
    """
    Work through the list to determine and replace toolchains with minimal possible value (respecting arguments)
    @param item_specs: list of easyconfigs
    @param parent: the name of the parent software in the list
    @param retain_all_deps: boolean indicating whether all dependencies must be retained, regardless of availability
    @param use_any_existing_modules: if you find an existing module for any TC, don't replace it
    """
    # Collect available modules
    if retain_all_deps:
        # assume that no modules are available when forced, to retain all dependencies
        avail_modules = []
        _log.info("Forcing all dependencies to be retained.")
    else:
        # Get a list of all available modules (format: [(name, installversion), ...])
        avail_modules = modules_tool().available()
        if len(avail_modules) == 0:
            _log.warning("No installed modules. Your MODULEPATH is probably incomplete: %s" % os.getenv('MODULEPATH'))

    # Let's grab the toolchain of the parent
    toolchains = [ec['ec']['toolchain'] for ec in item_specs if ec['ec']['name'] == parent]
    # Populate the other toolchain possibilities
    current = toolchains[0]['name']
    while True:
        # Get the next subtoolchain
        if subtoolchains[current]:
            # See if we have the corresponding easyconfig in our list so we can get the version
            toolchain_easyconfigs = [ec for ec in item_specs if ec['ec']['name'] == subtoolchains[current]]
            if len(toolchain_easyconfigs) == 1:
                toolchains += [{'name': toolchain_easyconfigs[0]['ec']['name'],
                                'version': det_full_ec_version(toolchain_easyconfigs[0]['ec'])}]
            elif len(toolchain_easyconfigs) == 0:
                _log.info("Your toolchain hierarchy is not fully populated!")
                _log.info("No version found for subtoolchain %s of %s with parent software %s"
                          % (subtoolchains[current], current, parent))
            else:
                _log_error("Multiple easyconfigs found in list for toolchain %s", subtoolchains[current])
            current = subtoolchains[current]
        else:
            break
    _log.info("Found toolchain hierarchy %s", toolchains)

    # For each element in the list check the toolchain, if it sits in the hierarchy (and is not at the bottom or
    # 'dummy') search for a replacement.
    resolved_easyconfigs =[]
    for ec in item_specs:
        # First go down the list looking for an existing module, removing the list item if we find one
        cand_dep = ec
        resolved = False
        # Check that the toolchain of the item is already in the hierarchy, if not, do nothing
        if not cand_dep['ec']['toolchain'] in toolchains:
            _log.info("Toolchain of %s does not match parent" %cand_dep)
            resolved_easyconfigs.append(cand_dep)
            resolved = True

        if not resolved and (use_any_existing_modules and not retain_all_deps):
            for tc in reversed(toolchains):
                cand_dep['ec']['toolchain'] = tc
                if ActiveMNS().det_full_module_name(cand_dep) in avail_modules:
                    resolved_easyconfigs.append(cand_dep)
                    resolved = True
                    break
        # Look for any matching easyconfig starting from the bottom
        if not resolved:
            for tc in toolchains:
                cand_dep['ec']['toolchain'] = tc
                eb_file = robot_find_easyconfig(cand_dep['ec']['name'], det_full_ec_version(cand_dep['ec']))
                if eb_file is not None:
                    _log.info("Robot: resolving dependency %s with %s" % (cand_dep, eb_file))
                    # build specs should not be passed down to resolved dependencies,
                    # to avoid that e.g. --try-toolchain trickles down into the used toolchain itself
                    hidden = cand_dep.get('hidden', False)
                    parsed_ec = process_easyconfig(eb_file, parse_only=True, hidden=hidden)
                    if len(parsed_ec) > 1:
                        self.log.warning(
                            "More than one parsed easyconfig obtained from %s, only retaining first" % eb_file
                        )
                        self.log.debug("Full list of parsed easyconfigs: %s" % parsed_ec)
                    resolved_easyconfigs.append(parsed_ec[0])
                    resolved = True
                    break
        if not resolved:
            raise EasyBuildError(
                "Failed to find any easyconfig file for '%s' when determining minimal toolchain for: %s",
                ec['name'], ec
            )
    # Check each piece of software in the initial list appears in the final list
    initial_names = [ec['ec']['name'] for ec in item_specs]
    final_names = [ec['ec']['name'] for ec in resolved_easyconfigs]
    if not set(initial_names) == set(final_names):
        _log.error('Not all software in initial list appears in final list:%s :: %s' %initial_names %final_names)

    # Update dependencies within the final list so that all toolchains correspond correctly
    for dep_ec in resolved_easyconfigs:
        # Search through all other easyconfigs for matching dependencies
        for ec in resolved_easyconfigs:
            for dependency in ec['ec']['dependencies']:
                if dependency['name'] == dep_ec['ec']['name']:
                    # Update toolchain
                    dependency['toolchain'] = dep_ec['ec']['toolchain']
                    if dependency['toolchain']['name'] == DUMMY_TOOLCHAIN_NAME:
                        dependency['toolchain']['dummy'] = True
                    # Update module name
                    dependency['short_mod_name'] = ActiveMNS().det_short_module_name(dependency)
                    dependency['full_mod_name'] = ActiveMNS().det_full_module_name(dependency)
    return resolved_easyconfigs

def minimally_resolve_dependencies(unprocessed, retain_all_deps=False, use_any_existing_modules=False):
    """
    Work through the list of easyconfigs to determine an optimal order with minimal dependency resolution
    @param unprocessed: list of easyconfigs
    @param retain_all_deps: boolean indicating whether all dependencies must be retained, regardless of availability
    """
    if build_option('robot_path') is None:
        _log.info("No robot path : not (minimally) resolving dependencies")
        return resolve_dependencies(unprocessed, retain_all_deps=retain_all_deps)
    else:
        _, all_tc_classes = search_toolchain('')
        subtoolchains = dict((tc_class.NAME, getattr(tc_class, 'SUBTOOLCHAIN', None)) for tc_class in all_tc_classes)

        # Look over all elements of the list individually
        minimal_list = []
        for ec in unprocessed:
            item_specs = resolve_dependencies([ec], retain_all_deps=True)

            # Now we have a complete list of the dependencies, let's do a
            # search/replace for the toolchain, removing existing elements from the list according to retain_all_deps
            item_specs = replace_toolchain_with_hierarchy(
                item_specs, parent=ec['ec']['name'],
                retain_all_deps=retain_all_deps,
                use_any_existing_modules=use_any_existing_modules,
                subtoolchains=subtoolchains
            )
            # There should be no duplicate software in the final list, spit the dummy if there is (unless they are
            # fully consistent versions)
            #item_specs = nub(item_specs)  # FIXME nub on list of dicts
            for idx, check in enumerate(item_specs):
                if len([x for x in item_specs[idx:] if x['ec']['name'] == check['ec']['name']]) > 1:
                    _log.error("Conflicting dependency versions for %s easyconfig: %s", ec['name'], check['name'])

            minimal_list.extend(item_specs)

        # Finally, we pass our minimal list back through resolve_dependencies again to clean up the ordering
        #minimal_list = nub(minimal_list) # Unique items only  # FIXME nub on list of dicts
        return resolve_dependencies(minimal_list, retain_all_deps=retain_all_deps)

def resolve_dependencies(unprocessed, retain_all_deps=False):
    """
    Work through the list of easyconfigs to determine an optimal order
    @param unprocessed: list of easyconfigs
    @param retain_all_deps: boolean indicating whether all dependencies must be retained, regardless of availability;
                            retain all deps when True, check matching build option when False
    """

    print [x.get('full_mod_name', x) for x in unprocessed]

    robot = build_option('robot_path')
    # retain all dependencies if specified by either the resp. build option or the dedicated named argument
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
    being_installed = [p['full_mod_name'] for p in unprocessed]
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
            raise EasyBuildError("Maximum loop cnt %s reached, so quitting (unprocessed: %s, irresolvable: %s)",
                                 maxloopcnt, unprocessed, irresolvable)

        # first try resolving dependencies without using external dependencies
        last_processed_count = -1
        while len(avail_modules) > last_processed_count:
            last_processed_count = len(avail_modules)
            res = find_resolved_modules(unprocessed, avail_modules, retain_all_deps=retain_all_deps)
            more_ecs, unprocessed, avail_modules = res
            for ec in more_ecs:
                if not ec['full_mod_name'] in [x['full_mod_name'] for x in ordered_ecs]:
                    ordered_ecs.append(ec)

        # dependencies marked as external modules should be resolved via available modules at this point
        missing_external_modules = [d['full_mod_name'] for ec in unprocessed for d in ec['dependencies']
                                    if d.get('external_module', False)]
        if missing_external_modules:
            raise EasyBuildError("Missing modules for one or more dependencies marked as external modules: %s",
                                 missing_external_modules)

        # robot: look for existing dependencies, add them
        if robot and unprocessed:

            # rely on EasyBuild module naming scheme when resolving dependencies, since we know that will
            # generate sensible module names that include the necessary information for the resolution to work
            # (name, version, toolchain, versionsuffix)
            being_installed = [EasyBuildMNS().det_full_module_name(p['ec']) for p in unprocessed]

            additional = []
            for entry in unprocessed:
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
                        mods = [spec['ec'].full_mod_name for spec in processed_ecs]
                        dep_mod_name = ActiveMNS().det_full_module_name(cand_dep)
                        if not dep_mod_name in mods:
                            raise EasyBuildError("easyconfig file %s does not contain module %s (mods: %s)",
                                                 path, dep_mod_name, mods)

                        for ec in processed_ecs:
                            if not ec in unprocessed + additional:
                                additional.append(ec)
                                _log.debug("Added %s as dependency of %s" % (ec, entry))
                else:
                    mod_name = EasyBuildMNS().det_full_module_name(entry['ec'])
                    _log.debug("No more candidate dependencies to resolve for %s" % mod_name)

            # add additional (new) easyconfigs to list of stuff to process
            unprocessed.extend(additional)
            _log.debug("Unprocessed dependencies: %s", unprocessed)

        elif not robot:
            # no use in continuing if robot is not enabled, dependencies won't be resolved anyway
            irresolvable = [dep for x in unprocessed for dep in x['dependencies']]
            break

    if irresolvable:
        _log.warning("Irresolvable dependencies (details): %s" % irresolvable)
        irresolvable_mods_eb = [EasyBuildMNS().det_full_module_name(dep) for dep in irresolvable]
        _log.warning("Irresolvable dependencies (EasyBuild module names): %s" % ', '.join(irresolvable_mods_eb))
        irresolvable_mods = [ActiveMNS().det_full_module_name(dep) for dep in irresolvable]
        raise EasyBuildError("Irresolvable dependencies encountered: %s", ', '.join(irresolvable_mods))

    _log.info("Dependency resolution complete, building as follows: %s" % ordered_ecs)
    return ordered_ecs


def search_easyconfigs(query, short=False):
    """Search for easyconfigs, if a query is provided."""
    robot_path = build_option('robot_path')
    if robot_path:
        search_path = robot_path
    else:
        search_path = [os.getcwd()]
    ignore_dirs = build_option('ignore_dirs')
    silent = build_option('silent')
    search_file(search_path, query, short=short, ignore_dirs=ignore_dirs, silent=silent)
