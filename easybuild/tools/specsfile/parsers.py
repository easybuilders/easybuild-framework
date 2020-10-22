import yaml
import os
from easybuild.tools.specsfile.specsfile import Specsfile, SoftwareSpecs

# implement this to your own needs - to create custom yaml/json/xml parser
class GenericSpecsParser(object):
    @staticmethod
    def parse(filename):
        raise NotImplementedError


class YamlSpecParser(GenericSpecsParser):
    @staticmethod
    def parse(filename):
        
        # try:
        with open(filename, 'r') as f:
            spec_dict = yaml.safe_load(f)

        eb = Specsfile()
        # except:
        #     print("Cannot open file '" + filename + "'. Try to provide absolute path or adjust permissions.")
        #     exit()
        # loads all softwares' dictionaries from yaml
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
                            if version_info['versionsuffix'] != None:
                                sw.version_suffix=version_info['versionsuffix']
                        except:
                            continue
                        
            except:
                print('Software ' + str(software) + ' has wrong yaml structure!')

        # assign general EB attributes
        eb.easybuild_version = spec_dict.get('easybuild_version', None)
        eb.robot = spec_dict.get('robot', False)
        
        return eb

