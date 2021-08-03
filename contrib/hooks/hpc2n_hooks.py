# Hooks for HPC2N site changes.
#
# Author: Ake Sandgren, HPC2N

import os

from easybuild.framework.easyconfig.format.format import DEPENDENCY_PARAMETERS
from easybuild.tools import LooseVersion
from easybuild.tools.filetools import apply_regex_substitutions
from easybuild.tools.build_log import EasyBuildError
from easybuild.tools.modules import get_software_root
from easybuild.tools.systemtools import get_shared_lib_ext


# Add/remove dependencies and/or patches
# Access to the raw values before templating and such.
def parse_hook(ec, *args, **kwargs):

    # Internal helper function
    def add_extra_dependencies(ec, dep_type, extra_deps):
        """dep_type: must be in DEPENDENCY_PARAMETERS or 'osdependencies'"""
        ec.log.info("[parse hook] Adding %s: %s" % (dep_type, extra_deps))

        if dep_type in DEPENDENCY_PARAMETERS:
            for dep in extra_deps:
                ec[dep_type].append(dep)
        elif dep_type == 'osdependencies':
            if isinstance(extra_deps, tuple):
                ec[dep_type].append(extra_deps)
            else:
                raise EasyBuildError("parse_hook: Type of extra_deps argument (%s), for 'osdependencies' must be "
                                     "tuple, found %s" % (extra_deps, type(extra_deps)))
        else:
            raise EasyBuildError("parse_hook: Incorrect dependency type in add_extra_dependencies: %s" % dep_type)

    extra_deps = []

    if ec.name == 'OpenMPI':
        if LooseVersion(ec.version) >= LooseVersion('2') and LooseVersion(ec.version) < LooseVersion('2.1.2'):
            ec.log.info("[parse hook] Adding pmi and lustre patches")
            if LooseVersion(ec.version) < LooseVersion('2.1.1'):
                ec['patches'].append('OpenMPI-2.0.0_fix_bad-include_of_pmi_h.patch')

            if LooseVersion(ec.version) < LooseVersion('2.0.2'):
                ec['patches'].append('OpenMPI-2.0.1_fix_lustre.patch')
            elif LooseVersion(ec.version) < LooseVersion('2.1'):
                ec['patches'].append('OpenMPI-2.0.2_fix_lustre.patch')
            elif LooseVersion(ec.version) < LooseVersion('2.1.1'):
                ec['patches'].append('OpenMPI-2.1.0_fix_lustre.patch')
            else:
                ec['patches'].append('OpenMPI-2.1.1_fix_lustre.patch')

        if LooseVersion(ec.version) == LooseVersion('4.0.0'):
            ec['patches'].append('OpenMPI-4.0.0_fix_configure_bug.patch')

        if LooseVersion(ec.version) >= LooseVersion('2.1'):
            pmix_version = '1.2.5'
            ucx_version = '1.4.0'
            if LooseVersion(ec.version) >= LooseVersion('3'):
                pmix_version = '2.2.1'
            if LooseVersion(ec.version) >= LooseVersion('4'):
                pmix_version = '3.0.2'  # OpenMPI 4.0.0 is not compatible with PMIx 3.1.x

            extra_deps.append(('PMIx', pmix_version))
            # Use of external PMIx requires external libevent
            # But PMIx already has it as a dependency so we don't need
            # to explicitly set it.

            extra_deps.append(('UCX', ucx_version))

    if ec.name == 'impi':
        pmix_version = '3.1.1'
        extra_deps.append(('PMIx', pmix_version))

    if extra_deps:
        add_extra_dependencies(ec, 'dependencies', extra_deps)


def pre_configure_hook(self, *args, **kwargs):
    if self.name == 'GROMACS':
        # HPC2N always uses -DGMX_USE_NVML=ON on GPU builds
        if get_software_root('CUDA'):
            self.log.info("[pre-configure hook] Adding -DGMX_USE_NVML=ON")
            self.cfg.update('configopts', "-DGMX_USE_NVML=ON ")

    if self.name == 'OpenMPI':
        extra_opts = ""
        # Old versions don't work with PMIx, use slurms PMI1
        if LooseVersion(self.version) < LooseVersion('2.1'):
            extra_opts += "--with-pmi=/lap/slurm "
            if LooseVersion(self.version) >= LooseVersion('2'):
                extra_opts += "--with-munge "

        # Using PMIx dependency in easyconfig, see above
        if LooseVersion(self.version) >= LooseVersion('2.1'):
            if get_software_root('PMIx'):
                extra_opts += "--with-pmix=$EBROOTPMIX "
                # Use of external PMIx requires external libevent
                # We're using the libevent that comes from the PMIx dependency
                if get_software_root('libevent'):
                    extra_opts += "--with-libevent=$EBROOTLIBEVENT "
                else:
                    raise EasyBuildError("Error in pre_configure_hook for OpenMPI: External use of PMIx requires "
                                         "external libevent, which was not found. "
                                         "Check parse_hook for dependency settings.")
            else:
                raise EasyBuildError("Error in pre_configure_hook for OpenMPI: PMIx not defined in dependencies. "
                                     "Check parse_hook for dependency settings.")

            if get_software_root('UCX'):
                extra_opts += "--with-ucx=$EBROOTUCX "

        if LooseVersion(self.version) >= LooseVersion('2'):
            extra_opts += "--with-cma "
            extra_opts += "--with-lustre "

        # We still need to fix the knem package to install its
        # pkg-config .pc file correctly, and we need a more generic
        # install dir.
        # extra_opts += "--with-knem=/opt/knem-1.1.2.90mlnx1 "

        self.log.info("[pre-configure hook] Adding %s" % extra_opts)
        self.cfg.update('configopts', extra_opts)

        if LooseVersion(self.version) >= LooseVersion('2.1'):
            self.log.info("[pre-configure hook] Re-enabling ucx")
            self.cfg['configopts'] = self.cfg['configopts'].replace('--without-ucx', ' ')

        self.log.info("[pre-configure hook] Re-enabling dlopen")
        self.cfg['configopts'] = self.cfg['configopts'].replace('--disable-dlopen', ' ')

    if self.name == 'PMIx':
        self.log.info("[pre-configure hook] Adding --with-munge")
        self.cfg.update('configopts', "--with-munge ")
        if LooseVersion(self.version) >= LooseVersion('2'):
            self.log.info("[pre-configure hook] Adding --with-tests-examples")
            self.cfg.update('configopts', "--with-tests-examples ")
            self.log.info("[pre-configure hook] Adding --disable-per-user-config-files")
            self.cfg.update('configopts', "--disable-per-user-config-files")


