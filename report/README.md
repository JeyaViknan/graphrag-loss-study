# BCSE497J final report

`out/RGI_Final_Report_23BCE1766.docx` is the report, with a PDF copy next to it. It follows the instructions in the BCE497J template: A4; margins 3.81 cm left and 2.54 cm elsewhere; Times New Roman 12 pt at 1.5 line spacing; chapter headings 16 pt bold; section headings 14 pt in capitals; subsection headings 12 pt in capitals; captions 11 pt; page numbers at the bottom centre, roman for the front matter and arabic from Chapter 1.

## Editing

The text lives in `content/` as one file per chapter, so you can edit it without touching the Word layout:

| File | Contents |
|:--|:--|
| `front.json` | Title, program, team, guide, HoD and month for the cover, declaration and certificate |
| `abstract.md`, `acknowledgement.md` | Abstract and acknowledgement |
| `acronyms.json` | List of acronyms and list of symbols |
| `01_introduction.md` to `07_conclusion.md` | Chapters |
| `08_references.md` | References (APA, numbered) |
| `09_appendices.md` | Appendices |

Numbers written as `{Name}` come from `assets/macros.json`, which is generated from the paper's result files, and `[@fig:id]`-style references become "Figure 4.2" and so on automatically.

You can also edit the finished `.docx` directly in Word. If you do, right-click the contents or a list and choose "Update Field" after editing, so the page numbers stay right. Edits made in Word are lost if you rebuild from `content/`.

## Rebuilding

```bash
# one-off: the docx library
npm install docx@9

# charts and tables from the paper's results (Python 3.11 project environment)
../.venv/bin/python make_assets.py

# diagrams (only if a .tex file in tikz/ changed)
cd tikz && for f in *.tex; do [ "$f" = _preamble.tex ] || pdflatex -interaction=nonstopmode "$f"; done && cd ..
# then convert each changed diagram: pdftoppm -png -r 300 -singlefile tikz/NAME.pdf assets/d_NAME

# build the document, then let Word fill in the contents and lists and export a PDF
node build_report.js RGI_Final_Report_23BCE1766.docx
osascript word_finalize.applescript "$PWD/out/RGI_Final_Report_23BCE1766.docx" "$PWD/out/RGI_Final_Report_23BCE1766.pdf"
```

Opening the document in Word for the first time can take several minutes, because of its size.
