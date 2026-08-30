# `date_of_birth` method no longer validates input parameters

### Description

I've discovered an issue with the `date_of_birth` method in the date_time provider. The method no longer validates its input parameters, which can lead to unexpected behavior or silent failures when invalid values are provided.

Previously, the method would raise appropriate ValueError exceptions when:
- minimum_age was negative
- maximum_age was negative
- minimum_age was greater than maximum_age

Now, these validation checks are missing, and the method will silently accept invalid parameters without raising any errors.

### Steps to Reproduce

```python
from faker import Faker

fake = Faker()

# These should raise ValueError but now silently accept invalid values
try:
    # Should fail with negative minimum age
    dob1 = fake.date_of_birth(minimum_age=-1)
    print(f"Accepted negative minimum age: {dob1}")
    
    # Should fail with negative maximum age
    dob2 = fake.date_of_birth(maximum_age=-1)
    print(f"Accepted negative maximum age: {dob2}")
    
    # Should fail when minimum age > maximum age
    dob3 = fake.date_of_birth(minimum_age=50, maximum_age=30)
    print(f"Accepted minimum_age > maximum_age: {dob3}")
except ValueError as e:
    print(f"Correctly raised ValueError: {e}")
```

When running this code, no ValueError is raised, and the method returns dates without any validation errors.

### Expected Behavior

The method should validate its input parameters and raise appropriate ValueError exceptions when:
- minimum_age is negative
- maximum_age is negative
- minimum_age is greater than maximum_age

### System Details
```
Python 3.10.16
Faker 36.2.2
```
