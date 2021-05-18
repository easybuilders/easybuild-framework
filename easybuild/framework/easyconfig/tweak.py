##
# Copyright 2009-2021 Ghent University
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
##
"""
Easyconfig module that provides functionality for tweaking existing eaysconfig (.eb) files.

:author: Stijn De Weirdt (Ghent University)
:author: Dries Verdegem (Ghent University)
:author: Kenneth Hoste (Ghent University)
:author: Pieter De Baets (Ghent University)
:author: Jens Timmerman (Ghent University)
:author: Toon Willems (Ghent University)
:author: Fotis Georgatos (Uni.Lu, NTUA)
:author: Alan O'Cais (Juelich Supercomputing Centre)
:author: Maxime Boissonneault (Universite Laval, Calcul Quebec, Compute Canada)
"""
import copy
import functools
import glob
import os
import re
import tempfile
from distutils.version import LooseVersion

from easybuild.base import fancylogger
from easybuild.framework.easyconfig.constants import EASYCONFIG_CONSTANTS
from easybuild.framework.easyconfig.default import is_easyconfig_parameter_default_value
from easybuild.framework.easyconfig.easyconfig import EasyConfig, create_paths, process_easyconfig
from easybuild.framework.easyconfig.easyconfig import get_toolchain_hierarchy
from easybuild.framework.easyconfig.format.one import EB_FORMAT_EXTENSION
from easybuild.framework.easyconfig.format.format import DEPENDENCY_PARAMETERS
from easybuild.framework.easyconfig.parser import fetch_parameters_from_easyconfig
from easybuild.framework.easyconfig.tools import alt_easyconfig_paths
from easybuild.toolchains.compiler.systemcompiler import TC_CONSTANT_SYSTEM
from easybuild.toolchains.gcccore import GCCcore
from easybuild.tools.build_log import EasyBuildError, print_warning
from easybuild.tools.config import build_option
from easybuild.tools.filetools import read_file, write_file
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.py2vs3 import string_type
from easybuild.tools.robot import resolve_dependencies, robot_find_easyconfig, search_easyconfigs
from easybuild.tools.toolchain.toolchain import SYSTEM_TOOLCHAIN_NAME
from easybuild.tools.toolchain.toolchain import TOOLCHAIN_CAPABILITIES
from easybuild.tools.utilities import flatten, nub, quote_str

_log = fancylogger.getLogger('easyconfig.tweak', fname=False)

EASYCONFIG_TEMPLATE = "TEMPLATE"


def ec_filename_for(path):
    """
    Return a suiting file name for the easyconfig file at <path>,
    as determined by its contents.
    """
    ec = EasyConfig(path, validate=False)

    fn = "%s-%s.eb" % (ec['name'], det_full_ec_version(ec))

    return fn


