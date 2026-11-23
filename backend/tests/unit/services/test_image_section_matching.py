"""图片与「知识点（章节）」归属匹配的回归测试。

用户反馈：提问某个知识点时，别的知识点的配图被当成"关联图片"显示出来。
规则：图片必须属于本次命中的章节；没有信号时宁可不展示，也不按文档位置兜底。
"""

import re

import pytest

from app.models import KnowledgeDocument, KnowledgeImage
from app.services.knowledge.image_service import KnowledgeImageService

DOC = """# 测试文档

## 1. 线路运行方向相反

现象：设备经过站点未报站，反方向经过两个站后自动切换方向。
GPS 上报间隔为 15S。

### 关键字

- `auto check change Out station reversal point`

### 关键字解释

![](/api/v1/knowledge/images/1)

## 2. GPS 上报时间间隔

现象：L10 设备 GPS 上报间隔 15S，询问是否支持修改。

### 关键字

- `gps report interval`

### 关键字解释

![](/api/v1/knowledge/images/2)
"""


def _line_index(prefix: str) -> int:
    """1-based 行号：以 prefix 开头的行。"""
    for i, line in enumerate(DOC.split("\n"), start=1):
        if line.startswith(prefix):
            return i
    raise AssertionError(f"line not found: {prefix}")


@pytest.fixture()
def doc_with_images(db_session):
    doc = KnowledgeDocument(title="测试文档", content=DOC, doc_type="manual", status="active")
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    images = []
    for i, m in enumerate(re.finditer(r"!\[[^\]]*\]\([^)]*\)", DOC), start=1):
        img = KnowledgeImage(
            doc_id=doc.id,
            storage_key=f"test/{i}.png",
            anchor="关键字解释",
            # 与 DocumentImporter 一致：以图片为中心的 ±120 字窗口
            context_text=DOC[max(0, m.start() - 120): m.end() + 120],
            position=i,
        )
        db_session.add(img)
        images.append(img)
    db_session.commit()
    for img in images:
        db_session.refresh(img)
    return doc, images


class TestSectionOwnedImages:
    def test_image_line_is_located_before_the_image_not_after(self, db_session, doc_with_images):
        """context_text 含图片后文，定位必须用图片之前的前文。"""
        doc, (img1, img2) = doc_with_images
        svc = KnowledgeImageService(db_session)
        start1 = _line_index("## 1.")
        start2 = _line_index("## 2.")

        line1 = svc._image_line(DOC, img1)
        line2 = svc._image_line(DOC, img2)
        assert line1 is not None and start1 <= line1 < start2, f"img1 应落在第1节，实际 {line1}"
        assert line2 is not None and line2 >= start2, f"img2 应落在第2节，实际 {line2}"

    def test_only_images_inside_the_matched_section_are_returned(self, db_session, doc_with_images):
        doc, (img1, _img2) = doc_with_images
        svc = KnowledgeImageService(db_session)
        section1 = (_line_index("## 1."), _line_index("## 2."))

        got = svc.match_images(
            doc.id,
            query="设备实际运行方向相反怎么处理",
            anchor="1. 线路运行方向相反",
            section_range=section1,
            content=DOC,
        )
        assert [i.id for i in got] == [img1.id]

    def test_out_section_image_excluded_even_when_query_text_overlaps(self, db_session, doc_with_images):
        """命中第2节时，第1节图片即使文本重合（都含 GPS）也必须排除。"""
        doc, (_img1, img2) = doc_with_images
        svc = KnowledgeImageService(db_session)
        section2 = (_line_index("## 2."), len(DOC.split("\n")))

        got = svc.match_images(
            doc.id,
            query="GPS上报时间间隔是多少",
            anchor="2. GPS 上报时间间隔",
            section_range=section2,
            content=DOC,
        )
        assert [i.id for i in got] == [img2.id]

    def test_no_signal_returns_empty_instead_of_position_fallback(self, db_session, doc_with_images):
        """没有章节、没有锚点、文本不重合 → 不展示（禁止按文档位置兜底）。"""
        doc, _imgs = doc_with_images
        svc = KnowledgeImageService(db_session)

        got = svc.match_images(
            doc.id,
            query="今天天气怎么样",
            anchor="",
            section_range=None,
            content=None,
        )
        assert got == []

    def test_short_generic_acronym_alone_is_not_a_match(self, db_session, doc_with_images):
        """gps / tmp 这类 3 字母缩写单独命中，不足以判定图片相关。"""
        doc, _imgs = doc_with_images
        svc = KnowledgeImageService(db_session)

        got = svc.match_images(
            doc.id,
            query="GPS上报",
            anchor="",
            section_range=None,
            content=None,
        )
        assert got == []


