#!/usr/bin/env python3
'''
Helper to convert a Cargo.lock file to a list of entries to add to the 
'crates' section of a `Cargo` derived EasyBlock, like `CargoPythonBundle`.

You might need to remove entries that are bundled/vendored already, and the
entry for the top-level package itself.
'''

import toml
pkgs = toml.load("Cargo.lock")
for pkg in pkgs["package"]:
    print("    ('" + pkg["name"] + "', '" + pkg["version"] + "'),")
