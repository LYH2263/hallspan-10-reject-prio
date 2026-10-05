"""Exam seating engine.

Single source of truth contract
--------------------------------
The ``issues`` list is the ONLY truth for both "未排" and "违规".

* 行说明 (seat / candidate notes) 由 issues 投影；
* 分类计数 (stats.by_code) 由 issues 计数；
* 引擎、列表、计数不得各算一套。

短路（同一对座位只留一句，优先级从高到低）：
blocked_seat > same_paper_adjacent > distance
* 既触损坏禁坐又算间距不足 → 只认 blocked_seat；
* 非禁坐但同卷四邻相邻   → 只认 same_paper_adjacent，不再并 distance；
* 仅间距不足             → 才写 distance。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# 权威原因码表：前端只能用这里下发的 code/label/category，禁止另写一套原因码。
# 顺序即分类计数与列表展示的稳定顺序。
# ---------------------------------------------------------------------------
REASON_CODES: dict[str, dict[str, str]] = {
    "blocked_seat": {"label": "损坏禁坐", "category": "violation"},
    "same_paper_adjacent": {"label": "同卷相邻", "category": "violation"},
    "distance": {"label": "间距不足", "category": "violation"},
    "unplaced": {"label": "未排上", "category": "unplaced"},
}
# pair 级短路优先级：索引小者压制索引大者。
_PAIR_PRIORITY = ("blocked_seat", "same_paper_adjacent", "distance")
VIOLATION_CODES = tuple(c for c, m in REASON_CODES.items() if m["category"] == "violation")


@dataclass
class SeatAssign:
    candidate_id: int
    name: str
    ticket_no: str
    paper_id: int
    row: int
    col: int


@dataclass
class Issue:
    """一条未排/违规事实。subject 标识行说明口径。"""
    code: str                 # 必须取自 REASON_CODES
    subject: str              # seat | seat_pair | candidate
    detail: str
    a_id: Optional[int] = None
    a_name: Optional[str] = None
    b_id: Optional[int] = None
    b_name: Optional[str] = None
    row: Optional[int] = None
    col: Optional[int] = None
    b_row: Optional[int] = None
    b_col: Optional[int] = None


def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def neighbors4(r: int, c: int, rows: int, cols: int) -> list[tuple[int, int]]:
    out = []
    for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            out.append((nr, nc))
    return out


def normalize_blocked(blocked_seats: Iterable[tuple[int, int]] | None,
                      blocked_enabled: bool) -> frozenset[tuple[int, int]]:
    """未启用损坏禁坐时损坏格一律视为不存在（禁坐计数必须为 0）。"""
    if not blocked_enabled:
        return frozenset()
    return frozenset(blocked_seats or ())


def place_candidates(rows: int, cols: int, min_dist: int, candidates: list[dict],
                     blocked_seats: Iterable[tuple[int, int]] | None = None,
                     blocked_enabled: bool = True) -> tuple[list[SeatAssign], list[dict]]:
    """贪心行-major 落位；启用时跳过损坏格。返回 (assigns, 未落位考生原始字典)。"""
    blocked = normalize_blocked(blocked_seats, blocked_enabled)
    occupied: dict[tuple[int, int], SeatAssign] = {}
    unplaced: list[dict] = []
    for cand in candidates:
        placed = False
        for r in range(rows):
            for c in range(cols):
                if (r, c) in occupied or (r, c) in blocked:
                    continue
                ok = True
                for pos, other in occupied.items():
                    if manhattan((r, c), pos) < min_dist:
                        ok = False
                        break
                    if other.paper_id == cand["paper_id"] and (r, c) in neighbors4(pos[0], pos[1], rows, cols):
                        ok = False
                        break
                if not ok:
                    continue
                for nr, nc in neighbors4(r, c, rows, cols):
                    if (nr, nc) in occupied and occupied[(nr, nc)].paper_id == cand["paper_id"]:
                        ok = False
                        break
                if not ok:
                    continue
                occupied[(r, c)] = SeatAssign(
                    cand["id"], cand["name"], cand["ticket_no"], cand["paper_id"], r, c)
                placed = True
                break
            if placed:
                break
        if not placed:
            unplaced.append(cand)
    return list(occupied.values()), unplaced


def _pair_issue(code: str, a: SeatAssign, b: SeatAssign, detail: str) -> Issue:
    return Issue(
        code=code, subject="seat_pair", detail=detail,
        a_id=a.candidate_id, a_name=a.name,
        b_id=b.candidate_id, b_name=b.name,
        row=a.row, col=a.col, b_row=b.row, b_col=b.col,
    )


def evaluate(rows: int, cols: int, min_dist: int,
             assigns: list[SeatAssign], unplaced: list[dict],
             blocked_seats: Iterable[tuple[int, int]] | None = None,
             blocked_enabled: bool = True) -> list[Issue]:
    """产出唯一 issues 列表。三口（行说明/列表/计数）都从它派生。"""
    blocked = normalize_blocked(blocked_seats, blocked_enabled)
    by_pos = {(a.row, a.col): a for a in assigns}
    seated_ids = {a.candidate_id for a in assigns}
    issues: list[Issue] = []

    # 1) seat 级：每个启用的损坏格一条 blocked_seat（行说明“损坏禁坐”的唯一来源）。
    for (r, c) in sorted(blocked):
        occ = by_pos.get((r, c))
        issues.append(Issue(
            code="blocked_seat", subject="seat",
            detail=f"座位 ({r + 1},{c + 1}) 损坏禁坐",
            a_id=occ.candidate_id if occ else None,
            a_name=occ.name if occ else None,
            row=r, col=c,
        ))

    # 2) pair 级：每对座位至多一条，按优先级短路。
    for i, a in enumerate(assigns):
        for b in assigns[i + 1:]:
            a_blocked = (a.row, a.col) in blocked
            b_blocked = (b.row, b.col) in blocked
            if a_blocked or b_blocked:
                # 已坐损坏格 → 只认禁坐（seat 级已记），禁止再并同卷/间距句。
                continue
            d = manhattan((a.row, a.col), (b.row, b.col))
            same_adj = (a.paper_id == b.paper_id
                        and (b.row, b.col) in neighbors4(a.row, a.col, rows, cols))
            if same_adj:
                # 非禁坐但同卷相邻 → 只认同卷相邻，短路，不再并间距句。
                issues.append(_pair_issue(
                    "same_paper_adjacent", a, b,
                    f"同试卷套 {a.paper_id} 四邻相邻（{a.name}↔{b.name}）"))
            elif d < min_dist:
                issues.append(_pair_issue(
                    "distance", a, b,
                    f"曼哈顿距离 {d} < 最小要求 {min_dist}（{a.name}↔{b.name}）"))

    # 3) candidate 级：未排考生。已合法落座者不得挂未排原因。
    for cand in unplaced:
        if cand["id"] in seated_ids:
            raise AssertionError(f"考生 {cand['id']} 已落座却挂未排原因，三口同码被破坏")
        issues.append(Issue(
            code="unplaced", subject="candidate",
            detail=f"无可用座位：受最小间距/同卷相邻/禁坐约束（{cand['name']}）",
            a_id=cand["id"], a_name=cand["name"], row=None, col=None,
        ))

    _validate(issues, blocked_enabled)
    return issues


def _validate(issues: list[Issue], blocked_enabled: bool) -> None:
    """冒码整场失败：码必须合法；未启用损坏禁坐时不得出现 blocked_seat。"""
    for it in issues:
        if it.code not in REASON_CODES:
            raise AssertionError(f"非法原因码 {it.code!r}，不在 REASON_CODES 中")
    if not blocked_enabled:
        bogus = [it for it in issues if it.code == "blocked_seat"]
        if bogus:
            raise AssertionError("未启用损坏禁坐却冒出 blocked_seat 计数，整场失败")


def derive_stats(issues: list[Issue], assigns: list[SeatAssign],
                 rows: int, cols: int) -> dict:
    """分类计数唯一由 issues 派生；列表为空时所有分类必须为 0。"""
    counts = {code: 0 for code in REASON_CODES}
    for it in issues:
        counts[it.code] += 1
    violations = sum(counts[c] for c in VIOLATION_CODES)
    return {
        "seated": len(assigns),
        "unplaced": counts["unplaced"],
        "violations": violations,
        "capacity": rows * cols,
        "issues": len(issues),
        "by_code": counts,
    }


def derive_unplaced(issues: list[Issue]) -> list[dict]:
    """未排列表由 issues 投影，不与引擎并行维护第二份。"""
    return [
        {"id": it.a_id, "name": it.a_name, "reason": it.code, "detail": it.detail}
        for it in issues if it.code == "unplaced"
    ]


def plan_seating(rows: int, cols: int, min_dist: int, candidates: list[dict],
                 blocked_seats: Iterable[tuple[int, int]] | None = None,
                 blocked_enabled: bool = True) -> dict:
    """排座 + 审计 + 投影，一次产出三口同码的结果。"""
    blocked = normalize_blocked(blocked_seats, blocked_enabled)
    assigns, unplaced = place_candidates(rows, cols, min_dist, candidates, blocked, blocked_enabled)
    issues = evaluate(rows, cols, min_dist, assigns, unplaced, blocked, blocked_enabled)
    return plan_to_dict(assigns, issues, rows, cols)


def plan_to_dict(assigns: list[SeatAssign], issues: list[Issue], rows: int, cols: int) -> dict:
    # 码合法性始终可校验；禁坐开关规则需上下文，已在 evaluate() 内校验。
    for it in issues:
        if it.code not in REASON_CODES:
            raise AssertionError(f"非法原因码 {it.code!r}，不在 REASON_CODES 中")
    return {
        "rows": rows,
        "cols": cols,
        "assignments": [asdict(a) for a in assigns],
        "issues": [asdict(i) for i in issues],
        "unplaced": derive_unplaced(issues),
        "reason_codes": REASON_CODES,
        "stats": derive_stats(issues, assigns, rows, cols),
    }
