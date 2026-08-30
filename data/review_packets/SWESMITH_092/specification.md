### Issue with PDF Structure Conversion

#### Description

After applying the recent changes to the `PDFStructElement` class in `pdfplumber/structure.py`, there seems to be an issue with the conversion of PDF structures to dictionary format. The `to_dict` method is not behaving as expected, leading to several failures in the structure-related functionalities.

#### Steps to Reproduce

1. Load a PDF file with complex structure elements using pdfplumber.
2. Attempt to convert the structure elements to a dictionary using the `to_dict` method.
3. Observe the output for missing or incorrect attributes.

#### Expected Behavior

The `to_dict` method should return a dictionary representation of the PDF structure with all relevant attributes included, and without any missing or incorrect data.

#### Actual Behavior

The method is currently omitting certain attributes or returning incorrect data, which is causing failures in tests that rely on the structure's dictionary representation.

#### Environment

- **pdfplumber version**: Latest commit
- **Python version**: 3.10.16
- **Operating System**: Linux

#### Additional Information

The issue seems to be related to the handling of optional attributes and the pruning of empty values in the `to_dict` method. This is affecting the integrity of the structure's dictionary representation, leading to multiple test failures.
