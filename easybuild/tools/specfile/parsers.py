import yaml
import os
from easybuild.tools.specfile.eb_from_specs import EbFromSpecs, SoftwareSpecs

# implement this to your own needs - to create custom yaml/json/xml parser
class GenericParser(object):
    @staticmethod
    def parse(filename):
        raise NotImplementedError


class YamlSpecParser(GenericParser):
    @staticmethod
    def parse(filename):
        try:
            with open(filename, 'r') as f:
                spec_dict = yaml.safe_load(f)

            eb = EbFromSpecs()
        except:
            print("Cannot open file '" + filename + "'. Try to provide relative path or adjust permissions.")
            exit()
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
                        sw = SoftwareSpecs()
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

