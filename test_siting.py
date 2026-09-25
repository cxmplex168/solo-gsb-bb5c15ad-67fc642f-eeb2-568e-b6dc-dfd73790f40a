"""solve_siting 算法测试 + API 端到端测试(选址预览只读, 不写库)。"""
import itertools
import os
import random
import sys
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmp, "test_siting.db")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from solver import (  # noqa: E402
    MAX_CANDIDATES, MAX_VALVES, NetworkValidationError, _Graph,
    solve_siting, validate_network,
)
from demo import DEMO_NETWORK  # noqa: E402

passed = 0


def check(cond, msg):
    global passed
    assert cond, "FAIL: " + msg
    passed += 1


# ---- 1. 示例管网: 候选提供了但无需新增(安装费最小为 0) ----
r = solve_siting(DEMO_NETWORK, [
    {"id": "N1", "segment_id": "s1", "install_cost": 5, "close_cost": 1},
    {"id": "N2", "segment_id": "s2", "install_cost": 4, "close_cost": 2},
])
check(r["feasible"] and r["solver"] == "siting", "demo feasible")
check(r["new_valves"] == [] and r["install_cost"] == 0, "demo no new valve")
check(r["closed_valves"] == ["V2", "V4"] and r["close_cost"] == 7, "demo closed")
check(r["total_cost"] == 7, "demo total_cost == close_cost")
check(len(r["unused_candidates"]) == 2 and r["candidate_count"] == 2,
      "demo unused candidates")
check("无需新增阀门" in r["message"], "demo message")

# ---- 2. 只有新增阀门才能修复: 漏点唯一通路无阀 ----
NET_FIX = {
    "nodes": [
        {"id": "S", "role": "inlet"}, {"id": "L", "role": "leak"},
        {"id": "H", "role": "must_keep"},
    ],
    "segments": [
        {"id": "p1", "endpoint_a": "S", "endpoint_b": "L"},
        {"id": "p2", "endpoint_a": "S", "endpoint_b": "H"},
    ],
    "valves": [],
}
r = solve_siting(NET_FIX, [{"id": "N1", "segment_id": "p1",
                            "install_cost": 10, "close_cost": 3}])
check(r["feasible"], "fix feasible")
check([v["valve_id"] for v in r["new_valves"]] == ["N1"], "fix adopt N1")
check(r["new_valves"][0]["segment_id"] == "p1"
      and r["new_valves"][0]["install_cost"] == 10
      and r["new_valves"][0]["close_cost"] == 3, "fix new valve fields")
check(r["install_cost"] == 10 and r["close_cost"] == 3, "fix costs")
check(r["closed_valves"] == ["N1"], "fix closed")
st = {n["id"]: n["status"] for n in r["node_status"]}
check(st["L"] == "isolated" and st["H"] == "supplied", "fix node status")
seg_st = {s["id"]: s for s in r["segment_status"]}
check(seg_st["p1"]["status"] == "closed" and seg_st["p1"]["valve_id"] == "N1",
      "fix segment closed with new valve")

# ---- 3. 先最小化安装费: 现有阀代价 100 也优先于安装费 1 的新阀 ----
# S--p1(V1,代价100)--M--p2(候选N1)--L: 关 V1 或关 N1 各自都能隔离 L
NET_PRIO = {
    "nodes": [
        {"id": "S", "role": "inlet"}, {"id": "M", "role": "normal"},
        {"id": "L", "role": "leak"}, {"id": "H", "role": "must_keep"},
    ],
    "segments": [
        {"id": "p1", "endpoint_a": "S", "endpoint_b": "M"},
        {"id": "p2", "endpoint_a": "M", "endpoint_b": "L"},
        {"id": "h", "endpoint_a": "S", "endpoint_b": "H"},
    ],
    "valves": [{"id": "V1", "segment_id": "p1", "cost": 100}],
}
r = solve_siting(NET_PRIO, [{"id": "N1", "segment_id": "p2",
                             "install_cost": 1, "close_cost": 1}])
check(r["closed_valves"] == ["V1"] and r["install_cost"] == 0
      and r["close_cost"] == 100, "install cost minimized first")