def tweak(easyconfigs, build_specs, modtool, targetdirs=None):
    """Tweak list of easyconfigs according to provided build specifications."""
    # keep track of originally listed easyconfigs (via their path)
    listed_ec_paths = [ec['spec'] for ec in easyconfigs]

    tweaked_ecs_path, tweaked_ecs_deps_path = None, None
    if targetdirs is not None:
        tweaked_ecs_path, tweaked_ecs_deps_path = targetdirs
    # make sure easyconfigs all feature the same toolchain (otherwise we *will* run into trouble)
    toolchains = nub(['%(name)s/%(version)s' % ec['ec']['toolchain'] for ec in easyconfigs])
    if len(toolchains) > 1:
        raise EasyBuildError("Multiple toolchains featured in easyconfigs, --try-X not supported in that case: %s",
                             toolchains)
    # Toolchain is unique, let's store it
    source_toolchain = easyconfigs[-1]['ec']['toolchain']
    modifying_toolchains_or_deps = False
    target_toolchain = {}
    src_to_dst_tc_mapping = {}
    revert_to_regex = False

    if 'update_deps' in build_specs:
        _log.experimental("Found build spec 'update_deps': Attempting to update dependency versions.")

    if any(key in build_specs for key in ['toolchain', 'toolchain_name', 'toolchain_version', 'update_deps']):
        if not build_option('map_toolchains'):
            if 'update_deps' in build_specs:
                raise EasyBuildError("Cannot use --try-update-deps without setting --map-toolchains")
            else:
                msg = "Mapping of (sub)toolchains (with --map-toolchains) disabled, so falling back to regex mode, "
                msg += "disabling recursion and not changing (sub)toolchains for dependencies"
                _log.info(msg)
                revert_to_regex = True

        if not revert_to_regex:
            # we're doing something that involves the toolchain hierarchy;
            # obtain full dependency graph for specified easyconfigs;
            # easyconfigs will be ordered 'top-to-bottom' (toolchains and dependencies appearing first)
            _log.debug("Updating toolchain and/or dependencies requested...applying build specifications recursively "
                       "(where appropriate):\n%s", build_specs)
            modifying_toolchains_or_deps = True
            pruned_build_specs = copy.copy(build_specs)

            update_dependencies = pruned_build_specs.pop('update_deps', None)
            ignore_versionsuffixes = pruned_build_specs.pop('ignore_versionsuffixes', None)
            if ignore_versionsuffixes and not update_dependencies:
                print_warning("--try-ignore-versionsuffixes is ignored if --try-update-deps is not True")
                ignore_versionsuffixes = False
            if 'toolchain' in pruned_build_specs:
                target_toolchain = pruned_build_specs.pop('toolchain')
                pruned_build_specs.pop('toolchain_name', '')
                pruned_build_specs.pop('toolchain_version', '')
            else:
                target_toolchain['name'] = pruned_build_specs.pop('toolchain_name', source_toolchain['name'])
                target_toolchain['version'] = pruned_build_specs.pop('toolchain_version', source_toolchain['version'])

            try:
                src_to_dst_tc_mapping = map_toolchain_hierarchies(source_toolchain, target_toolchain, modtool)
            except EasyBuildError as err:
                # make sure exception was raised by match_minimum_tc_specs because toolchain mapping didn't work
                if "No possible mapping from source toolchain" in err.msg:
                    error_msg = err.msg + '\n'
                    error_msg += "Toolchain %s is not equivalent to toolchain %s in terms of capabilities. "
                    error_msg += "(If you know what you are doing, "
                    error_msg += "you can use --disable-map-toolchains to proceed anyway.)"
                    raise EasyBuildError(error_msg, target_toolchain['name'], source_toolchain['name'])
                else:
                    # simply re-raise the exception if something else went wrong
                    raise err

            orig_ecs = resolve_dependencies(easyconfigs, modtool, retain_all_deps=True)

            # Filter out the toolchain hierarchy (which would only appear if we are applying build_specs recursively)
            # Also filter any dependencies of the hierarchy (unless they were originally listed for tweaking)
            _log.debug("Filtering out toolchain hierarchy and dependencies for %s", source_toolchain)
            if source_toolchain['name'] != SYSTEM_TOOLCHAIN_NAME:
                path = robot_find_easyconfig(source_toolchain['name'], source_toolchain['version'])
                toolchain_ec = process_easyconfig(path)
                toolchain_deps = resolve_dependencies(toolchain_ec, modtool, retain_all_deps=True)
                toolchain_dep_paths = [dep['spec'] for dep in toolchain_deps]
                # only retain toolchain dependencies that are not in original list of easyconfigs to tweak
                toolchain_dep_paths = [td for td in toolchain_dep_paths if td not in listed_ec_paths]
            else:
                toolchain_dep_paths = []

            i = 0
            while i < len(orig_ecs):
                if orig_ecs[i]['spec'] in toolchain_dep_paths:
                    # drop elements in toolchain hierarchy
                    del orig_ecs[i]
                else:
                    i += 1
    else:
        revert_to_regex = True

    if revert_to_regex:
        # no recursion if software name/version build specification are included or we are amending something
        # in that case, do not construct full dependency graph
        orig_ecs = easyconfigs
        _log.debug("Software name/version found, so not applying build specifications recursively: %s" % build_specs)

    # generate tweaked easyconfigs, and continue with those instead
    tweaked_easyconfigs = []
    for orig_ec in orig_ecs:
        # Only return tweaked easyconfigs for easyconfigs which were listed originally on the command line
        # (and use the prepended path so that they are found first).
        # easyconfig files for dependencies are also generated but not included, they will be resolved via --robot
        # either from existing easyconfigs or, if that fails, from easyconfigs in the appended path

        tc_name = orig_ec['ec']['toolchain']['name']

        new_ec_file = None
        verification_build_specs = copy.copy(build_specs)
        if orig_ec['spec'] in listed_ec_paths:
            if modifying_toolchains_or_deps:
                if tc_name in src_to_dst_tc_mapping:
                    new_ec_file = map_easyconfig_to_target_tc_hierarchy(orig_ec['spec'], src_to_dst_tc_mapping,
                                                                        targetdir=tweaked_ecs_path,
                                                                        update_build_specs=pruned_build_specs,
                                                                        update_dep_versions=update_dependencies,
                                                                        ignore_versionsuffixes=ignore_versionsuffixes)
                    # Need to update the toolchain in the build_specs to match the toolchain mapping
                    keys = verification_build_specs.keys()
                    if 'toolchain_name' in keys:
                        verification_build_specs['toolchain_name'] = src_to_dst_tc_mapping[tc_name]['name']
                    if 'toolchain_version' in keys:
                        verification_build_specs['toolchain_version'] = src_to_dst_tc_mapping[tc_name]['version']
                    if 'toolchain' in keys:
                        verification_build_specs['toolchain'] = src_to_dst_tc_mapping[tc_name]
            else:
                new_ec_file = tweak_one(orig_ec['spec'], None, build_specs, targetdir=tweaked_ecs_path)

            if new_ec_file:
                new_ecs = process_easyconfig(new_ec_file, build_specs=verification_build_specs)
                tweaked_easyconfigs.extend(new_ecs)
        else:
            # Place all tweaked dependency easyconfigs in the directory appended to the robot path
            if modifying_toolchains_or_deps:
                if tc_name in src_to_dst_tc_mapping:
                    # Note pruned_build_specs are not passed down for dependencies
                    map_easyconfig_to_target_tc_hierarchy(orig_ec['spec'], src_to_dst_tc_mapping,
                                                          targetdir=tweaked_ecs_deps_path,
                                                          update_dep_versions=update_dependencies,
                                                          ignore_versionsuffixes=ignore_versionsuffixes)
            else:
                tweak_one(orig_ec['spec'], None, build_specs, targetdir=tweaked_ecs_deps_path)

    return tweaked_easyconfigs


