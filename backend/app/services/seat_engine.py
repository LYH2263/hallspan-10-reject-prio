"""HallSpan 排座引擎 —— findings 列表是未排与违规的唯一真相。

三口同码：
  行说明(finding.detail) / 违规与未排列表(findings) / 分类计数(stats.by_code)
全部由同一次 ``build_plan`` 产出的 findings 派生，引擎内部不另算第二套。

同一对座位只留一句短路，优先级（高 → 低）：
  1. seat_blocked          损坏禁坐（启用禁坐时，落座方任一坐在损坏格）
  2. same_paper_adjacent   非禁坐但同试卷套四邻相邻（不再并间距句）
  3. distance              仅间距不足（曼哈顿距离 < min_dist）
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# --- 原因码（全系统唯一一套，前端不得另写） -------------------------------
# 顺序即短路优先级：索引越小优先级越高。
SEAT_BLOCKED = "seat_blocked"
SAME_PAPER_ADJACENT = "same_paper_adjacent"
DISTANCE = "distance"
CAPACITY_FULL = "capacity_full"  # 仅用于未排：可用座位被占满，非违规

# 参与“同一对座位”短路判定的违规码（也是违规分类计数的键）。
VIOLATION_CODES = (SEAT_BLOCKED, SAME_PAPER_ADJACENT, DISTANCE)
# 分类计数的固定键序（成功且无 findings 时全部为 0）。
ALL_CODES = (SEAT_BLOCKED, SAME_PAPER_ADJACENT, DISTANCE, CAPACITY_FULL)

_PRIORITY = {code: i for i, code in enumerate(ALL_CODES)}

# code -> 中文标签 / 语气色板（前端只用 label 与 tone，不自行造码）。
REASON_CODES: dict[str, dict[str, str]] = {
    SEAT_BLOCKED: {"label": "损坏禁坐", "tone": "bad", "scope": "both"},
    SAME_PAPER_ADJACENT: {"label": "同卷相邻", "tone": "bad", "scope": "violation"},
    DISTANCE: {"label": "间距不足", "tone": "warn", "scope": "violation"},
    CAPACITY_FULL: {"label": "座位已满", "tone": "muted", "scope": "unplaced"},
}

SCOPE_VIOLATION = "violation"
SCOPE_UNPLACED = "unplaced"


class EngineError(RuntimeError):
    """三口对不齐 / 冒码等整场失败。"""


@dataclass
class SeatAssign:
    candidate_id: int
    name: str
    ticket_no: str
    paper_id: int
    row: int
    col: int


@dataclass
class Finding:
    """唯一真相中的一条：要么是一对落座者的违规，要么是一个未排考生的原因。"""
    code: str
    scope: str
    detail: str
    a_id: int | None = None
    b_id: int | None = None
    candidate_id: int | None = None
    row: int | None = None
    col: int | None = None
    paper_id: int | None = None
    dist: int | None = None


def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def neighbors4(r: int, c: int, rows: int, cols: int) -> list[tuple[int, int]]:
    out = []
    for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            out.append((nr, nc))
    return out


def _higher(code_a: str | None, code_b: str | None) -> str | None:
    """返回优先级更高的原因码（索引更小者）。"""
    if code_a is None:
        return code_b
    if code_b is None:
        return code_a
    return code_a if _PRIORITY[code_a] <= _PRIORITY[code_b] else code_b


def normalize_blocked(rows: int, cols, blocked_seats, blocked_enabled: bool) -> set[tuple[int, int]]:
    """未启用损坏禁坐时损坏格一律视为普通格——禁坐计数因此必然为 0。"""
    if not blocked_enabled:
        return set()
    out: set[tuple[int, int]] = set()
    for item in blocked_seats or []:
        if isinstance(item, dict):
            r, c = item.get("row"), item.get("col")
        else:
            r, c = item[0], item[1]
        r, c = int(r), int(c)
        if 0 <= r < rows and 0 <= c < cols:
            out.add((r, c))
    return out


def classify_pair(
    pos_a: tuple[int, int], paper_a: int,
    pos_b: tuple[int, int], paper_b: int,
    rows: int, cols: int, min_dist: int,
    blocked: set[tuple[int, int]],
) -> tuple[str | None, int]:
    """对同一对座位只短路出唯一一个原因码（及曼哈顿距离）。

    顺序：损坏禁坐 > 同卷相邻 > 间距不足；都不触发返回 (None, d)。
    """
    d = manhattan(pos_a, pos_b)
    if pos_a in blocked or pos_b in blocked:
        return SEAT_BLOCKED, d
    if paper_a == paper_b and pos_b in neighbors4(pos_a[0], pos_a[1], rows, cols):
        return SAME_PAPER_ADJACENT, d  # 相邻本就间距过近，短路，不再并 distance 句
    if d < min_dist:
        return DISTANCE, d
    return None, d


def _detail(code: str, *, pos=None, paper_id=None, dist=None, min_dist=None) -> str:
    """每个原因码只有这一处文案——行说明与列表同句。"""
    if code == SEAT_BLOCKED:
        return f"座位 ({pos[0]},{pos[1]}) 损坏禁坐"
    if code == SAME_PAPER_ADJACENT:
        return f"同试卷套 {paper_id} 四邻相邻"
    if code == DISTANCE:
        return f"曼哈顿距离 {dist} < 最小要求 {min_dist}"
    if code == CAPACITY_FULL:
        return "可用座位已满，无法排入"
    raise EngineError(f"未知原因码: {code!r}")


def place_candidates(
    rows: int, cols: int, min_dist: int, candidates: list[dict],
    blocked: set[tuple[int, int]] | None = None,
) -> tuple[list[SeatAssign], list[dict]]:
    """贪婪行-major 落坐到非损坏格；返回已排与未排（未排带 reason）。"""
    blocked = blocked or set()
    occupied: dict[tuple[int, int], SeatAssign] = {}
    unplaced: list[dict] = []

    for cand in candidates:
        chosen: tuple[int, int] | None = None
        conflict: str | None = None   # 空闲非损坏格上遇到的最高优先级邻座冲突
        saw_blocked_free = False      # 是否存在“仅因损坏才不能坐”的空位
        saw_free = False
        for r in range(rows):
            for c in range(cols):
                if (r, c) in occupied:
                    continue
                if (r, c) in blocked:
                    saw_blocked_free = True
                    continue
                saw_free = True
                seat_code: str | None = None
                for opos, other in occupied.items():
                    code, _ = classify_pair(
                        (r, c), cand["paper_id"], opos, other.paper_id,
                        rows, cols, min_dist, blocked,
                    )
                    seat_code = _higher(seat_code, code)
                if seat_code is None:
                    chosen = (r, c)
                    break
                conflict = _higher(conflict, seat_code)
            if chosen is not None:
                break

        if chosen is not None:
            r, c = chosen
            occupied[(r, c)] = SeatAssign(
                cand["id"], cand["name"], cand["ticket_no"], cand["paper_id"], r, c
            )
        else:
            # 有空闲格却都因邻座冲突不能坐 → 归因冲突；
            # 一个空闲非损坏格都没有（仅剩损坏格）→ 禁坐；全占满 → 满座。
            if conflict is not None and saw_free:
                reason = conflict
            elif saw_blocked_free:
                reason = SEAT_BLOCKED
            else:
                reason = CAPACITY_FULL
            unplaced.append({**cand, "reason": reason})

    return list(occupied.values()), unplaced


def find_violations(
    rows: int, cols: int, min_dist: int, assigns: list[SeatAssign],
    blocked: set[tuple[int, int]] | None = None,
) -> list[Finding]:
    """对每对已落座者短路出至多一条违规 finding。"""
    blocked = blocked or set()
    viols: list[Finding] = []
    for i, a in enumerate(assigns):
        for b in assigns[i + 1:]:
            code, d = classify_pair(
                (a.row, a.col), a.paper_id, (b.row, b.col), b.paper_id,
                rows, cols, min_dist, blocked,
            )
            if code is None:
                continue
            if code == SEAT_BLOCKED:
                bad_pos = (a.row, a.col) if (a.row, a.col) in blocked else (b.row, b.col)
                detail = _detail(SEAT_BLOCKED, pos=bad_pos)
            elif code == SAME_PAPER_ADJACENT:
                detail = _detail(SAME_PAPER_ADJACENT, paper_id=a.paper_id)
            else:
                detail = _detail(DISTANCE, dist=d, min_dist=min_dist)
            viols.append(Finding(
                code=code, scope=SCOPE_VIOLATION, detail=detail,
                a_id=a.candidate_id, b_id=b.candidate_id,
                paper_id=a.paper_id if code == SAME_PAPER_ADJACENT else None,
                dist=d if code == DISTANCE else None,
            ))
    return viols


def _assert_consistent(findings: list[Finding], blocked_enabled: bool) -> None:
    """三口同码硬校验，对不齐 / 冒码即整场失败。"""
    for f in findings:
        if f.code not in ALL_CODES:
            raise EngineError(f"出现未登记原因码 {f.code!r}，整场失败")
        if f.code == SEAT_BLOCKED and not blocked_enabled:
            raise EngineError("未启用损坏禁坐却冒出 seat_blocked，整场失败")


def build_plan(
    rows: int, cols: int, min_dist: int, candidates: list[dict],
    blocked_seats=None, blocked_enabled: bool = False,
) -> dict:
    """一次排座，产出唯一真相 findings，并由它派生列表/计数/行说明。"""
    blocked = normalize_blocked(rows, cols, blocked_seats, blocked_enabled)
    meta = {int(c["id"]): c for c in candidates}

    assigns, unplaced_raw = place_candidates(rows, cols, min_dist, candidates, blocked)
    findings: list[Finding] = list(
        find_violations(rows, cols, min_dist, assigns, blocked)
    )

    # 未排 findings（已合法落座者绝不会出现在这里）。
    seated_ids = {a.candidate_id for a in assigns}
    for u in unplaced_raw:
        if u["id"] in seated_ids:  # 防御：已落座者不得挂未排原因
            raise EngineError(f"考生 {u['id']} 已落座却挂未排原因，整场失败")
        code = u["reason"]
        findings.append(Finding(
            code=code, scope=SCOPE_UNPLACED,
            detail=_detail(CAPACITY_FULL) if code == CAPACITY_FULL
            else _detail_unplaced(code),
            candidate_id=u["id"], paper_id=u["paper_id"],
        ))

    _assert_consistent(findings, blocked_enabled)

    return _derive(rows, cols, min_dist, assigns, findings, blocked, blocked_enabled, meta)


def _detail_unplaced(code: str) -> str:
    if code == SEAT_BLOCKED:
        return "受损坏禁坐座位影响，无座可排"
    if code == SAME_PAPER_ADJACENT:
        return "避开同卷相邻后无座可排"
    if code == DISTANCE:
        return "满足最小间距后无座可排"
    return _detail(CAPACITY_FULL)


def _derive(rows, cols, min_dist, assigns, findings, blocked, blocked_enabled, meta) -> dict:
    """所有三口（行说明 / 列表 / 计数）唯一的派生出口。"""
    viol_findings = [f for f in findings if f.scope == SCOPE_VIOLATION]
    unpl_findings = [f for f in findings if f.scope == SCOPE_UNPLACED]
    findex = {id(f): i for i, f in enumerate(findings)}

    # 每个落座考生涉及的违规（行说明直接引用同批 finding，不另写句子）。
    reasons_by_cand: dict[int, list[dict]] = {}
    for f in viol_findings:
        for cid in (f.a_id, f.b_id):
            if cid is None:
                continue
            reasons_by_cand.setdefault(cid, []).append(
                {"code": f.code, "detail": f.detail, "finding": findex[id(f)]}
            )

    assignments = []
    for a in assigns:
        d = asdict(a)
        d["reasons"] = reasons_by_cand.get(a.candidate_id, [])
        assignments.append(d)

    unplaced = []
    for f in unpl_findings:
        m = meta.get(f.candidate_id, {})
        unplaced.append({
            "candidate_id": f.candidate_id,
            "name": m.get("name"),
            "ticket_no": m.get("ticket_no"),
            "paper_id": f.paper_id,
            "reason": f.code,
            "detail": f.detail,
            "finding": findex[id(f)],
        })

    # 分类计数：纯粹对 findings 分桶 len，绝不另算。
    by_code = {code: 0 for code in ALL_CODES}
    violations_by_code = {code: 0 for code in VIOLATION_CODES}
    for f in findings:
        by_code[f.code] += 1
        if f.scope == SCOPE_VIOLATION:
            violations_by_code[f.code] += 1

    stats = {
        "seated": len(assigns),
        "unplaced": len(unplaced),
        "violations": len(viol_findings),
        "capacity": rows * cols,
        "by_code": by_code,
        "violations_by_code": violations_by_code,
    }

    result = {
        "rows": rows,
        "cols": cols,
        "min_dist": min_dist,
        "blocked_enabled": blocked_enabled,
        "blocked_seats": [{"row": r, "col": c} for r, c in sorted(blocked)],
        "ok": len(findings) == 0,
        "assignments": assignments,
        "findings": [asdict(f) for f in findings],
        "violations": [asdict(f) for f in viol_findings],
        "unplaced": unplaced,
        "stats": stats,
        "reason_codes": REASON_CODES,
    }
    _assert_derived(result)
    return result


def _assert_derived(result: dict) -> None:
    """派生结果自检：列表与计数必须可由 findings 复算，否则失败。"""
    findings = result["findings"]
    stats = result["stats"]
    # 列表一致性
    assert result["violations"] == [f for f in findings if f["scope"] == SCOPE_VIOLATION]
    assert len(result["unplaced"]) == sum(1 for f in findings if f["scope"] == SCOPE_UNPLACED)
    # 计数一致性（计数必须由列表派生）
    for code in ALL_CODES:
        assert stats["by_code"][code] == sum(1 for f in findings if f["code"] == code)
    for code in VIOLATION_CODES:
        assert stats["violations_by_code"][code] == sum(
            1 for f in findings if f["scope"] == SCOPE_VIOLATION and f["code"] == code
        )
    assert stats["violations"] == len(result["violations"])
    # 成功且列表为空 → 分类全 0
    if not findings:
        if any(stats["by_code"].values()) or any(stats["violations_by_code"].values()):
            raise EngineError("列表为空但分类计数非 0，三口对不齐")
        if stats["unplaced"] or stats["violations"]:
            raise EngineError("列表为空但未排/违规计数非 0，三口对不齐")
    # 未启用禁坐 → 禁坐计数必须为 0
    if not result["blocked_enabled"]:
        if stats["by_code"][SEAT_BLOCKED] or stats["violations_by_code"][SEAT_BLOCKED]:
            raise EngineError("未启用损坏禁坐但禁坐计数非 0，整场失败")
    # 已落座者不得出现在未排列表
    seated = {a["candidate_id"] for a in result["assignments"]}
    for u in result["unplaced"]:
        if u["candidate_id"] in seated:
            raise EngineError("已落座者挂了未排原因，整场失败")
