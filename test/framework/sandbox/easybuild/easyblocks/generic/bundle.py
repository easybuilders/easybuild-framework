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
EasyBuild support for installing a bundle of modules, implemented as a generic easyblock

@author: Stijn De Weirdt (Ghent University)
@author: Dries Verdegem (Ghent University)
@author: Kenneth Hoste (Ghent University)
@author: Pieter De Baets (Ghent University)
@author: Jens Timmerman (Ghent University)
"""
import os

import easybuild.tools.environment as env
from easybuild.framework.easyblock import EasyBlock
from easybuild.framework.easyconfig import CUSTOM
from easybuild.framework.easyconfig.easyconfig import get_easyblock_class
from easybuild.tools.build_log import EasyBuildError, print_msg
from easybuild.tools.modules import get_software_root, get_software_version


class Bundle(EasyBlock):
    """
    Bundle of modules: only generate module files, nothing to build/install
    """

    @staticmethod
    def extra_options():
        extra_vars = {
            'altroot': [None, "Software name of dependency to use to define $EBROOT for this bundle", CUSTOM],
            'altversion': [None, "Software name of dependency to use to define $EBVERSION for this bundle", CUSTOM],
            'default_component_specs': [{}, "Default specs to use for every component", CUSTOM],
            'components': [(), "List of components to install: tuples w/ name, version and easyblock to use", CUSTOM],
            'default_easyblock': [None, "Default easyblock to use for components", CUSTOM],
        }
        return EasyBlock.extra_options(extra_vars)

    def __init__(self, *args, **kwargs):
        """Initialize easyblock."""
        super(Bundle, self).__init__(*args, **kwargs)
        self.altroot = None
        self.altversion = None

        # list of EasyConfig instances for components
        self.comp_cfgs = []

        # list of sources for bundle itself *must* be empty
        if self.cfg['sources']:
            raise EasyBuildError("List of sources for bundle itself must be empty, found %s", self.cfg['sources'])

        # disable templating to avoid premature resolving of template values
        self.cfg.enable_templating = False

        # list of checksums for patches (must be included after checksums for sources)
        checksums_patches = []

        for comp in self.cfg['components']:
            comp_name, comp_version, comp_specs = comp[0], comp[1], {}
            if len(comp) == 3:
                comp_specs = comp[2]

            cfg = self.cfg.copy()

            cfg['name'] = comp_name
            cfg['version'] = comp_version
            cfg.generate_template_values()

            # do not inherit easyblock to use from parent (since that would result in an infinite loop in install_step)
            cfg['easyblock'] = None

            # reset list of sources/source_urls/checksums
            cfg['sources'] = cfg['source_urls'] = cfg['checksums'] = []

            for key in self.cfg['default_component_specs']:
                cfg[key] = self.cfg['default_component_specs'][key]

            for key in comp_specs:
                cfg[key] = comp_specs[key]

            # enable resolving of templates for component-specific EasyConfig instance
            cfg.enable_templating = True

            # 'sources' is strictly required
            if cfg['sources']:
                # add component sources to list of sources
                self.cfg.update('sources', cfg['sources'])
            else:
                raise EasyBuildError("No sources specification for component %s v%s", comp_name, comp_version)

            if cfg['source_urls']:
                # add per-component source_urls to list of bundle source_urls, expanding templates
                self.cfg.update('source_urls', cfg['source_urls'])

            if cfg['checksums']:
                src_cnt = len(cfg['sources'])

                # add per-component checksums for sources to list of checksums
                self.cfg.update('checksums', cfg['checksums'][:src_cnt])

                # add per-component checksums for patches to list of checksums for patches
                checksums_patches.extend(cfg['checksums'][src_cnt:])

            self.comp_cfgs.append(cfg)

        self.cfg.update('checksums', checksums_patches)

        self.cfg.enable_templating = True

    def configure_step(self):
        """Collect altroot/altversion info."""
        # pick up altroot/altversion, if they are defined
        self.altroot = None
        if self.cfg['altroot']:
            self.altroot = get_software_root(self.cfg['altroot'])
        self.altversion = None
        if self.cfg['altversion']:
            self.altversion = get_software_version(self.cfg['altversion'])

    def build_step(self):
        """Do nothing."""
        pass

    def install_step(self):
        """Install components, if specified."""
        comp_cnt = len(self.cfg['components'])
        for idx, cfg in enumerate(self.comp_cfgs):
            easyblock = cfg.get('easyblock') or self.cfg['default_easyblock']
            if easyblock is None:
                raise EasyBuildError("No easyblock specified for component %s v%s", cfg['name'], cfg['version'])
            elif easyblock == 'Bundle':
                raise EasyBuildError("The '%s' easyblock can not be used to install components in a bundle", easyblock)

            print_msg("installing bundle component %s v%s (%d/%d)..." % (cfg['name'], cfg['version'], idx+1, comp_cnt))
            self.log.info("Installing component %s v%s using easyblock %s", cfg['name'], cfg['version'], easyblock)

            comp = get_easyblock_class(easyblock, name=cfg['name'])(cfg)

            # correct build/install dirs
            comp.builddir = self.builddir
            comp.install_subdir, comp.installdir = self.install_subdir, self.installdir

            # figure out correct start directory
            comp.guess_start_dir()

            # need to run fetch_patches to ensure per-component patches are applied
            comp.fetch_patches()
            # location of first unpacked source is used to determine where to apply patch(es)
            comp.src = [{'finalpath': comp.cfg['start_dir']}]

            # run relevant steps
            for step_name in ['patch', 'configure', 'build', 'install']:
                if step_name in cfg['skipsteps']:
                    comp.log.info("Skipping '%s' step for component %s v%s", step_name, cfg['name'], cfg['version'])
                else:
                    comp.run_step(step_name, [lambda x: getattr(x, '%s_step' % step_name)])

            # update environment to ensure stuff provided by former components can be picked up by latter components
            # once the installation is finalised, this is handled by the generated module
            reqs = comp.make_module_req_guess()
            for envvar in reqs:
                curr_val = os.getenv(envvar, '')
                curr_paths = curr_val.split(os.pathsep)
                for subdir in reqs[envvar]:
                    path = os.path.join(self.installdir, subdir)
                    if path not in curr_paths:
                        if curr_val:
                            new_val = '%s:%s' % (path, curr_val)
                        else:
                            new_val = path
                        env.setvar(envvar, new_val)

    def make_module_extra(self, *args, **kwargs):
        """Set extra stuff in module file, e.g. $EBROOT*, $EBVERSION*, etc."""
        if 'altroot' not in kwargs:
            kwargs['altroot'] = self.altroot
        if 'altversion' not in kwargs:
            kwargs['altversion'] = self.altversion
        return super(Bundle, self).make_module_extra(*args, **kwargs)

    def sanity_check_step(self, *args, **kwargs):
        """
        Nothing is being installed, so just being able to load the (fake) module is sufficient
        """
        if self.cfg['exts_list'] or self.cfg['sanity_check_paths'] or self.cfg['sanity_check_commands']:
            super(Bundle, self).sanity_check_step(*args, **kwargs)
        else:
            self.log.info("Testing loading of module '%s' by means of sanity check" % self.full_mod_name)
            fake_mod_data = self.load_fake_module(purge=True)
            self.log.debug("Cleaning up after testing loading of module")
            self.clean_up_fake_module(fake_mod_data)
