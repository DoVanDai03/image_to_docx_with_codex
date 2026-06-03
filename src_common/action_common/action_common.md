# Action Common

Use this file as the common rule source when converting a UI screenshot or
workflow description into functional documentation and XML.

## Workflow Rules

- Preserve the visible business intent from the input image.
- Do not invent backend fields, APIs, or database details.
- Use `UNKNOWN` when a label, rule, or action is unclear.
- Keep `basic_flow` compact like `docx_common.docx`: normally 2-4 actor/system
  pairs describing only the visible business path.
- Keep `alternative_flow` compact like `docx_common.docx`: normally one row
  for the visible validation or failure response. Do not repeat the full main
  path in the alternative table.
- Keep validation failures, empty results, permission failures, and system
  errors in `error_scenarios` when they do not need a visible alternative row.
- Use CRUD values only when implied by the UI action.
- Keep Draw.io diagrams basic like `xml_common.xml`: start, a short sequence of
  visible user/system actions, and end. Do not add internal queries, backend
  processing steps, decisions, or exception branches unless the user asks for
  a detailed diagram.

## Output Rules

- The feature output folder name must match the feature id.
- The output folder must contain the generated DOCX, XML, and workflow JSON.
- Generated DOCX content must follow the structure detected from `docx_common.docx`.
- Generated XML must preserve the XML common format and naming conventions where possible.
