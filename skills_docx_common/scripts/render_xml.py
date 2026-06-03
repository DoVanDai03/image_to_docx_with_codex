import argparse
import re
import sys
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

from lxml import etree

from common import (
    DEFAULT_SRC_COMMON,
    get_common_paths,
    load_json,
    normalize_workflow,
    require_file,
    resolve_path,
    slugify,
)


CONTAINER_ID = "container"
USER_LANE_ID = "lane_user"
SYSTEM_LANE_ID = "lane_system"
CONTAINER_WIDTH = 620
LANE_HEADER_Y = 30
USER_LANE_WIDTH = 330
SYSTEM_LANE_WIDTH = 290
STANDARD_CONTAINER_WIDTH = 800
STANDARD_CONTAINER_HEIGHT = 1020
STANDARD_TITLE_HEIGHT = 26
STANDARD_LANE_WIDTH = 400
USER_LANE_X = 0
SYSTEM_LANE_X = USER_LANE_WIDTH


def local_name(tag: str) -> str:
    return etree.QName(tag).localname if tag else ""


def cell(container, **attrs):
    return etree.SubElement(container, "mxCell", **{k: str(v) for k, v in attrs.items() if v is not None})


def geometry(container, **attrs):
    return etree.SubElement(container, "mxGeometry", **{k: str(v) for k, v in attrs.items() if v is not None})


def add_vertex(root, cell_id: str | int, parent: str, value: str, style: str, x: int, y: int, width: int, height: int):
    node = cell(root, id=cell_id, parent=parent, value=value, style=style, vertex="1")
    geometry(node, x=x, y=y, width=width, height=height, as_="geometry")
    node[0].attrib["as"] = node[0].attrib.pop("as_")
    return str(cell_id)


def add_edge(
    root,
    cell_id: str | int,
    source: str,
    target: str,
    label: str = "",
    parent: str = CONTAINER_ID,
    style: str | None = None,
    points: list[tuple[int, int]] | None = None,
):
    edge = cell(
        root,
        id=cell_id,
        edge="1",
        parent=parent,
        source=source,
        target=target,
        value=label,
        style=style
        or (
            "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;"
            "html=1;endArrow=block;strokeColor=#000000;fontSize=11;"
        ),
    )
    geom = geometry(edge, relative="1", as_="geometry")
    geom.attrib["as"] = geom.attrib.pop("as_")
    if points:
        point_array = etree.SubElement(geom, "Array", as_="points")
        point_array.attrib["as"] = point_array.attrib.pop("as_")
        for x, y in points:
            etree.SubElement(point_array, "mxPoint", x=str(x), y=str(y))


def prefixed_value(prefix: str, value: str) -> str:
    text = str(value or "UNKNOWN").strip()
    if re.match(r"^(?:\d+(?:\.\d+)?|A\d+)\.\s", text):
        return text
    return f"{prefix} {text}"


def without_number_prefix(value: str) -> str:
    return re.sub(r"^\s*(?:\d+(?:\.\d+)?|A\d+)\.\s*", "", str(value or "")).strip()


def compact_text(value: str, limit: int = 95) -> str:
    text = re.sub(r"\s+", " ", str(value or "UNKNOWN")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def button_label(workflow: dict, keyword: str, fallback: str) -> str:
    keyword = keyword.lower()
    for item in workflow.get("buttons", []):
        label = str(item.get("label", "")).strip()
        if keyword in label.lower():
            return label
    return fallback


def export_button_text(workflow: dict) -> str:
    labels = [
        str(item.get("label", "")).strip()
        for item in workflow.get("buttons", [])
        if "xuất" in str(item.get("label", "")).lower()
    ]
    labels = [label for label in labels if label]
    if not labels:
        return "Xuất file"
    return " / ".join(labels)


def table_label(workflow: dict) -> str:
    tables = workflow.get("tables", [])
    if tables and isinstance(tables[0], dict):
        name = str(tables[0].get("name", "")).strip()
        if name:
            return name
    return "bảng báo cáo"


def safe_id(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "node")).strip("_")
    return text or "node"