def tweak_one(orig_ec, tweaked_ec, tweaks, targetdir=None):
    """
    Tweak an easyconfig file with the given list of tweaks, using replacement via regular expressions.
    Note: this will only work 'well-written' easyconfig files, i.e. ones that e.g. set the version
    once and then use the 'version' variable to construct the list of sources, and possibly other
    parameters that depend on the version (e.g. list of patch files, dependencies, version suffix, ...)

    The tweaks should be specified in a dictionary, with parameters and keys that map to the values
    to be set.

    Reads easyconfig file at path <orig_ec>, and writes the tweaked easyconfig file to <tweaked_ec>.

    If <tweaked_ec> is not provided, a target filepath is generated based on <targetdir> and the
    contents of the tweaked easyconfig file.

    :param orig_ec: location of original easyconfig file to read
    :param tweaked_ec: location where tweaked easyconfig file should be written
                       (if this is None, then filename for tweaked easyconfig is auto-derived from contents)
    :param tweaks: dictionary with set of changes to apply to original easyconfig file
    :param targetdir: target directory for tweaked easyconfig file, defaults to temporary directory
                      (only used if tweaked_ec is None)
    """

    # read easyconfig file
    ectxt = read_file(orig_ec)

    _log.debug("Contents of original easyconfig file, prior to tweaking:\n%s" % ectxt)
    # determine new toolchain if it's being changed
    keys = tweaks.keys()
    if 'toolchain_name' in keys or 'toolchain_version' in keys:
        # note: this assumes that the toolchain spec is single-line
        tc_regexp = re.compile(r"^\s*toolchain\s*=\s*(.*)$", re.M)
        res = tc_regexp.search(ectxt)
        if not res:
            raise EasyBuildError("No toolchain found in easyconfig file %s: %s", orig_ec, ectxt)

        # need to treat toolchain specified via 'SYSTEM' constant separately,
        # since SYSTEM constant is not defined during 'eval'
        if res.group(1) == 'SYSTEM':
            toolchain = copy.copy(EASYCONFIG_CONSTANTS['SYSTEM'][0])
        else:
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

    # automagically clear out list of checksums if software version is being tweaked
    if 'version' in tweaks and 'checksums' not in tweaks:
        tweaks['checksums'] = []
        _log.warning("Tweaking version: checksums cleared, verification disabled.")

    # we need to treat list values separately, i.e. we prepend to the current value (if any)
    for key in list(tweaks):
        val = tweaks[key]

        if isinstance(val, list):
            # use non-greedy matching for list value using '*?' to avoid including other parameters in match,
            # and a lookahead assertion (?=...) so next line is either another parameter definition or a blank line
            regexp = re.compile(r"^(?P<key>\s*%s)\s*=\s*(?P<val>\[(.|\n)*?\])\s*$(?=(\n^\w+\s*=.*|\s*)$)" % key, re.M)
            res = regexp.search(ectxt)
            if res:
                fval = [x for x in val if x != '']  # filter out empty strings
                # determine to prepend/append or overwrite by checking first/last list item
                # - input ending with comma (empty tail list element) => prepend
                # - input starting with comma (empty head list element) => append
                # - no empty head/tail list element => overwrite
                if not val:
                    newval = '[]'
                    _log.debug("Clearing %s to empty list (was: %s)" % (key, res.group('val')))
                elif val[0] == '':
                    newval = "%s + %s" % (res.group('val'), fval)
                    _log.debug("Appending %s to %s" % (fval, key))
                elif val[-1] == '':
                    newval = "%s + %s" % (fval, res.group('val'))
                    _log.debug("Prepending %s to %s" % (fval, key))
                else:
                    newval = "%s" % fval
                    _log.debug("Overwriting %s with %s" % (key, fval))
                ectxt = regexp.sub("%s = %s" % (res.group('key'), newval), ectxt)
                _log.info("Tweaked %s list to '%s'" % (key, newval))
            elif not is_easyconfig_parameter_default_value(key, val):
                additions.append("%s = %s" % (key, val))

            tweaks.pop(key)

    # add parameters or replace existing ones
    special_values = {
        # if the value is True/False/None then take that
        'True': True,
        'False': False,
        'None': None,
        # if e.g. (literal) True is wanted, then it can be passed as "True"/'True'
        "'True'": 'True',
        '"True"': 'True',
        "'False'": 'False',
        '"False"': 'False',
        "'None'": 'None',
        '"None"': 'None',
    }
    for (key, val) in tweaks.items():
        if isinstance(val, string_type) and val in special_values:
            str_val = val
            val = special_values[val]
        else:
            str_val = quote_str(val)

        regexp = re.compile(r"^(?P<key>\s*%s)\s*=\s*(?P<val>.*)$" % key, re.M)
        _log.debug("Regexp pattern for replacing '%s': %s" % (key, regexp.pattern))
        res = regexp.search(ectxt)
        if res:
            # only tweak if the value is different
            diff = True
            try:
                _log.debug("eval(%s): %s" % (res.group('val'), eval(res.group('val'))))
                diff = eval(res.group('val')) != val
            except (NameError, SyntaxError):
                # if eval fails, just fall back to string comparison
                _log.debug("eval failed for \"%s\", falling back to string comparison against \"%s\"...",
                           res.group('val'), val)
                diff = res.group('val') != val

            if diff:
                ectxt = regexp.sub("%s = %s" % (res.group('key'), str_val), ectxt)
                _log.info("Tweaked '%s' to '%s'" % (key, str_val))
        elif not is_easyconfig_parameter_default_value(key, val):
            additions.append("%s = %s" % (key, str_val))

    if additions:
        _log.info("Adding additional parameters to tweaked easyconfig file: %s" % additions)
        ectxt = '\n'.join([ectxt] + additions)

    _log.debug("Contents of tweaked easyconfig file:\n%s" % ectxt)

    # come up with suiting file name for tweaked easyconfig file if none was specified
    if tweaked_ec is None:
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
        except OSError as err:
            raise EasyBuildError("Failed to determine suiting filename for tweaked easyconfig file: %s", err)

        if targetdir is None:
            targetdir = tempfile.gettempdir()
        tweaked_ec = os.path.join(targetdir, fn)
        _log.debug("Generated file name for tweaked easyconfig file: %s", tweaked_ec)

    # write out tweaked easyconfig file
    write_file(tweaked_ec, ectxt, backup=True, always_overwrite=False, verbose=True)
    _log.info("Tweaked easyconfig file written to %s", tweaked_ec)

    return tweaked_ec


def pick_version(req_ver, avail_vers):
    """Pick version based on an optionally desired version and available versions.

    If a desired version is specifed, the most recent version that is less recent than or equal to
    the desired version will be picked; else, the most recent version will be picked.

    This function returns both the version to be used, which is equal to the required version
    if it was specified, and the version picked that matches that closest.

    :param req_ver: required version
    :param avail_vers: list of available versions
    """

    if not avail_vers:
        raise EasyBuildError("Empty list of available versions passed.")

    selected_ver = None
    if req_ver:
        # if a desired version is specified,
        # retain the most recent version that's less recent or equal than the desired version
        ver = req_ver

        if len(avail_vers) == 1:
            selected_ver = avail_vers[0]
        else:
            retained_vers = [v for v in avail_vers if LooseVersion(v) <= LooseVersion(ver)]
            if retained_vers:
                selected_ver = sorted(retained_vers, key=LooseVersion)[-1]
            else:
                # if no versions are available that are less recent, take the least recent version
                selected_ver = sorted(avail_vers, key=LooseVersion)[0]
    else:
        # if no desired version is specified, just use last version
        ver = avail_vers[-1]
        selected_ver = ver

    return (ver, selected_ver)


