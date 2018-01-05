##
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
"""
import copy
import glob
import os
import re
import tempfile
from distutils.version import LooseVersion
from vsc.utils import fancylogger
from vsc.utils.missing import nub

from easybuild.framework.easyconfig.default import get_easyconfig_parameter_default
from easybuild.framework.easyconfig.easyconfig import EasyConfig, create_paths, process_easyconfig
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.filetools import read_file, write_file
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
from easybuild.tools.robot import resolve_dependencies
from easybuild.tools.toolchain import DUMMY_TOOLCHAIN_NAME
from easybuild.tools.utilities import quote_str


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
    tweaked_ecs_path, tweaked_ecs_deps_path = None, None
    if targetdirs is not None:
        tweaked_ecs_path, tweaked_ecs_deps_path = targetdirs
    # make sure easyconfigs all feature the same toolchain (otherwise we *will* run into trouble)
    toolchains = nub(['%(name)s/%(version)s' % ec['ec']['toolchain'] for ec in easyconfigs])
    if len(toolchains) > 1:
        raise EasyBuildError("Multiple toolchains featured in easyconfigs, --try-X not supported in that case: %s",
                             toolchains)

    if 'name' in build_specs or 'version' in build_specs:
        # no recursion if software name/version build specification are included
        # in that case, do not construct full dependency graph
        orig_ecs = easyconfigs
        _log.debug("Software name/version found, so not applying build specifications recursively: %s" % build_specs)
    else:
        # build specifications should be applied to the whole dependency graph
        # obtain full dependency graph for specified easyconfigs
        # easyconfigs will be ordered 'top-to-bottom': toolchain dependencies and toolchain first
        _log.debug("Applying build specifications recursively (no software name/version found): %s" % build_specs)
        orig_ecs = resolve_dependencies(easyconfigs, modtool, retain_all_deps=True)

    # keep track of originally listed easyconfigs (via their path)
    listed_ec_paths = [ec['spec'] for ec in easyconfigs]

    # determine toolchain based on last easyconfigs
    if orig_ecs:
        toolchain = orig_ecs[-1]['ec']['toolchain']
        _log.debug("Filtering using toolchain %s" % toolchain)

        # filter easyconfigs unless a dummy toolchain is used: drop toolchain and toolchain dependencies
        if toolchain['name'] != DUMMY_TOOLCHAIN_NAME:
            while orig_ecs[0]['ec']['toolchain'] != toolchain:
                orig_ecs = orig_ecs[1:]

    # generate tweaked easyconfigs, and continue with those instead
    tweaked_easyconfigs = []
    for orig_ec in orig_ecs:  
        # Only return tweaked easyconfigs for easyconfigs which were listed originally on the command line (and use the
        # prepended path so that they are found first).
        # easyconfig files for dependencies are also generated but not included, they will be resolved via --robot
        # either from existing easyconfigs or, if that fails, from easyconfigs in the appended path
        if orig_ec['spec'] in listed_ec_paths:
            new_ec_file = tweak_one(orig_ec['spec'], None, build_specs, targetdir=tweaked_ecs_path)
            new_ecs = process_easyconfig(new_ec_file, build_specs=build_specs)
            tweaked_easyconfigs.extend(new_ecs)
        else:
            # Place all tweaked dependency easyconfigs in the directory appended to the robot path
            new_ec_file = tweak_one(orig_ec['spec'], None, build_specs, targetdir=tweaked_ecs_deps_path)

    return tweaked_easyconfigs


def tweak_one(src_fn, target_fn, tweaks, targetdir=None):
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
        # note: this assumes that the toolchain spec is single-line
        tc_regexp = re.compile(r"^\s*toolchain\s*=\s*(.*)$", re.M)
        res = tc_regexp.search(ectxt)
        if not res:
            raise EasyBuildError("No toolchain found in easyconfig file %s: %s", src_fn, ectxt)

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

    # we need to treat list values seperately, i.e. we prepend to the current value (if any)
    for (key, val) in tweaks.items():

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
            elif get_easyconfig_parameter_default(key) != val:
                additions.append("%s = %s" % (key, val))

            tweaks.pop(key)

    # add parameters or replace existing ones
    for (key, val) in tweaks.items():

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
                ectxt = regexp.sub("%s = %s" % (res.group('key'), quote_str(val)), ectxt)
                _log.info("Tweaked '%s' to '%s'" % (key, quote_str(val)))
        elif get_easyconfig_parameter_default(key) != val:
            additions.append("%s = %s" % (key, quote_str(val)))

    if additions:
        _log.info("Adding additional parameters to tweaked easyconfig file: %s" % additions)
        ectxt = '\n'.join([ectxt] + additions)

    _log.debug("Contents of tweaked easyconfig file:\n%s" % ectxt)

    # come up with suiting file name for tweaked easyconfig file if none was specified
    if target_fn is None:
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
            raise EasyBuildError("Failed to determine suiting filename for tweaked easyconfig file: %s", err)

        if targetdir is None:
            targetdir = tempfile.gettempdir()
        target_fn = os.path.join(targetdir, fn)
        _log.debug("Generated file name for tweaked easyconfig file: %s" % target_fn)

    # write out tweaked easyconfig file
    write_file(target_fn, ectxt)
    _log.info("Tweaked easyconfig file written to %s" % target_fn)

    return target_fn


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
            retained_vers = [v for v in avail_vers if v <= LooseVersion(ver)]
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
        'toolchain': {'name': DUMMY_TOOLCHAIN_NAME, 'version': '*'},
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
