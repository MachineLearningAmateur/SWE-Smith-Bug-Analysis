Export command no longer returns package list

### Problem Description

The `export` command in the Conan CLI is not returning the expected package list after a recent update. This issue seems to have been introduced with changes to the `export.py` file, where the handling of package lists was modified.

### Steps to Reproduce

1. Use the `export` command to export a recipe to the Conan package cache.
2. Observe the output of the command.

### Expected Behavior

The command should return a JSON object containing both the `reference` and a `pkglist` with the exported packages.

### Actual Behavior

The command only returns the `reference` without the `pkglist`, which is inconsistent with previous behavior and expectations.

### Additional Information

This change affects workflows that rely on the package list being returned for further processing or validation. The issue appears to be related to the removal of the `pkglist_export` function and associated logic in the `export.py` file. 

Any insights or suggestions on how to address this would be greatly appreciated!
