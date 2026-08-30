### Issue: `--test-missing` Flag No Longer Skips Tests as Expected

#### Description

After updating to the latest version, I've encountered an issue with the `--test-missing` flag during the package creation process. Previously, using this flag would skip the `test_package` stage if the package was not built from source. However, this behavior seems to have changed unexpectedly.

#### Steps to Reproduce

1. Create a Conan package with a `test_package` folder.
2. Run the following command to create the package without building from source:
   ```bash
   conan create . -tm --build=missing
   ```
3. Observe the output. The `test_package` stage is executed, contrary to the expected behavior where it should be skipped.

#### Expected Behavior

The `--test-missing` flag should prevent the `test_package` stage from running if the package is not built from source.

#### Actual Behavior

The `test_package` stage runs even when the `--test-missing` flag is used, leading to unnecessary test executions.

#### Additional Information

This issue was not present in previous versions and seems to have been introduced in a recent update. The behavior is consistent across different package configurations and test setups.
