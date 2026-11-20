# docs/handover/builder_common.py
import os
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls

# Brand Colors
CLR_PRIMARY = "005B7F"      # Dark Teal
CLR_ACCENT = "00A8CC"       # Bright Teal
CLR_TEXT = "2C3E50"         # Dark Slate
CLR_MUTED = "7F8C8D"        # Gray
CLR_LIGHT_BG = "F8F9FA"     # Very Light Gray
CLR_BORDER = "BDC3C7"       # Border Gray

# Callout Colors
CALLOUT_COLORS = {
    "NOTE": ("00A8CC", "F4FBFD"),       # Accent Teal bar, light blue bg
    "TIP": ("27AE60", "F4FAF6"),        # Green bar, light green bg
    "WARNING": ("F39C12", "FDFCF5"),    # Orange bar, light yellow bg
    "DANGER": ("C0392B", "FDF7F7"),     # Red bar, light pink bg
    "OPEN ITEM": ("8E44AD", "F9F5FB"),  # Purple bar, light purple bg
    "EVIDENCE": ("7F8C8D", "F7F9FA"),   # Gray bar, light gray bg
}

FONT_MAIN = "Segoe UI"
FONT_HEADING = "Segoe UI Semibold"
FONT_CODE = "Consolas"


def set_cell_margins(cell, top=120, bottom=120, left=180, right=180):
    """Set inner padding for a table cell (in twips, 20 twips = 1 pt)."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'''
        <w:tcMar {nsdecls("w")}>
            <w:top w:w="{top}" w:type="dxa"/>
            <w:bottom w:w="{bottom}" w:type="dxa"/>
            <w:left w:w="{left}" w:type="dxa"/>
            <w:right w:w="{right}" w:type="dxa"/>
        </w:tcMar>
    ''')
    tcPr.append(tcMar)


def set_cell_shading(cell, hex_color):
    """Apply background shading to a cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tcPr.append(shd)