def find_matching_easyconfigs(name, installver, paths):
    """
    Find easyconfigs that match specified name/installversion in specified list of paths.

    :param name: software name
    :param installver: software install version (which includes version, toolchain, versionprefix/suffix, ...)
    :param paths: list of paths to search easyconfigs in
    """
    ec_files = []
    for path in paths:
        patterns = create_paths(path, name, installver)
        for pattern in patterns:
            more_ec_files = filter(os.path.isfile, sorted(glob.glob(pattern)))
            _log.debug("Including files that match glob pattern '%s': %s" % (pattern, more_ec_files))
            ec_files.extend(more_ec_files)

    # only retain unique easyconfig paths
    return nub(ec_files)


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
        raise EasyBuildError("Supplied 'specs' dictionary doesn't even contain a name of a software package?")
    name = specs['name']
    handled_params = ['name']

    # find ALL available easyconfig files for specified software
    cfg = {
        'version': '*',
        'toolchain': {'name': SYSTEM_TOOLCHAIN_NAME, 'version': '*'},
        'versionprefix': '*',
        'versionsuffix': '*',
    }
    installver = det_full_ec_version(cfg)
    ec_files = find_matching_easyconfigs(name, installver, paths)
    _log.debug("Unique ec_files: %s" % ec_files)

    # we need at least one config file to start from
    if len(ec_files) == 0:
        # look for a template file if no easyconfig for specified software name is available
        for path in paths:
            templ_file = os.path.join(path, "%s.eb" % EASYCONFIG_TEMPLATE)

            if os.path.isfile(templ_file):
                ec_files = [templ_file]
                break
            else:
                _log.debug("No template found at %s." % templ_file)

        if len(ec_files) == 0:
            raise EasyBuildError("No easyconfig files found for software %s, and no templates available. "
                                 "I'm all out of ideas.", name)

    ecs_and_files = [(EasyConfig(f, validate=False), f) for f in ec_files]

    # TOOLCHAIN NAME

    # we can't rely on set, because we also need to be able to obtain a list of unique lists
    def unique(lst, sortkey=None):
        """Retain unique elements in a sorted list."""
        if sortkey:
            lst = sorted(lst, key=sortkey)
        else:
            lst = sorted(lst)
        if len(lst) > 1:
            res = [lst[0]]
            for x in lst:
                if not x == res[-1]:
                    res.append(x)
            return res
        else:
            return lst

    # determine list of unique toolchain names
    tcnames = unique([x[0]['toolchain']['name'] for x in ecs_and_files])
    _log.debug("Found %d unique toolchain names: %s" % (len(tcnames), tcnames))

    # if a toolchain was selected, and we have no easyconfig files for it, try and use a template
    if specs.get('toolchain_name') and not specs['toolchain_name'] in tcnames:
        if EASYCONFIG_TEMPLATE in tcnames:
            _log.info("No easyconfig file for specified toolchain, but template is available.")
        else:
            raise EasyBuildError("No easyconfig file for %s with toolchain %s, and no template available.",
                                 name, specs['toolchain_name'])

    tcname = specs.pop('toolchain_name', None)
    handled_params.append('toolchain_name')

    # trim down list according to selected toolchain
    if tcname in tcnames:
        # known toolchain, so only retain those
        selected_tcname = tcname
    else:
        if len(tcnames) == 1 and not tcnames[0] == EASYCONFIG_TEMPLATE:
            # only one (non-template) toolchain availble, so use that
            tcname = tcnames[0]
            selected_tcname = tcname
        elif len(tcnames) == 1 and tcnames[0] == EASYCONFIG_TEMPLATE:
            selected_tcname = tcnames[0]
        else:
            # fall-back: use template toolchain if a toolchain name was specified
            if tcname:
                selected_tcname = EASYCONFIG_TEMPLATE
            else:
                # if multiple toolchains are available, and none is specified, we quit
                # we can't just pick one, how would we prefer one over the other?
                raise EasyBuildError("No toolchain name specified, and more than one available: %s.", tcnames)

    _log.debug("Filtering easyconfigs based on toolchain name '%s'..." % selected_tcname)
    ecs_and_files = [x for x in ecs_and_files if x[0]['toolchain']['name'] == selected_tcname]
    _log.debug("Filtered easyconfigs: %s" % [x[1] for x in ecs_and_files])

    # TOOLCHAIN VERSION
    tcvers = unique([x[0]['toolchain']['version'] for x in ecs_and_files if x[0]['toolchain']['version']],
                    sortkey=LooseVersion)
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

    vers = unique([x[0]['version'] for x in ecs_and_files if x[0]['version']], sortkey=LooseVersion)

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
        if param not in handled_params:
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
            if vals and isinstance(vals[0], list) and not isinstance(val, list):
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
            raise EasyBuildError("No %s specified, and can't pick from available ones: %s", param, vals)

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
        raise EasyBuildError("Failed to select a single easyconfig from available ones, %s left: %s", cnt, fs)
    else:
        (selected_ec, selected_ec_file) = ecs_and_files[0]

        # check whether selected easyconfig matches requirements
        match = True
        for (key, val) in specs.items():
            if key in selected_ec._config:
                # values must be equal to have a full match
                if selected_ec[key] != val:
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
        if fp is None:
            cfg = {
                'version': ver,
                'toolchain': {'name': tcname, 'version': tcver},
                'versionprefix': verpref,
                'versionsuffix': versuff,
            }
            installver = det_full_ec_version(cfg)
            fp = "%s-%s.eb" % (name, installver)

        # generate tweaked easyconfig file
        tweak_one(selected_ec_file, fp, specs)

        _log.info("Generated easyconfig file %s, and using it to build the requested software." % fp)

        return (True, fp)