def create_mxfile(template_root, workflow: dict, page_height: int):
    mxfile = etree.Element("mxfile", **dict(template_root.attrib))
    diagram = etree.SubElement(mxfile, "diagram", name="Page-1", id=workflow["id"])
    model = etree.SubElement(
        diagram,
        "mxGraphModel",
        dx="1200",
        dy="800",
        grid="1",
        gridSize="10",
        guides="1",
        tooltips="1",
        connect="1",
        arrows="1",
        fold="1",
        page="1",
        pageScale="1",
        pageWidth="850",
        pageHeight=str(page_height),
        math="0",
        shadow="0",
    )
    root = etree.SubElement(model, "root")
    cell(root, id="0")
    cell(root, id="1", parent="0")
    return mxfile, model, root


def node_text(node: dict) -> str:
    return str(node.get("label") or node.get("name") or "UNKNOWN").strip()


def node_kind(node: dict) -> str:
    kind = str(node.get("type") or "").strip().lower()
    shape = str(node.get("shape") or "").strip().lower()
    if kind in {"start", "end", "decision"}:
        return kind
    if shape in {"oval", "ellipse"}:
        return "end" if "end" in str(node.get("id", "")).lower() else "start"
    if shape in {"diamond", "rhombus"}:
        return "decision"
    return "process"


def lane_key(node: dict) -> str:
    lane = str(node.get("lane") or "").strip().lower()
    if lane in {"system", "he-thong", "he_thong"}:
        return "system"
    if lane in {"user", "actor", "nguoi-dung", "nguoi_su_dung"}:
        return "user"
    return "system" if node_kind(node) in {"decision", "end"} else "user"


def lane_parent_id(lane: str) -> str:
    return SYSTEM_LANE_ID if lane == "system" else USER_LANE_ID


def lane_origin_x(lane: str) -> int:
    return SYSTEM_LANE_X if lane == "system" else USER_LANE_X


def lane_relative_box(node: dict, box: dict) -> dict:
    lane = lane_key(node)
    return {
        "x": box["x"] - lane_origin_x(lane),
        "y": box["y"],
        "width": box["width"],
        "height": box["height"],
    }


def label_number(node: dict) -> tuple[int | None, int | None]:
    match = re.match(r"\s*(\d+)(?:\.(\d+))?\.", node_text(node))
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2) or 0)


