
# general specs applicable to all commands
class EbFromSpecs(object):
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
        version_suffix = lambda version_suffix: str(sw.version_suffix) if sw.version_suffix != None else ''
        eb_cmd = 'eb ' + sw.software + '-' + sw.version + '-' + sw.toolchain + version_suffix(sw.version_suffix) + ' --robot=' + str(self.robot)
        return eb_cmd

# single sw command
class SoftwareSpecs(object):
    def __init__(self):
        self.software = None
        self.version = None
        self.toolchain = None
        self.version_suffix = None

