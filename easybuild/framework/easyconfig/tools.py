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

import copy
import glob
import os
import re
import sys
import tempfile
from distutils.version import LooseVersion
from vsc import fancylogger
from vsc.utils.missing import nub

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

from easybuild.tools.build_log import EasyBuildError, print_error, print_msg, print_warning
from easybuild.tools.filetools import det_common_path_prefix, run_cmd, read_file, write_file
from easybuild.tools.module_generator import det_full_module_name
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.modules import modules_tool
from easybuild.tools.ordereddict import OrderedDict
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME
from easybuild.tools.utilities import quote_str
from easybuild.framework.easyconfig.easyconfig import EasyConfig
from easybuild.framework.easyconfig.format.format import get_format_version, FORMAT_DEFAULT_VERSION
from easybuild.framework.easyconfig.format.version import EasyVersion

_log = fancylogger.getLogger('easyconfig.tools', fname=False)


def ec_filename_for(path):
    """
    Return a suiting file name for the easyconfig file at <path>,
    as determined by its contents.
    """
    ec = EasyConfig(path, build_options={'validate': False})

    fn = "%s-%s.eb" % (ec['name'], det_full_ec_version(ec))

    return fn


def pick_version(req_ver, avail_vers):
    """Pick version based on an optionally desired version and available versions.

    If a desired version is specifed, the most recent version that is less recent
    than the desired version will be picked; else, the most recent version will be picked.

    This function returns both the version to be used, which is equal to the desired version
    if it was specified, and the version picked that matches that closest.
    """

    if not avail_vers:
        _log.error("Empty list of available versions passed.")

    selected_ver = None
    if req_ver:
        # if a desired version is specified,
        # retain the most recent version that's less recent than the desired version

        ver = req_ver

        if len(avail_vers) == 1:
            selected_ver = avail_vers[0]
        else:
            retained_vers = [v for v in avail_vers if v < LooseVersion(ver)]
            if retained_vers:
                selected_ver = retained_vers[-1]
            else:
                # if no versions are available that are less recent, take the least recent version
                selected_ver = sorted([LooseVersion(v) for v in avail_vers])[0]

    else:
        # if no desired version is specified, just use last version
        ver = avail_vers[-1]
        selected_ver = ver

    return (ver, selected_ver)


def create_paths(path, name, version):
    """
    Returns all the paths where easyconfig could be located
    <path> is the basepath
    <name> should be a string
    <version> can be a '*' if you use glob patterns, or an install version otherwise
    """
    return [os.path.join(path, name, version + ".eb"),
            os.path.join(path, name, "%s-%s.eb" % (name, version)),
            os.path.join(path, name.lower()[0], name, "%s-%s.eb" % (name, version)),
            os.path.join(path, "%s-%s.eb" % (name, version)),
           ]


