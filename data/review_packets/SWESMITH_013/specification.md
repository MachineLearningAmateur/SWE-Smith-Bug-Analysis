### Issue: Group Description and Listing Malfunction

#### Describe the Bug

After recent changes, there seems to be an issue with the group description and listing functionality in the identity store. The `describe_group` and `list_groups` operations are not returning the expected results, leading to inconsistencies and errors.

#### How to Reproduce

1. **Create a Group**: Use the `create_group` function to create a new group in the identity store.
2. **Describe the Group**: Attempt to retrieve the group details using the `describe_group` function with the `IdentityStoreId` and `GroupId` of the newly created group.
3. **List Groups**: Use the `list_groups` function to retrieve all groups or filter by `DisplayName`.

#### Expected Behavior

- The `describe_group` function should return the correct group details, including `GroupId`, `DisplayName`, `Description`, and `IdentityStoreId`.
- The `list_groups` function should accurately list all groups or filter them based on the provided criteria.

#### Actual Behavior

- The `describe_group` function fails to return the expected group details, resulting in a `ResourceNotFoundException`.
- The `list_groups` function does not return the correct list of groups, especially when filters are applied.

#### Additional Context

This issue seems to be related to recent changes in the data structure for storing group information. The transition from using a `NamedTuple` to a dictionary might have introduced discrepancies in how group data is accessed and returned.

#### Environment

- **OS**: Linux
- **Python Version**: 3.12.9
- **Testing Framework**: pytest 8.3.4

Please investigate and address this issue to ensure the identity store's group functionalities work as expected.
