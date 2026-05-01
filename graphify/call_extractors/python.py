from __future__ import annotations

from pathlib import Path
from typing import List
from dataclasses import dataclass

from graphify.code_schema import ConfidenceTier


@dataclass
class _CallSite:
    caller_nid: str
    caller_file: str
    callee_name: str
    callee_receiver: str | None = None
    arity: int = 0
    is_constructor: bool = False
    source_location: str = ""
    confidence: ConfidenceTier = ConfidenceTier.EXTRACTED


def extract_python_calls(file_path: Path, extraction_result: dict) -> list[_CallSite]:
    nodes = extraction_result.get("nodes", [])
    edges = extraction_result.get("edges", [])
    str_path = str(file_path)

    nid_to_label: dict[str, str] = {}
    for n in nodes:
        nid = n.get("id", "")
        label = n.get("label", "").strip("()").lstrip(".")
        if nid and label:
            nid_to_label[nid] = label

    calls: list[_CallSite] = []
    seen: set[tuple[str, str, str]] = set()

    for edge in edges:
        if edge.get("relation") != "calls":
            continue

        caller_nid = edge.get("source", "")
        tgt_nid = edge.get("target", "")
        loc = edge.get("source_location", "")

        if not caller_nid or not tgt_nid:
            continue

        callee_name = nid_to_label.get(tgt_nid, tgt_nid)

        receiver: str | None = None
        is_constructor = False

        if callee_name and callee_name[0].isupper() and "." not in callee_name:
            is_constructor = True

        if "." in callee_name:
            parts = callee_name.rsplit(".", 1)
            receiver = parts[0]
            callee_name = parts[1]

        key = (caller_nid, callee_name, receiver or "")
        if key in seen:
            continue
        seen.add(key)

        calls.append(_CallSite(
            caller_nid=caller_nid,
            caller_file=str_path,
            callee_name=callee_name,
            callee_receiver=receiver,
            arity=0,
            is_constructor=is_constructor,
            source_location=loc,
            confidence=ConfidenceTier.EXTRACTED if edge.get("confidence") == "EXTRACTED" else ConfidenceTier.INFERRED,
        ))

    for rc in extraction_result.get("raw_calls", []):
        caller_nid = rc.get("caller_nid", "")
        callee_name = rc.get("callee", "")
        loc = rc.get("source_location", "")
        if not caller_nid or not callee_name:
            continue
        receiver: str | None = None
        if rc.get("is_member_call"):
            parts = callee_name.split(".")
            if len(parts) > 1:
                receiver = parts[0]
                callee_name = parts[-1]
        key = (caller_nid, callee_name, receiver or "")
        if key in seen:
            continue
        seen.add(key)
        calls.append(_CallSite(
            caller_nid=caller_nid,
            caller_file=str_path,
            callee_name=callee_name,
            callee_receiver=receiver,
            arity=0,
            is_constructor=False,
            source_location=loc,
            confidence=ConfidenceTier.INFERRED,
        ))

    return calls