# ---- 4. 安装费并列 -> 最小化本次关阀代价 ----
NET_TIE = {
    "nodes": [
        {"id": "S", "role": "inlet"}, {"id": "M", "role": "normal"},
        {"id": "L", "role": "leak"}, {"id": "H", "role": "must_keep"},
    ],
    "segments": [
        {"id": "a", "endpoint_a": "S", "endpoint_b": "M"},
        {"id": "b", "endpoint_a": "M", "endpoint_b": "L"},
        {"id": "h", "endpoint_a": "S", "endpoint_b": "H"},
    ],
    "valves": [],
}
r = solve_siting(NET_TIE, [
    {"id": "N1", "segment_id": "a", "install_cost": 5, "close_cost": 3},
    {"id": "N2", "segment_id": "b", "install_cost": 5, "close_cost": 2},
])
check(r["closed_valves"] == ["N2"] and r["close_cost"] == 2
      and r["install_cost"] == 5, "tie install -> min close cost")

# ---- 5. 安装费+关阀代价并列 -> 新增管段编号列表字典序 ----
r = solve_siting(NET_TIE, [
    {"id": "N1", "segment_id": "b", "install_cost": 5, "close_cost": 2},
    {"id": "N2", "segment_id": "a", "install_cost": 5, "close_cost": 2},
])
check(r["new_valves"][0]["segment_id"] == "a"
      and r["closed_valves"] == ["N2"], "tie -> segment id lexicographic")

# ---- 6. 新增管段也并列 -> 关阀编号列表字典序(V1 < V10) ----
NET_TIE2 = {
    "nodes": [
        {"id": "S", "role": "inlet"}, {"id": "X", "role": "normal"},
        {"id": "L", "role": "leak"}, {"id": "H", "role": "must_keep"},
    ],
    "segments": [
        {"id": "a", "endpoint_a": "S", "endpoint_b": "L"},
        {"id": "p1", "endpoint_a": "S", "endpoint_b": "X"},
        {"id": "p2", "endpoint_a": "X", "endpoint_b": "L"},
        {"id": "h", "endpoint_a": "S", "endpoint_b": "H"},
    ],
    "valves": [
        {"id": "V1", "segment_id": "p1", "cost": 5},
        {"id": "V10", "segment_id": "p2", "cost": 5},
    ],
}
r = solve_siting(NET_TIE2, [{"id": "N1", "segment_id": "a",
                             "install_cost": 3, "close_cost": 4}])
check(r["closed_valves"] == ["N1", "V1"],
      f"tie -> closed valve list lex {r['closed_valves']}")
check(r["install_cost"] == 3 and r["close_cost"] == 9, "tie2 costs")

# ---- 7. 录入校验 ----
def expect_siting_errors(net, cands, keys):
    try:
        solve_siting(net, cands)
    except NetworkValidationError as exc:
        joined = " | ".join(exc.errors)
        for key in keys:
            check(key in joined, f"error contains {key!r}; got: {exc.errors}")
        return
    raise AssertionError("should have raised: " + str(keys))


expect_siting_errors(DEMO_NETWORK, [], ["至少"])
expect_siting_errors(
    DEMO_NETWORK,
    [{"id": f"N{i}", "segment_id": f"x{i}", "install_cost": 1, "close_cost": 1}
     for i in range(MAX_CANDIDATES + 1)],
    ["超过上限"])
expect_siting_errors(DEMO_NETWORK, [
    {"id": "N1", "segment_id": "s3", "install_cost": 1, "close_cost": 1}],
    ["s3", "已绑定阀门", "V1"])
expect_siting_errors(DEMO_NETWORK, [
    {"id": "V1", "segment_id": "s1", "install_cost": 1, "close_cost": 1}],
    ["与现有阀门重复"])
expect_siting_errors(DEMO_NETWORK, [
    {"id": "N1", "segment_id": "s1", "install_cost": 1, "close_cost": 1},
    {"id": "N1", "segment_id": "s2", "install_cost": 1, "close_cost": 1}],
    ["新阀编号重复"])
expect_siting_errors(DEMO_NETWORK, [
    {"id": "N1", "segment_id": "s1", "install_cost": 1, "close_cost": 1},
    {"id": "N2", "segment_id": "s1", "install_cost": 1, "close_cost": 1}],
    ["重复选为候选"])
expect_siting_errors(DEMO_NETWORK, [
    {"id": "N1", "segment_id": "zz", "install_cost": 1, "close_cost": 1}],
    ["管段 zz 不存在"])
expect_siting_errors(DEMO_NETWORK, [
    {"id": "", "segment_id": "s1", "install_cost": 1, "close_cost": 1}],
    ["缺少新阀编号"])
