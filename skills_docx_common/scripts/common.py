import argparse
import json
import re
import unicodedata
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC_COMMON = REPO_ROOT / "src_common"


def slugify(value: str, fallback: str = "feature") -> str:
    text = unicodedata.normalize("NFD", value or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or fallback


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def resolve_path(value: str | None, default: Path) -> Path:
    if not value:
        return default.resolve()
    return Path(value).expanduser().resolve()


def get_common_paths(src_common: Path) -> dict:
    return {
        "docx": src_common / "docx_common" / "docx_common.docx",
        "xml": src_common / "xml_common" / "xml_common.xml",
        "action": src_common / "action_common" / "action_common.md",
    }


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def node_label(node: dict) -> str:
    return str(node.get("label") or node.get("name") or "UNKNOWN").strip()


def is_user_lane(node: dict) -> bool:
    lane = str(node.get("lane", "")).strip().lower()
    return lane in {"user", "actor", "nguoi-dung", "nguoi_su_dung"}


def is_system_lane(node: dict) -> bool:
    lane = str(node.get("lane", "")).strip().lower()
    return lane in {"system", "he-thong", "he_thong"}


def is_process_node(node: dict) -> bool:
    node_type = str(node.get("type", "")).strip().lower()
    shape = str(node.get("shape", "")).strip().lower()
    return node_type in {"", "process", "task"} and shape not in {"oval", "ellipse", "diamond", "rhombus"}


def is_alternative_label(label: str) -> bool:
    normalized = slugify(label)
    return any(token in normalized for token in ("khong", "loi", "fail", "invalid", "alternative", "no-data"))


def flow_rows_from_nodes(nodes: list[dict]) -> list[dict]:
    rows: list[dict] = []
    pending_actor: list[str] = []
    for node in nodes:
        if not is_process_node(node):
            continue
        if is_user_lane(node):
            pending_actor.append(node_label(node))
            continue
        if not is_system_lane(node):
            continue
        rows.append(
            {
                "actor": "\n".join(pending_actor) if pending_actor else "",
                "system": node_label(node),
                "crud": str(node.get("crud", "R")),
            }
        )
        pending_actor = []
    return rows


def alternative_row_from_nodes(nodes: list[dict], target_node: dict) -> list[dict]:
    """Keep derived alternative tables compact like the common DOCX."""
    actor = ""
    target_index = nodes.index(target_node)
    for node in reversed(nodes[:target_index]):
        if is_process_node(node) and is_user_lane(node):
            actor = node_label(node)
            break
    return [
        {
            "actor": actor,
            "system": node_label(target_node),
            "crud": str(target_node.get("crud", "R")),
        }
    ]


def derive_flows_from_graph(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Build a usable DOCX event table from explicit diagram nodes when needed."""
    incoming_labels: dict[str, list[str]] = {}
    node_by_id = {str(node.get("id") or ""): node for node in nodes}
    for edge in edges:
        target = str(edge.get("to") or edge.get("target") or "")
        label = str(edge.get("label") or "").strip()
        if target and label:
            incoming_labels.setdefault(target, []).append(label)

    alternative_targets: list[tuple[dict, str]] = []
    basic_nodes: list[dict] = []

    for node in nodes:
        if not is_process_node(node):
            continue
        if not is_system_lane(node):
            basic_nodes.append(node)
            continue

        labels = incoming_labels.get(str(node.get("id", "")), [])
        is_alternative = any(is_alternative_label(label) for label in labels)
        if is_alternative:
            continue
        basic_nodes.append(node)

    for edge in edges:
        target_id = str(edge.get("to") or edge.get("target") or "")
        label = str(edge.get("label") or "").strip()
        target = node_by_id.get(target_id)
        if not target or not is_process_node(target) or not is_system_lane(target):
            continue
        if is_alternative_label(label):
            alternative_targets.append((target, label or node_label(target)))

    basic_flow = flow_rows_from_nodes(basic_nodes)
    alternative_flow: list[dict] = []
    alternative_flows: list[dict] = []
    for target, label in alternative_targets:
        steps = alternative_row_from_nodes(nodes, target)
        alternative_flows.append({"name": label, "steps": steps})
        alternative_flow.extend(steps)

    return basic_flow, alternative_flow, alternative_flows


def normalize_alternative_flows(value) -> list[dict]:
    flows: list[dict] = []
    for index, item in enumerate(value or [], start=1):
        if isinstance(item, dict):
            steps = list(item.get("steps") or item.get("flow") or item.get("rows") or [])
            if not steps and "actor" in item and "system" in item:
                steps = [item]
            flows.append({"name": item.get("name") or item.get("title") or f"Alternative Flow {index}", "steps": steps})
            continue
        if isinstance(item, list):
            flows.append({"name": f"Alternative Flow {index}", "steps": item})
    return flows


def normalize_workflow(data: dict, name: str | None = None, image: str | None = None) -> dict:
    title = data.get("name") or data.get("title") or name or "UNKNOWN"
    feature_id = data.get("id") or slugify(title)
    default_postconditions = (
        "Trường hợp thành công: người dùng thực hiện được chức năng. "
        "Trường hợp không thành công: hệ thống hiển thị thông báo tương ứng."
    )
    nodes = list(data.get("nodes", []))
    edges = list(data.get("edges", []))
    if nodes:
        derived_basic_flow, derived_alternative_flow, derived_alternative_flows = derive_flows_from_graph(nodes, edges)
    else:
        derived_basic_flow, derived_alternative_flow, derived_alternative_flows = [], [], []
    explicit_alternative_flows = normalize_alternative_flows(data.get("alternative_flows") or data.get("alternativeFlows"))

    workflow = {
        "id": slugify(feature_id),
        "name": title,
        "title": data.get("title") or title,
        "diagram_title": data.get("diagram_title") or data.get("diagramTitle") or data.get("title") or title,
        "section_number": data.get("section_number") or data.get("sectionNumber") or "4.1.2.3.2",
        "purpose": data.get("purpose", "UNKNOWN"),
        "actor": data.get("actor", "Người dùng hệ thống"),
        "preconditions": (
            data.get("preconditions")
            or data.get("preConditions")
            or data.get("pre_conditions")
            or "Người dùng có quyền thực hiện chức năng."
        ),
        "postconditions": (
            data.get("postconditions")
            or data.get("postConditions")
            or data.get("post_conditions")
            or default_postconditions
        ),
        "source_image": data.get("source_image") or image or "",
        "lanes": dict(data.get("lanes") or {"user": "Người sử dụng", "system": "Hệ thống"}),
        "nodes": nodes,
        "edges": edges,
        "inputs": list(data.get("inputs", [])),
        "buttons": list(data.get("buttons", [])),
        "tables": list(data.get("tables", [])),
        "basic_flow": list(data.get("basic_flow") or data.get("basicFlow") or derived_basic_flow or []),
        "alternative_flow": list(data.get("alternative_flow") or data.get("alternativeFlow") or derived_alternative_flow or []),
        "alternative_flows": explicit_alternative_flows or derived_alternative_flows,
        "validation_rules": list(data.get("validation_rules") or data.get("validationRules") or []),
        "business_rules": list(data.get("business_rules") or data.get("businessRules") or []),
        "api_actions": list(data.get("api_actions") or data.get("apiActions") or []),
        "error_scenarios": list(data.get("error_scenarios") or data.get("errorScenarios") or []),
        "diagram_steps": dict(data.get("diagram_steps") or data.get("diagramSteps") or {}),
        "notes": list(data.get("notes", [])),
    }
    if not workflow["basic_flow"]:
        workflow["basic_flow"] = [
            {
                "actor": "UNKNOWN",
                "system": "UNKNOWN",
                "crud": "R",
            }
        ]
    return workflow


def draft_workflow(name: str | None, image: str | None) -> dict:
    title = name or (Path(image).stem if image else "UNKNOWN")
    return normalize_workflow(
        {
            "id": slugify(title),
            "name": title,
            "purpose": "UNKNOWN",
            "source_image": image or "",
            "basic_flow": [
                {
                    "actor": "UNKNOWN",
                    "system": "UNKNOWN",
                    "crud": "R",
                }
            ],
            "error_scenarios": ["UNKNOWN"],
            "notes": [
                "Draft workflow. Review and replace UNKNOWN values before final use.",
            ],
        },
        name=title,
        image=image,
    )


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--src-common", default=str(DEFAULT_SRC_COMMON), help="Path to src_common.")
    parser.add_argument("--docx-common", default="", help="Override common DOCX path.")
    parser.add_argument("--xml-common", default="", help="Override common XML path.")