def retrieve_blocks_in_spec(spec, only_blocks, silent=False):
    """
    Easyconfigs can contain blocks (headed by a [Title]-line)
    which contain commands specific to that block. Commands in the beginning of the file
    above any block headers are common and shared between each block.
    """
    reg_block = re.compile(r"^\s*\[([\w.-]+)\]\s*$", re.M)
    reg_dep_block = re.compile(r"^\s*block\s*=(\s*.*?)\s*$", re.M)

    spec_fn = os.path.basename(spec)
    try:
        txt = open(spec).read()
    except IOError, err:
        _log.error("Failed to read file %s: %s" % (spec, err))

    # split into blocks using regex
    pieces = reg_block.split(txt)
    # the first block contains common statements
    common = pieces.pop(0)

    # determine version of easyconfig format
    ec_format_version = get_format_version(txt)
    if ec_format_version is None:
        ec_format_version = FORMAT_DEFAULT_VERSION
    _log.debug("retrieve_blocks_in_spec: derived easyconfig format version: %s" % ec_format_version)

    # blocks in easyconfigs are only supported in format versions prior to 2.0
    if pieces and ec_format_version < EasyVersion('2.0'):
        # make a map of blocks
        blocks = []
        while pieces:
            block_name = pieces.pop(0)
            block_contents = pieces.pop(0)

            if block_name in [b['name'] for b in blocks]:
                msg = "Found block %s twice in %s." % (block_name, spec)
                _log.error(msg)

            block = {'name': block_name, 'contents': block_contents}

            # dependency block
            dep_block = reg_dep_block.search(block_contents)
            if dep_block:
                dependencies = eval(dep_block.group(1))
                if type(dependencies) == list:
                    block['dependencies'] = dependencies
                else:
                    block['dependencies'] = [dependencies]

            blocks.append(block)

        # make a new easyconfig for each block
        # they will be processed in the same order as they are all described in the original file
        specs = []
        for block in blocks:
            name = block['name']
            if only_blocks and not (name in only_blocks):
                print_msg("Skipping block %s-%s" % (spec_fn, name), silent=silent)
                continue

            (fd, block_path) = tempfile.mkstemp(prefix='easybuild-', suffix='%s-%s' % (spec_fn, name))
            os.close(fd)

            txt = common

            if 'dependencies' in block:
                for dep in block['dependencies']:
                    if not dep in [b['name'] for b in blocks]:
                        _log.error("Block %s depends on %s, but block was not found." % (name, dep))

                    dep = [b for b in blocks if b['name'] == dep][0]
                    txt += "\n# Dependency block %s" % (dep['name'])
                    txt += dep['contents']

            txt += "\n# Main block %s" % name
            txt += block['contents']

            write_file(block_path, txt)

            specs.append(block_path)

        _log.debug("Found %s block(s) in %s" % (len(specs), spec))
        return specs
    else:
        # no blocks, one file
        return [spec]


def process_easyconfig(path, build_options=None, build_specs=None):
    """
    Process easyconfig, returning some information for each block
    @param path: path to easyconfig file
    @param build_options: dictionary specifying build options (e.g. robot_path, check_osdeps, ...)
    @param build_specs: dictionary specifying build specifications (e.g. version, toolchain, ...)
    """
    blocks = retrieve_blocks_in_spec(path, build_options.get('only_blocks', None))

    easyconfigs = []
    for spec in blocks:
        # process for dependencies and real installversionname
        _log.debug("Processing easyconfig %s" % spec)

        # create easyconfig
        try:
            ec = EasyConfig(spec, build_options=build_options, build_specs=build_specs)
        except EasyBuildError, err:
            msg = "Failed to process easyconfig %s:\n%s" % (spec, err.msg)
            _log.exception(msg)

        name = ec['name']

        # this app will appear as following module in the list
        easyconfig = {
            'ec': ec,
            'spec': spec,
            'module': det_full_module_name(ec),
            'dependencies': [],
            'builddependencies': [],
        }
        if len(blocks) > 1:
            easyconfig['originalSpec'] = path

        # add build dependencies
        for dep in ec.builddependencies():
            _log.debug("Adding build dependency %s for app %s." % (dep, name))
            easyconfig['builddependencies'].append(dep)

        # add dependencies (including build dependencies)
        for dep in ec.dependencies():
            _log.debug("Adding dependency %s for app %s." % (dep, name))
            easyconfig['dependencies'].append(dep)

        # add toolchain as dependency too
        if ec.toolchain.name != DUMMY_TOOLCHAIN_NAME:
            dep = ec.toolchain.as_dict()
            _log.debug("Adding toolchain %s as dependency for app %s." % (dep, name))
            easyconfig['dependencies'].append(dep)

        del ec

        # this is used by the parallel builder
        easyconfig['unresolved_deps'] = copy.deepcopy(easyconfig['dependencies'])

        easyconfigs.append(easyconfig)

    return easyconfigs


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


