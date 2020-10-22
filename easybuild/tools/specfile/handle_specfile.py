from easybuild.tools.specfile.parsers import YamlSpecParser

def handle_specfile(filename):
    
    eb = YamlSpecParser().parse(filename)
    
    eb_cmds = eb.compose_eb_cmds()
    
    for x in eb_cmds:
        print(x)

if __name__ == "__main__":
    handle_specfile(specfile)
