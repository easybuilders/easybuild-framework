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
        eb_cmd = 'eb %s-%s-%s%s --robot=%s ' % (sw.software, sw.version, sw.toolchain, sw.get_version_suffix(), self.robot)
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

