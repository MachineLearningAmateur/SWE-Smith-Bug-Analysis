# find_dotenv() fails when called from inside a zip file

#### MCVE Code Sample

```python
import os
import sys
import zipfile
from pathlib import Path

# Create a zip file with a Python script that uses dotenv
zip_path = Path("test.zip")
with zipfile.ZipFile(zip_path, "w") as zf:
    zf.writestr("script.py", """
from dotenv import load_dotenv
load_dotenv()
""")

# Add the zip file to sys.path and import the script
sys.path.append(str(zip_path))
import script  # This will fail
```

#### Expected Behavior
When importing a module from a zip file that uses `load_dotenv()` or `find_dotenv()`, it should work correctly even if no `.env` file exists.

#### Actual Behavior
When importing a module from a zip file that uses `load_dotenv()`, it fails with an error because `find_dotenv()` doesn't handle zip file imports properly.

The issue appears to be in the frame inspection logic in `find_dotenv()`. When called from inside a zip file, the code tries to check if the frame's filename exists, but this check doesn't work correctly with zip file imports.

#### Environment Information
- Python version: 3.10
- dotenv version: latest
- OS: Linux

<END WRITING>
