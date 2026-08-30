CTE elimination not working correctly after scope reference counting changes

**Describe the bug**
After recent changes to the scope reference counting mechanism, CTE elimination is no longer working properly. The optimizer fails to correctly identify and eliminate CTEs that should be inlined.

**To Reproduce**

When trying to optimize a query with CTEs that should be eliminated:

```sql
WITH cte AS (SELECT x FROM table)
SELECT * FROM cte
```

The optimizer fails to eliminate the CTE and inline it into the main query.

This issue appears to be related to the scope reference counting logic in the optimizer. The current implementation is using `sources` instead of `selected_sources` when counting references, which causes incorrect reference counts.

**Expected behavior**
CTEs that are only referenced once should be eliminated and inlined into the main query when the optimizer is run with the eliminate_ctes option.

**Additional context**
The issue seems to be in the `scope_ref_count` method which now counts references incorrectly. The previous implementation was using `selected_sources` but the new one is using `sources` which changes the behavior.
