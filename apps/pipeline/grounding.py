from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

NUMBER_TOKEN_RE = re.compile(r"-?\d+(?:[.,]\d+)*")


def normalize_text(text: str) -> str:
    result = text.lower()
    result = result.replace("\u2018", "'").replace("\u2019", "'")
    result = result.replace("\u201c", '"').replace("\u201d", '"')
    result = re.sub(r"-\s*\n\s*", "", result)
    result = re.sub(r"\s+", " ", result)
    return result.strip()


def _token_to_float(token: str) -> float | None:
    negative = token.startswith("-")
    body = token[1:] if negative else token
    dots = body.count(".")
    commas = body.count(",")

    if dots > 1 or commas > 1:
        digits = body.replace(".", "").replace(",", "")
        if not digits.isdigit():
            return None
        value = float(digits)
    elif dots and commas:
        if body.rfind(",") > body.rfind("."):
            int_part, _, frac = body.partition(",")
            value = float(f"{int_part.replace('.', '')}.{frac}")
        else:
            int_part, _, frac = body.partition(".")
            value = float(f"{int_part.replace(',', '')}.{frac}")
    elif commas or dots:
        sep = "," if commas else "."
        left, _, right = body.partition(sep)
        if right.isdigit() and len(right) == 3 and left.isdigit():
            value = float(f"{left}{right}")
        elif right.isdigit() and 1 <= len(right) <= 2 and left.isdigit():
            value = float(f"{left}.{right}")
        elif right.isdigit() and left.isdigit():
            value = float(f"{left}{right}")
        else:
            return None
    else:
        if not body.isdigit():
            return None
        value = float(body)

    return -value if negative else value


def normalize_number(raw: str) -> float | None:
    match = NUMBER_TOKEN_RE.search(raw)
    if match is None:
        return None
    return _token_to_float(match.group(0))


def numbers_in(text: str) -> list[float]:
    values: list[float] = []
    for match in NUMBER_TOKEN_RE.finditer(text):
        value = _token_to_float(match.group(0))
        if value is not None:
            values.append(value)
    return values


def check_excerpt(excerpt: str, page_text: str) -> bool:
    normalized_excerpt = normalize_text(excerpt)
    normalized_page = normalize_text(page_text)
    if not normalized_excerpt:
        return False
    if normalized_excerpt in normalized_page:
        return True
    excerpt_compact = re.sub(r"[^0-9a-z]+", "", normalized_excerpt)
    page_compact = re.sub(r"[^0-9a-z]+", "", normalized_page)
    if excerpt_compact and excerpt_compact in page_compact:
        return True
    return _fuzzy_window_match(normalized_excerpt, normalized_page)


def _fuzzy_window_match(excerpt: str, page: str, threshold: float = 0.92) -> bool:
    window = len(excerpt)
    if window == 0 or len(page) < window:
        return False
    step = max(1, window // 2)
    for start in range(0, len(page) - window + 1, step):
        ratio = difflib.SequenceMatcher(None, page[start : start + window], excerpt).ratio()
        if ratio >= threshold:
            return True
    ratio = difflib.SequenceMatcher(None, page[-window:], excerpt).ratio()
    return ratio >= threshold


def check_number_in_excerpt(value: float, excerpt: str) -> bool:
    return any(abs(found - value) < 1e-6 for found in numbers_in(excerpt))


@dataclass(frozen=True)
class GroundingTarget:
    key: str
    page: int
    excerpt: str
    numeric_value: float | None = None


def check_grounding(
    targets: list[GroundingTarget],
    pages: dict[int, str],
) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for target in targets:
        page_text = pages.get(target.page)
        if page_text is None:
            results[target.key] = False
            continue
        ok = check_excerpt(target.excerpt, page_text)
        if ok and target.numeric_value is not None:
            ok = check_number_in_excerpt(target.numeric_value, target.excerpt)
        results[target.key] = ok
    return results
