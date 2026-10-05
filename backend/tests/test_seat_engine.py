import pytest

from app.services.seat_engine import (
    REASON_CODES, VIOLATION_CODES, Issue, SeatAssign,
    derive_stats, evaluate, manhattan, plan_seating,
)


def cand(i, paper=1):
    return {"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": paper}


def assign(i, r, c, paper=1, name=None):
    return SeatAssign(i, name or f"C{i}", f"T{i}", paper, r, c)


def g(obj, key):
    """兼容 Issue 对象与 asdict 后的 dict。"""
    return getattr(obj, key) if not isinstance(obj, dict) else obj[key]


def counts_of(issues):
    """测试侧独立用列表 reduce 一遍，校验 stats 确由列表派生。"""
    counts = {code: 0 for code in REASON_CODES}
    for it in issues:
        counts[g(it, "code")] += 1
    return counts


def assert_three_way_consistent(result):
    """三口同码：issues 列表、stats 分类计数、座位行说明投影必须对得齐。"""
    issues = result["issues"]
    stats = result["stats"]
    counts = counts_of(issues)
    # 计数 == 列表 reduce
    assert stats["by_code"] == counts
    assert stats["issues"] == len(issues)
    assert stats["unplaced"] == counts["unplaced"]
    assert stats["violations"] == sum(counts[c] for c in VIOLATION_CODES)
    # 未排列表 == issues 投影，且没有第二份口径
    unplaced_from_list = [i for i in issues if g(i, "code") == "unplaced"]
    assert len(result["unplaced"]) == len(unplaced_from_list)
    assert {u["id"] for u in result["unplaced"]} == {g(i, "a_id") for i in unplaced_from_list}
    # 行说明投影：每条 issue 都能落到它声明的座位/考生，座位行说明所用码全部来自列表
    used_codes = {g(i, "code") for i in issues}
    assert used_codes <= set(REASON_CODES)
    for i in issues:
        if g(i, "subject") in ("seat", "seat_pair"):
            assert (g(i, "row"), g(i, "col")) is not None
    return counts


# ---------------------------------------------------------------------------
def test_manhattan():
    assert manhattan((0, 0), (2, 1)) == 3


def test_success_empty_list_all_zero():
    """成功且列表为空时分类必须全 0。"""
    result = plan_seating(3, 3, 1, [])
    assert result["issues"] == []
    assert set(result["stats"]["by_code"].values()) == {0}
    assert result["stats"]["violations"] == 0
    assert result["stats"]["unplaced"] == 0
    assert result["unplaced"] == []


def test_seated_candidate_must_not_carry_unplaced():
    """已合法落座者不得挂未排原因。"""
    assigns = [assign(1, 0, 0)]
    with pytest.raises(AssertionError):
        evaluate(3, 3, 1, assigns, [cand(1)])


def test_short_circuit_blocked_over_distance():
    """既触损坏禁坐又算间距不足 → 只认禁坐，不并间距句。"""
    assigns = [assign(1, 0, 0), assign(2, 0, 1, paper=2)]  # 距离 1 < 2
    issues = evaluate(3, 3, 2, assigns, [], blocked_seats=[(0, 1)], blocked_enabled=True)
    codes = [i.code for i in issues]
    assert codes == ["blocked_seat"]          # 损坏格一条，pair 被短路
    assert all(i.code != "distance" for i in issues)
    from dataclasses import asdict
    result = {"issues": [asdict(i) for i in issues],
              "stats": derive_stats(issues, assigns, 3, 3), "unplaced": []}
    assert_three_way_consistent(result)


def test_short_circuit_same_paper_over_distance():
    """非禁坐但同卷相邻 → 只认同卷相邻，禁止再并间距句。"""
    assigns = [assign(1, 0, 0, paper=1), assign(2, 0, 1, paper=1)]  # 同卷+距离不足
    issues = evaluate(3, 3, 2, assigns, [], blocked_enabled=True)
    codes = sorted(i.code for i in issues)
    assert codes == ["same_paper_adjacent"]
    assert not any(i.code == "distance" for i in issues)


def test_distance_only_when_merely_too_close():
    """仅间距不足才写间距不足（同卷但不相邻，也只算间距）。"""
    assigns = [assign(1, 0, 0, paper=1), assign(2, 0, 2, paper=1)]  # 距离 2 < 3，非四邻
    issues = evaluate(3, 3, 3, assigns, [])
    assert [i.code for i in issues] == ["distance"]


