# Address parsing fails for all addresses after tokenFeatures refactoring

I've noticed that after recent changes to the `tokenFeatures` function in `usaddress/__init__.py`, the library is no longer able to correctly parse any addresses.

## Description

The address parser is completely broken after the recent refactoring of the `tokenFeatures` function. I tried parsing several simple addresses like:

```
9112 Mendenhall Mall Road, Juneau, AK 99801
2701 Thayer Street, Evanston, 60201
P.O. Box 123456
```

None of these addresses are parsed correctly anymore. The parser seems to be unable to identify any components of the addresses.

## Reproduction

Here's a simple script to reproduce the issue:

```python
import usaddress

address = "9112 Mendenhall Mall Road, Juneau, AK 99801"
parsed_address = usaddress.parse(address)

print("Parsed address:", parsed_address)
# Expected: A list of (token, label) tuples with proper component labels
# Actual: Either incorrect labels or an error
```

This issue affects all address parsing functionality in the library. The problem appears to be related to the recent changes in how token features are extracted and processed in the `tokenFeatures` function.
