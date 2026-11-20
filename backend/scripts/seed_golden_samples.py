"""黄金集初版种子（20+ 条，管理员提交即生效）。

来源：现有知识库章节主题（每条都对应真实存在的文档与章节），
外加一条已确认的真实失败样本与两条负样本。

用法::

    python -m scripts.seed_golden_samples --dry-run
    python -m scripts.seed_golden_samples            # 写入库（管理员身份，直接 approved）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# (问题, 期望文档 id, 期望章节主题词, 类别, 期望结论)
SEED: List[Dict[str, Any]] = [
    # ── 线路（doc 36）──────────────────────────────────────────
    {"q": "进出站日志中搜索什么", "doc": 36, "section": "查看设备是否有进出站", "cat": "线路"},
    {"q": "车辆反向运行了但没有切换方向，日志查什么", "doc": 36, "section": "反向运行切换方向", "cat": "线路"},
    {"q": "GPS 未定位的时候限速值是多少", "doc": 36, "section": "gps 未定位时限速值", "cat": "线路"},
    {"q": "设备经过分段限速却没有用分段限速值", "doc": 36, "section": "分段限速未使用", "cat": "线路"},
    {"q": "速度超过限速但没有报开始超速，怎么回事", "doc": 36, "section": "速度超过限速但未报开始超速", "cat": "线路"},
    {"q": "车辆偏离线路了怎么排查", "doc": 36, "section": "偏离线路", "cat": "线路"},
    # ── 超速 / 客流 ────────────────────────────────────────────
    {"q": "超速报警的判定规则是什么", "doc": 8, "section": "超速规则", "cat": "超速"},
    {"q": "客流数据什么时候上报、什么时候清空", "doc": 9, "section": "客流逻辑", "cat": "客流"},
    # ── 协议 ──────────────────────────────────────────────────
    {"q": "JT808 设备注册失败怎么排查", "doc": 31, "section": "JT808协议设备注册", "cat": "协议"},
    {"q": "JT1078 指令队列相关的日志关键字有哪些", "doc": 32, "section": "指令队列日志关键字", "cat": "协议"},
    {"q": "录像导出标志是什么意思", "doc": 32, "section": "录像导出标志", "cat": "协议"},
    {"q": "录像文件什么时候开始封装成 MP4", "doc": 33, "section": "录像开始封装为MP4", "cat": "录像"},
    {"q": "苏标设备怎么判断告警要不要上传平台", "doc": 33, "section": "苏标判断告警是否要上传平台", "cat": "录像"},
    # ── 平台对接 / TMP ─────────────────────────────────────────
    {"q": "启迪云控连接平台失败怎么分析", "doc": 35, "section": "启迪云控连接平台分析", "cat": "平台对接"},
    {"q": "TMP 下载文件怎么分析", "doc": 30, "section": "下载文件分析", "cat": "TMP"},
    {"q": "TMP 收到 0x20003 修改车辆编号和线路号怎么办", "doc": 30, "section": "TMP收到0x20003", "cat": "TMP"},
    # ── 设备端日志搜索 ─────────────────────────────────────────
    {"q": "日志搜索版本号 master_start 是什么", "doc": 17, "section": "日志搜索版本号", "cat": "日志搜索"},
    {"q": "怎么搜索协议启动的类型", "doc": 17, "section": "搜索协议启动的类型", "cat": "日志搜索"},
    {"q": "设备登录成功的日志怎么搜索", "doc": 11, "section": "设备登录成功搜索日志", "cat": "日志搜索"},
    # ── 现场案例 ───────────────────────────────────────────────
    {"q": "长沙 FC09 设备报站异常", "doc": 28, "section": "FC09 设备报站异常", "cat": "现场问题"},
    {"q": "长沙 L10 设备 GPS 校时有问题", "doc": 28, "section": "GPS 校时", "cat": "现场问题"},
    # ── 负样本（覆盖 ask_slot / refused，避免只测正样本）──────
    {"q": "帮我看看", "doc": None, "section": "", "cat": "负样本", "conclusion": "ask_slot"},
    {"q": "今天天气怎么样", "doc": None, "section": "", "cat": "负样本", "conclusion": "refused"},
]


def _kb_expected(doc_id: Any, section: str) -> List[Dict[str, Any]]:
    if not doc_id:
        return []
    return [{"doc_id": int(doc_id), "section": section}]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="导入黄金集初版样本")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    from app.database.session import create_session
    from app.models import GoldenSample, User
    from app.services.quality import GoldenSampleService

    db = create_session()
    try:
        admin = db.query(User).filter(User.role == "admin").first()
        if admin is None:
            print("[FAIL] 库中没有管理员用户，无法以管理员身份提交")
            return 2

        service = GoldenSampleService(db)
        created = skipped = 0
        for item in SEED:
            exists = (
                db.query(GoldenSample)
                .filter(GoldenSample.question == item["q"])
                .first()
            )
            if exists:
                skipped += 1
                continue
            if args.dry_run:
                print(f"  + {item['q']}  → {item['doc']} / {item['section']}")
                created += 1
                continue
            service.create(
                question=item["q"],
                actor_id=admin.id,
                actor_role="admin",
                actor_name=admin.username,
                kb_expected=_kb_expected(item["doc"], item["section"]),
                expected_conclusion=item.get("conclusion", "answered"),
                category=item["cat"],
                note="初版种子：按现有知识库章节主题生成",
            )
            created += 1

        print(f"{'[DRY] ' if args.dry_run else ''}新增 {created} 条，已存在跳过 {skipped} 条")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