def obtain_ec_for(specs, paths, fp=None):
    """
    Obtain an easyconfig file to the given specifications.

    Either select between available ones, or use the best suited available one
    to generate a new easyconfig file.

    :param specs: list of available easyconfig files
    :param paths: a list of paths where easyconfig files can be found
    :param fp: the desired file name
    """

    # ensure that at least name is specified
    if not specs.get('name'):
        raise EasyBuildError("Supplied 'specs' dictionary doesn't even contain a name of a software package?")

    # collect paths to search in
    if not paths:
        raise EasyBuildError("No paths to look for easyconfig files, specify a path with --robot.")

    # select best easyconfig, or try to generate one that fits the requirements
    res = select_or_generate_ec(fp, paths, specs)

    if res:
        return res
    else:
        raise EasyBuildError("No easyconfig found for requested software, and also failed to generate one.")


def check_capability_mapping(source_tc_spec, target_tc_spec):
    """
    Compare whether the capabilities of a source toolchain are all present in a target toolchain

    :param source_tc_spec: specs of source toolchain
    :param target_tc_spec: specs of target toolchain

    :return: boolean indicating whether or not source toolchain is compatible with target toolchain
    """
    can_map = True
    # Check they have same capabilities
    for key in TOOLCHAIN_CAPABILITIES:
        if target_tc_spec[key] is None and source_tc_spec[key] is not None:
            can_map = False
            break

    return can_map


def match_minimum_tc_specs(source_tc_spec, target_tc_hierarchy):
    """
    Match a source toolchain spec to the minimal corresponding toolchain in a target hierarchy

    :param source_tc_spec: specs of source toolchain
    :param target_tc_hierarchy: hierarchy of specs for target toolchain
    """
    minimal_matching_toolchain = {}
    target_compiler_family = ''

    # break out once we've found the first match since the hierarchy is ordered low to high in terms of capabilities
    for target_tc_spec in target_tc_hierarchy:
        if check_capability_mapping(source_tc_spec, target_tc_spec):
            # GCCcore has compiler capabilities,
            # but should only be used in the target if the original toolchain was also GCCcore
            if target_tc_spec['name'] != GCCcore.NAME or source_tc_spec['name'] == GCCcore.NAME:
                minimal_matching_toolchain = {'name': target_tc_spec['name'], 'version': target_tc_spec['version']}
                target_compiler_family = target_tc_spec['comp_family']
                break

    if not minimal_matching_toolchain:
        raise EasyBuildError("No possible mapping from source toolchain spec %s to target toolchain hierarchy specs %s",
                             source_tc_spec, target_tc_hierarchy)

    # Warn if we are changing compiler families, this is very likely to cause problems
    if target_compiler_family != source_tc_spec['comp_family']:
        print_warning("Your request will result in a compiler family switch (%s to %s). Here be dragons!" %
                      (source_tc_spec['comp_family'], target_compiler_family), silent=build_option('silent'))

    return minimal_matching_toolchain


def get_dep_tree_of_toolchain(toolchain_spec, modtool):
    """
    Get list of dependencies of a toolchain (as EasyConfig objects)

    :param toolchain_spec: toolchain spec to get the dependencies of
    :param modtool: module tool used

    :return: The dependency tree of the toolchain spec
    """
    path = robot_find_easyconfig(toolchain_spec['name'], toolchain_spec['version'])
    if path is None:
        raise EasyBuildError("Could not find easyconfig for %s toolchain version %s",
                             toolchain_spec['name'], toolchain_spec['version'])
    ec = process_easyconfig(path, validate=False)

    return [dep['ec'] for dep in resolve_dependencies(ec, modtool, retain_all_deps=True)]


def map_toolchain_hierarchies(source_toolchain, target_toolchain, modtool):
    """
    Create a map between toolchain hierarchy of the initial toolchain and that of the target toolchain

    :param source_toolchain: initial toolchain of the easyconfig(s)
    :param target_toolchain: target toolchain for tweaked easyconfig(s)
    :param modtool: module tool used

    :return: mapping from source hierarchy to target hierarchy
    """
    tc_mapping = {}
    source_tc_hierarchy = get_toolchain_hierarchy(source_toolchain, incl_capabilities=True)
    target_tc_hierarchy = get_toolchain_hierarchy(target_toolchain, incl_capabilities=True)

    for toolchain_spec in source_tc_hierarchy:
        tc_mapping[toolchain_spec['name']] = match_minimum_tc_specs(toolchain_spec, target_tc_hierarchy)

    # Check for presence of binutils in source and target toolchain dependency trees
    # (only do this when GCCcore is present in both and GCCcore is not the top of the tree)
    gcccore = GCCcore.NAME
    source_tc_names = [tc_spec['name'] for tc_spec in source_tc_hierarchy]
    target_tc_names = [tc_spec['name'] for tc_spec in target_tc_hierarchy]
    if gcccore in source_tc_names and gcccore in target_tc_names and source_tc_hierarchy[-1]['name'] != gcccore:
        binutils = 'binutils'
        # Determine the dependency trees
        source_dep_tree = get_dep_tree_of_toolchain(source_tc_hierarchy[-1], modtool)
        target_dep_tree = get_dep_tree_of_toolchain(target_tc_hierarchy[-1], modtool)
        # Find the binutils mapping
        if binutils in [dep['name'] for dep in source_dep_tree]:
            # We need the binutils that was built using GCCcore (we assume that everything is using standard behaviour:
            # build binutils with GCCcore and then use that for anything built with GCCcore)
            binutils_deps = [dep for dep in target_dep_tree if dep['name'] == binutils]
            binutils_gcccore_deps = [dep for dep in binutils_deps if dep['toolchain']['name'] == gcccore]
            if len(binutils_gcccore_deps) == 1:
                tc_mapping[binutils] = {'version': binutils_gcccore_deps[0]['version'],
                                        'versionsuffix': binutils_gcccore_deps[0]['versionsuffix']}
            else:
                raise EasyBuildError("Target hierarchy %s should have binutils using GCCcore, can't determine mapping!",
                                     target_tc_hierarchy[-1])

    return tc_mapping