def pre_build_hook(self, *args, **kwargs):
    if self.name == 'pyslurm':
        self.log.info("[pre-build hook] Adding --slurm=/lap/slurm")
        self.cfg.update('buildopts', "--slurm=/lap/slurm ")


def post_install_hook(self, *args, **kwargs):
    if self.name == 'impi':
        # Fix mpirun from IntelMPI to explicitly unset I_MPI_PMI_LIBRARY
        # it can only be used with srun.
        self.log.info("[post-install hook] Unset I_MPI_PMI_LIBRARY in mpirun")
        apply_regex_substitutions(os.path.join(self.installdir, "intel64", "bin", "mpirun"), [
            (r'^(#!/bin/sh.*)$', r'\1\nunset I_MPI_PMI_LIBRARY'),
        ])


def pre_module_hook(self, *args, **kwargs):
    if self.name == 'impi':
        # Add I_MPI_PMI_LIBRARY to module for IntelMPI so it works with
        # srun.
        self.log.info("[pre-module hook] Set I_MPI_PMI_LIBRARY in impi module")
        # Must be done this way, updating self.cfg['modextravars']
        # directly doesn't work due to templating.
        with self.cfg.disable_templating():
            shlib_ext = get_shared_lib_ext()
            pmix_root = get_software_root('PMIx')
            if pmix_root:
                mpi_type = 'pmix_v3'
                self.cfg['modextravars'].update({
                    'I_MPI_PMI_LIBRARY': os.path.join(pmix_root, "lib", "libpmi." + shlib_ext)
                })
                self.cfg['modextravars'].update({'SLURM_MPI_TYPE': mpi_type})
                # Unfortunately UCX doesn't yet work for unknown reasons. Make sure it is off.
                self.cfg['modextravars'].update({'SLURM_PMIX_DIRECT_CONN_UCX': 'false'})
            else:
                self.cfg['modextravars'].update({'I_MPI_PMI_LIBRARY': "/lap/slurm/lib/libpmi.so"})

    if self.name == 'OpenBLAS':
        self.log.info("[pre-module hook] Set OMP_NUM_THREADS=1 in OpenBLAS module")
        self.cfg.update('modluafooter', 'if ((mode() == "load" and os.getenv("OMP_NUM_THREADS") == nil) '
                        'or (mode() == "unload" and os.getenv("__OpenBLAS_set_OMP_NUM_THREADS") == "1")) then '
                        'setenv("OMP_NUM_THREADS","1"); setenv("__OpenBLAS_set_OMP_NUM_THREADS", "1") end')

    if self.name == 'OpenMPI':
        if LooseVersion(self.version) < LooseVersion('2.1'):
            mpi_type = 'openmpi'
        elif LooseVersion(self.version) < LooseVersion('3'):
            mpi_type = 'pmix_v1'
        elif LooseVersion(self.version) < LooseVersion('4'):
            mpi_type = 'pmix_v2'
        else:
            mpi_type = 'pmix_v3'

        self.log.info("[pre-module hook] Set SLURM_MPI_TYPE=%s in OpenMPI module" % mpi_type)
        # Must be done this way, updating self.cfg['modextravars']
        # directly doesn't work due to templating.
        with self.cfg.disable_templating():
            self.cfg['modextravars'].update({'SLURM_MPI_TYPE': mpi_type})
            # Unfortunately UCX doesn't yet work for unknown reasons. Make sure it is off.
            self.cfg['modextravars'].update({'SLURM_PMIX_DIRECT_CONN_UCX': 'false'})

    if self.name == 'PMIx':
        # This is a, hopefully, temporary workaround for https://github.com/pmix/pmix/issues/1114
        if LooseVersion(self.version) > LooseVersion('2') and LooseVersion(self.version) < LooseVersion('3'):
            self.log.info("[pre-module hook] Set PMIX_MCA_gds=^ds21 in PMIx module")
            with self.cfg.disable_templating():
                self.cfg['modextravars'].update({'PMIX_MCA_gds': '^ds21'})
