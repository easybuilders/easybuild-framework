import yaml


# general specs applicable to all commands
class Specsfile(object):
    def __init__(self):
        self.easybuild_version = None
        self.robot = False
        self.software_list = []

    # returns list of all commands - finished
    def compose_eb_cmds(self):
        eb_cmd_list = []
        for sw in self.software_list:
            eb_cmd_list.append(self.make_cmd(sw))
        return eb_cmd_list

    # single command
    def make_cmd(self, sw):
        eb_cmd = 'eb %s-%s-%s%s --robot=%s ' % (
            sw.software, sw.version, sw.toolchain, sw.get_version_suffix(), self.robot)
        return eb_cmd


# single sw command
class SoftwareSpecs(object):
    def __init__(self, software, version, toolchain):
        self.software = software
        self.version = version
        self.toolchain = toolchain
        self.version_suffix = None

    def get_version_suffix(self):
        return self.version_suffix or ''


# implement this to your own needs - to create custom yaml/json/xml parser
class GenericSpecsParser(object):
    @staticmethod
    def parse(filename):
        raise NotImplementedError


class YamlSpecParser(GenericSpecsParser):
    @staticmethod
    def parse(filename):
        
        try:
            with open(filename, 'r') as f:
                spec_dict = yaml.safe_load(f)

            eb = Specsfile()
        except FileNotFoundError:
            print("Cannot open file '" + filename + "'. Try to provide absolute path or adjust permissions.")
            exit()
        sw_dict = spec_dict["software"]

        # assign software-specific EB attributes
        for software in sw_dict:
            try:
                # iterates through toolchains to find out what sw version is needed
                for yaml_toolchain in sw_dict[software]['toolchains']:
                    # retrieves version number
                    for yaml_version in sw_dict[software]['toolchains'][yaml_toolchain]['versions']:
                        # creates a sw class instance
                        sw = SoftwareSpecs(software=software, version=yaml_version, toolchain=yaml_toolchain)
                        # assigns attributes retrieved from yaml stream
                        sw.software = str(software)
                        sw.version = str(yaml_version)
                        sw.toolchain = str(yaml_toolchain)
                        # append newly created class instance to the list inside EbFromSpecs class
                        eb.software_list.append(sw)
                        try:
                            version_info = sw_dict[software]['toolchains'][yaml_toolchain]['versions'][yaml_version]
                            if version_info['versionsuffix'] is not None:
                                sw.version_suffix = version_info['versionsuffix']
                        except (KeyError, TypeError, IndexError) as e:
                            continue
            except (KeyError, TypeError, IndexError) as ex:
                print('Software ' + str(software) + ' has wrong yaml structure!')

        # assign general EB attributes
        eb.easybuild_version = spec_dict.get('easybuild_version', None)
        eb.robot = spec_dict.get('robot', False)
        return eb


def handle_specsfile(filename):
    
    eb = YamlSpecParser.parse(filename)
    
    eb_cmds = eb.compose_eb_cmds()
    
    for x in eb_cmds:
        print(x)