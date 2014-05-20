##
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
##
"""
Easyconfig module that provides functionality for tweaking existing eaysconfig (.eb) files.

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
import tempfile
from distutils.version import LooseVersion
from vsc.utils import fancylogger
from vsc.utils.missing import nub

from easybuild.tools.build_log import print_error, print_msg, print_warning
from easybuild.framework.easyconfig.easyconfig import EasyConfig, create_paths, process_easyconfig
from easybuild.framework.easyconfig.tools import resolve_dependencies
from easybuild.tools.filetools import read_file, write_file
from easybuild.tools.module_naming_scheme.utilities import det_full_ec_version
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


def tweak(easyconfigs, build_specs):
    """Tweak list of easyconfigs according to provided build specifications."""

    # make sure easyconfigs all feature the same toolchain (otherwise we *will* run into trouble)
    toolchains = nub(['%(name)s/%(version)s' % ec['ec']['toolchain'] for ec in easyconfigs])
    if len(toolchains) > 1:
        _log.error("Multiple toolchains featured in easyconfigs, --try-X not supported in that case: %s" % toolchains)

    # obtain full dependency graph for specified easyconfigs
    # easyconfigs will be ordered 'top-to-bottom': toolchain dependencies and toolchain first
    orig_ecs = resolve_dependencies(easyconfigs, retain_all_deps=True)

    # determine toolchain based on last easyconfigs
    toolchain = orig_ecs[-1]['ec']['toolchain']
    _log.debug("Filtering using toolchain %s" % toolchain)

    # filter easyconfigs unless a dummy toolchain is used: drop toolchain and toolchain dependencies
    if toolchain['name'] != DUMMY_TOOLCHAIN_NAME:
        while orig_ecs[0]['ec']['toolchain'] != toolchain:
            orig_ecs = orig_ecs[1:]

    # generate tweaked easyconfigs, and continue with those instead
    easyconfigs = []
    for orig_ec in orig_ecs:
        new_ec_file = tweak_one(orig_ec['spec'], None, build_specs)
        new_ecs = process_easyconfig(new_ec_file, build_specs=build_specs)
        easyconfigs.extend(new_ecs)

    return easyconfigs


def tweak_one(src_fn, target_fn, tweaks):
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
            templ_file = os.path.join(path, "%s.eb" % EASYCONFIG_TEMPLATE)

            if os.path.isfile(templ_file):
                ec_files = [templ_file]
                break
            else:
                _log.debug("No template found at %s." % templ_file)

        if len(ec_files) == 0:
            _log.error("No easyconfig files found for software %s, and no templates available. I'm all out of ideas." % name)

    # only retain unique easyconfig files
    ec_files = nub(ec_files)
    _log.debug("Unique ec_files: %s" % ec_files)

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
            _log.error("No easyconfig file for %s with toolchain %s, " \
                      "and no template available." % (name, specs['toolchain_name']))

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
        tweak_one(selected_ec_file, fp, specs)

        _log.info("Generated easyconfig file %s, and using it to build the requested software." % fp)

        return (True, fp)


def obtain_ec_for(specs, paths, fp):
    """
    Obtain an easyconfig file to the given specifications.

    Either select between available ones, or use the best suited available one
    to generate a new easyconfig file.

    @param specs: list of available easyconfig files
    @param paths: a list of paths where easyconfig files can be found
    @param fp: the desired file name
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
