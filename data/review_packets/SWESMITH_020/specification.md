### Issue: Remote Management Regression

It seems there's a regression in the remote management functionality after the recent changes. Specifically, the handling of duplicate remote URLs and names has been affected.

#### Steps to Reproduce:

1. Attempt to add a remote with a duplicate URL without using the `--force` flag:
   ```bash
   conan remote add remote1 http://url
   conan remote add remote2 http://url
   ```
   Expected: An error indicating the URL is already in use.
   Actual: The command fails as expected, but the error message is inconsistent.

2. Try to add a remote with a duplicate name:
   ```bash
   conan remote add remote1 http://otherurl
   ```
   Expected: An error indicating the remote name already exists.
   Actual: The error message suggests using `--force`, but the behavior is inconsistent.

3. Use the `--index` option to insert a remote at a specific position:
   ```bash
   conan remote add origin https://myurl --index=0
   conan remote add origin2 https://myurl2 --index=0
   conan remote list
   ```
   Expected: The remotes should be listed in the order they were inserted.
   Actual: The order is not as expected, and the insertion logic seems broken.

#### Observations:

- The `--force` flag is no longer available, which affects the ability to override existing remotes.
- The `--index` option does not behave as intended, leading to incorrect remote ordering.

This regression impacts workflows that rely on precise remote management, especially in CI/CD environments. It would be great to have this addressed to restore the expected functionality.