def map_versionsuffixes_cache(func):
    """Function decorator to cache (and retrieve cached) versionsuffixes mapping between toolchains."""
    cache = {}

    @functools.wraps(func)
    def cache_aware_func(software_name, original_toolchain, toolchain_mapping):
        """Look up original_toolchain in cache first, determine and cache it if not available yet."""
        # No need for toolchain_mapping to change to be part of the key, it is unique in this context
        cache_key = (software_name, original_toolchain['name'], original_toolchain['version'])

        # fetch from cache if available, cache it if it's not
        if cache_key in cache:
            _log.debug("Using cache to return version suffix mapping for toolchain %s: %s", str(cache_key),
                       cache[cache_key])
        else:
            versionsuffix_mappings = func(software_name, original_toolchain, toolchain_mapping)
            cache[cache_key] = versionsuffix_mappings
        return cache[cache_key]

    # Expose clear method of cache to wrapped function
    cache_aware_func.clear = cache.clear

    return cache_aware_func


@map_versionsuffixes_cache
def map_common_versionsuffixes(software_name, original_toolchain, toolchain_mapping):
    """
    Create a mapping of common versionssuffixes (like `-Python-%(pyver)s`) between toolchains

    :param software_name: Name of software
    :param original_toolchain: original toolchain
    :param toolchain_mapping: toolchain mapping from that containing original to target
    :return: dictionary of possible mappings
    """
    orig_toolchain_hierarchy = get_toolchain_hierarchy(original_toolchain)

    versionsuffix_mappings = {}

    # Find all versions in the original toolchain hierarchy and register what they would be mapped to
    for toolchain in orig_toolchain_hierarchy:
        prefix_stub = '%s-' % software_name
        cand_paths, toolchain_suffix = get_matching_easyconfig_candidates(prefix_stub, toolchain)
        for path in cand_paths:

            version, versionsuffix = fetch_parameters_from_easyconfig(read_file(path), ['version', 'versionsuffix'])

            if version is None:
                raise EasyBuildError("Failed to extract 'version' value from %s", path)
            else:
                major_version = version.split('.')[0]
                try:
                    # make sure we have a have an integer value for the major version
                    int(major_version)
                except ValueError:
                    _log.warning("Cannot extract major version for %s from %s", prefix_stub, version)

            # Use these values to construct a dependency
            software_as_dep = {
                'name': software_name,
                'toolchain': toolchain,
                'version': version,
                'versionsuffix': versionsuffix or '',
            }
            # See what this dep would be mapped to
            version_matches = find_potential_version_mappings(software_as_dep, toolchain_mapping, quiet=True)
            if version_matches:
                target_version = version_matches[0]['version']
                if LooseVersion(target_version) > LooseVersion(version):
                    original_suffix = '-%s-%s' % (software_name, version)
                    mapped_suffix = '-%s-%s' % (software_name, target_version)
                    # Make sure mapping is unique
                    if original_suffix in versionsuffix_mappings:
                        if mapped_suffix != versionsuffix_mappings[original_suffix]:
                            raise EasyBuildError("No unique versionsuffix mapping for %s in %s toolchain "
                                                 "hierarchy to %s toolchain hierarchy (mapped suffix was %s but "
                                                 "versionsuffix mappings were %s)",
                                                 original_suffix, original_toolchain,
                                                 toolchain_mapping[original_toolchain['name']], mapped_suffix,
                                                 versionsuffix_mappings)
                    else:
                        versionsuffix_mappings[original_suffix] = mapped_suffix

    _log.info("Identified version suffix mappings: %s", versionsuffix_mappings)
    return versionsuffix_mappings


def get_matching_easyconfig_candidates(prefix_stub, toolchain):
    """
    Find easyconfigs that match specified requirements w.r.t. toolchain and partial filename pattern.

    :param prefix_stub: stub used in regex (e.g., 'Python-' or 'Python-2')
    :param toolchain: the toolchain to use with the search
    :return: list of candidate paths, toolchain_suffix of candidates
    """
    if toolchain['name'] == SYSTEM_TOOLCHAIN_NAME:
        toolchain_suffix = EB_FORMAT_EXTENSION
    else:
        toolchain_suffix = '-%s-%s' % (toolchain['name'], toolchain['version'])
    regex_search_query = '^%s.*' % prefix_stub + toolchain_suffix
    cand_paths = search_easyconfigs(regex_search_query, consider_extra_paths=False, print_result=False,
                                    case_sensitive=True)
    return cand_paths, toolchain_suffix


