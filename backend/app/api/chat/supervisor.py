"""Supervisor Agent API — Multi-agent coordination endpoints.

支持：
- 启动 Supervisor 诊断任务
- 查询各 Agent 执行状态
- Supervisor 健康检查
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.agents.supervisor.supervisor_agent import (
    SupervisorAgent,
    RouteStrategy,
)
from app.agents.tools.builtin import create_default_registry

router = APIRouter(prefix="/supervisor", tags=["supervisor"])


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


# ── Request/Response Models ────────────────────────────────

class DiagnoseRequest(BaseModel):
    """Supervisor 诊断请求。"""
    user_query: str = Field("", description="用户问题描述")
    log_content: Optional[str] = Field(None, description="日志内容（可选）")
    log_file_path: Optional[str] = Field(None, description="日志文件路径（可选）")
    events: Optional[List[Dict[str, Any]]] = Field(None, description="预解析的事件列表")
    route_strategy: Optional[str] = Field("hybrid", description="路由策略: llm, keyword, hybrid")
    parallel: bool = Field(True, description="是否启用并行执行")
    max_agents: int = Field(5, description="最多执行的 Agent 数量")


class DiagnoseResponse(BaseModel):
    """Supervisor 诊断响应。"""
    success: bool
    summary: str
    agent_results: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    route_strategy: str


class HealthResponse(BaseModel):
    """Supervisor 健康检查响应。"""
    status: str
    total_agents: int
    healthy_agents: int
    agents: Dict[str, str]


# ── Supervisor 实例缓存 ───────────────────────────────────

_supervisor_instance: Optional[SupervisorAgent] = None


def get_supervisor(db: Session = Depends(get_db_session)) -> SupervisorAgent:
    """获取或创建 SupervisorAgent 实例。"""
    global _supervisor_instance
    if _supervisor_instance is None or _supervisor_instance.db is not db:
        registry = create_default_registry()
        _supervisor_instance = SupervisorAgent(
            tool_registry=registry,
            db=db,
            route_strategy=RouteStrategy.HYBRID,
            parallel_enabled=True,
        )
    return _supervisor_instance


# ── Endpoints ─────────────────────────────────────────────

@router.post("/diagnose", response_model=DiagnoseResponse)
def run_diagnosis(
    body: DiagnoseRequest,
    db: Session = Depends(get_db_session),
):
    """启动 Supervisor 多 Agent 诊断。

    请求示例：
    ```json
    {
      "user_query": "设备USB连接后频繁断开",
      "log_content": "...",
      "route_strategy": "hybrid",
      "parallel": true
    }
    ```
    """
    # 验证路由策略
    valid_strategies = {"llm", "keyword", "hybrid"}
    if body.route_strategy not in valid_strategies:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid route_strategy. Must be one of: {valid_strategies}",
        )

    # 读取日志文件（如果提供路径）
    log_content = body.log_content
    if body.log_file_path and not log_content:
        try:
            from pathlib import Path
            log_content = Path(body.log_file_path).read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Cannot read log file: {exc}")

    try:
        # 创建 Supervisor
        strategy = RouteStrategy(body.route_strategy)
        registry = create_default_registry()
        supervisor = SupervisorAgent(
            tool_registry=registry,
            db=db,
            route_strategy=strategy,
            parallel_enabled=body.parallel,
        )

        # 执行诊断
        result = supervisor.run(
            user_query=body.user_query,
            log_content=log_content or "",
            events=body.events or [],
        )

        # 提取 agent_results
        agent_results = result.steps if result.steps else []

        return DiagnoseResponse(
            success=result.success,
            summary=result.summary,
            agent_results=agent_results[:body.max_agents],
            metadata=result.metadata,
            route_strategy=body.route_strategy,
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Supervisor execution failed: {exc}")


@router.post("/route")
def route_only(
    body: DiagnoseRequest,
    db: Session = Depends(get_db_session),
):
    """仅执行路由分析，不运行 Agent — 用于预览路由结果。"""
    strategy = RouteStrategy(body.route_strategy or "hybrid")
    registry = create_default_registry()
    supervisor = SupervisorAgent(
        tool_registry=registry,
        db=db,
        route_strategy=strategy,
    )

    plan, strategy_used = supervisor.route_and_plan(
        user_query=body.user_query,
        log_content=body.log_content or "",
    )

    return {
        "strategy_used": strategy_used,
        "planned_agents": plan,
        "agent_count": len(plan),
        "available_agents": list(supervisor.specialized_agents.keys()),
    }


@router.get("/health", response_model=HealthResponse)
def supervisor_health(
    db: Session = Depends(get_db_session),
):
    """Supervisor 系统健康检查。"""
    registry = create_default_registry()
    supervisor = SupervisorAgent(
        tool_registry=registry,
        db=db,
    )

    health = supervisor.health_check()

    return HealthResponse(
        status=health.get("supervisor", "unknown"),
        total_agents=health.get("total", 0),
        healthy_agents=health.get("healthy_count", 0),
        agents=health.get("agents", {}),
    )


@router.get("/agents")
def list_available_agents(
    db: Session = Depends(get_db_session),
):
    """列出所有可用的专业 Agent 及其描述。"""
    registry = create_default_registry()
    supervisor = SupervisorAgent(
        tool_registry=registry,
        db=db,
    )

    return {
        "agents": [
            {
                "name": agent.name,
                "description": agent.description,
            }
            for agent in supervisor.specialized_agents.values()
        ],
        "total": len(supervisor.specialized_agents),
    }
