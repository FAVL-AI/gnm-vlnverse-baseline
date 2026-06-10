# FleetSafe-VLN Paper

## Draft

`FleetSafe_VLN_Paper_Draft.md` — working draft, not for citation.

## Export to PDF

```bash
# Option A — pandoc
pip install pandoc
pandoc FleetSafe_VLN_Paper_Draft.md -o FleetSafe_VLN.pdf \
  --pdf-engine=xelatex -V geometry:margin=1in

# Option B — markdownpdf
npm install -g markdown-pdf
markdown-pdf FleetSafe_VLN_Paper_Draft.md

# Option C — VS Code Markdown PDF extension
# Install: vscode ms-ceintl.vscode-markdown-pdf
# Right-click > Markdown PDF: Export (pdf)
```

## Status

PDF not yet generated. Generate from the draft above when ready.
