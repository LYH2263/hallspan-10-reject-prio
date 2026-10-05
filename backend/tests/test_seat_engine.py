"""验收测试：违规/未排列表是唯一真相，行说明、列表、分类计数三口同码。

纯引擎层，无第三方依赖（可用 pytest，也可直接 python 运行）。
"""
from app.services.seat_engine import (
    ALL_CODES, CAPACITY_FULL, DISTANCE, SAME_PAPER_ADJACENT, SEAT_BLOCKED,
    VIOLATION_CODES, EngineError, SeatAssign, build_plan, classify_pair,
    find_violations, manhattan, place_candidates,
)


def C(i, p, name=None):
    return {"id": i, "name": name or f"C{i}", "ticket_no": f"T{i}", "paper_id": p}


# --- 基础 ----------------------------------------------------------------
def test_manhattan():
    assert manhattan((0, 0), (2, 1)) == 3


# --- 同一对座位只留一句短路 ----------------------------------------------
def test_blocked_short_circuits_distance():
    # 既触损坏禁坐又间距不足，只认禁坐。
    v = find_violations(2, 2, 2, [
        SeatAssign(1, "A", "t1", 1, 0, 0),
        SeatAssign(2, "B", "t2", 2, 0, 1),
    ], blocked={(0, 1)})
    assert [f.code for f in v] == [SEAT_BLOCKED]
    assert len(v) == 1
    assert "间距" not in v[0].detail


def test_same_paper_short_circuits_distance():
    # 非禁坐、同卷相邻：只认同卷相邻，禁止再并间距句。
    v = find_violations(2, 2, 2, [
        SeatAssign(1, "A", "t1", 1, 0, 0),
        SeatAssign(2, "B", "t2", 1, 0, 1),
    ], blocked=set())
    assert [f.code for f in v] == [SAME_PAPER_ADJACENT]
    assert len(v) == 1
    assert "曼哈顿" not in v[0].detail


def test_only_distance_when_distance_only():
    # 相邻但不同卷、非禁坐：仅间距不足才写间距不足。
    v = find_violations(2, 2, 2, [
        SeatAssign(1, "A", "t1", 1, 0, 0),
        SeatAssign(2, "B", "t2", 2, 0, 1),
    ], blocked=set())
    assert [f.code for f in v] == [DISTANCE]


def test_one_pair_one_finding_never_two():
    v = find_violations(3, 3, 3, [
        SeatAssign(1, "A", "t1", 1, 0, 0),
        SeatAssign(2, "B", "t2", 1, 0, 1),
    ])
    # 同卷相邻且距离不足，但每对最多一句。
    assert len(v) == 1


def test_classify_priority_order():
    # 直接验证优先级：禁坐 > 同卷相邻 > 间距。
    code, _ = classify_pair((0, 0), 1, (0, 1), 1, 2, 2, 2, {(0, 1)})
    assert code == SEAT_BLOCKED
    code, _ = classify_pair((0, 0), 1, (0, 1), 1, 2, 2, 2, set())
    assert code == SAME_PAPER_ADJACENT
    code, _ = classify_pair((0, 0), 1, (0, 1), 2, 2, 2, 2, set())
    assert code == DISTANCE
    code, _ = classify_pair((0, 0), 1, (2, 2), 2, 4, 4, 2, set())
    assert code is None


# --- 三口同码：行说明 == 列表 == 计数 ------------------------------------
def _recompute_tally(findings):
    return {code: sum(1 for f in findings if f["code"] == code) for code in ALL_CODES}


def test_counts_derived_from_list():
    r = build_plan(3, 3, 2, [C(1, 1), C(2, 1), C(3, 2), C(4, 1)])
    findings = r["findings"]
    # 计数必须等于对列表分桶。
    assert r["stats"]["by_code"] == _recompute_tally(findings)
    for code in VIOLATION_CODES:
        assert r["stats"]["violations_by_code"][code] == sum(
            1 for f in findings if f["scope"] == "violation" and f["code"] == code)
    assert r["stats"]["violations"] == sum(
        1 for f in findings if f["scope"] == "violation")


def test_row_detail_equals_list_detail():
    # 行说明（assignment.reasons）必须与列表里那条 finding 同码同句。
    r = build_plan(3, 3, 2, [C(1, 1), C(2, 1)])
    fmap = {}
    for f in r["findings"]:
        if f["scope"] == "violation":
            fmap.setdefault(f["code"], []).append(f)
    for a in r["assignments"]:
        for rs in a["reasons"]:
            fl = fmap[rs["code"]][0]
            assert rs["detail"] == fl["detail"]  # 三口同句
            assert a["candidate_id"] in (fl["a_id"], fl["b_id"])


def test_violations_and_unplaced_are_slices_of_findings():
    r = build_plan(2, 2, 2, [C(i, (i % 2) + 1) for i in range(1, 6)])
    assert r["violations"] == [f for f in r["findings"] if f["scope"] == "violation"]
    assert [f["candidate_id"] for f in r["findings"] if f["scope"] == "unplaced"] == \
           [u["candidate_id"] for u in r["unplaced"]]


# --- 成功且列表为空时分类必须全 0 ----------------------------------------
def test_empty_list_all_zero():
    r = build_plan(4, 4, 2, [C(1, 1), C(2, 2)])
    assert r["findings"] == []
    assert r["ok"] is True
    assert all(v == 0 for v in r["stats"]["by_code"].values())
    assert all(v == 0 for v in r["stats"]["violations_by_code"].values())
    assert r["stats"]["unplaced"] == 0 and r["stats"]["violations"] == 0


