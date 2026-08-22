# Synthetic fixture

Generate with:

```powershell
.venv\Scripts\python.exe tools\create_synthetic.py fixtures\synthetic\synthetic.pptx
```

The fixture contains rich text, bullets, a local cropped image, shapes, a connector, a table, notes, an external hyperlink, and editable column/line/pie charts. WPS COM adds the animation and transition during the PoC because `python-pptx` cannot create them.

The file contains no customer or personal data. Its external hyperlink exists only to verify static security scanning and default blocking.
