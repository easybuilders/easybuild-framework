import pkg_resources

# Extend path so python finds our easyblocks in the subdirectories where they are located
subdirs = [chr(l) for l in range(ord('a'), ord('z') + 1)] + ['0']
for subdir in subdirs:
    pkg_resources.declare_namespace('%s.%s' % (__name__, subdir))

# And let python know this is not the only place to look for them, so we can have multiple
# easybuild/easyblock paths in your python search path, next to the official easyblocks distribution
pkg_resources.declare_namespace(__name__)

del subdir, subdirs, l