# ------------------------------------------------------------------
# 真实回归：同一篇文档里「关键字解释」出现多次（TMP 文档）
# ------------------------------------------------------------------

DOC_TMP = """# TMP

## 1. 下载文件分析

### 关键字解释

`FileListUpgradeProc begin` 下载开始打印。

## 2. 搜索协议启动的类型

### 关键字解释

`***Plat:` 后面的数字代表第几路部标。

## 3. TMP登录后自动生成手机号

### 关键字解释

查看关键字上面的平台指令打印，确认车牌号汉字编码为GBK，需要升级网关，如下图所示：

![](/api/v1/knowledge/images/60)

## 4. TMP更新XML

### 关键字解释

| `FileListUpgradeProc end` | 下载结束打印 |
"""


@pytest.fixture()
def tmp_doc_with_images(db_session):
    doc = KnowledgeDocument(title="TMP", content=DOC_TMP, doc_type="manual", status="active")
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    m = re.search(r"!\[[^\]]*\]\([^)]*\)", DOC_TMP)
    assert m
    img = KnowledgeImage(
        doc_id=doc.id,
        storage_key="test/tmp60.png",
        anchor="关键字解释",
        context_text=DOC_TMP[max(0, m.start() - 120): m.end() + 120],
        position=1,
    )
    db_session.add(img)
    db_session.commit()
    db_session.refresh(img)
    return doc, img


class TestRepeatedSectionNames:
    """检索层不给行号时，靠锚点会把同名小节的图串到别的知识点上。"""

    def test_hierarchical_anchor_keeps_image_in_its_own_section(self, db_session, tmp_doc_with_images):
        doc, _img = tmp_doc_with_images
        svc = KnowledgeImageService(db_session)

        # 命中「4. TMP更新XML > 关键字解释」：那张图在 §3，不属于这一节
        got = svc.match_images(
            doc.id,
            query="TMP · 关键字解释",
            anchor="4. TMP更新XML > 关键字解释",
            section_range=(0, 0),
            content=DOC_TMP,
        )
        assert got == []

    def test_hierarchical_anchor_returns_image_of_its_section(self, db_session, tmp_doc_with_images):
        doc, img = tmp_doc_with_images
        svc = KnowledgeImageService(db_session)

        got = svc.match_images(
            doc.id,
            query="TMP · 关键字解释",
            anchor="3. TMP登录后自动生成手机号 > 关键字解释",
            section_range=(0, 0),
            content=DOC_TMP,
        )
        assert [i.id for i in got] == [img.id]

    def test_flat_repeated_anchor_is_not_trusted(self, db_session, tmp_doc_with_images):
        """锚点只剩「关键字解释」（同名 4 节）时不能凭锚点挂图。"""
        doc, _img = tmp_doc_with_images
        svc = KnowledgeImageService(db_session)

        assert svc.match_images(
            doc.id, query="TMP · 关键字解释", anchor="关键字解释",
            section_range=(0, 0), content=DOC_TMP,
        ) == []

        # 但问题本身问到图里的内容（车牌号 GBK 编码）时，应该挂上
        got = svc.match_images(
            doc.id, query="车牌号汉字编码GBK需要升级网关", anchor="关键字解释",
            section_range=(0, 0), content=DOC_TMP,
        )
        assert [i.id for i in got] == [_img.id]