expect_siting_errors(DEMO_NETWORK, [
    {"id": "N1", "segment_id": "s1", "install_cost": 0, "close_cost": 1}],
    ["安装费", "正整数"])
expect_siting_errors(DEMO_NETWORK, [
    {"id": "N1", "segment_id": "s1", "install_cost": 2, "close_cost": -1}],
    ["关阀代价", "正整数"])
expect_siting_errors(DEMO_NETWORK, [
    {"id": "N1", "segment_id": "s1", "install_cost": 1.5, "close_cost": 1}],
    ["正整数"])
expect_siting_errors(DEMO_NETWORK, [
    {"id": "N1", "segment_id": "s1", "install_cost": 1, "close_cost": "x"}],
    ["正整数"])

# 现有阀门 + 候选 > 14 -> 报错; 恰好 14 -> 可解
CHAIN_NODES = ([{"id": "S", "role": "inlet"}]
               + [{"id": f"m{i}", "role": "normal"} for i in range(12)]
               + [{"id": "L", "role": "leak"},
                  {"id": "H", "role": "must_keep"}])
CHAIN_IDS = ["S"] + [f"m{i}" for i in range(12)] + ["L"]
CHAIN_SEGS = [{"id": f"e{i}", "endpoint_a": CHAIN_IDS[i],
               "endpoint_b": CHAIN_IDS[i + 1]} for i in range(13)]
CHAIN_SEGS.append({"id": "h", "endpoint_a": "S", "endpoint_b": "H"})
CHAIN_SEGS.append({"id": "x1", "endpoint_a": "S", "endpoint_b": "m0"})
CHAIN_SEGS.append({"id": "x2", "endpoint_a": "m0", "endpoint_b": "m1"})
net13 = {"nodes": CHAIN_NODES, "segments": CHAIN_SEGS,
         "valves": [{"id": f"V{i+1}", "segment_id": f"e{i}", "cost": 1}
                    for i in range(13)]}
expect_siting_errors(net13, [
    {"id": "N1", "segment_id": "x1", "install_cost": 1, "close_cost": 1},
    {"id": "N2", "segment_id": "x2", "install_cost": 1, "close_cost": 1}],
    ["合计超过上限", "14"])

net12 = {"nodes": CHAIN_NODES, "segments": CHAIN_SEGS,
         "valves": [{"id": f"V{i+1}", "segment_id": f"e{i}", "cost": 1}
                    for i in range(12)]}
r = solve_siting(net12, [
    {"id": "N1", "segment_id": "x1", "install_cost": 1, "close_cost": 1},
    {"id": "N2", "segment_id": "x2", "install_cost": 1, "close_cost": 1}])
check(r["feasible"] and r["subset_count"] == 2 ** MAX_VALVES,
      "exactly 14 valves enumerated")
# 安装费 0 优先: 不关任何候选阀。x1/x2 是无阀旁路, V1/V2 单独关闭切不断
# 主链; V3..V12 单独关闭均可行(代价同为 1), 字典序最小为 V10
check(r["install_cost"] == 0 and r["closed_valves"] == ["V10"],
      f"14-valve result {r['closed_valves']}")

# ---- 8. 无解: 候选范围内不可修复 ----
NET_BAD = {
    "nodes": [
        {"id": "S", "role": "inlet"}, {"id": "L", "role": "leak"},
        {"id": "H", "role": "must_keep"},
    ],
    "segments": [
        {"id": "p1", "endpoint_a": "S", "endpoint_b": "L"},
        {"id": "p2", "endpoint_a": "S", "endpoint_b": "L"},
        {"id": "h", "endpoint_a": "S", "endpoint_b": "H"},
    ],
    "valves": [],
}
r = solve_siting(NET_BAD, [{"id": "N1", "segment_id": "p1",
                            "install_cost": 1, "close_cost": 1}])
check(not r["feasible"] and r["solver"] == "siting", "uncuttable tag")
check(r["reason_code"] == "UNCUTTABLE_LEAK_PATH", "uncuttable code")
check("候选范围内不可修复" in r["message"], "uncuttable message")
check(r["reason_detail"]["witness_path"], "uncuttable witness")

