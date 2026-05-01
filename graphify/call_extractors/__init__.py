from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from graphify.code_schema import ConfidenceTier


@dataclass
class ExtractedCallSite:
    caller_nid: str
    caller_file: str
    callee_name: str
    callee_receiver: Optional[str] = None
    arity: int = 0
    is_constructor: bool = False
    source_location: str = ""
    confidence: ConfidenceTier = ConfidenceTier.EXTRACTED


def extract_calls(file_path: Path, language: str, extraction_result: dict) -> List[ExtractedCallSite]:
    suffix_to_extractor = {
        "python": _extract_python_calls,
        "javascript": _extract_typescript_calls,
        "typescript": _extract_typescript_calls,
        "go": _extract_go_calls,
        "java": _extract_java_calls,
    }
    extractor = suffix_to_extractor.get(language)
    if extractor:
        return extractor(file_path, extraction_result)
    return []


def _extract_python_calls(file_path: Path, extraction_result: dict) -> List[ExtractedCallSite]:
    return _dispatch_import(file_path, extraction_result, "python")


def _extract_typescript_calls(file_path: Path, extraction_result: dict) -> List[ExtractedCallSite]:
    return _dispatch_import(file_path, extraction_result, "typescript")


def _extract_go_calls(file_path: Path, extraction_result: dict) -> List[ExtractedCallSite]:
    return _dispatch_import(file_path, extraction_result, "go")


def _extract_java_calls(file_path: Path, extraction_result: dict) -> List[ExtractedCallSite]:
    return _dispatch_import(file_path, extraction_result, "java")


def _dispatch_import(file_path: Path, extraction_result: dict, language: str) -> List[ExtractedCallSite]:
    module_name = f"graphify.call_extractors.{language}"
    import importlib
    mod = importlib.import_module(module_name)
    func_name = f"extract_{language}_calls"
    fn = getattr(mod, func_name, None)
    if fn:
        return fn(file_path, extraction_result)
    return []
