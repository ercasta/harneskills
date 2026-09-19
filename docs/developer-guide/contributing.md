# Building these docs

The documentation is MkDocs with the Material theme, configured in `mkdocs.yml`; sources are in `docs/`.

```bash
.venv\Scripts\python -m pip install mkdocs mkdocs-material
.venv\Scripts\python -m mkdocs serve      # live preview at http://127.0.0.1:8000
.venv\Scripts\python -m mkdocs build      # static site into ./site
```

To add a page, create the file under `docs/` and list it in `nav:` in `mkdocs.yml`.