def set_cell_border(cell, top=None, bottom=None, left=None, right=None):
    """Set specific borders on a cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    b_xml = [f'<w:tcBorders {nsdecls("w")}>']
    for side, border in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        if border:
            val, sz, col = border
            b_xml.append(f'<w:{side} w:val="{val}" w:sz="{sz}" w:space="0" w:color="{col}"/>')
        else:
            b_xml.append(f'<w:{side} w:val="none"/>')
    b_xml.append('</w:tcBorders>')
    tcPr.append(parse_xml(''.join(b_xml)))


def set_row_cant_split(row):
    """Prevent table row from splitting across a page break."""
    trPr = row._tr.get_or_add_trPr()
    trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))


def set_repeat_header(row):
    """Repeat header row on subsequent pages."""
    trPr = row._tr.get_or_add_trPr()
    trPr.append(parse_xml(f'<w:tblHeader {nsdecls("w")}/>'))


def enable_update_fields(doc):
    """Instruct Word to automatically update fields (TOC, page refs) upon opening."""
    settings = doc.settings.element
    settings.append(parse_xml(f'<w:updateFields {nsdecls("w")} w:val="true"/>'))


def create_base_document():
    """Create a configured Document with A4 page size and standard margins."""
    doc = Document()
    enable_update_fields(doc)

    section = doc.sections[0]
    section.page_width = Inches(8.27)    # A4 width
    section.page_height = Inches(11.69)  # A4 height
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)
    section.header_distance = Inches(0.5)
    section.footer_distance = Inches(0.5)

    # Configure Default Styles
    normal = doc.styles['Normal']
    normal.font.name = FONT_MAIN
    normal.font.size = Pt(10.0)
    normal.font.color.rgb = RGBColor(44, 62, 80)
    normal.paragraph_format.line_spacing = 1.15
    normal.paragraph_format.space_after = Pt(5)

    return doc


def add_title_page(doc, main_title, subtitle, system_model, doc_version, doc_date, author, reviewer):
    """Add professional InsituMicron branded title page."""
    section = doc.sections[0]
    section.different_first_page_header_footer = True

    for _ in range(2):
        doc.add_paragraph()

    # Brand Title
    p_brand = doc.add_paragraph()
    r_brand = p_brand.add_run("INSITUMICRON")
    r_brand.font.name = FONT_HEADING
    r_brand.font.size = Pt(30)
    r_brand.font.bold = True
    r_brand.font.color.rgb = RGBColor(0, 91, 127)  # Primary Dark Teal
    p_brand.paragraph_format.space_after = Pt(4)

    # Accent decorative line
    p_line = doc.add_paragraph()
    r_line = p_line.add_run("-" * 45)
    r_line.font.color.rgb = RGBColor(0, 168, 204)  # Accent Bright Teal
    r_line.font.size = Pt(12)
    p_line.paragraph_format.space_after = Pt(20)

    # Main Document Title
    p_title = doc.add_paragraph()
    r_title = p_title.add_run(main_title.upper())
    r_title.font.name = FONT_HEADING
    r_title.font.size = Pt(21)
    r_title.font.bold = True
    r_title.font.color.rgb = RGBColor(44, 62, 80)
    p_title.paragraph_format.space_after = Pt(10)

    # Subtitle
    p_sub = doc.add_paragraph()
    r_sub = p_sub.add_run(subtitle)
    r_sub.font.name = FONT_MAIN
    r_sub.font.size = Pt(12.5)
    r_sub.font.italic = True
    r_sub.font.color.rgb = RGBColor(127, 140, 141)
    p_sub.paragraph_format.space_after = Pt(45)

    # Info Table (Metadata)
    table = doc.add_table(rows=6, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False

    meta = [
        ("System Model:", system_model),
        ("Software Version:", doc_version),
        ("Document Date:", doc_date),
        ("Document Status:", "Release / Verified"),
        ("Author:", author),
        ("Reviewer / Successor:", reviewer),
    ]

    for i, (k, v) in enumerate(meta):
        row = table.rows[i]
        set_row_cant_split(row)
        c0, c1 = row.cells[0], row.cells[1]
        c0.width = Inches(2.2)
        c1.width = Inches(4.0)
        set_cell_margins(c0, top=50, bottom=50, left=60, right=60)
        set_cell_margins(c1, top=50, bottom=50, left=60, right=60)

        p0 = c0.paragraphs[0]
        p0.paragraph_format.space_after = Pt(2)
        r0 = p0.add_run(k)
        r0.font.bold = True
        r0.font.color.rgb = RGBColor(0, 91, 127)

        p1 = c1.paragraphs[0]
        p1.paragraph_format.space_after = Pt(2)
        r1 = p1.add_run(v)
        r1.font.color.rgb = RGBColor(44, 62, 80)

    doc.add_page_break()


def setup_header_footer(doc, short_title, doc_version, doc_date, logo_path=None):
    """Configure running headers and footers for pages after title page."""
    section = doc.sections[0]
    header = section.header
    footer = section.footer

    # Header: Logo left, Short Title right
    hp = header.paragraphs[0]
    hp.text = ""
    hp.paragraph_format.space_after = Pt(2)

    htab = header.add_table(rows=1, cols=2, width=Inches(6.27))
    htab.alignment = WD_TABLE_ALIGNMENT.CENTER
    c_left = htab.cell(0, 0)
    c_right = htab.cell(0, 1)
    c_left.width = Inches(2.5)
    c_right.width = Inches(3.77)
    set_cell_margins(c_left, top=0, bottom=30, left=0, right=0)
    set_cell_margins(c_right, top=0, bottom=30, left=0, right=0)

    p_hleft = c_left.paragraphs[0]
    p_hleft.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if logo_path and os.path.exists(logo_path):
        p_hleft.add_run().add_picture(logo_path, width=Inches(1.4))
    else:
        r_logofallback = p_hleft.add_run("INSITUMICRON")
        r_logofallback.font.bold = True
        r_logofallback.font.color.rgb = RGBColor(0, 91, 127)

    p_hright = c_right.paragraphs[0]
    p_hright.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_st = p_hright.add_run(short_title)
    r_st.font.name = FONT_MAIN
    r_st.font.size = Pt(8.5)
    r_st.font.color.rgb = RGBColor(127, 140, 141)

    set_cell_border(c_left, bottom=('single', '6', CLR_ACCENT))
    set_cell_border(c_right, bottom=('single', '6', CLR_ACCENT))

    # Footer: Version/Date on left, Page X of Y on right
    fp = footer.paragraphs[0]
    fp.text = ""
    ftab = footer.add_table(rows=1, cols=2, width=Inches(6.27))
    ftab.alignment = WD_TABLE_ALIGNMENT.CENTER
    fc_left = ftab.cell(0, 0)
    fc_right = ftab.cell(0, 1)
    fc_left.width = Inches(3.5)
    fc_right.width = Inches(2.77)
    set_cell_margins(fc_left, top=30, bottom=0, left=0, right=0)
    set_cell_margins(fc_right, top=30, bottom=0, left=0, right=0)
    set_cell_border(fc_left, top=('single', '4', CLR_BORDER))
    set_cell_border(fc_right, top=('single', '4', CLR_BORDER))

    p_fleft = fc_left.paragraphs[0]
    p_fleft.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r_fl = p_fleft.add_run(f"InsituMicron Handover | {doc_version} ({doc_date})")
    r_fl.font.size = Pt(8.5)
    r_fl.font.color.rgb = RGBColor(127, 140, 141)

    p_fright = fc_right.paragraphs[0]
    p_fright.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_fr = p_fright.add_run("Page ")
    r_fr.font.size = Pt(8.5)
    r_fr.font.color.rgb = RGBColor(127, 140, 141)

    p_fright._p.append(parse_xml(r'<w:fldSimple %s w:instr="PAGE"/>' % nsdecls('w')))
    r_mid = p_fright.add_run(" of ")
    r_mid.font.size = Pt(8.5)
    r_mid.font.color.rgb = RGBColor(127, 140, 141)
    p_fright._p.append(parse_xml(r'<w:fldSimple %s w:instr="NUMPAGES"/>' % nsdecls('w')))


def add_document_control(doc, history_rows):
    """Add formal Document Control block with change history."""
    p_h = doc.add_paragraph()
    r = p_h.add_run("Document Control")
    r.font.name = FONT_HEADING
    r.font.size = Pt(13)
    r.font.bold = True
    r.font.color.rgb = RGBColor(0, 91, 127)
    p_h.paragraph_format.space_before = Pt(6)
    p_h.paragraph_format.space_after = Pt(6)

    headers = ["Version", "Release Date", "Author / Role", "Reviewer / Custodian", "Change Description"]
    add_header_table(doc, headers, history_rows, col_widths=[Inches(0.8), Inches(1.1), Inches(1.3), Inches(1.3), Inches(1.77)])
    doc.add_paragraph().paragraph_format.space_after = Pt(8)


def add_table_of_contents(doc):
    """Insert Word Table of Contents field code."""
    p_toc = doc.add_paragraph()
    r = p_toc.add_run("Table of Contents")
    r.font.name = FONT_HEADING
    r.font.size = Pt(15)
    r.font.bold = True
    r.font.color.rgb = RGBColor(0, 91, 127)
    p_toc.paragraph_format.space_after = Pt(10)

    p_field = doc.add_paragraph()
    p_field.paragraph_format.space_after = Pt(14)
    run = p_field.add_run()
    fldChar1 = parse_xml(r'<w:fldChar %s w:fldCharType="begin"/>' % nsdecls('w'))
    instrText = parse_xml(r'<w:instrText %s xml:space="preserve"> TOC \o "1-3" \h \z \u </w:instrText>' % nsdecls('w'))
    fldChar2 = parse_xml(r'<w:fldChar %s w:fldCharType="separate"/>' % nsdecls('w'))
    fldChar3 = parse_xml(r'<w:fldChar %s w:fldCharType="end"/>' % nsdecls('w'))
    run._r.append(fldChar1)
    run._r.append(instrText)
    run._r.append(fldChar2)
    run._r.append(fldChar3)

    doc.add_page_break()


def add_chapter_heading(doc, chapter_num, title):
    """Add Heading 1 in format: Chapter N: Title with page break."""
    if chapter_num > 1:
        doc.add_page_break()
    p = doc.add_paragraph(style='Heading 1')
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.keep_with_next = True

    r = p.add_run(f"Chapter {chapter_num}: {title}")
    r.font.name = FONT_HEADING
    r.font.size = Pt(17)
    r.font.bold = True
    r.font.color.rgb = RGBColor(0, 91, 127)


def add_section_heading(doc, sec_num_str, title):
    """Add Heading 2 in format: N.M Title."""
    p = doc.add_paragraph(style='Heading 2')
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.keep_with_next = True

    r = p.add_run(f"{sec_num_str} {title}")
    r.font.name = FONT_HEADING
    r.font.size = Pt(13)
    r.font.bold = True
    r.font.color.rgb = RGBColor(0, 168, 204)  # Accent color


def add_sub_heading(doc, title):
    """Add Heading 3 descriptive sub-block."""
    p = doc.add_paragraph(style='Heading 3')
    p.paragraph_format.space_before = Pt(9)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True

    r = p.add_run(title)
    r.font.name = FONT_HEADING
    r.font.size = Pt(10.5)
    r.font.bold = True
    r.font.color.rgb = RGBColor(44, 62, 80)


def add_callout(doc, callout_type, label, body_text):
    """Add a styled callout box with colored left bar and background tint."""
    bar_col, bg_col = CALLOUT_COLORS.get(callout_type, ("005B7F", "F8F9FA"))

    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False

    cell = tbl.cell(0, 0)
    cell.width = Inches(6.27)
    set_cell_margins(cell, top=90, bottom=90, left=160, right=120)
    set_cell_shading(cell, bg_col)
    set_cell_border(cell, left=('single', '36', bar_col))

    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.15

    r_lbl = p.add_run(f"[{callout_type}] {label}\n")
    r_lbl.font.name = FONT_HEADING
    r_lbl.font.size = Pt(9.5)
    r_lbl.font.bold = True
    r_lbl.font.color.rgb = RGBColor(int(bar_col[:2], 16), int(bar_col[2:4], 16), int(bar_col[4:], 16))

    r_body = p.add_run(body_text)
    r_body.font.name = FONT_MAIN
    r_body.font.size = Pt(9.5)
    r_body.font.color.rgb = RGBColor(44, 62, 80)

    sp = doc.add_paragraph()
    sp.paragraph_format.space_before = Pt(1)
    sp.paragraph_format.space_after = Pt(3)


def add_code_block(doc, code_str, caption=None):
    """Add a shaded monospace code box."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False

    cell = tbl.cell(0, 0)
    cell.width = Inches(6.27)
    set_cell_margins(cell, top=70, bottom=70, left=120, right=120)
    set_cell_shading(cell, CLR_LIGHT_BG)
    set_cell_border(cell,
                    top=('single', '4', CLR_BORDER),
                    bottom=('single', '4', CLR_BORDER),
                    left=('single', '12', CLR_PRIMARY),
                    right=('single', '4', CLR_BORDER))

    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.05

    r = p.add_run(code_str)
    r.font.name = FONT_CODE
    r.font.size = Pt(8.5)
    r.font.color.rgb = RGBColor(44, 62, 80)

    if caption:
        p_cap = doc.add_paragraph()
        p_cap.paragraph_format.space_before = Pt(1)
        p_cap.paragraph_format.space_after = Pt(4)
        r_c = p_cap.add_run(f"Listing: {caption}")
        r_c.font.size = Pt(8.5)
        r_c.font.italic = True
        r_c.font.color.rgb = RGBColor(127, 140, 141)


