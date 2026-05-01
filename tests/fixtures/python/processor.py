"""
A simple data processor module with cross-file imports.
Exercises: class extraction, method detection, import resolution, calls.
"""


class DataProcessor:
    """Processes raw data through a pipeline of transformations."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._transformers: list = []

    def add_transformer(self, transformer):
        self._transformers.append(transformer)

    def process(self, data: dict) -> dict:
        result = data
        for t in self._transformers:
            result = t(result)
        return result

    def validate(self, data: dict) -> bool:
        required = self.config.get("required_fields", [])
        return all(f in data for f in required)


class JSONProcessor(DataProcessor):
    def process(self, data: dict) -> dict:
        import json
        parsed = json.loads(json.dumps(data))
        return super().process(parsed)


def create_default_processor() -> DataProcessor:
    from .filters import NormalizeFilter, RemoveNullFilter
    proc = DataProcessor({"required_fields": ["id", "name"]})
    proc.add_transformer(NormalizeFilter())
    proc.add_transformer(RemoveNullFilter())
    return proc
