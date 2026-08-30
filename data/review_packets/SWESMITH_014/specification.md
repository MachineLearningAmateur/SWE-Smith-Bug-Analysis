Multiple issues with CLI commands in dotenv

Description

I've found several issues with the CLI commands in dotenv that are causing unexpected behavior:

1. The `list` command is displaying values in reverse order instead of sorted alphabetically
2. The `list` command with `--format=json` is not sorting keys
3. The `unset` command is showing success message when it fails and vice versa
4. The `run` command is showing "No command given" error when a command is actually provided
5. The `run` command with `--no-override` flag is not working correctly with environment variables

When trying to use the CLI, I'm getting unexpected results. For example:

```
$ dotenv list
# Shows values in reverse order instead of alphabetically sorted

$ dotenv --file .env unset KEY
Successfully removed KEY
# But the key wasn't actually removed

$ dotenv run printenv VAR
No command given.
# Even though I provided a command
```

Also, when trying to open a directory as a file (instead of a regular file), the error handling is incorrect.

This affects multiple commands including `list`, `get`, `unset`, and `run`. The behavior is inconsistent with the documentation and previous versions.
