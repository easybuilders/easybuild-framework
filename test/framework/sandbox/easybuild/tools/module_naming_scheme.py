def det_full_module_name(ec):
    if ec['toolchain']['name'] == 'goolf':
        return ('gnu', 'openmpi', ec['name'], ec['version'])
    elif ec['toolchain']['name'] == 'GCC':
        return ('gnu', ec['name'], ec['version'])
    elif ec['toolchain']['name'] == 'ictce':
        return ('intel', 'intelmpi', ec['name'], ec['version'])
    else:
        return (ec['name'], ec['version'])