def robot_find_easyconfig(paths, name, version):
    """
    Find an easyconfig for module in path
    """
    if not isinstance(paths, list):
        paths = [paths]
    # candidate easyconfig paths
    for path in paths:
        easyconfigs_paths = create_paths(path, name, version)
        for easyconfig_path in easyconfigs_paths:
            _log.debug("Checking easyconfig path %s" % easyconfig_path)
            if os.path.isfile(easyconfig_path):
                _log.debug("Found easyconfig file for name %s, version %s at %s" % (name, version, easyconfig_path))
                return os.path.abspath(easyconfig_path)

    return None


def resolve_dependencies(unprocessed, build_options=None, build_specs=None):
    """
    Work through the list of easyconfigs to determine an optimal order
    @param unprocessed: list of easyconfigs
    @param build_options: dictionary specifying build options (e.g. robot_path, check_osdeps, ...)
    @param build_specs: dictionary specifying build specifications (e.g. version, toolchain, ...)
    """

    robot = build_options.get('robot_path', None)

    if build_options.get('retain_all_deps', False):
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
                            irresolvable.append(cand_dep)
                        # remove irresolvable dependency from list of dependencies so we can continue
                        entry['dependencies'].remove(cand_dep)
                    else:
                        _log.info("Robot: resolving dependency %s with %s" % (cand_dep, path))
                        processed_ecs = process_easyconfig(path, build_options=build_options, build_specs=build_specs)

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


def print_dry_run(easyconfigs, short=False, build_options=None, build_specs=None):
    """
    Print dry run information
    @param easyconfigs: list of easyconfig files
    @param short: print short output (use a variable for the common prefix)
    @param build_options: dictionary specifying build options (e.g. robot_path, check_osdeps, ...)
    @param build_specs: dictionary specifying build specifications (e.g. version, toolchain, ...)
    """
    lines = []
    if build_options.get('robot_path', None) is None:
        lines.append("Dry run: printing build status of easyconfigs")
        all_specs = easyconfigs
    else:
        lines.append("Dry run: printing build status of easyconfigs and dependencies")
        build_options = copy.deepcopy(build_options)
        build_options.update({
            'retain_all_deps': True,
            'check_osdeps': False,
        })
        all_specs = resolve_dependencies(easyconfigs, build_options=build_options, build_specs=build_specs)

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
    silent = build_options.get('silent', False)
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


def obtain_ec_for(specs, paths, fp):
    """
    Obtain an easyconfig file to the given specifications.

    Either select between available ones, or use the best suited available one
    to generate a new easyconfig file.

    <paths> is a list of paths where easyconfig files can be found
    <fp> is the desired file name
    <log> is an EasyBuildLog instance
    """

    # ensure that at least name is specified
    if not specs.get('name'):
        _log.error("Supplied 'specs' dictionary doesn't even contain a name of a software package?")

    # collect paths to search in
    if not paths:
        _log.error("No paths to look for easyconfig files, specify a path with --robot.")

    # create glob patterns based on supplied info

    # figure out the install version
    cfg = {
        'version': specs.get('version', '*'),
        'toolchain': {
            'name': specs.get('toolchain_name', '*'),
            'version': specs.get('toolchain_version', '*'),
        },
        'versionprefix': specs.get('versionprefix', '*'),
        'versionsuffix': specs.get('versionsuffix', '*'),
    }
    installver = det_full_ec_version(cfg)

    # find easyconfigs that match a pattern
    easyconfig_files = []
    for path in paths:
        patterns = create_paths(path, specs['name'], installver)
        for pattern in patterns:
            easyconfig_files.extend(glob.glob(pattern))

    cnt = len(easyconfig_files)

    _log.debug("List of obtained easyconfig files (%d): %s" % (cnt, easyconfig_files))

    # select best easyconfig, or try to generate one that fits the requirements
    res = select_or_generate_ec(fp, paths, specs)

    if res:
        return res
    else:
        _log.error("No easyconfig found for requested software, and also failed to generate one.")