# --- 未启用损坏禁坐时禁坐计数必须为 0；冒码整场失败 ----------------------
def test_blocked_zero_when_disabled():
    # 即便传了损坏格，开关关闭也视为普通格，seat_blocked 必须为 0。
    r = build_plan(2, 2, 2, [C(1, 1), C(2, 2)],
                   blocked_seats=[{"row": 0, "col": 1}], blocked_enabled=False)
    assert r["blocked_seats"] == []
    assert r["stats"]["by_code"][SEAT_BLOCKED] == 0
    assert r["stats"]["violations_by_code"][SEAT_BLOCKED] == 0


def test_stray_blocked_code_when_disabled_fails():
    from app.services.seat_engine import Finding, _assert_consistent
    stray = Finding(code=SEAT_BLOCKED, scope="violation", detail="x", a_id=1, b_id=2)
    try:
        _assert_consistent([stray], blocked_enabled=False)
    except EngineError:
        return
    raise AssertionError("未启用禁坐却冒出 seat_blocked，必须整场失败")


def test_unknown_code_fails():
    from app.services.seat_engine import Finding, _assert_consistent
    bad = Finding(code="made_up_code", scope="violation", detail="x", a_id=1, b_id=2)
    try:
        _assert_consistent([bad], blocked_enabled=True)
    except EngineError:
        return
    raise AssertionError("未登记原因码必须整场失败")


# --- 已合法落座者不得挂未排原因 ------------------------------------------
def test_seated_candidate_has_no_unplaced_reason():
    r = build_plan(2, 2, 2, [C(i, (i % 2) + 1) for i in range(1, 6)])
    seated = {a["candidate_id"] for a in r["assignments"]}
    unplaced = {u["candidate_id"] for u in r["unplaced"]}
    assert seated.isdisjoint(unplaced)
    # 每个未排都必须带且只带一个来自统一码表的原因。
    for u in r["unplaced"]:
        assert u["reason"] in ALL_CODES
        assert u["detail"]


def test_capacity_full_reason():
    # 间距宽松仍超员：原因是满座，而非违规码。
    r = build_plan(2, 2, 1, [C(i, (i % 3) + 1) for i in range(1, 6)])
    assert any(u["reason"] == CAPACITY_FULL for u in r["unplaced"])
    assert r["stats"]["by_code"][CAPACITY_FULL] >= 1


# --- 启用禁坐时三口一致出现 blocked 视图 ---------------------------------
def test_enabled_blocked_reflected_everywhere():
    r = build_plan(2, 2, 2, [C(1, 1), C(2, 2), C(3, 1)],
                   blocked_seats=[{"row": 1, "col": 1}], blocked_enabled=True)
    assert {"row": 1, "col": 1} in r["blocked_seats"]
    # 计数与列表同源。
    assert r["stats"]["by_code"][SEAT_BLOCKED] == _recompute_tally(r["findings"])[SEAT_BLOCKED]


# --- 改损坏格 / 套卷 / 最小距后三口一起变 --------------------------------
def _self_consistent(r):
    # 任意结果都必须三口对齐。
    assert r["stats"]["by_code"] == _recompute_tally(r["findings"])
    assert r["stats"]["violations"] == len(r["violations"])
    assert r["stats"]["unplaced"] == len(r["unplaced"])


def test_change_min_dist_changes_three_views_together():
    # 2x2 中曼哈顿最大为 2：min_dist=3 只容 1 人，其余因间距未排；放宽到 1 全落座。
    cands = [C(1, 1), C(2, 2), C(3, 3), C(4, 4)]
    a = build_plan(2, 2, 3, cands)
    b = build_plan(2, 2, 1, cands)
    assert a["stats"]["unplaced"] == 3
    assert a["stats"]["by_code"][DISTANCE] >= 1
    assert b["findings"] == [] and b["stats"]["seated"] == 4
    _self_consistent(a)
    _self_consistent(b)


def test_change_paper_changes_three_views_together():
    # 1x3、min_dist=1（仅同卷相邻约束）：三人同卷时中间位因同卷相邻未排；
    # 第三人换卷后相邻合法，全部落座。
    before = [C(1, 1), C(2, 1), C(3, 1)]
    after = [C(1, 1), C(2, 1), C(3, 2)]
    a = build_plan(1, 3, 1, before)
    b = build_plan(1, 3, 1, after)
    assert a["stats"]["by_code"][SAME_PAPER_ADJACENT] >= 1
    assert a["stats"]["unplaced"] == 1
    assert b["findings"] == [] and b["stats"]["seated"] == 3
    _self_consistent(a)
    _self_consistent(b)


def test_toggle_blocked_changes_three_views_together():
    cands = [C(1, 1), C(2, 2), C(3, 1), C(4, 2)]
    off = build_plan(2, 2, 2, cands, blocked_seats=[], blocked_enabled=False)
    on = build_plan(2, 2, 2, cands,
                    blocked_seats=[{"row": 1, "col": 1}], blocked_enabled=True)
    assert off["stats"]["by_code"][SEAT_BLOCKED] == 0
    assert on["blocked_seats"] and on["blocked_enabled"]
    _self_consistent(off)
    _self_consistent(on)


# --- 排座本身尽量不产生违规（贪婪） --------------------------------------
def test_greedy_places_without_avoidable_violations():
    assigns, unplaced = place_candidates(
        3, 3, 2, [C(1, 1), C(2, 1), C(3, 2)])
    v = find_violations(3, 3, 2, assigns)
    assert not any(f.code == SAME_PAPER_ADJACENT for f in v)
    assert len(assigns) + len(unplaced) == 3


if __name__ == "__main__":
    # 无 pytest 环境下的直接运行器。
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