def add_def_table(doc, pairs):
    """Add 2-column definition table (bold left term, plain right description)."""
    tbl = doc.add_table(rows=len(pairs), cols=2)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False

    for idx, (term, desc) in enumerate(pairs):
        row = tbl.rows[idx]
        set_row_cant_split(row)
        c0, c1 = row.cells[0], row.cells[1]
        c0.width = Inches(2.0)
        c1.width = Inches(4.27)
        set_cell_margins(c0, top=50, bottom=50, left=70, right=70)
        set_cell_margins(c1, top=50, bottom=50, left=70, right=70)

        bg = CLR_LIGHT_BG if idx % 2 == 1 else "FFFFFF"
        set_cell_shading(c0, bg)
        set_cell_shading(c1, bg)
        set_cell_border(c0, bottom=('single', '4', CLR_BORDER))
        set_cell_border(c1, bottom=('single', '4', CLR_BORDER))

        p0 = c0.paragraphs[0]
        p0.paragraph_format.space_after = Pt(2)
        r0 = p0.add_run(term)
        r0.font.bold = True
        r0.font.size = Pt(9.5)
        r0.font.color.rgb = RGBColor(0, 91, 127)

        p1 = c1.paragraphs[0]
        p1.paragraph_format.space_after = Pt(2)
        r1 = p1.add_run(desc)
        r1.font.size = Pt(9.5)
        r1.font.color.rgb = RGBColor(44, 62, 80)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def add_header_table(doc, headers, rows, col_widths=None):
    """Add multi-column data table with teal header row and zebra body."""
    tbl = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False

    hdr_row = tbl.rows[0]
    set_row_cant_split(hdr_row)
    set_repeat_header(hdr_row)

    for i, h in enumerate(headers):
        cell = hdr_row.cells[i]
        if col_widths and i < len(col_widths):
            cell.width = col_widths[i]
        set_cell_margins(cell, top=80, bottom=80, left=70, right=70)
        set_cell_shading(cell, CLR_PRIMARY)
        set_cell_border(cell, bottom=('single', '12', CLR_ACCENT))

        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(h)
        r.font.name = FONT_HEADING
        r.font.bold = True
        r.font.size = Pt(9.0)
        r.font.color.rgb = RGBColor(255, 255, 255)

    for r_idx, row_data in enumerate(rows):
        row = tbl.rows[r_idx + 1]
        set_row_cant_split(row)
        bg = CLR_LIGHT_BG if r_idx % 2 == 1 else "FFFFFF"

        for c_idx, val in enumerate(row_data):
            cell = row.cells[c_idx]
            if col_widths and c_idx < len(col_widths):
                cell.width = col_widths[c_idx]
            set_cell_margins(cell, top=50, bottom=50, left=70, right=70)
            set_cell_shading(cell, bg)
            set_cell_border(cell, bottom=('single', '4', CLR_BORDER))

            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run(str(val))
            r.font.name = FONT_MAIN
            r.font.size = Pt(9.0)
            r.font.color.rgb = RGBColor(44, 62, 80)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)