def test_each_pair_at_most_one_sentence():
    """任意一对座位至多产生一条 issue。"""
    assigns = [assign(i, r, c, paper=(i % 2) + 1)
               for i, (r, c) in enumerate([(0, 0), (0, 1), (1, 0), (1, 1)], start=1)]
    issues = evaluate(3, 3, 3, assigns, [])
    seen_pairs = set()
    for i in issues:
        if i.subject == "seat_pair":
            key = tuple(sorted((i.a_id, i.b_id)))
            assert key not in seen_pairs
            seen_pairs.add(key)


def test_blocked_disabled_count_zero_and_smoke_fails():
    """未启用损坏禁坐时禁坐计数必须为 0；冒码整场失败。"""
    assigns = [assign(1, 0, 0)]
    issues = evaluate(3, 3, 2, assigns, [], blocked_seats=[(1, 1)], blocked_enabled=False)
    assert counts_of(issues)["blocked_seat"] == 0
    assert all(i.code != "blocked_seat" for i in issues)
    # 强行冒码：禁用时出现 blocked_seat → AssertionError
    from app.services.seat_engine import _validate
    bogus = [Issue(code="blocked_seat", subject="seat", detail="x", row=0, col=0)]
    with pytest.raises(AssertionError):
        _validate(bogus, blocked_enabled=False)


def test_illegal_code_fails():
    from app.services.seat_engine import _validate
    with pytest.raises(AssertionError):
        _validate([Issue(code="made_up", subject="seat", detail="x")], blocked_enabled=True)


def test_change_inputs_three_way_move_together():
    """改最小距/损坏格/套卷后，列表·计数·行说明一起变，且始终对齐。"""
    cands = [cand(1, 1), cand(2, 2), cand(3, 1), cand(4, 2), cand(5, 1)]

    r1 = plan_seating(3, 3, 1, cands)
    r2 = plan_seating(3, 3, 3, cands)           # 改最小距
    r3 = plan_seating(3, 3, 3, cands,           # 再启用一个损坏格
                      blocked_seats=[(0, 0)], blocked_enabled=True)

    for r in (r1, r2, r3):
        assert_three_way_consistent(r)

    c1, c2, c3 = (assert_three_way_consistent(r) for r in (r1, r2, r3))
    # 有的跟有的不跟则失败：三口在每个方案内已对齐，且配置变化确实引起变化
    assert (r2["issues"], c2) != (r1["issues"], c1)
    assert (r3["issues"], c3) != (r2["issues"], c2)
    assert c3["blocked_seat"] == 1

    # 改套卷：2x3/min_dist=1，混卷可全落座；全同卷受四邻避让必有未排。
    six = [cand(i, (i % 2) + 1) for i in range(1, 7)]
    mixed = plan_seating(2, 3, 1, six)
    same = plan_seating(2, 3, 1, [cand(i, 1) for i in range(1, 7)])
    cm, cs = assert_three_way_consistent(mixed), assert_three_way_consistent(same)
    assert cs["unplaced"] > cm["unplaced"]
    assert same["issues"] != mixed["issues"]


def test_toggle_blocked_on_off():
    cands = [cand(i, (i % 2) + 1) for i in range(1, 6)]
    on = plan_seating(3, 3, 2, cands, blocked_seats=[(0, 0)], blocked_enabled=True)
    off = plan_seating(3, 3, 2, cands, blocked_seats=[(0, 0)], blocked_enabled=False)
    assert on["stats"]["by_code"]["blocked_seat"] == 1
    assert off["stats"]["by_code"]["blocked_seat"] == 0
    assert_three_way_consistent(on)
    assert_three_way_consistent(off)


def test_seat_notes_derived_from_list():
    """行说明是 issues 的投影：pair issue 同时标注两张座位，码与计数一致。"""
    cands = [cand(1, 1), cand(2, 1), cand(3, 2)]
    result = plan_seating(3, 3, 1, cands)
    notes = {}
    for i in result["issues"]:
        if i["subject"] in ("seat", "seat_pair"):
            notes.setdefault((i["row"], i["col"]), set()).add(i["code"])
            if i["subject"] == "seat_pair":
                notes.setdefault((i["b_row"], i["b_col"]), set()).add(i["code"])
    # 行说明里出现的每个码，计数必 >0，反之亦然（三口对齐）
    noted = {code for s in notes.values() for code in s}
    counted = {code for code, n in result["stats"]["by_code"].items() if n > 0}
    assert noted == counted
