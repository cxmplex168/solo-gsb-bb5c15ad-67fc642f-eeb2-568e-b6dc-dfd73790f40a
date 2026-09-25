"""管网漏点隔离规划台 — FastAPI 入口。

API:
  GET  /api/network                 读取当前管网输入
  PUT  /api/network                 整体保存管网输入(校验后覆盖)
  POST /api/plan                    常规求解并保存方案
  POST /api/plan-failover           单阀失效备援求解并保存方案
  POST /api/plan-siting             新增阀门选址预览(只读计算, 不写管网与历史方案)
  GET  /api/plans                   最近方案列表
  GET  /api/plans/{id}              方案详情(含节点/管段状态)
  POST /api/plans/{id}/sequence     可行方案的现场执行顺序规划(只读计算)
  POST /api/demo                    恢复内置示例管网
  POST /api/clear                   清空管网输入
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

import database
from demo import DEMO_NETWORK
from solver import (MAX_CANDIDATES, MAX_VALVES, NetworkValidationError,
                    plan_sequence, solve, solve_failover, solve_siting)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class NodeIn(BaseModel):
    id: str = Field(min_length=1)
    role: Literal["inlet", "leak", "must_keep", "normal"] = "normal"
    label: str | None = None

    @field_validator("id")
    @classmethod
    def _strip_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("节点编号不能为空")
        return v


class SegmentIn(BaseModel):
    id: str = Field(min_length=1)
    endpoint_a: str = Field(min_length=1)
    endpoint_b: str = Field(min_length=1)

    @field_validator("id", "endpoint_a", "endpoint_b")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class ValveIn(BaseModel):
    id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    cost: int = Field(gt=0)

    @field_validator("id", "segment_id")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class NetworkIn(BaseModel):
    nodes: list[NodeIn] = Field(default_factory=list)
    segments: list[SegmentIn] = Field(default_factory=list)
    valves: list[ValveIn] = Field(default_factory=list, max_length=MAX_VALVES)


class SequenceIn(BaseModel):
    """执行顺序规划录入: 计划阀门操作时长 + 漏点漏水权重。

    值的正整数校验在 solver.plan_sequence 中逐条进行, 以便返回明确错误。
    """
    durations: dict[str, Any] = Field(default_factory=dict)
    leak_weights: dict[str, Any] = Field(default_factory=dict)


class CandidateIn(BaseModel):
    """选址预览候选位置: 无阀管段 + 唯一新阀编号 + 正整数安装费/关阀代价。"""
    id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    install_cost: int = Field(gt=0)
    close_cost: int = Field(gt=0)

    @field_validator("id", "segment_id")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class SitingIn(BaseModel):
    """选址预览请求: 管网部分可整体省略(用已保存管网), 候选位置 1~6 个。"""
    nodes: list[NodeIn] | None = None
    segments: list[SegmentIn] | None = None
    valves: list[ValveIn] | None = Field(default=None, max_length=MAX_VALVES)
    candidates: list[CandidateIn] = Field(min_length=1,
                                          max_length=MAX_CANDIDATES)


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield


app = FastAPI(title="管网漏点隔离规划台", version="1.0.0", lifespan=lifespan)


def _payload(net: NetworkIn) -> dict:
    return net.model_dump()


@app.get("/api/network")
def get_network() -> dict:
    with database.get_conn() as conn:
        return database.load_network(conn)


@app.put("/api/network")
def save_network(net: NetworkIn) -> dict:
    payload = _payload(net)
    try:
        # 提前用求解器的完整校验(端点存在、阀门绑定等), 保证保存的是有效管网
        from solver import validate_network
        validate_network(payload)
    except NetworkValidationError as exc:
        raise HTTPException(status_code=422, detail={"errors": exc.errors})
    with database.get_conn() as conn:
        database.replace_network(conn, payload)
    return {"ok": True, "counts": {
        "nodes": len(payload["nodes"]),
        "segments": len(payload["segments"]),
        "valves": len(payload["valves"]),
    }}


@app.post("/api/plan")
def create_plan(net: NetworkIn | None = None) -> dict:
    """常规求解。请求体可空: 为空时使用数据库中已保存的管网。"""
    with database.get_conn() as conn:
        payload = _payload(net) if net is not None else database.load_network(conn)
        try:
            result = solve(payload)
        except NetworkValidationError as exc:
            raise HTTPException(status_code=422,
                                detail={"errors": exc.errors})
        plan_id = database.save_plan(conn, result, payload)
    result["id"] = plan_id
    return result


@app.post("/api/plan-failover")
def create_failover_plan(net: NetworkIn | None = None) -> dict:
    """单阀失效备援求解(独立 API)。请求体可空: 为空时用已保存管网。

    要求计划关阀方案在正常执行及任意一枚计划阀门关不上(保持开启)时,
    全部漏点与进水点断开、全部必保点仍连通至少一个进水点。
    """
    with database.get_conn() as conn:
        payload = _payload(net) if net is not None else database.load_network(conn)
        try:
            result = solve_failover(payload)
        except NetworkValidationError as exc:
            raise HTTPException(status_code=422,
                                detail={"errors": exc.errors})
        plan_id = database.save_plan(conn, result, payload)
    result["id"] = plan_id
    return result


@app.post("/api/plan-siting")
def create_siting_preview(req: SitingIn) -> dict:
    """新增阀门选址预览(独立 API, 只读计算)。

    请求体: nodes/segments/valves 三者一起提交(当前编辑中的管网), 或全部
    省略(使用已保存管网); candidates 为 1~6 个候选位置。结果不写入管网,
    也不保存到历史方案。
    """
    given = [req.nodes is not None, req.segments is not None,
             req.valves is not None]
    if any(given) and not all(given):
        raise HTTPException(status_code=422, detail={"errors": [
            "nodes/segments/valves 需同时提供; 三者全部省略时使用已保存管网"
        ]})
    if all(given):
        payload = {
            "nodes": [n.model_dump() for n in req.nodes or []],
            "segments": [s.model_dump() for s in req.segments or []],
            "valves": [v.model_dump() for v in req.valves or []],
        }
    else:
        with database.get_conn() as conn:
            payload = database.load_network(conn)
    try:
        return solve_siting(payload,
                            [c.model_dump() for c in req.candidates])
    except NetworkValidationError as exc:
        raise HTTPException(status_code=422,
                            detail={"errors": exc.errors})


@app.get("/api/plans")
def get_plans(limit: int = 20) -> dict:
    limit = max(1, min(limit, 100))
    with database.get_conn() as conn:
        return {"plans": database.list_plans(conn, limit)}


@app.get("/api/plans/{plan_id}")
def get_plan(plan_id: int) -> dict:
    with database.get_conn() as conn:
        plan = database.get_plan(conn, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")
    return plan


@app.post("/api/plans/{plan_id}/sequence")
def plan_execution_sequence(plan_id: int, seq: SequenceIn) -> dict:
    """已保存可行方案的现场执行顺序规划(独立 API)。

    只读计算: 仅读取方案及其管网快照, 不修改、不新增任何数据。
    不可行方案、遗漏/多余编号、非正整数数值都会返回明确错误。
    """
    with database.get_conn() as conn:
        plan = database.get_plan(conn, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")
    if not plan.get("feasible"):
        reason = plan.get("reason_code")
        raise HTTPException(status_code=422, detail={"errors": [
            f"方案 #{plan_id} 为不可行方案"
            + (f"(reason_code: {reason})" if reason else "")
            + ", 没有可执行的关阀清单, 不能规划执行顺序"
        ]})
    try:
        result = plan_sequence(plan["network_snapshot"],
                               plan.get("closed_valves", []),
                               seq.durations, seq.leak_weights)
    except NetworkValidationError as exc:
        raise HTTPException(status_code=422, detail={"errors": exc.errors})
    result["plan_id"] = plan_id
    result["solver"] = plan.get("solver", "base")
    return result


@app.post("/api/demo")
def load_demo() -> dict:
    with database.get_conn() as conn:
        database.replace_network(conn, DEMO_NETWORK)
    return {"ok": True, "network": DEMO_NETWORK}


@app.post("/api/clear")
def clear_network() -> dict:
    with database.get_conn() as conn:
        database.replace_network(conn,
                                 {"nodes": [], "segments": [], "valves": []})
    return {"ok": True}


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


# ---- 静态页面 ----
STATIC_DIR = os.path.join(BASE_DIR, "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
