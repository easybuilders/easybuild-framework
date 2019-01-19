import pkg_resources
import pkgutil

subdirs = [chr(l) for l in range(ord('a'), ord('z') + 1)] + ['0']
for subdir in subdirs:
    __path__ = pkgutil.extend_path(__path__, '%s.%s' % (__name__, subdir))

del subdir, subdirs
if 'l' in dir():
    del l

pkg_resources.declare_namespace(__name__)