# 关阀才能隔离漏点, 但唯一可关位置在必保点上游 -> 冲突
NET_CONFLICT = {
    "nodes": [
        {"id": "S", "role": "inlet"}, {"id": "M", "role": "normal"},
        {"id": "L", "role": "leak"}, {"id": "H", "role": "must_keep"},
    ],
    "segments": [
        {"id": "a", "endpoint_a": "S", "endpoint_b": "M"},
        {"id": "b", "endpoint_a": "M", "endpoint_b": "L"},
        {"id": "c", "endpoint_a": "M", "endpoint_b": "H"},
    ],
    "valves": [],
}
r = solve_siting(NET_CONFLICT, [{"id": "N1", "segment_id": "a",
                                 "install_cost": 1, "close_cost": 1}])
check(not r["feasible"] and r["reason_code"] == "GUARANTEED_CONFLICT",
      "conflict code")
check("候选范围内不可修复" in r["message"], "conflict message")

# 无进水点 / 必保点本来就断水
NET_NOINLET = {
    "nodes": [{"id": "L", "role": "leak"}, {"id": "H", "role": "must_keep"}],
    "segments": [{"id": "p", "endpoint_a": "L", "endpoint_b": "H"}],
    "valves": [],
}
r = solve_siting(NET_NOINLET, [{"id": "N1", "segment_id": "p",
                                "install_cost": 1, "close_cost": 1}])
check(not r["feasible"] and r["reason_code"] == "NO_INLET", "no inlet")
check("候选范围内不可修复" in r["message"], "no inlet message")

NET_STARVED = {
    "nodes": [
        {"id": "S", "role": "inlet"}, {"id": "L", "role": "leak"},
        {"id": "H", "role": "must_keep"},
    ],
    "segments": [{"id": "p", "endpoint_a": "S", "endpoint_b": "L"}],
    "valves": [],
}
r = solve_siting(NET_STARVED, [{"id": "N1", "segment_id": "p",
                                "install_cost": 1, "close_cost": 1}])
check(not r["feasible"]
      and r["reason_code"] == "GUARANTEED_ALREADY_DISCONNECTED", "starved")
check("候选范围内不可修复" in r["message"], "starved message")

# ---- 9. 无漏点: 无需增设或关闭 ----
NET_NOLEAK = {
    "nodes": [{"id": "S", "role": "inlet"}, {"id": "H", "role": "must_keep"}],
    "segments": [{"id": "p", "endpoint_a": "S", "endpoint_b": "H"}],
    "valves": [],
}
r = solve_siting(NET_NOLEAK, [{"id": "N1", "segment_id": "p",
                               "install_cost": 5, "close_cost": 1}])
check(r["feasible"] and r["closed_valves"] == [] and r["new_valves"] == [],
      "no leak empty plan")
check(r["install_cost"] == 0 and r["close_cost"] == 0, "no leak zero cost")

# ---- 10. 随机对拍: 独立组合暴力验证最优键 ----
def siting_bruteforce(net, cands):
    """独立暴力枚举(按大小组合), 返回最优 key 或 None(无可行)。"""
    nodes, segments, valves = validate_network(net)
    cand_by_seg = {c["segment_id"]: c for c in cands}
    aug_segments = []
    for sg in segments:
        sg2 = dict(sg)
        cd = cand_by_seg.get(sg["id"])
        if cd is not None:
            sg2["valve_id"] = cd["id"]
        aug_segments.append(sg2)
    aug_valves = valves + [{"id": c["id"], "cost": c["close_cost"],
                            "segment_id": c["segment_id"]} for c in cands]
    g = _Graph(nodes, aug_segments, aug_valves)
    v_idx = {vl["id"]: i for i, vl in enumerate(g.valves_sorted)}
    install_of = {c["id"]: c["install_cost"] for c in cands}
    seg_of = {vl["id"]: vl["segment_id"] for vl in aug_valves}
    cost_of = {vl["id"]: vl["cost"] for vl in aug_valves}
    vids = sorted(v_idx)
    best = None
    for size in range(len(vids) + 1):
        for combo in itertools.combinations(vids, size):
            mask = 0
            for vid in combo:
                mask |= 1 << v_idx[vid]
            fed = g.reachable(mask, g.inlet_set)
            if (fed & g.leak_bits) != 0:
                continue
            if (fed & g.keep_bits) != g.keep_bits:
                continue
            key = (sum(install_of.get(v, 0) for v in combo),
                   sum(cost_of[v] for v in combo),
                   tuple(sorted(seg_of[v] for v in combo
                                if v in install_of)),
                   tuple(sorted(combo)))
            if best is None or key < best:
                best = key
    return best


