Lean Lexer Import Error

Description

After updating the lexer mappings, I encountered an issue when trying to use the Lean lexer. It seems that the import statement for the Lean lexer is missing, causing a `NameError: name 'include' is not defined` when attempting to process Lean files. This error occurs during the collection phase of the test suite, specifically affecting tests related to various formatters and the theorem module.

Steps to Reproduce:

1. Ensure you have the latest version of the codebase with the recent changes to the lexer mappings.
2. Attempt to run any script or test that involves the Lean lexer.
3. Observe the `NameError` indicating that 'include' is not defined.

This issue seems to be related to the recent changes in the lexer mappings and the removal of the Lean lexer file. It would be great to have this resolved to continue using the Lean lexer without interruptions.