def obtain_path(specs, paths, try_to_generate=False, exit_on_error=True, silent=False):
    """Obtain a path for an easyconfig that matches the given specifications."""

    # if no easyconfig files/paths were provided, but we did get a software name,
    # we can try and find a suitable easyconfig ourselves, or generate one if we can
    (generated, fn) = obtain_ec_for(specs, paths, None)
    if not generated:
        return (fn, generated)
    else:
        # if an easyconfig was generated, make sure we're allowed to use it
        if try_to_generate:
            print_msg("Generated an easyconfig file %s, going to use it now..." % fn, silent=silent)
            return (fn, generated)
        else:
            try:
                os.remove(fn)
            except OSError, err:
                print_warning("Failed to remove generated easyconfig file %s: %s" % (fn, err))
            print_error(("Unable to find an easyconfig for the given specifications: %s; "
                         "to make EasyBuild try to generate a matching easyconfig, "
                         "use the --try-X options ") % specs, log=_log, exit_on_error=exit_on_error)


def select_or_generate_ec(fp, paths, specs):
    """
    Select or generate an easyconfig file with the given requirements, from existing easyconfig files.

    If easyconfig files are available for the specified software package,
    then this function will first try to determine which toolchain to use.
     * if a toolchain is given, it will use it (possible using a template easyconfig file as base);
     * if not, and only a single toolchain is available, is will assume it can use that toolchain
     * else, it fails -- EasyBuild doesn't select between multiple available toolchains

    Next, it will trim down the selected easyconfig files to a single one,
    based on the following requirements (in order of preference):
     * toolchain version
     * software version
     * other parameters (e.g. versionprefix, versionsuffix, etc.)

    If a complete match is found, it will return that easyconfig.
    Else, it will generate a new easyconfig file based on the selected 'best matching' easyconfig file.
    """

    specs = copy.deepcopy(specs)

    # ensure that at least name is specified
    if not specs.get('name'):
        _log.error("Supplied 'specs' dictionary doesn't even contain a name of a software package?")
    name = specs['name']
    handled_params = ['name']

    # find ALL available easyconfig files for specified software
    ec_files = []
    cfg = {
        'version': '*',
        'toolchain': {'name': DUMMY_TOOLCHAIN_NAME, 'version': '*'},
        'versionprefix': '*',
        'versionsuffix': '*',
    }
    installver = det_full_ec_version(cfg)
    for path in paths:
        patterns = create_paths(path, name, installver)
        for pattern in patterns:
            ec_files.extend(glob.glob(pattern))

    # we need at least one config file to start from
    if len(ec_files) == 0:
        # look for a template file if no easyconfig for specified software name is available
        for path in paths:
            templ_file = os.path.join(path, "TEMPLATE.eb")

            if os.path.isfile(templ_file):
                ec_files = [templ_file]
                break
            else:
                _log.debug("No template found at %s." % templ_file)

        if len(ec_files) == 0:
            _log.error("No easyconfig files found for software %s, and no templates available. I'm all out of ideas." % name)

    # we can't rely on set, because we also need to be able to obtain a list of unique lists
    def unique(l):
        """Retain unique elements in a sorted list."""
        l = sorted(l)
        if len(l) > 1:
            l2 = [l[0]]
            for x in l:
                if not x == l2[-1]:
                    l2.append(x)
            return l2
        else:
            return l

    # filter unique
    ec_files = nub(ec_files)
    _log.debug("Unique ec_files: %s" % ec_files)

    ecs_and_files = [(EasyConfig(f, build_options={'validate': False}), f) for f in ec_files]

    # TOOLCHAIN NAME

    # determine list of unique toolchain names
    tcnames = unique([x[0]['toolchain']['name'] for x in ecs_and_files])
    _log.debug("Found %d unique toolchain names: %s" % (len(tcnames), tcnames))

    # if a toolchain was selected, and we have no easyconfig files for it, try and use a template
    if specs.get('toolchain_name') and not specs['toolchain_name'] in tcnames:
        if "TEMPLATE" in tcnames:
            _log.info("No easyconfig file for specified toolchain, but template is available.")
        else:
            _log.error("No easyconfig file for %s with toolchain %s, " \
                      "and no template available." % (name, specs['toolchain_name']))

    tcname = specs.pop('toolchain_name', None)
    handled_params.append('toolchain_name')

    # trim down list according to selected toolchain
    if tcname in tcnames:
        # known toolchain, so only retain those
        selected_tcname = tcname
    else:
        if len(tcnames) == 1 and not tcnames[0] == "TEMPLATE":
            # only one (non-template) toolchain availble, so use that
            tcname = tcnames[0]
            selected_tcname = tcname
        elif len(tcnames) == 1 and tcnames[0] == "TEMPLATE":
            selected_tcname = tcnames[0]
        else:
            # fall-back: use template toolchain if a toolchain name was specified
            if tcname:
                selected_tcname = "TEMPLATE"
            else:
                # if multiple toolchains are available, and none is specified, we quit
                # we can't just pick one, how would we prefer one over the other?
                _log.error("No toolchain name specified, and more than one available: %s." % tcnames)

    _log.debug("Filtering easyconfigs based on toolchain name '%s'..." % selected_tcname)
    ecs_and_files = [x for x in ecs_and_files if x[0]['toolchain']['name'] == selected_tcname]
    _log.debug("Filtered easyconfigs: %s" % [x[1] for x in ecs_and_files])

    # TOOLCHAIN VERSION

    tcvers = unique([x[0]['toolchain']['version'] for x in ecs_and_files])
    _log.debug("Found %d unique toolchain versions: %s" % (len(tcvers), tcvers))

    tcver = specs.pop('toolchain_version', None)
    handled_params.append('toolchain_version')
    (tcver, selected_tcver) = pick_version(tcver, tcvers)

    _log.debug("Filtering easyconfigs based on toolchain version '%s'..." % selected_tcver)
    ecs_and_files = [x for x in ecs_and_files if x[0]['toolchain']['version'] == selected_tcver]
    _log.debug("Filtered easyconfigs: %s" % [x[1] for x in ecs_and_files])

    # add full toolchain specification to specs
    if tcname and tcver:
        specs.update({'toolchain': {'name': tcname, 'version': tcver}})
        handled_params.append('toolchain')
    else:
        if tcname:
            specs.update({'toolchain_name': tcname})
        if tcver:
            specs.update({'toolchain_version': tcver})

    # SOFTWARE VERSION

    vers = unique([x[0]['version'] for x in ecs_and_files])
    _log.debug("Found %d unique software versions: %s" % (len(vers), vers))

    ver = specs.pop('version', None)
    handled_params.append('version')
    (ver, selected_ver) = pick_version(ver, vers)
    if ver:
        specs.update({'version': ver})

    _log.debug("Filtering easyconfigs based on software version '%s'..." % selected_ver)
    ecs_and_files = [x for x in ecs_and_files if x[0]['version'] == selected_ver]
    _log.debug("Filtered easyconfigs: %s" % [x[1] for x in ecs_and_files])

    # go through parameters specified via --amend
    # always include versionprefix/suffix, because we might need it to generate a file name
    verpref = None
    versuff = None
    other_params = {'versionprefix': None, 'versionsuffix': None}
    for (param, val) in specs.items():
        if not param in handled_params:
            other_params.update({param: val})

    _log.debug("Filtering based on other parameters (specified via --amend): %s" % other_params)
    for (param, val) in other_params.items():

        if param in ecs_and_files[0][0]._config:
            vals = unique([x[0][param] for x in ecs_and_files])
        else:
            vals = []

        filter_ecs = False
        # try and select a value from the available ones, or fail if we can't
        if val in vals:
            # if the specified value is available, use it
            selected_val = val
            _log.debug("Specified %s is available, so using it: %s" % (param, selected_val))
            filter_ecs = True
        elif val:
            # if a value is specified, use that, even if it's not available yet
            selected_val = val
            # promote value to list if deemed appropriate
            if vals and type(vals[0]) == list and not type(val) == list:
                _log.debug("Promoting type of %s value to list, since original value was." % param)
                specs[param] = [val]
            _log.debug("%s is specified, so using it (even though it's not available yet): %s" % (param, selected_val))
        elif len(vals) == 1:
            # if only one value is available, use that
            selected_val = vals[0]
            _log.debug("Only one %s available ('%s'), so picking that" % (param, selected_val))
            filter_ecs = True
        else:
            # otherwise, we fail, because we don't know how to pick between different fixes
            _log.error("No %s specified, and can't pick from available %ses %s" % (param,
                                                                                  param,
                                                                                  vals))

        if filter_ecs:
            _log.debug("Filtering easyconfigs based on %s '%s'..." % (param, selected_val))
            ecs_and_files = [x for x in ecs_and_files if x[0][param] == selected_val]
            _log.debug("Filtered easyconfigs: %s" % [x[1] for x in ecs_and_files])

        # keep track of versionprefix/suffix
        if param == "versionprefix":
            verpref = selected_val
        elif param == "versionsuffix":
            versuff = selected_val

    cnt = len(ecs_and_files)
    if not cnt == 1:
        fs = [x[1] for x in ecs_and_files]
        _log.error("Failed to select a single easyconfig from available ones, %s left: %s" % (cnt, fs))
    else:
        (selected_ec, selected_ec_file) = ecs_and_files[0]

        # check whether selected easyconfig matches requirements
        match = True
        for (key, val) in specs.items():
            if key in selected_ec._config:
                # values must be equal to have a full match
                if not selected_ec[key] == val:
                    match = False
            else:
                # if we encounter a key that is not set in the selected easyconfig, we don't have a full match
                match = False

        # if it matches, no need to tweak
        if match:
            _log.info("Perfect match found: %s" % selected_ec_file)
            return (False, selected_ec_file)

        # GENERATE

        # if no file path was specified, generate a file name
        if not fp:
            cfg = {
                'version': ver,
                'toolchain': {'name': tcname, 'version': tcver},
                'versionprefix': verpref,
                'versionsuffix': versuff,
            }
            installver = det_full_ec_version(cfg)
            fp = "%s-%s.eb" % (name, installver)

        # generate tweaked easyconfig file
        tweak(selected_ec_file, fp, specs)

        _log.info("Generated easyconfig file %s, and using it to build the requested software." % fp)

        return (True, fp)


