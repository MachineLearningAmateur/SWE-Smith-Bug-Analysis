### Describe the bug

After applying the recent changes to the `BufferedPipe` class, it seems that the order of operations within the `close` method has been altered. This change appears to have introduced a race condition that affects the notification mechanism when closing the pipe.

### How to Reproduce

1. Create an instance of `BufferedPipe`.
2. Start a thread that waits on the pipe to be closed.
3. Close the pipe from another thread.
4. Observe that the waiting thread may not be notified correctly, leading to unexpected behavior or deadlock.

### Expected behavior

The waiting thread should be reliably notified when the pipe is closed, without any race conditions or deadlocks.

### Environment info

- Python version: 3.10.15
- Platform: Linux
- Paramiko version: 3.5.0

### Additional context

This issue seems to be related to the recent changes in the `BufferedPipe` class, specifically the reordering of the `notify_all` call within the `close` method.
