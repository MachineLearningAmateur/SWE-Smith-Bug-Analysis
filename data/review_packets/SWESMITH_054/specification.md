# Missing methods in authors.py causing site generation to fail

## Description

I noticed that after a recent update, the site generation is completely broken. When trying to build my Nikola site, it fails with numerous errors.

After investigating, I found that several critical methods are missing from the `authors.py` plugin:

- `classify`
- `provide_overview_context_and_uptodate`
- `get_other_language_variants`

These methods appear to have been removed, but they're essential for the site generation process. Without them, almost all integration tests fail with various errors.

## Steps to reproduce

1. Create a basic Nikola site with author pages enabled
2. Try to build the site
3. Observe that the build fails with numerous errors

## Expected behavior

The site should build successfully, generating all required pages including author pages.

## Actual behavior

The build process fails with multiple errors. The site cannot be generated because the required methods for author classification and context generation are missing.
