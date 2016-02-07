import pkg_resources
import os
import sys

pkg_resources.declare_namespace(__name__)

subdirs = [chr(l) for l in range(ord('a'), ord('z') + 1)] + ['0']
for subdir in subdirs:
    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), subdir)):
        full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), subdir)
        if os.path.exists(full_path):
            __import__('%s.%s' % (__name__, subdir))

del l, subdir, subdirs
