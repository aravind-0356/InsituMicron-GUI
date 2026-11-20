---
name: handover-document-style
description: Use when producing a Word (.docx) manual, handover, or technical guide in the InsituMicron house style (chapter-numbered, branded title page, auto-updating contents, NOTE/TIP/WARNING/DANGER callouts, definition tables, numbered steps, quick-reference card). Matches the DAQ Operator"C:\Users\rohit\work\GUI files\GUI_Creep\Insitumicron_Creep_GUI_User_Manual_V1.1.pdf" and "C:\Users\rohit\work\GUI files\PI_HMI_v1_lc\InsituMicron_DAQ_Operator_Manual_V1.1.pdf"
---

# Handover Document Style Skill

## 1. Purpose

Generate documents that look and read like the InsituMicron DAQ Operator Manual V1.1 and Creep GUI User Manual V1.1. This skill controls LAYOUT, STRUCTURE and TONE. The `knowledge-transfer-content` skill controls WHAT goes in.

## 2. Step 0: extract exact style tokens (do not guess)

The reference manuals are the source of truth. Exact fonts, sizes, colours, margins and header/footer layout are NOT written in this file because they were not available as text.

1. Locate the reference files (ask the owner for paths if not in the repo): the two reference manuals as `.docx`, or exported from Google Docs as `.docx`.
2. Unzip and inspect `word/styles.xml`, `word/document.xml`, `word/header*.xml`, `word/footer*.xml`, `word/theme/theme1.xml`, `word/media/`.
3. Record into `style_tokens.json`: body font and size, heading fonts, sizes and colours for Heading 1/2/3, title page layout, table header fill and border colours, callout fill/border/label colours per type, page size and margins, header content (logo placement and size), footer content.
4. Extract the logo image from `word/media/` (or use the repo file `InsituMicronlogo.jpg`).
5. Known brand colours from the codebase: primary `#005b7f` (dark teal), accent `#00a8cc` (bright teal). Use as fallback only if the reference cannot be read.
6. If the references cannot be obtained, say so, use the structure below with the brand colours, and flag "visual match not verified".

Palette option: default is the reference palette. If the owner asks for a black-and-white version, keep every structural element and replace colours with greys and black borders.

## 3. Document structure (in this order)

1. Title page
   - Brand line `INSITUMICRON` (large, bold).
   - Document title in capitals, then a subtitle line.
   - Small two-column info table: Software Version, System Model, Document Date, Document Status (e.g. Release). Add Author and Reviewer for handover documents.
2. Document control block (handover documents only): version, date, author, reviewer, status, change log table.
3. `Table of Contents` heading, then entries for every `Chapter` and every `N.M` section with right-aligned page numbers. Page numbers must be real Word fields (bookmark + PAGEREF per heading, `updateFields` enabled), never typed text.
4. Chapters. Heading 1 text is exactly `Chapter N: Title`. Heading 2 is `N.M Title`. Heading 3 is an unnumbered descriptive label for a sub-block (e.g. `Unload Position (single)`).
5. Standard Workflow chapter (table: `#` | `Action` | `Details`, with chapter/section references in Details), when the document describes a procedure.
6. Troubleshooting chapter (table: `Issue` | `Resolution`).
7. Final chapter `Quick Reference Card` with compact tables: defaults, limits, menu map, status labels, colour conventions, output files.

## 4. Building blocks

### 4.1 Definition table (most common)
Two columns. Left column bold, short term. Right column one to three sentences. No header row. Used for hardware lists, field descriptions, options, behaviours.

### 4.2 Header-row table
First row filled with the header colour, bold text. Used for multi-column data: parameters (Parameter | Value | Unit), messages, pin maps, BOM, issue register, valid ranges.

### 4.3 Numbered steps
```
Step 1: Short action title in bold
One or two sentences describing exactly what to do and what to expect.
```
Each step is one action. Include the exact UI label or command in bold or monospace.

### 4.4 Callouts
Single-cell table with a coloured left bar or fill, a bold uppercase label, then text. Four types from the references:

