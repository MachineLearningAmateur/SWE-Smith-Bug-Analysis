# SELECT INTO functionality broken in latest commit

## Description

After the recent changes to the `into` method in `QueryBuilder`, the SELECT INTO functionality is no longer working. This appears to be a regression as the functionality was working correctly before.

## Steps to Reproduce

Here's a simple example that demonstrates the issue:

```python
from pypika import Query, Table

table_abc = Table('abc')
table_efg = Table('efg')

# This should generate a SELECT INTO query but doesn't work anymore
query = Query.from_(table_abc).select(table_abc.foo, table_abc.bar).into(table_efg)
print(str(query))
```

## Expected Results

The query should generate SQL with the INTO clause:
```
SELECT "foo","bar" INTO "efg" FROM "abc"
```

## Actual Results

The query doesn't properly handle the SELECT INTO pattern. The issue appears to be in the implementation of the `into` method in the `QueryBuilder` class.

When trying to use the SELECT INTO functionality, the query doesn't generate the expected SQL. The problem seems to be related to the recent changes in the implementation of the `into` method, which no longer sets the `_select_into` flag when there are existing selects.

## Additional Information

This also affects more complex queries that use SELECT INTO with JOINs:

```python
table_abc = Table('abc')
table_efg = Table('efg')
table_hij = Table('hij')

query = Query.from_(table_abc).select(table_abc.foo, table_abc.bar).join(table_hij).on(table_abc.id == table_hij.abc_id).select(table_hij.fiz, table_hij.buz).into(table_efg)
```

The expected SQL would be:
```
SELECT "abc"."foo","abc"."bar","hij"."fiz","hij"."buz" INTO "efg" FROM "abc" JOIN "hij" ON "abc"."id"="hij"."abc_id"
```

But this is no longer working with the current implementation.
