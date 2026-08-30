# Import from remote storage fails with no_download option

## Description

I've discovered an issue when importing files from a remote storage with the `no_download` option. When trying to import a file from a remote storage, the file is not properly downloaded and the import fails.

## Steps to Reproduce

1. Set up a remote storage
2. Add a file to the remote storage
3. Try to import the file using `dvc import` with a remote URL

```python
# Example code to reproduce
# Set up remote storage
dvc remote add --local tmp /path/to/tmp
dvc remote add --local storage remote://tmp/storage

# Create a file in remote storage
# (file content: "Isle of Dogs")

# Try to import the file
dvc import remote://storage/file movie.txt
```

## Expected Behavior

The file should be successfully imported from the remote storage and available in the local workspace.

## Actual Behavior

The import fails and the file is not properly downloaded. It seems that when importing from a remote storage, the file is not being properly synced.

## Environment

- DVC version: latest
- OS: Linux/macOS/Windows

## Additional Context

This appears to be related to how DVC handles the `no_download` option during import operations. The issue specifically affects imports from remote storage URLs.

<END WRITING>
