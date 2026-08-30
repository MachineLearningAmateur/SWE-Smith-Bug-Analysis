**TypeError in batch_update method**

**Describe the bug**
When using the `batch_update` method on a worksheet, a `TypeError` is raised. This occurs when attempting to update multiple cell ranges in a single call. The error seems to be related to the handling of the data parameter within the method.

**To Reproduce**
Here's a simple script to reproduce the issue:

```python
import gspread

# Assuming you have a valid Google Sheets API client
gc = gspread.service_account(filename='path/to/credentials.json')
sh = gc.open('Test Spreadsheet')
worksheet = sh.sheet1

# Attempt to batch update
worksheet.batch_update([
    {'range': 'A1:D1', 'values': [['A1', 'B1', '', 'D1']]},
    {'range': 'A4:D4', 'values': [['A4', 'B4', '', 'D4']]}
])
```

Running this script should result in a `TypeError`.

**Expected behavior**
The `batch_update` method should update the specified cell ranges without raising an error, and the data should be correctly reflected in the spreadsheet.

**Environment info**
- OS: Ubuntu 20.04
- Python version: 3.10.16
- gspread version: 5.0.0

**Additional context**
This issue might be related to recent changes in the method's parameter handling. Any insights or workarounds would be appreciated!
