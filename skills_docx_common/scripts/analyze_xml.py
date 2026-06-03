import argparse
import sys
from collections import Counter
from pathlib import Path

from lxml import etree

from common import DEFAULT_SRC_COMMON, get_common_paths, require_file, resolve_path, write_json


def local_name(tag: str) -> str:
    return etree.QName(tag).localname if tag else ""


def analyze_xml(xml_path: Path) -> dict:
    parser = etree.XMLParser(remove_blank_text=False, recover=True)
    tree = etree.parse(str(xml_path), parser)
    root = tree.getroot()
    counts = Counter(local_name(el.tag) for el in root.iter())
    result = {
        "source": str(xml_path),
        "root_tag": local_name(root.tag),
        "root_attributes": dict(root.attrib),
        "namespaces": {k or "default": v for k, v in root.nsmap.items()},
        "element_counts": dict(sorted(counts.items())),
        "is_drawio": local_name(root.tag) == "mxfile",
    }

    if result["is_drawio"]:
        diagrams = []
        cells = []
        for diagram in root.findall(".//diagram"):
            diagrams.append(
                {
                    "name": diagram.get("name", ""),
                    "id": diagram.get("id", ""),
                }
            )
        for cell in root.findall(".//mxCell"):
            value = cell.get("value", "")
            style = cell.get("style", "")
            if value or style:
                cells.append(
                    {
                        "id": cell.get("id", ""),
                        "value": value,
                        "style": style,
                        "vertex": cell.get("vertex", ""),
                        "edge": cell.get("edge", ""),
                    }
                )
        result["drawio"] = {
            "diagram_count": len(diagrams),
            "diagrams": diagrams,
            "mx_cells_with_value_or_style": cells[:200],
        }

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze a common XML template.")
    parser.add_argument("--xml", default="", help="XML path.")
    parser.add_argument("--out", default="", help="Output JSON path.")
    args = parser.parse_args(argv)

    default_xml = get_common_paths(DEFAULT_SRC_COMMON)["xml"]
    xml_path = require_file(resolve_path(args.xml, default_xml), "XML common")
    out_path = resolve_path(args.out, xml_path.with_suffix(".analysis.json"))
    write_json(out_path, analyze_xml(xml_path))
    print(f"xml_analysis: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