rng = random.Random(20260925)
for trial in range(50):
    n = rng.randint(3, 8)
    node_ids = [f"n{i}" for i in range(n)]
    roles = ["inlet"]
    n_leak = rng.randint(1, 2)
    roles += ["leak"] * n_leak
    n_keep = rng.randint(0, 2)
    roles += ["must_keep"] * n_keep
    roles += ["normal"] * (n - len(roles))
    rng.shuffle(roles)
    role_map = dict(zip(node_ids, roles))
    if "inlet" not in role_map.values():
        role_map[node_ids[0]] = "inlet"
    seg_list = []
    order = node_ids[:]
    rng.shuffle(order)
    used = [order[0]]
    si = 0
    for u in order[1:]:
        v = rng.choice(used)
        seg_list.append({"id": f"e{si}", "endpoint_a": u, "endpoint_b": v})
        used.append(u)
        si += 1
    for _ in range(rng.randint(0, 4)):
        a, b = rng.sample(node_ids, 2)
        seg_list.append({"id": f"e{si}", "endpoint_a": a, "endpoint_b": b})
        si += 1
    k = rng.randint(0, min(6, len(seg_list)))
    chosen = rng.sample(seg_list, k) if k else []
    valve_list = [{"id": f"V{i+1}", "segment_id": sg["id"],
                   "cost": rng.randint(1, 9)}
                  for i, sg in enumerate(chosen)]
    free_segs = [sg for sg in seg_list if sg not in chosen]
    nc = rng.randint(1, min(MAX_CANDIDATES, len(free_segs))) if free_segs else 0
    if nc == 0 or k + nc > MAX_VALVES:
        continue
    cand_segs = rng.sample(free_segs, nc)
    cands = [{"id": f"N{i+1}", "segment_id": sg["id"],
              "install_cost": rng.randint(1, 9),
              "close_cost": rng.randint(1, 9)}
             for i, sg in enumerate(cand_segs)]
    net = {"nodes": [{"id": nid, "role": role_map[nid]} for nid in node_ids],
           "segments": seg_list, "valves": valve_list}
    res = solve_siting(net, cands)
    best = siting_bruteforce(net, cands)
    if best is None:
        check(not res["feasible"], f"trial {trial}: expected infeasible")
        check("候选范围内不可修复" in res["message"]
              or res["reason_code"] in ("NO_INLET",
                                        "GUARANTEED_ALREADY_DISCONNECTED"),
              f"trial {trial}: infeasible message")
        continue
    check(res["feasible"], f"trial {trial}: expected feasible")
    got = (res["install_cost"], res["close_cost"],
           tuple(v["segment_id"] for v in res["new_valves"]),
           tuple(res["closed_valves"]))
    check(got == best, f"trial {trial}: {got} != brute {best}")
    # 安装费只计实际关闭的候选阀
    adopted_ids = {v["valve_id"] for v in res["new_valves"]}
    check(sum(c["install_cost"] for c in cands
              if c["id"] in adopted_ids) == res["install_cost"],
          f"trial {trial}: install accounting")
    check({c["valve_id"] for c in res["unused_candidates"]}
          == {c["id"] for c in cands} - adopted_ids,
          f"trial {trial}: unused candidates")
    # 关阀清单 = 现有关闭 + 新增关闭
    check(set(res["closed_valves"]) >= adopted_ids,
          f"trial {trial}: closed contains new valves")

print(f"siting solver tests: {passed} checks passed")

# ===========================================================================
# API 端到端测试
# ===========================================================================
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

client = TestClient(main.app).__enter__()

r = client.get("/api/health")
check(r.status_code == 200, "api health")

plans_before = client.get("/api/plans?limit=100").json()["plans"]
net_before = client.get("/api/network").json()

# 显式提交管网 + 候选
r = client.post("/api/plan-siting", json={**NET_FIX, "candidates": [
    {"id": "N1", "segment_id": "p1", "install_cost": 10, "close_cost": 3}]})
check(r.status_code == 200, f"api siting {r.status_code} {r.text}")
res = r.json()
check(res["feasible"] and res["solver"] == "siting", "api feasible")
check(res["install_cost"] == 10 and res["close_cost"] == 3, "api costs")
check(res["new_valves"][0]["valve_id"] == "N1"
      and res["new_valves"][0]["segment_id"] == "p1", "api new valve")
