import pkgutil

subdirs = [chr(x) for x in range(ord('a'), ord('z') + 1)] + ['0']
for subdir in subdirs:
    __path__ = pkgutil.extend_path(__path__, '%s.%s' % (__name__, subdir))

del subdir, subdirs
if 'x' in dir():
    del x

__path__ = __import__('pkgutil').extend_path(__path__, __name__)
