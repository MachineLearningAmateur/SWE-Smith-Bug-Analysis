String formatting issues in PtyProcess causing multiple failures

### Description

I've discovered several issues with string formatting in the PtyProcess class that cause various failures when spawning processes. The problems appear to be related to incorrect string formatting patterns in error messages and process handling.

### Expected behavior

PtyProcess should correctly spawn processes, handle errors properly, and format error messages correctly.

### How to Reproduce

I've found multiple scenarios where this fails:

```python
# Example 1: Command not found error message is malformed
from ptyprocess import PtyProcess
try:
    child = PtyProcess.spawn(['nonexistent_command'])
except FileNotFoundError as e:
    print(e)  # This prints a malformed error message

# Example 2: Passing file descriptors doesn't work correctly
import tempfile, fcntl
with tempfile.NamedTemporaryFile() as temp_file:
    temp_file_fd = temp_file.fileno()
    fcntl.fcntl(temp_file_fd, fcntl.F_SETFD, fcntl.fcntl(temp_file_fd, fcntl.F_GETFD) & ~fcntl.FD_CLOEXEC)
    # This fails when it should work
    p = PtyProcess.spawn(['bash', '-c', f'printf hello >&{temp_file_fd}'], pass_fds=(temp_file_fd,))
    p.wait()
    # Check if anything was written to the file
    with open(temp_file.name, 'r') as f:
        print(f.read())  # Should print "hello" but doesn't

# Example 3: Preexec function errors are not properly propagated
def preexec_fn():
    raise ValueError("Test error")

try:
    child = PtyProcess.spawn(['ls'], preexec_fn=preexec_fn)
except Exception as e:
    print(e)  # Error message is malformed
```

I think there are issues with how string formatting is being handled in several places, particularly in error messages and in the file descriptor handling code.

### Versions

Python 3.10
ptyprocess (latest version)
