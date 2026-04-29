import hashlib
import time
from pathlib import Path

CACHE_TTL = 3600


def cache_key(query_text: str, mode: str, depth: int, budget: int) -> str:
    """SHA256 of (query_text, mode, depth, budget)."""
    return hashlib.sha256(
        f"{query_text}|{mode}|{depth}|{budget}".encode()
    ).hexdigest()


def _read_counter(cache_dir: Path, name: str) -> int:
    counter_file = cache_dir / f".{name}"
    try:
        return int(counter_file.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return 0


def _increment_counter(cache_dir: Path, name: str) -> None:
    counter_file = cache_dir / f".{name}"
    current = _read_counter(cache_dir, name)
    counter_file.write_text(str(current + 1), encoding="utf-8")


def get_cached_query(cache_dir: Path, key: str) -> str | None:
    """Load cached result if exists and not expired.

    Cache files stored as cache_dir/{key}.txt.
    Each file has first line as timestamp (epoch), rest is result.
    """
    cache_file = cache_dir / f"{key}.txt"
    if not cache_file.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        _increment_counter(cache_dir, "misses")
        return None
    try:
        content = cache_file.read_text(encoding="utf-8")
        newline_idx = content.index("\n")
        timestamp = float(content[:newline_idx])
        result = content[newline_idx + 1:]
    except (ValueError, FileNotFoundError):
        _increment_counter(cache_dir, "misses")
        return None
    if time.time() - timestamp > CACHE_TTL:
        _increment_counter(cache_dir, "misses")
        return None
    _increment_counter(cache_dir, "hits")
    return result


def set_cached_query(cache_dir: Path, key: str, result: str) -> None:
    """Store query result as cache_dir/{key}.txt.

    Writes atomic (write to .tmp, rename).
    Creates cache_dir if not exists.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{key}.txt"
    tmp_file = cache_dir / f"{key}.tmp"
    tmp_file.write_text(f"{time.time()}\n{result}", encoding="utf-8")
    tmp_file.rename(cache_file)


def clear_expired_cache(cache_dir: Path, ttl: int = CACHE_TTL) -> int:
    """Remove expired cache entries. Returns count removed."""
    if not cache_dir.exists():
        return 0
    removed = 0
    now = time.time()
    for entry in cache_dir.iterdir():
        if not entry.name.endswith(".txt"):
            continue
        try:
            content = entry.read_text(encoding="utf-8")
            newline_idx = content.index("\n")
            timestamp = float(content[:newline_idx])
        except (ValueError, FileNotFoundError):
            continue
        if now - timestamp > ttl:
            entry.unlink()
            removed += 1
    return removed


def cache_stats(cache_dir: Path) -> dict:
    """Return {entries, hits, misses, hit_rate} from cache directory."""
    if not cache_dir.exists():
        return {"entries": 0, "hits": 0, "misses": 0, "hit_rate": 0.0}
    entries = sum(1 for e in cache_dir.iterdir() if e.name.endswith(".txt"))
    hits = _read_counter(cache_dir, "hits")
    misses = _read_counter(cache_dir, "misses")
    total = hits + misses
    hit_rate = hits / total if total > 0 else 0.0
    return {"entries": entries, "hits": hits, "misses": misses, "hit_rate": hit_rate}
