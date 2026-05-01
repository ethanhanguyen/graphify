// Pipeline.ts — entry point, cross-module composition

import {
  DataProcessor,
  JSONProcessor,
  createDefaultProcessor,
  ProcessorConfig,
} from "./processor";
import { NormalizeFilter, chainFilters } from "./filters";

export class PipelineConfig {
  private mode: string;

  constructor(mode: string = "default") {
    this.mode = mode;
  }

  buildPipeline(): DataProcessor {
    if (this.mode === "default") {
      return createDefaultProcessor();
    }
    const proc = new JSONProcessor(this.toConfig());
    proc.addTransformer(chainFilters(new NormalizeFilter()));
    return proc;
  }

  private toConfig(): ProcessorConfig {
    return { mode: this.mode, version: 1 } as ProcessorConfig;
  }
}

export function runPipeline(
  inputData: Record<string, unknown>[]
): Record<string, unknown>[] {
  const config = new PipelineConfig();
  const proc = config.buildPipeline();
  return inputData.map((d) => proc.process(d));
}
