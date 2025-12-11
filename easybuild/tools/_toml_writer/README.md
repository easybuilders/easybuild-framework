# TOML writer library

This is an implementation of a library for writing TOML files.  
To be able to update, change and remove it without breaking backwards compatibility in EasyBuild
it is in a "private" sub-package and should not be used directly: **It can be changed without warning!**

The stable interface is `easybuild.tools.dump_toml`.

## Implementation

Currently, a copy of [`tomli-w`](https://github.com/hukkin/tomli-w) is vendored in this folder.
The used version is 1.2.

Minor modifications to make it compatible with Python 3.6.
