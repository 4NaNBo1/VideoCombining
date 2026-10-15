"""组合规划与输出命名（纯函数）。"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence


class ComboLimitError(Exception):
    """请求数量超过可用不重复组合上限。"""

    def __init__(self, requested: int, maximum: int, generated: int):
        self.requested = requested
        self.maximum = maximum
        self.generated = generated
        super().__init__(
            f"最多可生成 {maximum} 个不重复组合，已请求 {requested} 个，已成功 {generated} 个"
        )


def perm_count(n: int, k: int) -> int:
    if k < 0 or n < 0 or k > n:
        return 0
    result = 1
    for i in range(k):
        result *= n - i
    return result


def max_combinations(
    n_heads: int,
    k_heads: int,
    n_mids: int,
    k_mids: int,
    n_tails: int,
    k_tails: int,
) -> int:
    return (
        perm_count(n_heads, k_heads)
        * perm_count(n_mids, k_mids)
        * perm_count(n_tails, k_tails)
    )


@dataclass(frozen=True)
class ComboSpec:
    heads: tuple[str, ...]
    mids: tuple[str, ...]
    tails: tuple[str, ...]

    @property
    def segments(self) -> tuple[str, ...]:
        return self.heads + self.mids + self.tails


def _random_perm(items: Sequence[str], k: int, rng: random.Random) -> tuple[str, ...]:
    if k > len(items):
        raise ValueError(f"需要从 {len(items)} 个素材中取 {k} 个")
    return tuple(rng.sample(list(items), k))


def plan_combos(
    heads: Sequence[str],
    mids: Sequence[str],
    tails: Sequence[str],
    k_heads: int,
    k_mids: int,
    k_tails: int,
    count: int,
    *,
    seed: int | None = None,
) -> list[ComboSpec]:
    if count <= 0:
        return []
    maximum = max_combinations(len(heads), k_heads, len(mids), k_mids, len(tails), k_tails)
    if count > maximum:
        raise ComboLimitError(count, maximum, 0)

    rng = random.Random(seed)
    seen: set[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = set()
    out: list[ComboSpec] = []
    attempts = 0
    max_attempts = count * 200 + 1000

    while len(out) < count:
        attempts += 1
        if attempts > max_attempts:
            raise ComboLimitError(count, maximum, len(out))
        h = _random_perm(heads, k_heads, rng)
        m = _random_perm(mids, k_mids, rng)
        t = _random_perm(tails, k_tails, rng)
        key = (h, m, t)
        if key in seen:
            continue
        seen.add(key)
        out.append(ComboSpec(heads=h, mids=m, tails=t))
    return out


# (显示名, 年, 月, 日, 时, 分, 秒, 分隔符) — 空字符串表示不含该段
DATE_FORMAT_PRESETS: tuple[tuple[str, str, str, str, str, str, str, str], ...] = (
    ("紧凑 YYYYMMDD", "%Y", "%m", "%d", "", "", "", ""),
    ("紧凑 YYMMDD", "%y", "%m", "%d", "", "", "", ""),
    ("紧凑 YYYYMMDDHHmmss", "%Y", "%m", "%d", "%H", "%M", "%S", ""),
    ("紧凑 YYYYMMDD_HHmmss", "%Y", "%m", "%d", "%H", "%M", "%S", "_"),
    ("横线 YYYY-MM-DD", "%Y", "%m", "%d", "", "", "", "-"),
    ("横线 YYYY-MM-DD HH-mm-ss", "%Y", "%m", "%d", "%H", "%M", "%S", "-"),
    ("下划线 YYYY_MM_DD", "%Y", "%m", "%d", "", "", "", "_"),
    ("下划线 YYYY_MM_DD_HH_mm_ss", "%Y", "%m", "%d", "%H", "%M", "%S", "_"),
    ("点 YYYY.MM.DD", "%Y", "%m", "%d", "", "", "", "."),
    ("点 YYYY.MM.DD.HH.mm.ss", "%Y", "%m", "%d", "%H", "%M", "%S", "."),
    ("仅日期 YYYY-MM-DD", "%Y", "%m", "%d", "", "", "", "-"),
    ("仅时间 HH-mm-ss", "", "", "", "%H", "%M", "%S", "-"),
    ("仅时间 HHmmss", "", "", "", "%H", "%M", "%S", ""),
    ("年月 YYYY-MM", "%Y", "%m", "", "", "", "", "-"),
    ("月日 MMDD", "", "%m", "%d", "", "", "", ""),
    ("12 小时 hh-mm-ss", "", "", "", "%I", "%M", "%S", "-"),
    ("12 小时 YYYYMMDD hhmmss", "%Y", "%m", "%d", "%I", "%M", "%S", ""),
)


def compose_date_format(
    *,
    year_token: str = "",
    month_token: str = "",
    day_token: str = "",
    hour_token: str = "",
    minute_token: str = "",
    second_token: str = "",
    separator: str = "",
) -> str:
    tokens = [
        t
        for t in (
            year_token,
            month_token,
            day_token,
            hour_token,
            minute_token,
            second_token,
        )
        if t
    ]
    if not tokens:
        return ""
    return separator.join(tokens)


def build_output_name(
    *,
    prefix: str,
    suffix: str,
    seq: int,
    ext: str,
    include_date: bool = True,
    date_format: str = "%Y%m%d",
    on_moment: datetime | None = None,
) -> str:
    parts: list[str] = []
    if prefix.strip():
        parts.append(prefix.strip())
    if include_date:
        if not date_format:
            raise ValueError("date_format 为空")
        moment = on_moment or datetime.now()
        parts.append(moment.strftime(date_format))
    parts.append(f"{seq:03d}")
    if suffix.strip():
        parts.append(suffix.strip())
    base = "_".join(parts)
    ext_clean = ext.lstrip(".").lower() or "mp4"
    return f"{base}.{ext_clean}"


def _self_check() -> None:
    assert perm_count(5, 2) == 20
    assert max_combinations(3, 1, 3, 1, 3, 1) == 27
    combos = plan_combos(
        ["h1", "h2"],
        ["m1"],
        ["t1", "t2"],
        2,
        1,
        1,
        2,
        seed=42,
    )
    assert len(combos) == 2
    assert len(set((c.heads, c.mids, c.tails) for c in combos)) == 2
    no_mid = plan_combos(["h1"], [], ["t1"], 1, 0, 1, 1, seed=0)[0]
    assert no_mid.segments == ("h1", "t1")
    name = build_output_name(prefix="pre", suffix="suf", seq=1, ext="mp4")
    assert name.endswith(".mp4") and "pre" in name and "suf" in name
    fmt = compose_date_format(
        year_token="%Y",
        month_token="%m",
        day_token="%d",
        separator="-",
    )
    assert fmt == "%Y-%m-%d"
    dashed = build_output_name(
        prefix="pre",
        suffix="",
        seq=1,
        ext="mp4",
        on_moment=datetime(2026, 10, 15, 9, 8, 7),
        date_format=compose_date_format(
            year_token="%Y",
            month_token="%m",
            day_token="%d",
            hour_token="%H",
            minute_token="%M",
            second_token="%S",
        ),
    )
    assert "20261015090807" in dashed
    try:
        plan_combos(["a"], ["b"], ["c"], 1, 1, 1, 2, seed=1)
        raise AssertionError("expected ComboLimitError")
    except ComboLimitError:
        pass


if __name__ == "__main__":
    _self_check()
    print("combo self-check ok")
