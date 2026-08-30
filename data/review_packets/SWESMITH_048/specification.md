# seed_instance() doesn't create a new random instance

When using `seed_instance()` on a Faker generator, it doesn't create a new random instance when called for the first time. This causes inconsistent behavior when trying to seed specific instances.

## To reproduce:

```python
from faker import Faker

# Create two Faker instances
fake1 = Faker()
fake2 = Faker()

# Seed the first instance
fake1.seed_instance(123)

# Generate some random values
print("First instance values:")
print(fake1.random_int())
print(fake1.random_int())

print("Second instance values:")
print(fake2.random_int())
print(fake2.random_int())
```

## Expected behavior:
When calling `seed_instance()`, a new random instance should be created for that specific Faker instance, and subsequent random values should be deterministic based on the seed value.

## Actual behavior:
The `seed_instance()` method doesn't create a new random instance, so both Faker instances end up sharing the same random state. This means that seeding one instance affects all other instances, which breaks the ability to have independent, reproducible random sequences per instance.

This is particularly problematic when working with multiple Faker instances in the same application where you need deterministic output from one instance without affecting others.