def map_easyconfig_to_target_tc_hierarchy(ec_spec, toolchain_mapping, targetdir=None, update_build_specs=None,
                                          update_dep_versions=False, ignore_versionsuffixes=False):
    """
    Take an easyconfig spec, parse it, map it to a target toolchain and dump it out

    :param ec_spec: location of original easyconfig file
    :param toolchain_mapping: mapping between source toolchain and target toolchain
    :param targetdir: directory to dump the modified easyconfig file in
    :param update_build_specs: dict with names and values of easyconfig parameters to tweak
    :param update_dep_versions: boolean indicating whether dependency versions should be updated

    :return: Location of the modified easyconfig file
    """
    # Fully parse the original easyconfig
    parsed_ec = process_easyconfig(ec_spec, validate=False)[0]['ec']

    versonsuffix_mapping = {}
    # We only need to map versionsuffixes if we are updating dependency versions and if there are
    # versionsuffixes being used in dependencies
    if update_dep_versions and (list_deps_versionsuffixes(ec_spec) or parsed_ec['versionsuffix']):
        # We may need to update the versionsuffix if it is like, for example, `-Python-2.7.8`
        versonsuffix_mapping = map_common_versionsuffixes('Python', parsed_ec['toolchain'], toolchain_mapping)
        versonsuffix_mapping.update(map_common_versionsuffixes('Perl', parsed_ec['toolchain'], toolchain_mapping))

    if update_build_specs is not None:
        if 'version' in update_build_specs:

            # take into account that version in exts_list may have to be updated as well
            if 'exts_list' in parsed_ec and parsed_ec['exts_list']:
                _log.warning("Found 'exts_list' in %s, will only update extension version of %s (if applicable)",
                             ec_spec, parsed_ec['name'])
                for idx, extension in enumerate(parsed_ec['exts_list']):
                    if isinstance(extension, tuple) and extension[0] == parsed_ec['name']:
                        ext_as_list = list(extension)
                        # in the extension tuple the version is the second element
                        if len(ext_as_list) > 1 and ext_as_list[1] == parsed_ec['version']:
                            ext_as_list[1] = update_build_specs['version']
                            # also need to clear the checksum (if it exists)
                            if len(ext_as_list) > 2:
                                ext_as_list[2].pop('checksums', None)
                            # now replace the tuple in the dict of parameters
                            # to update the original dep dict, we need to get a reference with templating disabled...
                            parsed_ec.get_ref('exts_list')[idx] = tuple(ext_as_list)
                            _log.info("Updated extension found in %s with new version", ec_spec)

            # automagically clear out list of checksums if software version is being tweaked
            if 'checksums' not in update_build_specs:
                update_build_specs['checksums'] = []
                _log.warning("Tweaking version: checksums cleared, verification disabled.")

        # update the keys according to the build specs
        for key in update_build_specs:
            parsed_ec[key] = update_build_specs[key]

    # Replace the toolchain if the mapping exists
    tc_name = parsed_ec['toolchain']['name']
    if tc_name in toolchain_mapping:
        new_toolchain = toolchain_mapping[tc_name]
        _log.debug("Replacing parent toolchain %s with %s", parsed_ec['toolchain'], new_toolchain)
        parsed_ec['toolchain'] = new_toolchain

    # Replace the toolchains of all the dependencies
    for key in DEPENDENCY_PARAMETERS:
        # loop over a *copy* of dependency dicts (with resolved templates);

        # to update the original dep dict, we need to get a reference with templating disabled...
        val = parsed_ec[key]
        orig_val = parsed_ec.get_ref(key)

        if key in parsed_ec.iterate_options:
            val = flatten(val)
            orig_val = flatten(orig_val)

        for idx, dep in enumerate(val):

            # reference to original dep dict, this is the one we should be updating
            orig_dep = orig_val[idx]

            # skip dependencies that are marked as external modules
            if dep['external_module']:
                continue
            dep_tc_name = dep['toolchain']['name']
            if dep_tc_name in toolchain_mapping:
                orig_dep['toolchain'] = toolchain_mapping[dep_tc_name]

            dep_changed = False

            # replace the binutils version (if necessary)
            if 'binutils' in toolchain_mapping and (dep['name'] == 'binutils' and dep_tc_name == GCCcore.NAME):
                orig_dep.update(toolchain_mapping['binutils'])
                dep_changed = True

            elif update_dep_versions:
                # search for available updates for this dependency:
                # first get highest version candidate paths for this (include search through subtoolchains)
                potential_version_mappings = find_potential_version_mappings(
                    dep,
                    toolchain_mapping,
                    versionsuffix_mapping=versonsuffix_mapping,
                    ignore_versionsuffixes=ignore_versionsuffixes
                )
                # only highest version match is retained by default in potential_version_mappings,
                # compare that version to the original version and replace if appropriate (upgrades only).
                if potential_version_mappings:
                    highest_version_match = potential_version_mappings[0]['version']
                    highest_versionsuffix_match = potential_version_mappings[0]['versionsuffix']
                    if LooseVersion(highest_version_match) > LooseVersion(dep['version']):
                        _log.info("Updating version of %s dependency from %s to %s", dep['name'], dep['version'],
                                  highest_version_match)
                        _log.info("Depending on your configuration, this will be resolved with one of the following "
                                  "easyconfigs: \n%s", '\n'.join(cand['path'] for cand in potential_version_mappings))
                        orig_dep['version'] = highest_version_match
                        dep['versionsuffix'] = highest_versionsuffix_match
                        orig_dep['versionsuffix'] = highest_versionsuffix_match
                        dep_changed = True

            if dep_changed:
                _log.debug("Modified dependency %s of %s", dep['name'], ec_spec)

    # determine the name of the modified easyconfig and dump it to target_dir
    if parsed_ec['versionsuffix'] in versonsuffix_mapping:
        parsed_ec['versionsuffix'] = versonsuffix_mapping[parsed_ec['versionsuffix']]
    ec_filename = '%s-%s.eb' % (parsed_ec['name'], det_full_ec_version(parsed_ec))
    tweaked_spec = os.path.join(targetdir or tempfile.gettempdir(), ec_filename)

    parsed_ec.dump(tweaked_spec, always_overwrite=False, backup=True)
    _log.debug("Dumped easyconfig tweaked via --try-* to %s", tweaked_spec)

    return tweaked_spec


def list_deps_versionsuffixes(ec_spec):
    """
    Take an easyconfig spec, parse it, extracts the list of version suffixes used in its dependencies

    :param ec_spec: location of original easyconfig file

    :return: The list of versionsuffixes used by the dependencies of this recipe
    """
    # Fully parse the original easyconfig
    parsed_ec = process_easyconfig(ec_spec, validate=False)[0]['ec']

    versionsuffix_list = []
    for key in DEPENDENCY_PARAMETERS:
        val = parsed_ec[key]

        if key in parsed_ec.iterate_options:
            val = flatten(val)

        for dep in val:
            if dep['versionsuffix']:
                versionsuffix_list += [dep['versionsuffix']]

    return list(set(versionsuffix_list))


