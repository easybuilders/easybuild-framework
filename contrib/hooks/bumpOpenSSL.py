from easybuild.framework.easyconfig.constants import EASYCONFIG_CONSTANTS


def parse_hook(ec, *args, **kwargs):
    """
    EasyBuild parse hook for EL9+ compatibility
    """
    # looks like [('zlib', '1.2.13'), ('OpenSSL', '1.1', '', {'name': 'system', 'version': 'system'})]
    raw_deps = ec['dependencies'] if 'dependencies' in ec else []

    # Check if OpenSSL is in any dependency tuple's first element
    openssl_found = any(dep[0] == 'OpenSSL' for dep in raw_deps)

    # if found, replace its version - second element in the tuple with '3'.
    if openssl_found:
        print(f"[openssl1->3 hook] OpenSSL found in dependencies of {ec['name']}, replacing with OpenSSL 3")
        for i, dep in enumerate(raw_deps):
            if dep[0] == 'OpenSSL' and dep[1] == '1.1':
                raw_deps[i] = ('OpenSSL', '3', '', EASYCONFIG_CONSTANTS['SYSTEM'][0])
                break

    else:
        # no need to do anything
        return

    ec['dependencies'] = raw_deps
