// DataProcessor.ts — core data processing with inheritance and cross-file imports

export interface ProcessorConfig {
  requiredFields?: string[];
  strict?: boolean;
}

export interface Transformer {
  transform(data: Record<string, unknown>): Record<string, unknown>;
}

export class DataProcessor {
  private transformers: Transformer[] = [];

  constructor(protected config: ProcessorConfig = {}) {}

  addTransformer(t: Transformer): void {
    this.transformers.push(t);
  }

  process(data: Record<string, unknown>): Record<string, unknown> {
    let result = { ...data };
    for (const t of this.transformers) {
      result = t.transform(result);
    }
    return result;
  }

  validate(data: Record<string, unknown>): boolean {
    const required = this.config.requiredFields ?? [];
    return required.every((f) => f in data);
  }
}

export class JSONProcessor extends DataProcessor {
  process(data: Record<string, unknown>): Record<string, unknown> {
    const parsed = JSON.parse(JSON.stringify(data));
    return super.process(parsed);
  }
}

export function createDefaultProcessor(): DataProcessor {
  // cross-file import — tests call resolution
  return new DataProcessor({ requiredFields: ["id", "name"] });
}
