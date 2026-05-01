from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from graphify.call_extractors import ExtractedCallSite


class SelfInferrer:
    def infer(self, call_site: ExtractedCallSite, context: dict) -> Optional[str]:
        if call_site.callee_receiver is not None and call_site.callee_receiver:
            return call_site.callee_receiver
        callee = call_site.callee_name
        enclosing_class = context.get("enclosing_class")
        if callee in ("this", "self", "me") and enclosing_class:
            return enclosing_class
        class_hierarchy = context.get("class_hierarchy", {})
        if enclosing_class and callee in class_hierarchy.get(enclosing_class, []):
            return enclosing_class
        return None


class ConstructorInferrer:
    def infer(self, call_site: ExtractedCallSite, context: dict) -> Optional[str]:
        if not call_site.is_constructor:
            return None
        return call_site.callee_name


class ChainInferrer:
    def infer(self, call_site: ExtractedCallSite, context: dict) -> Optional[str]:
        callee = call_site.callee_name
        if not callee:
            return None
        enclosing_class = context.get("enclosing_class")
        method_map = context.get("method_map", {})
        if enclosing_class and callee in method_map.get(enclosing_class, set()):
            return enclosing_class
        if callee in method_map:
            return enclosing_class
        return None


class ImportInferrer:
    def infer(self, call_site: ExtractedCallSite, context: dict) -> Optional[str]:
        imports = context.get("imports", {})
        callee = call_site.callee_name
        if not callee:
            return None
        if callee in imports:
            return imports[callee]
        for import_source, imported_names in context.get("import_map", {}).items():
            if callee in imported_names:
                return import_source
        return None


def infer_receiver(
    call_site: ExtractedCallSite,
    enclosing_scope: str,
    class_map: dict[str, str],
) -> Optional[str]:
    context: dict = {
        "enclosing_scope": enclosing_scope,
        "enclosing_class": class_map.get(enclosing_scope) or class_map.get(call_site.caller_nid),
        "class_map": class_map,
        "class_hierarchy": {},
        "method_map": {},
        "imports": {},
        "import_map": {},
    }

    self_inferrer = SelfInferrer()
    result = self_inferrer.infer(call_site, context)
    if result:
        return result

    constructor_inferrer = ConstructorInferrer()
    result = constructor_inferrer.infer(call_site, context)
    if result:
        return result

    chain_inferrer = ChainInferrer()
    result = chain_inferrer.infer(call_site, context)
    if result:
        return result

    import_inferrer = ImportInferrer()
    result = import_inferrer.infer(call_site, context)
    if result:
        return result

    return None
