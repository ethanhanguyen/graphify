"""Filters used by the data processor."""


class NormalizeFilter:
    def __call__(self, data: dict) -> dict:
        result = {}
        for k, v in data.items():
            if isinstance(v, str):
                v = v.strip().lower()
            result[k] = v
        return result


class RemoveNullFilter:
    def __call__(self, data: dict) -> dict:
        return {k: v for k, v in data.items() if v is not None}


class enrich_filter:
    def __call__(self, data: dict) -> dict:
        data["_enriched"] = True
        return data


def chain_filters(*filters):
    def composed(data):
        r = data
        for f in filters:
            r = f(r)
        return r
    return composed
