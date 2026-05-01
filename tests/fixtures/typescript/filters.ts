// Filters.ts — transformer implementations

import { Transformer } from "./processor";

export class NormalizeFilter implements Transformer {
  transform(data: Record<string, unknown>): Record<string, unknown> {
    const result: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(data)) {
      result[k] = typeof v === "string" ? v.trim().toLowerCase() : v;
    }
    return result;
  }
}

export class RemoveNullFilter implements Transformer {
  transform(data: Record<string, unknown>): Record<string, unknown> {
    const result: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(data)) {
      if (v !== null && v !== undefined) {
        result[k] = v;
      }
    }
    return result;
  }
}

export function chainFilters(
  ...filters: Transformer[]
): Transformer {
  return {
    transform(data: Record<string, unknown>): Record<string, unknown> {
      let r = data;
      for (const f of filters) {
        r = f.transform(r);
      }
      return r;
    },
  };
}
