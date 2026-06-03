import argparse
import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

from lxml import etree

from common import require_file, resolve_path


def local_name(tag: str) -> str:
    return etree.QName(tag).localname if tag else ""


def style_map(style: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in str(style or "").split(";"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        result[key] = value
    return result


def geometry(cell) -> dict[str, float]:
    item = cell.find("./mxGeometry")
    if item is None:
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    return {
        "x": float(item.get("x") or 0),
        "y": float(item.get("y") or 0),
        "width": float(item.get("width") or 0),
        "height": float(item.get("height") or 0),
    }


def find_browser() -> str:
    candidates = [
        shutil.which("chrome"),
        shutil.which("msedge"),
        shutil.which("chromium"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise SystemExit("Cannot export PNG: Chrome or Edge was not found.")


def absolute_boxes(cells: dict[str, etree._Element]) -> dict[str, dict[str, float]]:
    boxes: dict[str, dict[str, float]] = {}

    def compute(cell_id: str) -> dict[str, float]:
        if cell_id in boxes:
            return boxes[cell_id]
        cell = cells[cell_id]
        box = geometry(cell)
        parent_id = cell.get("parent")
        if parent_id in cells and cells[parent_id].get("vertex") == "1":
            parent = compute(parent_id)
            box = {
                "x": parent["x"] + box["x"],
                "y": parent["y"] + box["y"],
                "width": box["width"],
                "height": box["height"],
            }
        boxes[cell_id] = box
        return box

    for cell_id, cell in cells.items():
        if cell.get("vertex") == "1":
            compute(cell_id)
    return boxes


def parent_offset(edge, boxes: dict[str, dict[str, float]]) -> tuple[float, float]:
    parent_id = edge.get("parent")
    if parent_id in boxes:
        box = boxes[parent_id]
        return box["x"], box["y"]
    return 0.0, 0.0


def port(box: dict[str, float], style: dict[str, str], prefix: str, fallback: tuple[float, float]) -> tuple[float, float]:
    x = float(style.get(f"{prefix}X", fallback[0]))
    y = float(style.get(f"{prefix}Y", fallback[1]))
    return box["x"] + box["width"] * x, box["y"] + box["height"] * y


def center(box: dict[str, float], rel_x: float = 0.5, rel_y: float = 0.5) -> tuple[float, float]:
    return box["x"] + box["width"] * rel_x, box["y"] + box["height"] * rel_y


def clean_standard_edge_points(edge_id: str, boxes: dict[str, dict[str, float]]) -> list[tuple[float, float]]:
    base_required = {
        "node_start",
        "node_step1",
        "node_step2",
        "node_step3",
        "node_step4",
        "node_decision",
        "node_no_data",
        "node_has_data",
        "node_step7",
        "node_end",
    }
    has_step6 = "node_step6" in boxes
    required = set(base_required)
    if has_step6:
        required.add("node_step6")
    if not required.issubset(boxes):
        return []

    start = boxes["node_start"]
    step1 = boxes["node_step1"]
    step2 = boxes["node_step2"]
    step3 = boxes["node_step3"]
    step4 = boxes["node_step4"]
    decision = boxes["node_decision"]
    no_data = boxes["node_no_data"]
    has_data = boxes["node_has_data"]
    step6 = boxes.get("node_step6")
    step7 = boxes["node_step7"]
    end = boxes["node_end"]

    if "node_step5" in boxes and step6 is not None:
        step5 = boxes["node_step5"]
        routes: dict[str, list[tuple[float, float]]] = {
            "edge_start_step1": [center(start, 0.5, 1), center(step1, 0.5, 0)],
            "edge_step1_step2": [
                center(step1, 1, 0.5),
                ((center(step1, 1, 0.5)[0] + center(step2, 0, 0.5)[0]) / 2, center(step1, 1, 0.5)[1]),
                ((center(step1, 1, 0.5)[0] + center(step2, 0, 0.5)[0]) / 2, center(step2, 0, 0.5)[1]),
                center(step2, 0, 0.5),
            ],
            "edge_step2_step3": [
                center(step2, 0.5, 1),
                (center(step2)[0], step2["y"] + step2["height"] + 35),
                (center(step3)[0], step2["y"] + step2["height"] + 35),
                center(step3, 0.5, 0),
            ],
            "edge_step3_step4": [
                center(step3, 1, 0.5),
                center(step4, 0, 0.5),
            ],
            "edge_step4_step5": [
                center(step4, 0.5, 1),
                (center(step4)[0], step4["y"] + step4["height"] + 45),
                (center(step5)[0], step4["y"] + step4["height"] + 45),
                center(step5, 0.5, 0),
            ],
            "edge_step5_decision": [
                center(step5, 1, 0.5),
                ((center(step5, 1, 0.5)[0] + center(decision, 0, 0.5)[0]) / 2, center(step5, 1, 0.5)[1]),
                ((center(step5, 1, 0.5)[0] + center(decision, 0, 0.5)[0]) / 2, center(decision, 0, 0.5)[1]),
                center(decision, 0, 0.5),
            ],
            "edge_decision_no_data": [
                center(decision, 0.25, 1),
                (center(no_data)[0], decision["y"] + decision["height"] + 35),
                center(no_data, 0.5, 0),
            ],
            "edge_decision_has_data": [
                center(decision, 0.75, 1),
                (center(has_data)[0], decision["y"] + decision["height"] + 35),
                center(has_data, 0.5, 0),
            ],
            "edge_no_data_end": [
                center(no_data, 0.5, 1),
                (center(no_data)[0], max(no_data["y"] + no_data["height"], has_data["y"] + has_data["height"]) + 18),
                (max(has_data["x"] + has_data["width"], step7["x"] + step7["width"]) + 20, max(no_data["y"] + no_data["height"], has_data["y"] + has_data["height"]) + 18),
                (max(has_data["x"] + has_data["width"], step7["x"] + step7["width"]) + 20, center(end, 1, 0.5)[1]),
                center(end, 1, 0.5),
            ],
            "edge_has_data_step6": [
                center(has_data, 0.5, 1),
                (center(has_data)[0], center(step6, 1, 0.5)[1]),
                center(step6, 1, 0.5),
            ],
            "edge_step6_step7": [
                center(step6, 0.5, 1),
                (center(step6)[0], center(step7, 0, 0.5)[1]),
                center(step7, 0, 0.5),
            ],
            "edge_step7_end": [center(step7, 0.5, 1), center(end, 0.5, 0)],
        }
        return routes.get(edge_id, [])

    routes: dict[str, list[tuple[float, float]]] = {
        "edge_start_step1": [center(start, 0.5, 1), center(step1, 0.5, 0)],
        "edge_step1_step2": [
            center(step1, 1, 0.5),
            ((center(step1, 1, 0.5)[0] + center(step2, 0, 0.5)[0]) / 2, center(step1, 1, 0.5)[1]),
            ((center(step1, 1, 0.5)[0] + center(step2, 0, 0.5)[0]) / 2, center(step2, 0, 0.5)[1]),
            center(step2, 0, 0.5),
        ],
        "edge_step2_step3": [
            center(step2, 0.5, 1),
            (center(step2)[0], step2["y"] + step2["height"] + 30),
            (center(step3)[0], step2["y"] + step2["height"] + 30),
            center(step3, 0.5, 0),
        ],
        "edge_step3_step4": [center(step3, 0.5, 1), center(step4, 0.5, 0)],
        "edge_step4_decision": [
            center(step4, 1, 0.5),
            ((center(step4, 1, 0.5)[0] + center(decision, 0, 0.5)[0]) / 2, center(step4, 1, 0.5)[1]),
            ((center(step4, 1, 0.5)[0] + center(decision, 0, 0.5)[0]) / 2, center(decision, 0, 0.5)[1]),
            center(decision, 0, 0.5),
        ],
        "edge_decision_no_data": [
            center(decision, 0.25, 1),
            (center(no_data)[0], decision["y"] + decision["height"] + 35),
            center(no_data, 0.5, 0),
        ],
        "edge_decision_has_data": [
            center(decision, 0.75, 1),
            (center(has_data)[0], decision["y"] + decision["height"] + 85),
            center(has_data, 0.5, 0),
        ],
        "edge_no_data_end": [
            center(no_data, 0.5, 1),
            (center(no_data)[0], center(end)[1]),
            center(end, 0, 0.5),
        ],
        "edge_step7_end": [center(step7, 0.5, 1), center(end, 0.5, 0)],
    }
    if has_step6 and step6 is not None:
        routes.update(
            {
                "edge_has_data_step6": [center(has_data, 0, 0.5), center(step6, 1, 0.5)],
                "edge_step6_step7": [center(step6, 1, 0.5), (470, center(step6, 1, 0.5)[1]), (470, center(step7, 0, 0.5)[1]), center(step7, 0, 0.5)],
            }
        )
    else:
        routes["edge_has_data_step7"] = [
            center(has_data, 0.5, 1),
            (center(step7)[0], has_data["y"] + has_data["height"] + 40),
            center(step7, 0.5, 0),
        ]
    return routes.get(edge_id, [])


def edge_points(edge, boxes: dict[str, dict[str, float]]) -> list[tuple[float, float]]:
    standard_points = clean_standard_edge_points(edge.get("id", ""), boxes)
    if standard_points:
        return standard_points

    source = edge.get("source")
    target = edge.get("target")
    if source not in boxes or target not in boxes:
        return []

    style = style_map(edge.get("style", ""))
    source_point = port(boxes[source], style, "exit", (0.5, 0.5))
    target_point = port(boxes[target], style, "entry", (0.5, 0.5))
    offset_x, offset_y = parent_offset(edge, boxes)
    points = [
        (offset_x + float(item.get("x") or 0), offset_y + float(item.get("y") or 0))
        for item in edge.findall(".//mxPoint")
    ]
    if points:
        return [source_point, *points, target_point]

    source_exit_x = float(style.get("exitX", 0.5))
    target_entry_x = float(style.get("entryX", 0.5))
    if abs(source_point[0] - target_point[0]) < 2 or abs(source_point[1] - target_point[1]) < 2:
        return [source_point, target_point]
    if source_exit_x in {0.0, 1.0} or target_entry_x in {0.0, 1.0}:
        mid_x = (source_point[0] + target_point[0]) / 2
        return [source_point, (mid_x, source_point[1]), (mid_x, target_point[1]), target_point]
    mid_y = (source_point[1] + target_point[1]) / 2
    return [source_point, (source_point[0], mid_y), (target_point[0], mid_y), target_point]


def xml_text(value: str) -> str:
    return html.escape(str(value or ""), quote=True)


def text_block(value: str, x: float, y: float, width: float, height: float, size: int = 12, bold: bool = False) -> str:
    weight = "700" if bold else "400"
    return (
        f'<foreignObject x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}">'
        f'<div xmlns="http://www.w3.org/1999/xhtml" style="width:100%;height:100%;'
        f"display:flex;align-items:center;justify-content:center;text-align:center;"
        f"font-family:Arial,'Times New Roman',sans-serif;font-size:{size}px;font-weight:{weight};"
        f'line-height:1.25;padding:4px;box-sizing:border-box;overflow:hidden;">{xml_text(value)}</div>'
        f"</foreignObject>"
    )


def render_vertex(cell, box: dict[str, float]) -> str:
    styles = style_map(cell.get("style", ""))
    fill = styles.get("fillColor") or "#ffffff"
    stroke = styles.get("strokeColor") or "#000000"
    stroke_width = styles.get("strokeWidth") or "1"
    value = cell.get("value", "")
    shape = styles.get("shape", "")
    is_swimlane = "swimlane" in cell.get("style", "")
    is_diamond = "rhombus" in cell.get("style", "") or "diamond" in cell.get("style", "")
    is_terminator = "terminator" in shape
    x, y, width, height = box["x"], box["y"], box["width"], box["height"]

    if is_swimlane:
        start_size = float(styles.get("startSize") or 26)
        header_fill = fill
        return (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
            f'fill="#ffffff" stroke="{stroke}" stroke-width="1"/>'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{start_size:.1f}" '
            f'fill="{header_fill}" stroke="{stroke}" stroke-width="1"/>'
            + text_block(value, x, y, width, start_size, int(float(styles.get("fontSize") or 12)), "fontStyle=1" in cell.get("style", ""))
        )

    if is_terminator:
        shape_svg = (
            f'<ellipse cx="{x + width / 2:.1f}" cy="{y + height / 2:.1f}" rx="{width / 2:.1f}" ry="{height / 2:.1f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        )
    elif is_diamond:
        points = [
            (x + width / 2, y),
            (x + width, y + height / 2),
            (x + width / 2, y + height),
            (x, y + height / 2),
        ]
        point_text = " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
        shape_svg = f'<polygon points="{point_text}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
    else:
        shape_svg = (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        )
    return shape_svg + text_block(value, x, y, width, height, int(float(styles.get("fontSize") or 12)))


def render_edge(edge, boxes: dict[str, dict[str, float]]) -> str:
    points = edge_points(edge, boxes)
    if len(points) < 2:
        return ""
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return (
        f'<polyline points="{path}" fill="none" stroke="#000000" stroke-width="1.2" '
        f'marker-end="url(#arrow)" stroke-linejoin="round" stroke-linecap="square"/>'
    )


def render_svg(xml_path: Path) -> tuple[str, int, int]:
    parser = etree.XMLParser(remove_blank_text=True, recover=True)
    root = etree.parse(str(xml_path), parser).getroot()
    if local_name(root.tag) != "mxfile":
        raise SystemExit(f"Cannot export PNG: {xml_path} is not a Draw.io mxfile.")
    cells = {cell.get("id"): cell for cell in root.findall(".//mxCell") if cell.get("id")}
    boxes = absolute_boxes(cells)
    vertices = [cell for cell in root.findall(".//mxCell") if cell.get("vertex") == "1"]
    edges = [cell for cell in root.findall(".//mxCell") if cell.get("edge") == "1"]

    margin = 20
    min_x = min((box["x"] for box in boxes.values()), default=0) - margin
    min_y = min((box["y"] for box in boxes.values()), default=0) - margin
    max_x = max((box["x"] + box["width"] for box in boxes.values()), default=800) + margin
    max_y = max((box["y"] + box["height"] for box in boxes.values()), default=900) + margin
    width = int(max_x - min_x)
    height = int(max_y - min_y)

    grid_id = "grid"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="{min_x:.1f} {min_y:.1f} {width} {height}">',
        "<defs>",
        '<pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse">'
        '<path d="M 10 0 L 0 0 0 10" fill="none" stroke="#e6e6e6" stroke-width="0.8"/></pattern>',
        '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#000000"/></marker>',
        "</defs>",
        f'<rect x="{min_x:.1f}" y="{min_y:.1f}" width="{width}" height="{height}" fill="url(#{grid_id})"/>',
    ]
    parts.extend(render_vertex(cell, boxes[cell.get("id")]) for cell in vertices if cell.get("id") in boxes)
    parts.extend(render_edge(edge, boxes) for edge in edges)
    parts.append("</svg>")
    return "\n".join(parts), width, height


def export_png(xml_path: Path, output_png: Path) -> None:
    svg, width, height = render_svg(xml_path)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    html_path = output_png.with_suffix(".render.html")
    html_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;padding:0;background:white;overflow:hidden}</style>"
        f"</head><body>{svg}</body></html>",
        encoding="utf-8",
    )
    browser = find_browser()
    try:
        subprocess.run(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                f"--window-size={width},{height}",
                f"--screenshot={output_png}",
                html_path.resolve().as_uri(),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    finally:
        try:
            html_path.unlink()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a Draw.io XML file to PNG.")
    parser.add_argument("--xml", required=True, help="Input Draw.io XML path.")
    parser.add_argument("--out", required=True, help="Output PNG path.")
    args = parser.parse_args(argv)

    xml_path = require_file(resolve_path(args.xml, Path.cwd()), "Draw.io XML")
    output_png = resolve_path(args.out, Path.cwd())
    export_png(xml_path, output_png)
    print(f"png: {output_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