def tweak(src_fn, target_fn, tweaks):
    """
    Tweak an easyconfig file with the given list of tweaks, using replacement via regular expressions.
    Note: this will only work 'well-written' easyconfig files, i.e. ones that e.g. set the version
    once and then use the 'version' variable to construct the list of sources, and possibly other
    parameters that depend on the version (e.g. list of patch files, dependencies, version suffix, ...)

    The tweaks should be specified in a dictionary, with parameters and keys that map to the values
    to be set.

    Reads easyconfig file at path <src_fn>, and writes the tweaked easyconfig file to <target_fn>.

    If no target filename is provided, a target filepath is generated based on the contents of
    the tweaked easyconfig file.
    """

    # read easyconfig file
    ectxt = read_file(src_fn)

    _log.debug("Contents of original easyconfig file, prior to tweaking:\n%s" % ectxt)
    # determine new toolchain if it's being changed
    keys = tweaks.keys()
    if 'toolchain_name' in keys or 'toolchain_version' in keys:

        tc_regexp = re.compile(r"^\s*toolchain\s*=\s*(.*)$", re.M)

        res = tc_regexp.search(ectxt)
        if not res:
            _log.error("No toolchain found in easyconfig file %s?" % src_fn)

        toolchain = eval(res.group(1))

        for key in ['name', 'version']:
            tc_key = "toolchain_%s" % key
            if tc_key in keys:
                toolchain.update({key: tweaks[tc_key]})
                tweaks.pop(tc_key)

        class TcDict(dict):
            """A special dict class that represents trivial toolchains properly."""
            def __repr__(self):
                return "{'name': '%(name)s', 'version': '%(version)s'}" % self

        tweaks.update({'toolchain': TcDict({'name': toolchain['name'], 'version': toolchain['version']})})

        _log.debug("New toolchain constructed: %s" % tweaks['toolchain'])

    additions = []

    # we need to treat list values seperately, i.e. we prepend to the current value (if any)
    for (key, val) in tweaks.items():

        if isinstance(val, list):

            regexp = re.compile(r"^\s*%s\s*=\s*(.*)$" % key, re.M)

            res = regexp.search(ectxt)
            if res:
                fval = [x for x in val if x != '']  # filter out empty strings
                # determine to prepend/append or overwrite by checking first/last list item
                # - input ending with comma (empty tail list element) => prepend
                # - input starting with comma (empty head list element) => append
                # - no empty head/tail list element => overwrite
                if val[0] == '':
                    newval = "%s + %s" % (res.group(1), fval)
                    _log.debug("Appending %s to %s" % (fval, key))
                elif val[-1] == '':
                    newval = "%s + %s" % (fval, res.group(1))
                    _log.debug("Prepending %s to %s" % (fval, key))
                else:
                    newval = "%s" % fval
                    _log.debug("Overwriting %s with %s" % (key, fval))
                ectxt = regexp.sub("%s = %s # tweaked by EasyBuild (was: %s)" % (key, newval, res.group(1)), ectxt)
                _log.info("Tweaked %s list to '%s'" % (key, newval))
            else:
                additions.append("%s = %s # added by EasyBuild" % (key, val))

            tweaks.pop(key)

    # add parameters or replace existing ones
    for (key, val) in tweaks.items():

        regexp = re.compile(r"^\s*%s\s*=\s*(.*)$" % key, re.M)
        _log.debug("Regexp pattern for replacing '%s': %s" % (key, regexp.pattern))

        res = regexp.search(ectxt)
        if res:
            # only tweak if the value is different
            diff = True
            try:
                _log.debug("eval(%s): %s" % (res.group(1), eval(res.group(1))))
                diff = not eval(res.group(1)) == val
            except (NameError, SyntaxError):
                # if eval fails, just fall back to string comparison
                _log.debug("eval failed for \"%s\", falling back to string comparison against \"%s\"..." % (res.group(1), val))
                diff = not res.group(1) == val

            if diff:
                ectxt = regexp.sub("%s = %s # tweaked by EasyBuild (was: %s)" % (key, quote_str(val), res.group(1)), ectxt)
                _log.info("Tweaked '%s' to '%s'" % (key, quote_str(val)))
        else:
            additions.append("%s = %s" % (key, quote_str(val)))

    if additions:
        _log.info("Adding additional parameters to tweaked easyconfig file: %s")
        ectxt += "\n\n# added by EasyBuild as dictated by command line options\n"
        ectxt += '\n'.join(additions) + '\n'

    _log.debug("Contents of tweaked easyconfig file:\n%s" % ectxt)

    # come up with suiting file name for tweaked easyconfig file if none was specified
    if not target_fn:

        fn = None

        try:
            # obtain temporary filename
            fd, tmpfn = tempfile.mkstemp()
            os.close(fd)

            # write easyconfig to temporary file
            write_file(tmpfn, ectxt)

            # determine suiting filename
            fn = ec_filename_for(tmpfn)

            # get rid of temporary file
            os.remove(tmpfn)

        except OSError, err:
            _log.error("Failed to determine suiting filename for tweaked easyconfig file: %s" % err)

        target_fn = os.path.join(tempfile.gettempdir(), fn)
        _log.debug("Generated file name for tweaked easyconfig file: %s" % target_fn)

    # write out tweaked easyconfig file
    write_file(target_fn, ectxt)
    _log.info("Tweaked easyconfig file written to %s" % target_fn)

    return target_fn


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
