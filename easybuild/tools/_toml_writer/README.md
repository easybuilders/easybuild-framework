# TOML writer library

This is an implementation of a library for writing TOML files.  
To be able to update, change and remove it without breaking backwards compatibility in EasyBuild
it is in a "private" sub-package and should not be used directly: **It can be changed without warning!**

The stable interface is `easybuild.tools.filetools.dump_toml`.

## Implementation

Currently, a copy of [`tomli-w`](https://github.com/hukkin/tomli-w) is vendored in this folder.
The used version is 1.2.0 (https://github.com/hukkin/tomli-w/releases/tag/1.2.0, commit a8f80172ba16fe694e37f6e07e6352ecee384c58).

Minor modifications to make it compatible with Python 3.6.
