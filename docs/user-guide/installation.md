# Installation

HarneSkills needs Python 3.9+ and one dependency, `loopingrules`, which is **not yet published**. It is expected as a sibling checkout:

```text
creazioni/
├── harneskills/
└── loopingrules/
```

From the `harneskills` directory, in a virtual environment:

=== "Windows (PowerShell)"

    ```powershell
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -e ..\loopingrules -e ".[dev]"
    ```

=== "Linux / macOS"

    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install -e ../loopingrules -e ".[dev]"
    ```

Two console scripts are installed: `harneskills` and `harneskills-client`. `python -m harneskills` and `python -m harneskills.client` are equivalent.

`pytest` finds `../loopingrules` on its own (`pythonpath` in `pyproject.toml`), so the test suite runs even without installing it.
