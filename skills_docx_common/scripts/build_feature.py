import argparse
import sys
from pathlib import Path

from analyze_docx import analyze_docx
from analyze_xml import analyze_xml
from common import (
    DEFAULT_SRC_COMMON,
    draft_workflow,
    get_common_paths,
    load_json,
    normalize_workflow,
    require_file,
    resolve_path,
    slugify,
    write_json,
)
from render_docx import render_docx
from render_png import export_png
from render_xml import render_xml


def load_or_draft_workflow(workflow_json: str, name: str, image: str) -> dict:
    if workflow_json:
        workflow_path = require_file(Path(workflow_json).resolve(), "Workflow JSON")
        return normalize_workflow(load_json(workflow_path), name=name or None, image=image or None)
    return draft_workflow(name or None, image or None)


def build_feature(
    workflow: dict,
    docx_common: Path,
    xml_common: Path,
    action_common: Path,
    output_root: Path,
) -> dict:
    feature_id = slugify(workflow["id"])
    workflow["id"] = feature_id
    output_dir = output_root / feature_id
    output_dir.mkdir(parents=True, exist_ok=True)

    workflow_path = output_dir / "workflow.json"
    docx_analysis_path = output_dir / "docx_analysis.json"
    xml_analysis_path = output_dir / "xml_analysis.json"
    output_docx = output_dir / f"{feature_id}.docx"
    output_xml = output_dir / f"{feature_id}.xml"
    output_png = output_dir / f"{feature_id}.png"

    write_json(workflow_path, workflow)
    write_json(docx_analysis_path, analyze_docx(docx_common))
    write_json(xml_analysis_path, analyze_xml(xml_common))
    render_xml(xml_common, workflow, output_xml)
    export_png(output_xml, output_png)
    workflow["source_image"] = str(output_png)
    write_json(workflow_path, workflow)
    render_docx(docx_common, workflow, output_docx)

    return {
        "dir": str(output_dir),
        "workflow": str(workflow_path),
        "docx_analysis": str(docx_analysis_path),
        "xml_analysis": str(xml_analysis_path),
        "docx": str(output_docx),
        "xml": str(output_xml),
        "png": str(output_png),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a feature DOCX/XML package from common sources.")
    parser.add_argument("--workflow-json", default="", help="Workflow JSON path.")
    parser.add_argument("--image", default="", help="Input screenshot/image path for draft workflow metadata.")
    parser.add_argument("--name", default="", help="Feature name used when drafting workflow.")
    parser.add_argument("--src-common", default=str(DEFAULT_SRC_COMMON), help="Common source root.")
    parser.add_argument("--docx-common", default="", help="Override common DOCX path.")
    parser.add_argument("--xml-common", default="", help="Override common XML path.")
    parser.add_argument("--action-common", default="", help="Override common action markdown path.")
    parser.add_argument("--output-root", default="", help="Output root folder.")
    args = parser.parse_args(argv)

    src_common = resolve_path(args.src_common, DEFAULT_SRC_COMMON)
    common_paths = get_common_paths(src_common)
    docx_common = require_file(resolve_path(args.docx_common, common_paths["docx"]), "DOCX common")
    xml_common = require_file(resolve_path(args.xml_common, common_paths["xml"]), "XML common")
    action_common = resolve_path(args.action_common, common_paths["action"])
    output_root = resolve_path(args.output_root, Path.cwd())

    workflow = load_or_draft_workflow(args.workflow_json, args.name, args.image)
    result = build_feature(workflow, docx_common, xml_common, action_common, output_root)
    for key in ["dir", "workflow", "docx_analysis", "xml_analysis", "docx", "xml", "png"]:
        print(f"{key}: {result[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
