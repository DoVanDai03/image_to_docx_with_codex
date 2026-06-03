---
name: skills_docx_common
description: Generate a feature DOCX and XML from docx_common_workflow/src_common templates and an input UI screenshot or workflow JSON.
metadata:
  short-description: Build DOCX/XML from common templates and UI workflow
---

# skills_docx_common

Use this skill when the user wants to generate a DOCX and XML package for a
feature from common templates and a UI screenshot/workflow.

## Inputs

Default common sources:

- `docx_common_workflow/src_common/docx_common/docx_common.docx`
- `docx_common_workflow/src_common/xml_common/xml_common.xml`
- `docx_common_workflow/src_common/action_common/action_common.md`

Optional user inputs:

- UI screenshot or image
- workflow JSON that follows `references/workflow_schema.json`
- feature name/id

## Workflow

1. Analyze the UI screenshot visually and produce `workflow.json`.
   - For XML diagrams, prefer explicit `lanes`, `nodes`, and `edges`.
   - Keep Draw.io basic like `xml_common.xml`: start, 2-4 visible user/system
     actions, and end. Omit internal queries, backend steps, decisions, and
     error branches unless the user explicitly requests a detailed diagram.
   - Keep `basic_flow` compact like `docx_common.docx`: normally 2-4
     actor/system pairs for the visible happy path.
   - Keep `alternative_flow` compact like `docx_common.docx`: normally one row
     for a visible validation or failure response. Do not repeat the full path.
   - Use `alternative_flows` only when the user explicitly needs separate
     alternative tables.
2. If a screenshot is not available to the script, create or update `workflow.json` manually with `UNKNOWN` for missing data.
3. Run:

```powershell
python .\docx_common_workflow\skills_docx_common\scripts\build_feature.py --workflow-json .\workflow.json
```

4. If only an image is available and no workflow has been written yet, run a draft:

```powershell
python .\docx_common_workflow\skills_docx_common\scripts\build_feature.py --image .\screen.png --name "Ten chuc nang"
```

5. Review `workflow.json`, replace `UNKNOWN`, then rerun with `--workflow-json`.

## Script Roles

- `scripts/analyze_docx.py`: uses `python-docx` and DOCX package XML to inspect `docx_common.docx`.
- `scripts/analyze_xml.py`: uses `lxml` to inspect `xml_common.xml`.
- `scripts/render_docx.py`: renders a new DOCX from common DOCX styles and workflow JSON.
- `scripts/render_xml.py`: renders a new XML from common XML structure and workflow JSON.
- `scripts/build_feature.py`: orchestrates the full build.
- `references/template_format.md`: DOCX layout and formatting rules.
- `references/template_format_full.json`: detailed DOCX format reference for debugging; use only when format output does not match the source DOCX.

## XML Graph Shape

Prefer this structure when the target is a swimlane Draw.io XML:

```json
{
  "title": "Ten chuc nang",
  "lanes": { "user": "Nguoi su dung", "system": "He thong" },
  "nodes": [
    { "id": "start", "type": "start", "shape": "oval", "label": "Bat dau", "lane": "user" },
    { "id": "step1", "type": "process", "shape": "rectangle", "label": "1. Chon menu", "lane": "user" },
    { "id": "step2", "type": "process", "shape": "rectangle", "label": "2. Hien thi man hinh", "lane": "system" },
    { "id": "end", "type": "end", "shape": "oval", "label": "Ket thuc", "lane": "system" }
  ],
  "edges": [
    { "from": "start", "to": "step1" },
    { "from": "step1", "to": "step2" },
    { "from": "step2", "to": "end" }
  ]
}
```

## Output

For feature id `bao-cao-ton-kho`, output goes to:

```text
bao-cao-ton-kho/
  bao-cao-ton-kho.docx
  bao-cao-ton-kho.xml
  workflow.json
  docx_analysis.json
  xml_analysis.json
```

## Guardrails

- Do not overwrite unrelated files.
- Prefer `workflow.json` as the machine-readable source of truth.
- Use `action_common.md` for rules, not as a generated output.
- Treat `src_common/docx_common/docx_common.docx` XML as the source of truth. Use `template_format_full.json` only as a secondary reference.
- If `python-docx` is missing, install `docx_common_workflow/skills_docx_common/requirements.txt`.