def find_potential_version_mappings(dep, toolchain_mapping, versionsuffix_mapping=None, highest_versions_only=True,
                                    ignore_versionsuffixes=False, quiet=False):
    """
    Find potential version mapping for a dependency in a new hierarchy

    :param dep: dependency specification (dict)
    :param toolchain_mapping: toolchain mapping used for search
    :param versionsuffix_mapping: mapping of version suffixes
                                  (required by software with a special version suffix, such as Python packages)
    :param highest_versions_only: only return highest versions
    :return: list of dependencies that match
    """
    if versionsuffix_mapping is None:
        versionsuffix_mapping = {}

    # Find the target toolchain and create the hierarchy to search within
    dep_tc_name = dep['toolchain']['name']
    if dep_tc_name in toolchain_mapping:
        search_toolchain = toolchain_mapping[dep_tc_name]
    else:
        # dummy
        search_toolchain = dep['toolchain']

    toolchain_hierarchy = get_toolchain_hierarchy(search_toolchain)

    # Figure out what precedes the version (i.e. name + versionprefix (if any))
    versionprefix = dep.get('versionprefix', '')
    prefix_to_version = dep['name'] + '-' + versionprefix

    # Figure out the main versionsuffix (altered depending on toolchain in the loop below)
    versionsuffix = dep.get('versionsuffix', '')
    # If versionsuffix is equal to None, it should be put to empty string
    if versionsuffix is None:
        versionsuffix = ''
    # If versionsuffix is in our mapping then we expect it to be updated
    if versionsuffix in versionsuffix_mapping:
        versionsuffix = versionsuffix_mapping[versionsuffix]

    # the candidate version is a regex string, let's be conservative and search for patch upgrade first;
    # if that doesn't work look for a minor version upgrade and if that fails will we try a global search,
    # i.e, a major version upgrade (assumes major.minor.xxx versioning)
    candidate_ver_list = []
    version_components = dep['version'].split('.')
    major_version = version_components[0]
    if len(version_components) > 2:  # Have something like major.minor.xxx
        minor_version = version_components[1]
        candidate_ver_list.append(r'%s\.%s\..*' % (major_version, minor_version))
    if len(version_components) > 1:  # Have at least major.minor
        candidate_ver_list.append(r'%s\..*' % major_version)
    candidate_ver_list.append(r'.*')  # Include a major version search
    potential_version_mappings = []
    highest_version = None
    highest_version_ignoring_versionsuffix = None

    for candidate_ver in candidate_ver_list:

        # if any potential version mappings were found already at this point, we don't add more
        if not potential_version_mappings:
            for toolchain in toolchain_hierarchy:

                # determine search pattern based on toolchain, version prefix/suffix & version regex
                if toolchain['name'] == SYSTEM_TOOLCHAIN_NAME:
                    toolchain_suffix = ''
                else:
                    toolchain_suffix = '-%s-%s' % (toolchain['name'], toolchain['version'])
                # Search for any version suffix but only use what we are allowed to
                full_versionsuffix = toolchain_suffix + r'.*' + EB_FORMAT_EXTENSION
                depver = '^' + prefix_to_version + candidate_ver + full_versionsuffix
                cand_paths = search_easyconfigs(depver, consider_extra_paths=False, print_result=False,
                                                case_sensitive=True)

                # filter out easyconfigs that have been tweaked in this instance, they are not relevant here
                tweaked_ecs_paths, _ = alt_easyconfig_paths(tempfile.gettempdir(), tweaked_ecs=True)
                cand_paths = [path for path in cand_paths if not path.startswith(tweaked_ecs_paths)]

                # if SYSTEM_TOOLCHAIN_NAME is used, it produces regex of the form
                # <name>-<version_regex>.eb, which can map to incompatible toolchains.
                # For example Boost-1.68\..*.eb would match Boost-1.68.0-intel-2019a.eb
                # This filters out such matches unless the toolchain in the easyconfig matches a system toolchain
                if toolchain['name'] == SYSTEM_TOOLCHAIN_NAME:
                    cand_paths_filtered = []
                    for path in cand_paths:
                        tc_candidate = fetch_parameters_from_easyconfig(read_file(path), ['toolchain'])[0]
                        if isinstance(tc_candidate, dict) and tc_candidate['name'] == SYSTEM_TOOLCHAIN_NAME:
                            cand_paths_filtered += [path]
                        if isinstance(tc_candidate, string_type) and tc_candidate == TC_CONSTANT_SYSTEM:
                            cand_paths_filtered += [path]

                    cand_paths = cand_paths_filtered

                # add what is left to the possibilities
                for path in cand_paths:
                    version, newversionsuffix = fetch_parameters_from_easyconfig(read_file(path), ['version',
                                                                                                   'versionsuffix'])
                    if not newversionsuffix:
                        newversionsuffix = ''
                    if version:
                        if versionsuffix == newversionsuffix:
                            if highest_version is None or LooseVersion(version) > LooseVersion(highest_version):
                                highest_version = version
                        else:
                            if highest_version_ignoring_versionsuffix is None or \
                                    LooseVersion(version) > LooseVersion(highest_version_ignoring_versionsuffix):
                                highest_version_ignoring_versionsuffix = version
                    else:
                        raise EasyBuildError("Failed to determine version from contents of %s", path)

                    potential_version_mappings.append({'path': path, 'toolchain': toolchain, 'version': version,
                                                       'versionsuffix': newversionsuffix})

    ignored_versionsuffix_greater = \
        highest_version_ignoring_versionsuffix is not None and highest_version is None or \
        (highest_version_ignoring_versionsuffix is not None and highest_version is not None and
         LooseVersion(highest_version_ignoring_versionsuffix) > LooseVersion(highest_version))

    exclude_alternate_versionsuffixes = False
    if ignored_versionsuffix_greater:
        if ignore_versionsuffixes:
            highest_version = highest_version_ignoring_versionsuffix
        else:
            if not quiet:
                print_warning(
                    "There may be newer version(s) of dep '%s' available with a different versionsuffix to '%s': %s",
                    dep['name'], versionsuffix, [d['path'] for d in potential_version_mappings if
                                                 d['version'] == highest_version_ignoring_versionsuffix])
            # exclude candidates with a different versionsuffix
            exclude_alternate_versionsuffixes = True
    else:
        # If the other version suffixes are not greater, then just ignore them
        exclude_alternate_versionsuffixes = True
    if exclude_alternate_versionsuffixes:
        potential_version_mappings = [d for d in potential_version_mappings if d['versionsuffix'] == versionsuffix]

    if highest_versions_only and highest_version is not None:
        potential_version_mappings = [d for d in potential_version_mappings if d['version'] == highest_version]

    _log.debug("Found potential version mappings for %s: %s", dep, potential_version_mappings)
    return potential_version_mappings
