# Small example of how to add/delete a configure option.
#
# Author: Åke Sandgren, HPC2N

# We need to be able to distinguish between versions of OpenMPI
from easybuild.tools import LooseVersion


def pre_configure_hook(self, *args, **kwargs):
    # Check that we're dealing with the correct easyconfig file
    if self.name == 'OpenMPI':
        extra_opts = ""
        # Enable using pmi from slurm
        extra_opts += "--with-pmi=/lap/slurm "

        # And enable munge for OpenMPI versions that knows about it
        if LooseVersion(self.version) >= LooseVersion('2'):
            extra_opts += "--with-munge "

        # Now add the options
        self.log.info("[pre-configure hook] Adding %s" % extra_opts)
        self.cfg.update('configopts', extra_opts)

        # Now we delete some options
        # For newer versions of OpenMPI we can re-enable ucx, i.e. delete the --without-ucx flag
        if LooseVersion(self.version) >= LooseVersion('2.1'):
            self.log.info("[pre-configure hook] Re-enabling ucx")
            self.cfg['configopts'] = self.cfg['configopts'].replace('--without-ucx', ' ')

        # And we can remove the --disable-dlopen option from the easyconfig file
        self.log.info("[pre-configure hook] Re-enabling dlopen")
        self.cfg['configopts'] = self.cfg['configopts'].replace('--disable-dlopen', ' ')
