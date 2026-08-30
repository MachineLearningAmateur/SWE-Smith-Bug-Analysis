### Issue: Incomplete File Download Handling in `fetch_data_files`

#### Description

The `fetch_data_files` function in the `data_manager.py` module seems to have an issue with handling file download failures. When attempting to download missing test files, the function does not raise an error if a file fails to download. Instead, it logs a warning and continues execution.

#### Steps to Reproduce

1. Ensure that the local cache directory is empty or contains outdated files.
2. Simulate a network condition or modify the URL map to ensure that at least one file cannot be downloaded.
3. Call the `fetch_data_files()` function.

#### Expected Behavior

The function should raise a `RuntimeError` indicating which files failed to download, similar to the previous behavior.

#### Actual Behavior

The function logs a warning message for each failed download but does not raise an error, potentially leading to incomplete data in the local cache.

#### Additional Information

This issue may affect any processes relying on the complete set of test files being available in the local cache.
