# Template Format Reference

This reference captures the DOCX format rules supplied by the user. Use it when
rendering generated documents from `docx_common.docx`.

## Page

- Paper: US Letter, `w:w="12240" w:h="15840"`.
- Margins: 1 inch on all sides, `1440 DXA`.
- Header/footer: 0.5 inch, `720 DXA`.

## Fonts

- Body font: `Yu Mincho`.
- Heading font: `Yu Gothic Light`.
- Main size: 12pt, `w:sz="24"`.
- Default line spacing: 1.15x auto.
- Default spacing after: 8pt.

## Heading Paragraphs

- Used for section numbers such as `4.1.2.3.2.x`.
- Font: `Yu Gothic Light`.
- Size: 12pt.
- Italic.
- Title text underlined; number text not underlined.
- Spacing before 2pt, after 8pt.
- Keep next and keep lines enabled.
- Outline levels: 4 and 5.

## General Info Table

- 2 columns.
- Centered.
- Width: `4855 pct`.
- Column widths: `1590 pct`, `3410 pct`.
- Borders: single gray `808080`; outer border heavier.
- Left cells: fill `F3F3F3`, vertical center, justify, left indent 142 twips, bold.
- Right cells: white, vertical center, justify, regular.

## Flow Tables

- 3 columns.
- Width: `9279 DXA`.
- Indent: `-34 DXA`.
- Borders: dotted, size 4.
- Column widths: `2572`, `4950`, `1757` DXA.
- Header row: height 530 twips, center, bold, light gray fill `F5F5F5`.
- Body rows: columns 1 and 2 justify, column 3 center.
- Footer row: light gray fill `EBEBEB`.

## Captions

- Font: `Yu Mincho`.
- Size: 12pt.
- Italic.
- Center aligned.
- Spacing after 8pt.
