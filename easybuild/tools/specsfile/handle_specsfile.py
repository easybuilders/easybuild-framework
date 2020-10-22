from easybuild.tools.specsfile.parsers import YamlSpecParser

def handle_specsfile(filename):
    
    eb = YamlSpecParser.parse(filename)
    
    eb_cmds = eb.compose_eb_cmds()
    
    for x in eb_cmds:
        print(x)