def graph_ranks(nodes: list[dict]) -> dict[str, float]:
    ranks: dict[str, float] = {}
    last_numeric = 0.0
    deferred_end: list[str] = []

    for index, node in enumerate(nodes, start=1):
        node_id = str(node.get("id") or f"node{index}")
        kind = node_kind(node)
        number, _ = label_number(node)

        if kind == "start":
            ranks[node_id] = 0.0
            continue
        if kind == "end":
            deferred_end.append(node_id)
            continue
        if number is not None:
            ranks[node_id] = float((number + 1) // 2)
            last_numeric = ranks[node_id]
            continue
        if kind == "decision":
            ranks[node_id] = last_numeric + 0.55
            continue

        last_numeric += 1.0
        ranks[node_id] = last_numeric

    end_rank = (max(ranks.values()) if ranks else 0.0) + 1.0
    for node_id in deferred_end:
        ranks[node_id] = end_rank
    return ranks


def node_size(node: dict, group_size: int = 1) -> tuple[int, int]:
    kind = node_kind(node)
    if kind in {"start", "end"}:
        return 105, 50
    if kind == "decision":
        return 125, 90
    width = 180 if group_size > 1 and lane_key(node) == "system" else 235
    height = 50 if len(node_text(node)) <= 85 else 70
    return width, height


def graph_layout(nodes: list[dict]) -> tuple[dict[str, dict], int]:
    ranks = graph_ranks(nodes)
    groups: dict[tuple[str, float], list[dict]] = defaultdict(list)
    for node in nodes:
        node_id = str(node.get("id") or "")
        if node_kind(node) == "process":
            groups[(lane_key(node), ranks.get(node_id, 0.0))].append(node)

    layout: dict[str, dict] = {}
    max_bottom = 0

    for index, node in enumerate(nodes, start=1):
        node_id = str(node.get("id") or f"node{index}")
        lane = lane_key(node)
        rank = ranks.get(node_id, float(index))
        group = groups.get((lane, rank), [])
        width, height = node_size(node, len(group))

        lane_x = SYSTEM_LANE_X if lane == "system" else USER_LANE_X
        lane_width = SYSTEM_LANE_WIDTH if lane == "system" else USER_LANE_WIDTH
        y = int(node.get("y", 50 + rank * 95))

        if "x" in node:
            x = int(node["x"])
        elif node_kind(node) == "decision":
            x = lane_x + (lane_width - width) // 2 - 8
        elif len(group) > 1 and lane == "system":
            _, sub_number = label_number(node)
            if sub_number == 1:
                x = lane_x + lane_width - width - 28
            elif sub_number == 2:
                x = lane_x + 28
            else:
                slot = group.index(node)
                x = lane_x + 28 + slot * (width + 18)
        elif len(group) > 1:
            slot = group.index(node)
            x = lane_x + (lane_width - width) // 2
            y += slot * (height + 18)
        else:
            x = lane_x + (lane_width - width) // 2

        if "width" in node:
            width = int(node["width"])
        if "height" in node:
            height = int(node["height"])

        layout[node_id] = {"x": x, "y": y, "width": width, "height": height}
        max_bottom = max(max_bottom, y + height)

    return layout, max(440, max_bottom + 50)


def graph_node_style(node: dict) -> str:
    kind = node_kind(node)
    if kind in {"start", "end"}:
        return "strokeWidth=1;html=1;shape=mxgraph.flowchart.terminator;whiteSpace=wrap;fontSize=12;"
    if kind == "decision":
        return "rhombus;whiteSpace=wrap;html=1;strokeWidth=1;spacing=6;fontSize=11;"
    return "rounded=0;whiteSpace=wrap;html=1;strokeWidth=1;spacing=8;fontSize=12;"


def render_graph_drawio_xml(template_root, workflow: dict) -> etree._ElementTree:
    nodes = list(workflow.get("nodes", []))
    edges = list(workflow.get("edges", []))
    layout, container_height = graph_layout(nodes)
    mxfile, model, root = create_mxfile(template_root, workflow, max(1100, container_height + 160))

    title_style = "swimlane;childLayout=stackLayout;resizeParent=1;resizeParentMax=0;startSize=30;fontSize=14;fillColor=#ffe6cc;strokeColor=#d79b00;"
    lane_style = "swimlane;startSize=20;fillColor=#d5e8d4;strokeColor=#82b366;"
    title = workflow.get("diagram_title") or workflow.get("title") or workflow["name"]
    lanes = workflow.get("lanes", {})

    add_vertex(root, CONTAINER_ID, "1", title, title_style, 40, 40, CONTAINER_WIDTH, container_height)
    add_vertex(root, USER_LANE_ID, CONTAINER_ID, lanes.get("user", "Người sử dụng"), lane_style, USER_LANE_X, LANE_HEADER_Y, USER_LANE_WIDTH, container_height - LANE_HEADER_Y)
    add_vertex(root, SYSTEM_LANE_ID, CONTAINER_ID, lanes.get("system", "Hệ thống"), lane_style, SYSTEM_LANE_X, LANE_HEADER_Y, SYSTEM_LANE_WIDTH, container_height - LANE_HEADER_Y)

    id_map: dict[str, str] = {}
    node_by_id: dict[str, dict] = {}
    for index, node in enumerate(nodes, start=1):
        source_id = str(node.get("id") or f"node{index}")
        cell_id = f"node_{safe_id(source_id)}"
        id_map[source_id] = cell_id
        node_by_id[source_id] = node
        box = lane_relative_box(node, layout[source_id])
        lane = lane_key(node)
        add_vertex(
            root,
            cell_id,
            lane_parent_id(lane),
            node_text(node),
            graph_node_style(node),
            box["x"],
            box["y"],
            box["width"],
            box["height"],
        )

    for index, edge in enumerate(edges, start=1):
        source = str(edge.get("from") or edge.get("source") or "")
        target = str(edge.get("to") or edge.get("target") or "")
        if source not in id_map or target not in id_map:
            continue
        edge_id = f"edge_{index}_{safe_id(source)}_{safe_id(target)}"
        source_lane = lane_key(node_by_id[source])
        target_lane = lane_key(node_by_id[target])
        parent = lane_parent_id(source_lane) if source_lane == target_lane else CONTAINER_ID
        add_edge(root, edge_id, id_map[source], id_map[target], str(edge.get("label") or ""), parent=parent)

    model.attrib["pageHeight"] = str(max(1100, container_height + 120))
    return etree.ElementTree(mxfile)


def render_flow_drawio_xml(template_root, workflow: dict) -> etree._ElementTree:
    flow = list(workflow.get("basic_flow", []))
    container_height = max(440, 240 + len(flow) * 100)
    mxfile, model, root = create_mxfile(template_root, workflow, max(1100, container_height + 160))
    title_style = "swimlane;childLayout=stackLayout;resizeParent=1;resizeParentMax=0;startSize=30;fontSize=14;fillColor=#ffe6cc;strokeColor=#d79b00;"
    lane_style = "swimlane;startSize=20;fillColor=#d5e8d4;strokeColor=#82b366;"
    node_style = "rounded=0;whiteSpace=wrap;html=1;strokeWidth=1;fontSize=12;"
    end_style = "strokeWidth=1;html=1;shape=mxgraph.flowchart.terminator;whiteSpace=wrap;fontSize=12;"
    lanes = workflow.get("lanes", {})

    add_vertex(root, CONTAINER_ID, "1", workflow["name"], title_style, 40, 40, CONTAINER_WIDTH, container_height)
    add_vertex(root, USER_LANE_ID, CONTAINER_ID, lanes.get("user", "Người sử dụng"), lane_style, USER_LANE_X, LANE_HEADER_Y, USER_LANE_WIDTH, container_height - LANE_HEADER_Y)
    add_vertex(root, SYSTEM_LANE_ID, CONTAINER_ID, lanes.get("system", "Hệ thống"), lane_style, SYSTEM_LANE_X, LANE_HEADER_Y, SYSTEM_LANE_WIDTH, container_height - LANE_HEADER_Y)
    add_vertex(root, "node_start", USER_LANE_ID, "Bắt đầu", end_style, 112, 50, 105, 50)

    next_id = 1
    previous = "node_start"
    y = 140
    for index, step in enumerate(flow, start=1):
        actor_id = f"node_actor_{index}"
        system_id = f"node_system_{index}"
        actor_value = prefixed_value(f"{index * 2 - 1}.", step.get("actor", "UNKNOWN"))
        system_value = prefixed_value(f"{index * 2}.", step.get("system", "UNKNOWN"))
        add_vertex(root, actor_id, USER_LANE_ID, actor_value, node_style, 47, y, 235, 50)
        add_vertex(root, system_id, SYSTEM_LANE_ID, system_value, node_style, 27, y, 235, 50)
        parent = USER_LANE_ID if previous == "node_start" else CONTAINER_ID
        add_edge(root, f"edge_auto_{next_id}", previous, actor_id, parent=parent)
        next_id += 1
        add_edge(root, f"edge_auto_{next_id}", actor_id, system_id, parent=CONTAINER_ID)
        next_id += 1
        previous = system_id
        y += 100

    end_id = "node_end"
    add_vertex(root, end_id, SYSTEM_LANE_ID, "Kết thúc", end_style, 92, y, 105, 50)
    add_edge(root, f"edge_auto_{next_id}", previous, end_id, parent=SYSTEM_LANE_ID)
    return etree.ElementTree(mxfile)


def standard_labels(workflow: dict) -> dict[str, str]:
    report_label = button_label(workflow, "báo cáo", "Báo cáo")
    name = workflow["name"]
    labels = {
        "title": workflow.get("diagram_title") or workflow.get("title") or name,
        "start": "Bắt đầu",
        "step1": compact_text(f"1. Mở màn hình {name}", 80),
        "step2": compact_text(f"2. Hiển thị màn hình {name}", 80),
        "step3": "3. Chọn thao tác",
        "step4": compact_text(f"4. Nhấn nút {report_label}", 70),
        "step5": "5. Nhập hoặc xác nhận thông tin",
        "decision": "Dữ liệu hợp lệ?",
        "no_data": "5.2. Thông báo lỗi",
        "has_data": "5.1. Cập nhật dữ liệu",
        "step6": "6. Xem kết quả",
        "step7": "7. Hiển thị kết quả",
        "step8": "",
        "step9": "",
        "step10": "",
        "end": "Kết thúc",
    }
    labels.update({k: v for k, v in dict(workflow.get("diagram_steps") or {}).items() if v})
    return labels


def add_standard_vertex(root, cell_id: str, parent: str, value: str, x: int, y: int, width: int, height: int, *, kind: str = "process"):
    base = "whiteSpace=wrap;html=1;strokeColor=#000000;fontSize=12;align=center;verticalAlign=middle;"
    if kind == "terminator":
        style = base + "strokeWidth=2;shape=mxgraph.flowchart.terminator;fillColor=#ffffff;"
    elif kind == "decision":
        style = base + "strokeWidth=1;rhombus;spacing=6;fillColor=#ffffff;"
    else:
        style = base + "rounded=0;strokeWidth=1;spacing=6;fillColor=#ffffff;"
    return add_vertex(root, cell_id, parent, value, style, x, y, width, height)


def render_basic_flow_mapping_drawio_xml(template_root, workflow: dict) -> etree._ElementTree:
    labels = standard_labels(workflow)
    mxfile, model, root = create_mxfile(template_root, workflow, 1100)
    model.attrib["dx"] = "1114"
    model.attrib["dy"] = "639"

    title_style = (
        "swimlane;childLayout=stackLayout;resizeParent=1;resizeParentMax=0;"
        "startSize=26;fontSize=14;fontStyle=1;align=center;html=1;"
        "fillColor=#dae8fc;swimlaneFillColor=none;strokeColor=#6c8ebf;"
    )
    lane_style = (
        "swimlane;startSize=26;fontSize=12;fontStyle=1;align=center;html=1;"
        "fillColor=#fff2cc;swimlaneFillColor=none;strokeColor=#d6b656;"
    )
    edge_style = (
        "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;"
        "html=1;endArrow=block;strokeColor=#000000;fontSize=11;strokeWidth=1;"
    )

    container_height = 980
    lanes = workflow.get("lanes", {})
    add_vertex(root, CONTAINER_ID, "1", labels["title"], title_style, 10, 10, STANDARD_CONTAINER_WIDTH, container_height)
    add_vertex(root, USER_LANE_ID, CONTAINER_ID, lanes.get("user", "Người sử dụng"), lane_style, 0, STANDARD_TITLE_HEIGHT, STANDARD_LANE_WIDTH, container_height - STANDARD_TITLE_HEIGHT)
    add_vertex(root, SYSTEM_LANE_ID, CONTAINER_ID, lanes.get("system", "Hệ thống"), lane_style, STANDARD_LANE_WIDTH, STANDARD_TITLE_HEIGHT, STANDARD_LANE_WIDTH, container_height - STANDARD_TITLE_HEIGHT)

    add_standard_vertex(root, "node_start", USER_LANE_ID, labels["start"], 115, 55, 105, 50, kind="terminator")
    add_standard_vertex(root, "node_step1", USER_LANE_ID, labels["step1"], 55, 145, 230, 55)
    add_standard_vertex(root, "node_step3", USER_LANE_ID, labels["step3"], 55, 295, 230, 55)
    add_standard_vertex(root, "node_step5", USER_LANE_ID, labels["step5"], 55, 435, 230, 55)
    add_standard_vertex(root, "node_step6", USER_LANE_ID, labels["step6"], 85, 670, 230, 55)

    add_standard_vertex(root, "node_step2", SYSTEM_LANE_ID, labels["step2"], 55, 170, 240, 55)
    add_standard_vertex(root, "node_step4", SYSTEM_LANE_ID, labels["step4"], 55, 295, 240, 55)
    add_standard_vertex(root, "node_decision", SYSTEM_LANE_ID, labels["decision"], 140, 465, 115, 90, kind="decision")
    add_standard_vertex(root, "node_no_data", SYSTEM_LANE_ID, labels["no_data"], 25, 615, 175, 55)
    add_standard_vertex(root, "node_has_data", SYSTEM_LANE_ID, labels["has_data"], 220, 615, 165, 55)
    add_standard_vertex(root, "node_step7", SYSTEM_LANE_ID, labels["step7"], 85, 760, 230, 55)
    add_standard_vertex(root, "node_end", SYSTEM_LANE_ID, labels["end"], 148, 875, 105, 50, kind="terminator")

    down_style = edge_style + "exitX=0.5;exitY=1;entryX=0.5;entryY=0;exitDx=0;exitDy=0;entryDx=0;entryDy=0;"
    right_style = edge_style + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;exitDx=0;exitDy=0;entryDx=0;entryDy=0;"
    left_style = edge_style + "exitX=0;exitY=0.5;entryX=1;entryY=0.5;exitDx=0;exitDy=0;entryDx=0;entryDy=0;"
    branch_left_style = edge_style + "exitX=0.25;exitY=1;entryX=0.5;entryY=0;exitDx=0;exitDy=0;entryDx=0;entryDy=0;"
    branch_right_style = edge_style + "exitX=0.75;exitY=1;entryX=0.5;entryY=0;exitDx=0;exitDy=0;entryDx=0;entryDy=0;"
    no_data_end_style = edge_style + "exitX=0.5;exitY=1;entryX=1;entryY=0.5;exitDx=0;exitDy=0;entryDx=0;entryDy=0;"

    add_edge(root, "edge_start_step1", "node_start", "node_step1", parent=USER_LANE_ID, style=down_style)
    add_edge(root, "edge_step1_step2", "node_step1", "node_step2", parent=CONTAINER_ID, style=right_style)
    add_edge(root, "edge_step2_step3", "node_step2", "node_step3", parent=CONTAINER_ID, style=down_style, points=[(575, 285), (170, 285)])
    add_edge(root, "edge_step3_step4", "node_step3", "node_step4", parent=CONTAINER_ID, style=right_style)
    add_edge(root, "edge_step4_step5", "node_step4", "node_step5", parent=CONTAINER_ID, style=down_style, points=[(575, 420), (170, 420)])
    add_edge(root, "edge_step5_decision", "node_step5", "node_decision", parent=CONTAINER_ID, style=right_style, points=[(410, 489), (410, 536)])
    add_edge(root, "edge_decision_no_data", "node_decision", "node_no_data", parent=SYSTEM_LANE_ID, style=branch_left_style)
    add_edge(root, "edge_decision_has_data", "node_decision", "node_has_data", parent=SYSTEM_LANE_ID, style=branch_right_style)
    add_edge(root, "edge_no_data_end", "node_no_data", "node_end", parent=SYSTEM_LANE_ID, style=no_data_end_style, points=[(112, 690), (390, 690), (390, 900)])
    add_edge(root, "edge_has_data_step6", "node_has_data", "node_step6", parent=CONTAINER_ID, style=left_style, points=[(703, 724)])
    add_edge(root, "edge_step6_step7", "node_step6", "node_step7", parent=CONTAINER_ID, style=down_style, points=[(200, 814)])
    add_edge(root, "edge_step7_end", "node_step7", "node_end", parent=SYSTEM_LANE_ID, style=down_style)
    return etree.ElementTree(mxfile)


def render_standard_drawio_xml(template_root, workflow: dict) -> etree._ElementTree:
    if bool(dict(workflow.get("diagram_steps") or {}).get("full_mapping")):
        return render_basic_flow_mapping_drawio_xml(template_root, workflow)

    labels = standard_labels(workflow)
    skip_step6 = bool(dict(workflow.get("diagram_steps") or {}).get("skip_step6"))
    mxfile, model, root = create_mxfile(template_root, workflow, 1100)
    model.attrib["dx"] = "1114"
    model.attrib["dy"] = "639"

    title_style = (
        "swimlane;childLayout=stackLayout;resizeParent=1;resizeParentMax=0;"
        "startSize=26;fontSize=14;fontStyle=1;align=center;html=1;"
        "fillColor=#dae8fc;swimlaneFillColor=none;strokeColor=#6c8ebf;"
    )
    lane_style = (
        "swimlane;startSize=26;fontSize=12;fontStyle=1;align=center;html=1;"
        "fillColor=#fff2cc;swimlaneFillColor=none;strokeColor=#d6b656;"
    )
    edge_style = (
        "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;"
        "html=1;endArrow=block;strokeColor=#000000;fontSize=11;strokeWidth=1;"
    )

    container_height = 930
    add_vertex(root, CONTAINER_ID, "1", labels["title"], title_style, 10, 10, STANDARD_CONTAINER_WIDTH, container_height)
    add_vertex(root, USER_LANE_ID, CONTAINER_ID, "Người sử dụng", lane_style, 0, STANDARD_TITLE_HEIGHT, STANDARD_LANE_WIDTH, container_height - STANDARD_TITLE_HEIGHT)
    add_vertex(root, SYSTEM_LANE_ID, CONTAINER_ID, "Hệ thống", lane_style, STANDARD_LANE_WIDTH, STANDARD_TITLE_HEIGHT, STANDARD_LANE_WIDTH, container_height - STANDARD_TITLE_HEIGHT)

    add_standard_vertex(root, "node_start", USER_LANE_ID, labels["start"], 115, 55, 105, 50, kind="terminator")
    add_standard_vertex(root, "node_step1", USER_LANE_ID, labels["step1"], 55, 145, 230, 55)
    add_standard_vertex(root, "node_step3", USER_LANE_ID, labels["step3"], 55, 285, 230, 55)
    add_standard_vertex(root, "node_step4", USER_LANE_ID, labels["step4"], 55, 385, 230, 55)
    if not skip_step6:
        add_standard_vertex(root, "node_step6", USER_LANE_ID, labels["step6"], 135, 630, 210, 55)

    add_standard_vertex(root, "node_step2", SYSTEM_LANE_ID, labels["step2"], 55, 170, 240, 55)
    add_standard_vertex(root, "node_decision", SYSTEM_LANE_ID, labels["decision"], 140, 360, 115, 90, kind="decision")
    add_standard_vertex(root, "node_no_data", SYSTEM_LANE_ID, labels["no_data"], 25, 535, 175, 55)
    if skip_step6:
        add_standard_vertex(root, "node_has_data", SYSTEM_LANE_ID, labels["has_data"], 220, 535, 165, 55)
        add_standard_vertex(root, "node_step7", SYSTEM_LANE_ID, labels["step7"], 165, 660, 210, 55)
        add_standard_vertex(root, "node_end", SYSTEM_LANE_ID, labels["end"], 218, 790, 105, 50, kind="terminator")
    else:
        add_standard_vertex(root, "node_has_data", SYSTEM_LANE_ID, labels["has_data"], 220, 630, 165, 55)
        add_standard_vertex(root, "node_step7", SYSTEM_LANE_ID, labels["step7"], 70, 715, 210, 55)
        add_standard_vertex(root, "node_end", SYSTEM_LANE_ID, labels["end"], 122, 840, 105, 50, kind="terminator")

    down_style = edge_style + "exitX=0.5;exitY=1;entryX=0.5;entryY=0;exitDx=0;exitDy=0;entryDx=0;entryDy=0;"
    right_style = edge_style + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;exitDx=0;exitDy=0;entryDx=0;entryDy=0;"
    left_style = edge_style + "exitX=0;exitY=0.5;entryX=1;entryY=0.5;exitDx=0;exitDy=0;entryDx=0;entryDy=0;"
    back_style = edge_style + "exitX=0.5;exitY=1;entryX=0.5;entryY=0;exitDx=0;exitDy=0;entryDx=0;entryDy=0;"
    branch_left_style = edge_style + "exitX=0.25;exitY=1;entryX=0.5;entryY=0;exitDx=0;exitDy=0;entryDx=0;entryDy=0;"
    branch_right_style = edge_style + "exitX=0.75;exitY=1;entryX=0.5;entryY=0;exitDx=0;exitDy=0;entryDx=0;entryDy=0;"
    no_data_end_style = edge_style + "exitX=0;exitY=0.5;entryX=0;entryY=0.5;exitDx=0;exitDy=0;entryDx=0;entryDy=0;"
    no_data_down_style = edge_style + "exitX=0.5;exitY=1;entryX=0;entryY=0.5;exitDx=0;exitDy=0;entryDx=0;entryDy=0;"
    has_data_export_style = edge_style + "exitX=0.5;exitY=1;entryX=1;entryY=0.5;exitDx=0;exitDy=0;entryDx=0;entryDy=0;"

    add_edge(root, "edge_start_step1", "node_start", "node_step1", parent=USER_LANE_ID, style=down_style)
    add_edge(root, "edge_step1_step2", "node_step1", "node_step2", parent=CONTAINER_ID, style=right_style)
    add_edge(root, "edge_step2_step3", "node_step2", "node_step3", parent=CONTAINER_ID, style=back_style, points=[(575, 255), (170, 255)])
    add_edge(root, "edge_step3_step4", "node_step3", "node_step4", parent=USER_LANE_ID, style=down_style)
    add_edge(root, "edge_step4_decision", "node_step4", "node_decision", parent=CONTAINER_ID, style=right_style)
    add_edge(root, "edge_decision_no_data", "node_decision", "node_no_data", parent=SYSTEM_LANE_ID, style=branch_left_style, points=[(110, 500)])
    add_edge(root, "edge_decision_has_data", "node_decision", "node_has_data", parent=SYSTEM_LANE_ID, style=branch_right_style, points=[(327, 500 if skip_step6 else 565)])
    if skip_step6:
        add_edge(root, "edge_no_data_end", "node_no_data", "node_end", parent=SYSTEM_LANE_ID, style=no_data_down_style, points=[(112, 815)])
    else:
        add_edge(root, "edge_no_data_end", "node_no_data", "node_end", parent=SYSTEM_LANE_ID, style=no_data_end_style, points=[(15, 562), (15, 865)])
    if skip_step6:
        add_edge(root, "edge_has_data_step7", "node_has_data", "node_step7", parent=SYSTEM_LANE_ID, style=down_style)
    else:
        add_edge(root, "edge_has_data_step6", "node_has_data", "node_step6", parent=CONTAINER_ID, style=left_style)
        add_edge(root, "edge_step6_step7", "node_step6", "node_step7", parent=CONTAINER_ID, style=right_style, points=[(470, 657)])
    add_edge(root, "edge_step7_end", "node_step7", "node_end", parent=SYSTEM_LANE_ID, style=down_style)
    return etree.ElementTree(mxfile)


def render_generic_xml(template_root, workflow: dict) -> etree._ElementTree:
    root = deepcopy(template_root)
    for child in list(root):
        root.remove(child)
    root.set("featureId", workflow["id"])
    root.set("featureName", workflow["name"])

    if workflow.get("nodes"):
        diagram = etree.SubElement(root, "diagram", title=str(workflow.get("diagram_title") or workflow["name"]))
        nodes = etree.SubElement(diagram, "nodes")
        for node in workflow.get("nodes", []):
            item = etree.SubElement(nodes, "node", id=str(node.get("id", "")), type=str(node.get("type", "")), lane=str(node.get("lane", "")))
            item.text = node_text(node)
        edges = etree.SubElement(diagram, "edges")
        for edge in workflow.get("edges", []):
            etree.SubElement(edges, "edge", source=str(edge.get("from", "")), target=str(edge.get("to", "")), label=str(edge.get("label", "")))

    basic = etree.SubElement(root, "basicFlow")
    for step in workflow.get("basic_flow", []):
        item = etree.SubElement(basic, "step", crud=str(step.get("crud", "R")))
        etree.SubElement(item, "actor").text = str(step.get("actor", "UNKNOWN"))
        etree.SubElement(item, "system").text = str(step.get("system", "UNKNOWN"))
    alternative = etree.SubElement(root, "alternativeFlow")
    for step in workflow.get("alternative_flow", []):
        item = etree.SubElement(alternative, "step", crud=str(step.get("crud", "R")))
        etree.SubElement(item, "actor").text = str(step.get("actor", "UNKNOWN"))
        etree.SubElement(item, "system").text = str(step.get("system", "UNKNOWN"))
    return etree.ElementTree(root)


def render_xml(template_xml: Path, workflow: dict, output_xml: Path) -> None:
    parser = etree.XMLParser(remove_blank_text=True, recover=True)
    template_tree = etree.parse(str(template_xml), parser)
    template_root = template_tree.getroot()
    if local_name(template_root.tag) == "mxfile":
        out_tree = render_standard_drawio_xml(template_root, workflow)
    else:
        out_tree = render_generic_xml(template_root, workflow)
    output_xml.parent.mkdir(parents=True, exist_ok=True)
    out_tree.write(str(output_xml), encoding="utf-8", xml_declaration=True, pretty_print=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render XML from common XML and workflow JSON.")
    parser.add_argument("--workflow-json", required=True)
    parser.add_argument("--xml-common", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    workflow_path = require_file(Path(args.workflow_json).resolve(), "Workflow JSON")
    workflow = normalize_workflow(load_json(workflow_path))
    default_xml = get_common_paths(DEFAULT_SRC_COMMON)["xml"]
    template_xml = require_file(resolve_path(args.xml_common, default_xml), "XML common")
    output_xml = resolve_path(args.out, Path.cwd() / workflow["id"] / f"{slugify(workflow['id'])}.xml")
    render_xml(template_xml, workflow, output_xml)
    print(f"xml: {output_xml}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
