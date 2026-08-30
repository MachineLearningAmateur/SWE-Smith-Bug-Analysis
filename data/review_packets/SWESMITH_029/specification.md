### Account Assignment Deletion Fails to Return RequestId

Description

The recent changes to the `SSOAdminBackend` class have introduced an issue where the `delete_account_assignment` method no longer returns the `RequestId` in its response. This is causing problems when trying to track the status of account assignment deletions.

Steps to Reproduce:

1. Attempt to delete an account assignment using the `delete_account_assignment` method.
2. Observe the response returned by the method.

Expected Result:
The response should include a `RequestId` field to uniquely identify the deletion request.

Actual Result:
The response does not include a `RequestId`, making it difficult to track and verify the deletion request.

This issue affects any functionality that relies on the `RequestId` for tracking account assignment deletions.
