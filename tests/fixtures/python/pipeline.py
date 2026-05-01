"""Entry point and configuration for the processing pipeline."""

from .processor import DataProcessor, JSONProcessor, create_default_processor
from .filters import NormalizeFilter, chain_filters


class PipelineConfig:
    def __init__(self, mode: str = "default"):
        self.mode = mode

    def build_pipeline(self):
        if self.mode == "default":
            return create_default_processor()
        proc = JSONProcessor(self.as_dict())
        flt = chain_filters(NormalizeFilter())
        proc.add_transformer(flt)
        return proc

    def as_dict(self) -> dict:
        return {"mode": self.mode, "version": 1}


def run_pipeline(input_data: list[dict]) -> list[dict]:
    config = PipelineConfig()
    proc = config.build_pipeline()
    return [proc.process(d) for d in input_data]
