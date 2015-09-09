from easybuild.toolchains.intel import Intel

METADATA_BY_VERSION = {
    '15.0.2': {
        'prefixes': {
            'GCC': '/appl/opt/gcc/4.9.2',
            'icc': '/appl/opt/cluster_studio_xe2015/composer_xe_2015.2.164',
            'ifort': '/appl/opt/cluster_studio_xe2015/composer_xe_2015.2.164',
            'imkl': '/appl/opt/cluster_studio_xe2015/composer_xe_2015.2.164',
            'impi': '/appl/opt/cluster_studio_xe2015/composer_xe_2015.2.164',
        },
        'versions': {
            'GCC': '4.9.2',
            'icc': '2015.2.164',
            'ifort': '2015.2.164',
            'imkl': '11.2.2.164',
            'impi': '???',  # FIXME
        }
    }
}

class IntelTaito(Intel):
    NAME = 'intel'
    COMPILER_MODULE_NAME = []
    MPI_MODULE_NAME = []
    BLAS_MODULE_NAME = []
    LAPACK_MODULE_NAME = []
    SCALAPACK_MODULE_NAME = []

    def _get_software_root(self, name):
        """Get install prefix for specified software name"""
        # TODO

    def _get_software_version(self, name):
        """Get install prefix for specified software name"""
        # TODO
