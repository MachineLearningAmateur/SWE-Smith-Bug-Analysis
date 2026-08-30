### Bug Report

**Unexpected Behavior in PDF Text Extraction**

**Bug Summary:**

After the recent changes, there seems to be an issue with extracting text from certain PDF files. The output does not match the expected results, particularly when dealing with specific configurations or file types.

**Steps to Reproduce:**

1. Use the `run_with_string` function to process the `simple1.pdf` file with `laparams={'boxes_flow': None}`.
2. Compare the output string with the expected result stored in `test_strings['simple1.pdf_no_boxes_flow']`.

```python
test_file = 'simple1.pdf'
s = run_with_string(test_file, laparams={'boxes_flow': None})
assert s == test_strings['simple1.pdf_no_boxes_flow']
```

**Actual Outcome:**

The extracted text does not match the expected string, indicating a discrepancy in the text extraction process.

**Expected Outcome:**

The output string should match the expected result as defined in the test strings.

**Additional Information:**

- The issue is also observed with other PDF files such as `simple3.pdf` and `nonfree/i1040nr.pdf`.
- The problem seems to be related to the handling of specific PDF structures or configurations.

**Environment:**

- Operating System: Linux
- Python Version: 3.10.15
- PDFMiner Version: Latest from the repository

Please investigate this issue as it affects the reliability of text extraction from PDFs.
