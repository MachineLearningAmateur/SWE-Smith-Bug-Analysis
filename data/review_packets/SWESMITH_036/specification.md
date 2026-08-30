# Enum _ignore_ attribute not working and missing _name_/_value_ properties

Hi,

I've found an issue with the enum support in astroid. There are two problems:

1. The `_ignore_` attribute in Enum classes is not being respected. Here's a simple example:

```python
import enum

class MyEnum(enum.Enum):
    FOO = enum.auto()
    BAR = enum.auto()
    _ignore_ = ["BAZ"]  # This should exclude BAZ from __members__
    BAZ = 42

# But BAZ is still included in the members
print(MyEnum.__members__)  # Contains BAZ when it shouldn't
```

2. The `_name_` and `_value_` sunder properties are missing from enum members. These are standard properties that should be available on all enum members:

```python
import enum

class MyEnum(enum.Enum):
    APPLE = 42

# These properties should exist but don't
print(MyEnum.APPLE._name_)   # Should return "APPLE"
print(MyEnum.APPLE._value_)  # Should return 42
```

I'm using the latest version of astroid. This is causing issues with my code that relies on these standard enum features. Is there a workaround available until this is fixed?
