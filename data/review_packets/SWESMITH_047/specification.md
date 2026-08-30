### Issue: Incorrect Length Calculation for YBR_FULL_422 Photometric Interpretation

#### Description

It seems there is an issue with the `get_expected_length` function when calculating the expected length of pixel data for datasets with the YBR_FULL_422 photometric interpretation. The function does not correctly account for the specific requirements of this photometric interpretation, leading to incorrect length calculations.

#### Steps to Reproduce

1. Create a DICOM dataset with the following attributes:
   - Photometric Interpretation: "YBR_FULL_422"
   - Rows, Columns, SamplesPerPixel, BitsAllocated, and NumberOfFrames set to valid values.
2. Call the `get_expected_length` function with the dataset and unit set to "bytes".
3. Compare the returned length with the expected length for YBR_FULL_422 data.

#### Expected Behavior

The function should return the correct byte length for YBR_FULL_422 data, which involves specific calculations due to its unique packing of pixel data.

#### Actual Behavior

The function returns an incorrect length, which does not match the expected value for YBR_FULL_422 photometric interpretation.

#### Additional Information

This issue affects datasets with YBR_FULL_422 photometric interpretation, potentially leading to incorrect handling of pixel data. Adjustments to the length calculation logic are necessary to ensure accurate results.
