"""
CLI tool: diag

Usage:
    diag analyze test.log
    diag chat "What caused this kernel panic?"
    diag upload /path/to/logs/*.log
    diag search "kernel panic"
    diag stats
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

from .client import DiagnosticClient

console = Console()


def get_client() -> DiagnosticClient:
    """从环境变量创建客户端"""
    base_url = os.environ.get("DIAG_API_URL", "http://localhost:8000/api/v1")
    token = os.environ.get("DIAG_TOKEN", "")

    client = DiagnosticClient(base_url)
    if token:
        client.set_token(token)
    return client


def login_interactive(client: DiagnosticClient) -> bool:
    """交互式登录"""
    if client._token:
        return True

    username = os.environ.get("DIAG_USERNAME", "")
    password = os.environ.get("DIAG_PASSWORD", "")

    if not username:
        username = click.prompt("用户名", type=str)
    if not password:
        password = click.prompt("密码", type=str, hide_input=True)

    try:
        client.login(username, password)
        console.print("[green]✓ 登录成功[/green]")
        return True
    except Exception as e:
        console.print(f"[red]✗ 登录失败: {e}[/red]")
        return False


@click.group()
@click.version_option(version="1.0.0", prog_name="diag")
def main():
    """AI Diagnostic Platform CLI - 智能故障诊断工具

    环境变量:
      DIAG_API_URL     API 地址（默认 http://localhost:8000/api/v1）
      DIAG_TOKEN       JWT Token（可选）
      DIAG_USERNAME    用户名（可选）
      DIAG_PASSWORD    密码（可选）
    """
    pass


@main.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--model", "-m", default="deepseek-v4-flash", help="模型名称")
@click.option("--query", "-q", default="请分析此日志中的错误", help="分析查询")
@click.option("--wait/--no-wait", default=True, help="等待分析完成")
def analyze(file: str, model: str, query: str, wait: bool):
    """上传并分析日志文件

    \b
    Examples:
      diag analyze test.log
      diag analyze kernel.log -m deepseek-v4-pro -q "分析 kernel panic 原因"
      diag analyze system.log --no-wait
    """
    client = get_client()
    if not login_interactive(client):
        sys.exit(1)

    path = Path(file)
    console.print(f"[bold]上传日志: {path.name}[/bold]")

    try:
        if wait:
            with console.status("[cyan]分析中...[/cyan]"):
                result = client.analyze_log(path, model, query)

            console.print()
            if result.status == "completed":
                console.print(Panel.fit(
                    f"[green]✓ 分析完成 (置信度: {(result.confidence or 0) * 100:.0f}%)[/green]",
                    border_style="green",
                ))
                console.print()
                console.print(Markdown(result.diagnosis_markdown or result.summary or "无分析结果"))

                if result.root_cause:
                    console.print(f"\n[bold]根因:[/bold] {result.root_cause}")
                if result.next_steps:
                    console.print("\n[bold]建议措施:[/bold]")
                    for i, step in enumerate(result.next_steps, 1):
                        console.print(f"  {i}. {step}")
            else:
                console.print(f"[red]✗ 分析失败: {result.status}[/red]")
                console.print(result.summary)
        else:
            upload = client.upload_log(path, query)
            log_id = upload.get("id")
            analysis = client.run_analysis(log_id, model, query)
            console.print(f"[green]✓ 已提交分析任务[/green]")
            console.print(f"  日志 ID: {log_id}")
            console.print(f"  分析 ID: {analysis.get('id')}")
            console.print(f"  状态: {analysis.get('status', 'pending')}")

    except Exception as e:
        console.print(f"[red]✗ 错误: {e}[/red]")
        sys.exit(1)
    finally:
        client.close()


@main.command()
@click.argument("message", type=str)
@click.option("--model", "-m", default="deepseek-v4-flash", help="模型名称")
@click.option("--session", "-s", type=int, default=None, help="会话 ID（可选，不指定则新建）")
def chat(message: str, model: str, session: Optional[int]):
    """发送对话消息

    \b
    Examples:
      diag chat "什么是 kernel panic？"
      diag chat "这个错误怎么修复？" -s 42
    """
    client = get_client()
    if not login_interactive(client):
        sys.exit(1)

    try:
        if session is None:
            s = client.create_session("CLI 对话", model)
            session = s.id
            console.print(f"[dim]新会话: {s.title} (ID={session})[/dim]")

        reply = client.chat(session, message, model)
        console.print()
        console.print(Markdown(reply.content))
        console.print()
        console.print(f"[dim]会话 ID: {session}[/dim]")

    except Exception as e:
        console.print(f"[red]✗ 错误: {e}[/red]")
        sys.exit(1)
    finally:
        client.close()


@main.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True), required=True)
def upload(files):
    """批量上传日志文件

    \b
    Examples:
      diag upload test.log
      diag upload logs/*.log
    """
    client = get_client()
    if not login_interactive(client):
        sys.exit(1)

    table = Table(title="上传结果")
    table.add_column("文件", style="cyan")
    table.add_column("日志 ID", style="green")
    table.add_column("状态", style="yellow")

    for f in files:
        path = Path(f)
        try:
            result = client.upload_log(path)
            table.add_row(path.name, str(result.get("id", "-")), "✓")
        except Exception as e:
            table.add_row(path.name, "-", f"[red]✗ {e}[/red]")

    console.print(table)
    client.close()


@main.command()
@click.argument("query", type=str)
@click.option("--type", "-t", "search_type", default="all", help="搜索类型 (all/logs/knowledge/analyses)")
@click.option("--limit", "-l", default=10, help="返回数量")
def search(query: str, search_type: str, limit: int):
    """搜索知识库和日志

    \b
    Examples:
      diag search "kernel panic"
      diag search "USB error" -t logs -l 5
    """
    client = get_client()
    if not login_interactive(client):
        sys.exit(1)

    try:
        results = client.search(query, search_type, limit)
        console.print(f"[bold]搜索结果: \"{query}\"[/bold]")
        console.print_json(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    except Exception as e:
        console.print(f"[yellow]统一搜索 API 不可用: {e}[/yellow]")
        console.print("[dim]尝试分别搜索...[/dim]")

        try:
            kb = client.search_knowledge(query, limit)
            if kb:
                console.print(f"\n[bold]知识库结果:[/bold]")
                console.print_json(json.dumps(kb, ensure_ascii=False, indent=2, default=str))
        except Exception:
            console.print("[dim]知识库搜索不可用[/dim]")

    finally:
        client.close()


@main.command()
def stats():
    """查看系统统计

    \b
    Examples:
      diag stats
    """
    client = get_client()
    if not login_interactive(client):
        sys.exit(1)

    try:
        data = client.get_stats()
        table = Table(title="系统概览")
        table.add_column("指标", style="cyan")
        table.add_column("值", style="green")

        metrics = [
            ("用户总数", data.get("total_users", "-")),
            ("项目数", data.get("total_projects", "-")),
            ("日志总数", data.get("total_logs", "-")),
            ("分析任务", data.get("total_analyses", "-")),
            ("已完成", data.get("analysis_completed", "-")),
            ("失败", data.get("analysis_failed", "-")),
            ("知识文档", data.get("total_knowledge", "-")),
            ("活跃插件", data.get("active_plugins", "-")),
        ]

        for label, value in metrics:
            table.add_row(label, str(value))

        console.print(table)

    except Exception as e:
        console.print(f"[red]✗ 错误: {e}[/red]")
        sys.exit(1)
    finally:
        client.close()


@main.command()
@click.option("--username", "-u", prompt=True, help="用户名")
@click.option("--password", "-p", prompt=True, hide_input=True, help="密码")
def login(username: str, password: str):
    """登录并获取 token

    \b
    Examples:
      diag login
      diag login -u admin -p secret
    """
    client = get_client()
    try:
        token = client.login(username, password)
        console.print(f"[green]✓ 登录成功[/green]")
        console.print(f"[bold]Token:[/bold] {token}")
        console.print()
        console.print("[dim]设置环境变量以复用:[/dim]")
        console.print(f"  export DIAG_TOKEN={token}")
    except Exception as e:
        console.print(f"[red]✗ 登录失败: {e}[/red]")
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
