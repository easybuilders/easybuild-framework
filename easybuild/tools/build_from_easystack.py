import yaml
from easybuild.tools.robot import search_easyconfigs
from easybuild.tools.build_log import EasyBuildError
from easybuild.base import fancylogger


_log = fancylogger.getLogger('easystack', fname=False)


# general specs applicable to all commands
class Easystack(object):
    def __init__(self):
        self.easybuild_version = None
        self.robot = False
        self.software_list = []

    # returns list of all easyconfig names - finished
    def compose_ec_names(self):
        ec_names = []
        for sw in self.software_list:
            ec_to_append = '%s-%s-%s-%s.eb' % (str(sw.software), str(sw.version),
                                            str(sw.toolchain_name), str(sw.toolchain_version))
            if ec_to_append is None:
                continue
            else:
                ec_names.append(ec_to_append)
        return ec_names

    # flags applicable to all sw (i.e. robot)
    def get_general_options(self):
        general_options = {}
        # TODO add support for general_options
        # general_options['robot'] = self.robot
        # general_options['easybuild_version'] = self.easybuild_version
        return general_options


# single sw command
class SoftwareSpecs(object):
    def __init__(self, software, version, toolchain, toolchain_version, toolchain_name):
        self.software = software
        self.version = version
        self.toolchain = toolchain
        self.toolchain_version = toolchain_version
        self.toolchain_name = toolchain_name
        self.toolchain = toolchain

        self.versionsuffix = None

    def get_versionsuffix(self):
        return self.versionsuffix or ''


# implement this to your own needs - to create custom yaml/json/xml parser
class GenericSpecsParser(object):
    @ staticmethod
    def parse(filename):
        raise NotImplementedError


class YamlSpecParser(GenericSpecsParser):
    @ staticmethod
    def parse(filename):

        try:
            with open(filename, 'r') as f:
                spec_dict = yaml.safe_load(f)

            eb = Easystack()
        except FileNotFoundError:
            raise EasyBuildError("Could not read provided easystack.")

        sw_dict = spec_dict["software"]

        # assign software-specific EB attributes
        for software in sw_dict:
            try:
                # iterates through toolchains to find out what sw version is needed
                for yaml_toolchain in sw_dict[software]['toolchains']:
                    # retrieves version number
                    for yaml_version in sw_dict[software]['toolchains'][yaml_toolchain]['versions']:

                        # if among versions there is anything else than known flags or version flag itself, it is wrong
                        # identification of version strings is vague
                        if str(yaml_version)[0].isdigit() \
                                or str(yaml_version)[-1].isdigit():
                            # creates a sw class instance
                            try:
                                yaml_toolchain_name = str(yaml_toolchain).split('-', 1)[0]
                                yaml_toolchain_version = str(yaml_toolchain).split('-', 1)[1]
                            except IndexError:
                                yaml_toolchain_name = str(yaml_toolchain)
                                yaml_toolchain_version = ''

                            sw = SoftwareSpecs(software=software, version=yaml_version,
                                               toolchain=yaml_toolchain, toolchain_name=yaml_toolchain_name,
                                               toolchain_version=yaml_toolchain_version)

                            # append newly created class instance to the list inside EbFromSpecs class
                            eb.software_list.append(sw)

                        elif str(yaml_version) == 'versionsuffix':
                            try:
                                version_info = sw_dict[software]['toolchains'][yaml_toolchain]['versions'][yaml_version]
                                if version_info['versionsuffix'] is not None:
                                    sw.version_suffix = version_info['versionsuffix']
                            except (KeyError, TypeError, IndexError):
                                continue
                        elif str(yaml_version) == 'exclude-labels' \
                                or str(yaml_version) == 'include-labels':
                            continue
                        else:
                            raise EasyBuildError('Software % s has wrong yaml structure!' % (str(software)))

            except (KeyError, TypeError, IndexError):
                raise EasyBuildError('Software % s has wrong yaml structure!' % (str(software)))

        # assign general EB attributes
        eb.easybuild_version = spec_dict.get('easybuild_version', None)
        eb.robot = spec_dict.get('robot', False)
        return eb


def parse_easystack(filename):
    _log.info("Building from easystack: '%s'" % filename)

    # class instance which contains all info about planned build
    eb = YamlSpecParser.parse(filename)

    easyconfigs_full_paths = eb.compose_ec_names()

    general_options = eb.get_general_options()

    _log.debug("Easystack parsed. Proceeding to install these Easyconfigs: \n'%s'" % ',\n'.join(easyconfigs_full_paths))

    return easyconfigs_full_paths, general_options