| Type | Use for | Icon prefix in creep manual |
| :---- | :---- | :---- |
| NOTE | Neutral facts, quirks, scope limits | info |
| TIP | Better practice, time savers | check |
| WARNING | Risk of wrong data, wrong result, or equipment misuse | warning triangle |
| DANGER | Risk of injury, equipment damage, or irreversible data loss | stop sign |

Add two handover-specific callouts using the same shape:
- `OPEN ITEM`: an unresolved question or `[UNKNOWN]` fact that the owner must answer.
- `EVIDENCE`: where a claim came from (file, function, config key) when not obvious.

Rules: at most two callouts per page. DANGER only for real injury or irreversible loss. Never put a procedure step inside a callout.

### 4.5 Code and message blocks
Monospace, light grey fill, thin border, no syntax colouring. Used for serial messages, commands, JSON, file paths, build commands. One example per format, with units in the explanation below.

### 4.6 Figures
- Architecture, wiring and flow diagrams as PNG (300 dpi) generated with graphviz, matplotlib, or draw-style SVG converted to PNG. Black/teal lines on white, labels at least 9 pt.
- Caption below: `Figure N.M: description`. Reference every figure in text.
- Screenshots only if the owner supplies them. Never fabricate UI screenshots.

### 4.7 Cross-references
Write `Section 7.3` and `Chapter 9`. Keep numbering stable. Verify every reference after final generation.

## 5. Tone and wording rules

- Imperative, second person for procedures: "Click Start Rec." "Tare both sensors before every test."
- Use exact UI labels with the same capitalisation as the software (Start Rec, Tare Load, Go to Load).
- One idea per sentence. Short paragraphs, 1 to 4 sentences.
- Units in parentheses in headings and column names: `Speed (mm/sec)`, `Load (N)`.
- Explain each technical term once, in plain words, at first use.
- State defaults, ranges and limits explicitly.
- Prefer a table over a paragraph when there are three or more parallel items.
- No em dashes, no filler adjectives, no marketing language. Use a colon or a hyphen.
- Mark gaps visibly: `[UNKNOWN: ask owner]` inline, plus an OPEN ITEM callout for important ones.
- Do not reproduce credentials, tokens, or personal data.

## 6. Page furniture

- Header on every page after the title page: logo at left, document short title at right.
- Footer: document version and date at left, `Page X of Y` at right (fields).
- Page breaks: every Chapter starts on a new page. Tables must not split a row across pages. Keep a heading with its first paragraph.
- Consistent spacing: take values from `style_tokens.json`.

## 7. Generation method

1. Choose the library available in the environment: `python-docx` (Python) or `docx` (Node). Check which is installed; install if missing.
2. Build styles first (Normal, Heading 1 to 3, Title, table styles, callout styles, code style), then content.
3. Build long documents in stages: outline, then chapter by chapter, from a structured content source (YAML/JSON or Python data) so edits do not require rewriting layout code.
4. Insert TOC entries as bookmark + PAGEREF fields and set `updateFields` to true so Word refreshes on open.
5. Save to `docs/handover/` with a versioned name, e.g. `Insitumicron_Creep_Handover_Architecture_V1.0.docx`.

## 8. Verification (required before reporting done)

1. Convert to PDF (LibreOffice headless) and render pages to images. Look at the title page, TOC, one page of each element type, and the last page.
2. Check: TOC page numbers match headings; no orphan headings; no table row split across pages; callouts render with labels; header/footer appear; figures legible.
3. Check content rules: every claim tagged where the content skill requires it; no `[UNKNOWN]` hidden; no credentials; all cross-references resolve.
4. Compare side by side with a reference manual page for visual parity. Report any mismatch honestly, including which tokens could not be extracted.
5. Report to the owner: file path, page count, list of OPEN ITEMs, and anything not verified.

## 9. Do not

- Do not guess fonts or colours when the reference can be inspected.
- Do not type page numbers into the TOC.
- Do not mix chapter numbering schemes within one document.
- Do not embed generated screenshots that pretend to be the real UI.
- Do not overwrite an existing handover document without versioning it.