check(res["closed_valves"] == ["N1"], "api closed")
check(res["node_status"] and res["segment_status"], "api statuses")
check("id" not in res, "api result has no plan id (not saved)")

# 只读: 历史方案与管网均未变化
check(client.get("/api/plans?limit=100").json()["plans"] == plans_before,
      "plans unchanged after siting")
check(client.get("/api/network").json() == net_before,
      "network unchanged after siting")

# 省略管网部分 -> 使用已保存管网(示例管网)
r = client.post("/api/plan-siting", json={"candidates": [
    {"id": "N1", "segment_id": "s1", "install_cost": 5, "close_cost": 1},
    {"id": "N2", "segment_id": "s2", "install_cost": 4, "close_cost": 2}]})
check(r.status_code == 200, f"api saved net {r.status_code} {r.text}")
res = r.json()
check(res["feasible"] and res["install_cost"] == 0
      and res["closed_valves"] == ["V2", "V4"], "api saved net result")
check(res["candidate_count"] == 2 and len(res["unused_candidates"]) == 2,
      "api unused candidates")

# 部分提供管网 -> 422
r = client.post("/api/plan-siting", json={"nodes": [], "candidates": [
    {"id": "N1", "segment_id": "s1", "install_cost": 1, "close_cost": 1}]})
check(r.status_code == 422, f"partial network {r.status_code}")

# 候选数量非法: 0 个 / 超过 6 个 / 缺失字段
r = client.post("/api/plan-siting", json={"candidates": []})
check(r.status_code == 422, "empty candidates 422")
r = client.post("/api/plan-siting", json={"candidates": [
    {"id": f"N{i}", "segment_id": f"x{i}", "install_cost": 1, "close_cost": 1}
    for i in range(7)]})
check(r.status_code == 422, "too many candidates 422")
r = client.post("/api/plan-siting", json={})
check(r.status_code == 422, "missing candidates 422")

# 安装费/关阀代价非正整数(Pydantic 层, 与现有阀门代价字段行为一致;
# bool 会被 Pydantic 强制转为 int, solver 层 _positive_int 拒绝 bool
# 的情形见上方 solver 测试)
for bad in [0, -1, 1.5, "x", None]:
    r = client.post("/api/plan-siting", json={"candidates": [
        {"id": "N1", "segment_id": "s1", "install_cost": bad,
         "close_cost": 1}]})
    check(r.status_code == 422, f"bad install {bad!r} -> {r.status_code}")
    r = client.post("/api/plan-siting", json={"candidates": [
        {"id": "N1", "segment_id": "s1", "install_cost": 1,
         "close_cost": bad}]})
    check(r.status_code == 422, f"bad close {bad!r} -> {r.status_code}")

# 候选管段已有阀门(solver 校验, errors 逐条)
r = client.post("/api/plan-siting", json={"candidates": [
    {"id": "N1", "segment_id": "s3", "install_cost": 1, "close_cost": 1}]})
check(r.status_code == 422, "valved segment 422")
errs = r.json()["detail"]["errors"]
check(any("s3" in e and "已绑定阀门" in e for e in errs),
      f"valved segment err {errs}")

# 新阀编号与现有阀门重复
r = client.post("/api/plan-siting", json={"candidates": [
    {"id": "V1", "segment_id": "s1", "install_cost": 1, "close_cost": 1}]})
check(r.status_code == 422 and "与现有阀门重复" in r.text, "dup valve id 422")

# 无解: 候选范围内不可修复
r = client.post("/api/plan-siting", json={**NET_BAD, "candidates": [
    {"id": "N1", "segment_id": "p1", "install_cost": 1, "close_cost": 1}]})
check(r.status_code == 200, "infeasible returns 200")
res = r.json()
check(res["feasible"] is False and res["solver"] == "siting",
      "infeasible solver tag")
check(res["reason_code"] == "UNCUTTABLE_LEAK_PATH", "infeasible code")
check("候选范围内不可修复" in res["message"], "infeasible message")

# 再次确认只读: 历史方案与管网仍未变化
check(client.get("/api/plans?limit=100").json()["plans"] == plans_before,
      "plans unchanged at end")
check(client.get("/api/network").json() == net_before,
      "network unchanged at end")

print(f"siting API tests: {passed} checks passed (cumulative)")
