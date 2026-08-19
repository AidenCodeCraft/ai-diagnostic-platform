# 知识库图片在对话回答中的自动附带与展示方案

> 归属：AI Diagnostic Platform · RAG 增强
> 目标：当 AI 的回答引用或涵盖「含图片的知识库文档」时，在对话界面相应回答中自动附带并正确展示这些相关图片。
> 现状基线：v1.0 企业版（Commit 001–015 + v1.1 RAG 增强）

---

## 1. 现状分析与差距

### 1.1 现有链路

```
知识导入            →  检索              →  回答生成           →  前端渲染
DocumentImporter   →  KnowledgeService  →  DiagnosticChatAgent →  ChatMessageList.vue
(.md/.txt → content)   .search()          _retrieve_knowledge     renderMarkdown(marked)
                                            self.references        processRefLinks → doc panel
```

### 1.2 关键事实（与代码一一对应）

| 环节 | 现状 | 代码位置 |
| --- | --- | --- |
| 知识存储 | `KnowledgeDocument` 只有 `content`(Markdown 文本)，**无图片字段/无附件表** | `backend/app/models/knowledge/knowledge.py` |
| 文档导入 | `DocumentImporter` 只支持 `.md/.txt`，`![alt](path)` 原样保留为文本，**图片文件不上传、无法解析** | `backend/app/services/knowledge/document_importer.py` |
| 检索 | 文档级检索（Milvus 向量 + BM25 回退），返回 `id/title/snippet/score`，**无图片信息** | `backend/app/services/knowledge/knowledge_service.py` |
| 回答生成 | `DiagnosticChatAgent._retrieve_knowledge` 组装 `self.references`（id/title/source/excerpt），**不含图片** | `backend/app/services/chat/diagnostic_chat_agent.py` |
| 流式传输 | `ChatService.send_message_stream` 已能 SSE 下发 `sources` 事件 | `backend/app/services/chat/chat_service.py` |
| 消息持久化 | `ChatMessage.sources` 为 JSON 列，**可无损扩展 `images` 字段**（无需迁移） | `backend/app/models/chat/chat_session.py` |
| 前端渲染 | `renderMarkdown` 未处理图片解析；`ChatSource` 类型无 images；文档面板只渲染文本 | `apps/web/src/utils/markdown.ts`、`apps/web/src/api/chat.ts`、`apps/web/src/components/chat/ChatMessageList.vue` |
| 静态服务 | FastAPI 无 `StaticFiles` 挂载，无图片服务端点 | `backend/app/main.py` |

### 1.3 核心差距

1. **图片没有「物理载体」**：导入只存文本，图片文件被丢弃，无从渲染。
2. **图片与内容没有「关联图谱」**：检索到文档后，不知道哪些图片属于被引用/被覆盖的那一段。
3. **回答生成链路没有「图片通道」**：references 不带图片，SSE 不带图片。
4. **前端没有「图片渲染组件」**：无画廊、无灯箱、无降级。

---

## 2. 总体设计

```
        ┌────────────────────────── 知识导入期 ─────────────────────────┐
        │  DocumentImporter                                           │
        │   1) 解析 Markdown / (未来 PDF/DOCX)                          │
        │   2) 抽取图片 → 上传对象存储 → 回写稳定 URL                    │
        │   3) 建立「图片 ↔ 文档/章节/上下文」关联记录                   │
        └──────────────────────────────┬───────────────────────────────┘
                                       ▼
        ┌────────────────────────── 检索期 ────────────────────────────┐
        │  KnowledgeService.search() / DiagnosticChatAgent             │
        │   定位匹配的「文档 + 章节」，反查该范围覆盖的图片               │
        │   按 proximity + caption/text 相似度排序、去重、截断 top-N      │
        └──────────────────────────────┬───────────────────────────────┘
                                       ▼
        ┌────────────────────────── 生成期 ────────────────────────────┐
        │  references[].images 附加到 SSE sources 事件                  │
        │  （可选）LLM 用 [图1](ref://img/<id>) 内联引用，前端内联放置     │
        └──────────────────────────────┬───────────────────────────────┘
                                       ▼
        ┌────────────────────────── 前端渲染期 ────────────────────────┐
        │  ChatMessageList.vue                                         │
        │   内联引用图片 + 回答底部「关联图片」画廊 + 灯箱                │
        │   懒加载 / 占位 / 失败重试 / 缺失降级 / 反馈                   │
        └──────────────────────────────────────────────────────────────┘
```

---

## 3. 数据模型与存储

### 3.1 新增 `knowledge_images` 表

> 独立表优于在 `KnowledgeDocument` 上塞 JSON：支持按 `doc_id`/`anchor` 索引、去重、以及后续多模态检索。

```python
# backend/app/models/knowledge/knowledge.py
class KnowledgeImage(Base):
    __tablename__ = "knowledge_images"

    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True)
    # 稳定存储键：minio object key 或 本地相对路径
    storage_key = Column(String(500), nullable=False)
    # 可访问 URL（MinIO 预签名 / 本地 /images/... 路径），前端直接使用
    url = Column(String(1000), nullable=False)
    # 图注 / alt 文本（最重要的语义锚点，参与检索匹配）
    caption = Column(String(500), nullable=True)
    # 图片所在的 Markdown 标题/章节锚点（见 4.2）
    anchor = Column(String(300), nullable=True)
    # 图片在文档中的出现顺序
    position = Column(Integer, default=0)
    # 图片上下文文本（图片前后 N 字，用于向量匹配/校验）
    context_text = Column(Text, nullable=True)
    # 文件元信息
    mime_type = Column(String(100), default="image/png")
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    size_bytes = Column(Integer, default=0)
    sha256 = Column(String(64), nullable=True, index=True)  # 去重
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

配套 Alembic 迁移：新增表 + `doc_id`/`sha256` 索引。

### 3.2 存储介质（两档，可配置）

| 档位 | 方案 | 适用 |
| --- | --- | --- |
| 生产 | **MinIO 对象存储**（`MINIO_ENABLED=True`，复用现有 `MINIO_*` 配置），桶 `knowledge-images` | 大图、多副本、CDN |
| 开发/单机 | **本地静态目录** `data/knowledge_images/`，FastAPI 挂载 `StaticFiles` | 免依赖、一键启动 |

- 上传成功 → 返回 `storage_key`；本地模式即相对路径，对象存储模式即 object key。
- 生产环境图片访问优先走**预签名 URL**（有鉴权、有时效），本地模式走 `/api/v1/knowledge/images/{id}` 端点。

### 3.3 Schema

```python
# backend/app/schemas/knowledge/knowledge.py
class KnowledgeImageResponse(BaseModel):
    id: int
    doc_id: int
    url: str
    caption: Optional[str] = None
    anchor: Optional[str] = None
    mime_type: str = "image/png"
    width: Optional[int] = None
    height: Optional[int] = None

class KnowledgeResponse(BaseModel):
    # ... 原有字段 ...
    images: List[KnowledgeImageResponse] = []   # 文档级图片列表
```

---

## 4. 图片与答案内容的关联匹配（核心）

采用**三层关联 + 一种增强**，从粗到细、成本递增：

### 4.1 文档级关联（基础）

`KnowledgeImage.doc_id` 建立图片 → 文档的归属。检索命中文档即可拿到其全部图片候选。

### 4.2 章节级关联（主力，推荐）

导入时给每张图打「章节锚点」，回答生成时用锚点把图片限定到「被引用/被覆盖的那一段」。

- **锚点生成**（导入时，`DocumentImporter`）：
  1. 找到图片上方的最近一个 `# / ## / ###` 标题，取标题文本为 `anchor`。
  2. 无标题时，取图片前后 120 字的上下文文本作为 `anchor`（或 `context_text`）。
- **锚点匹配**（生成时，`DiagnosticChatAgent._retrieve_knowledge`）：
  - 当前代码已按「匹配章节」提取 `snippet`（`KnowledgeService._extract_snippet` → `_extract_markdown_section`）。
  - **复用同一段逻辑**：确定命中章节后，仅挑选 `anchor` 落在该章节范围内、或 `anchor` 文本与命中关键词相交的图片。这保证「答案只引用相关段落 → 图片也只来自相关段落」，从源头抑制无关图片。

### 4.3 内容级关联（增强，可选二期）

- **文本侧**：用 `caption + context_text` 拼成短文本，与用户问题做向量/BM25 相似度打分，作为图片排序信号。
- **多模态侧（选配）**：引入 CLIP / BGE-VL（中文）对「图片 ↔ 问题」做图-文检索，支持「有电路图/拓扑图吗」这类直接找图的意图。仅在图片量大、需要精确找图时启用，MVP 不强制。

### 4.4 排序与去重

```text
对命中文档的候选图片：
1. 按 sha256 去重（同图多文档只保留一次）
2. 打分 = 0.6 * 章节命中度 + 0.3 * caption/text 相似度 + 0.1 * position 邻近度
3. 截断 top-N（N=4~6，可配置），避免刷屏
```

---

## 5. 回答生成时识别并提取相关图片

### 5.1 在 `DiagnosticChatAgent` 中扩展

改动点：`backend/app/services/chat/diagnostic_chat_agent.py` 的 `_retrieve_knowledge`。

```python
# 伪代码：组装 references 时附加 images
for item in items:
    doc_id = item.get("id")
    matched_section = item.get("section_anchor")  # 由 _extract_snippet 逻辑回传
    images = self.knowledge.list_images(
        doc_id=doc_id,
        anchor=matched_section,          # 章节级过滤
        query=cleaned,                   # 用于 caption/text 相似度排序
        top_k=4,
    )
    self.references.append({
        "id": doc_id,
        "title": title,
        "source": item.get("source") or "知识库",
        "excerpt": snippet,
        "images": [{
            "id": img.id, "url": img.url, "caption": img.caption,
            "anchor": img.anchor, "width": img.width, "height": img.height,
        } for img in images],
    })
```

### 5.2 内联引用（可选、分两档）

| 档位 | 做法 | 优点 | 风险 |
| --- | --- | --- | --- |
| **A（MVP，推荐）** | 不要求 LLM 输出图片标记；前端在回答底部统一渲染「关联图片」画廊（数据来自 `sources[].images`） | 稳定、零幻觉、改动小 | 图片与正文位置不完全一一对应 |
| **B（增强）** | 在 `RAG_STRICT_SYSTEM_PROMPT` 中增加约束：命中段落含图时，用 `[图1](ref://img/<id>)` 内联标注 | 图片出现在精确位置、体验最佳 | 依赖 LLM 遵守格式，需校验 id 存在性，非法 id 走降级 |

> 建议：先落地 A，前端同时支持识别 `ref://img/<id>`，等 A 稳定后逐步开启 B。

### 5.3 流式与持久化（改动很小）

- `ChatService.send_message_stream` **已**在 `enrich_messages` 后 `yield sources` 事件；扩展 `agent.references` 后图片自动随 SSE 下发，**无需改动**。
- 前端 `onSources` 收到后把 `sources`（含 `images`）存到消息上，`saveMessage` 写入 `ChatMessage.sources` JSON，多轮/刷新可恢复。

---

## 6. 前端渲染方案

### 6.1 类型扩展

```typescript
// apps/web/src/api/chat.ts
export interface ChatImage {
  id: number
  url: string
  caption?: string
  anchor?: string
  width?: number
  height?: number
}
export interface ChatSource {
  id?: number
  title: string
  source: string
  excerpt: string
  images?: ChatImage[]   // 新增
}
```

### 6.2 加载方式

1. **URL 获取**：后端返回可直接访问的 URL。
   - 本地模式：`/api/v1/knowledge/images/{id}`（`FileResponse`）。
   - 对象存储：预签名 URL（有效期 10–60 分钟，过期前端自动重新请求签名）。
2. **鉴权**：`<img>` 无法带 `Authorization` 头，故图片端点走 **短期签名 URL 或 Cookie**；本地开发可临时放行。
3. **懒加载**：`loading="lazy"` + `IntersectionObserver`，进入视口才请求，配 `decoding="async"`。
4. **占位/过渡**：请求期间显示灰底骨架（shimmer）；加载完成淡入。

### 6.3 布局与组件

新增 `KnowledgeImageGallery.vue`（内联引用图 + 底部画廊共用）：

```
回答正文
  ├─ [内联] 正文中 ref://img/<id> 处内嵌小图（档位 B）
  └─ [底部] 「📎 关联图片」画廊（档位 A，主展示位）
          ┌─────┬─────┬─────┐
          │ 缩略 │ 缩略 │ 缩略 │   ← 横向可换行，单图最大 ~220px
          └─────┴─────┴─────┘
          图注（caption）灰字居中，超长省略
```

- **单张**：按原始宽高比、最大宽度约束展示（`max-width: min(100%, 480px)`）。
- **多张**：等宽缩略图网格，点击进灯箱。

### 6.4 交互体验（灯箱 `ImageLightbox`）

- **点击缩略图/内联图** → 全屏灯箱（遮罩 + 居中大图）。
- 操作：左右切换（多图时）、`ESC` 关闭、`←/→` 键盘导航、`+/-` 或滚轮缩放、下载按钮。
- Hover 缩略图显示 `caption` 与来源文档标题。
- 移动端：滑动切换、双击缩放。

### 6.5 Markdown 渲染扩展

`apps/web/src/utils/markdown.ts` 的 `renderer.image`：

1. 识别 `ref://img/<id>` 与相对路径，统一解析为后端 URL。
2. 输出 `<img class="kb-image" data-img-id loading="lazy">`，挂载点击进灯箱。
3. 文档面板 `doc-panel-content` 复用同一解析逻辑，使右侧文档预览也能显示图片。

---

## 7. 图片缺失 / 关联不准确的容错策略

### 7.1 图片缺失（文件丢失 / URL 失效）

| 场景 | 处理 |
| --- | --- |
| `<img>` 加载失败 | `onerror` 触发：显示占位块「🖼 图片缺失 / 加载失败」，附「重试」按钮；重试仍失败则自动降级为「查看文档文字」链接 |
| 签名 URL 过期 | 前端捕获 403/401 → 调用 `POST /knowledge/images/{id}/presign` 换新 URL → 重试一次 |
| 存储对象被删 | 后端图片端点返回 404 时，`KnowledgeImage.status` 标记 `missing`，后续检索直接跳过该图 |
| 文档整体无图 | 画廊不渲染，仅保留原有文本引用（行为与现在一致） |

### 7.2 关联不准确（图不对文）

| 机制 | 说明 |
| --- | --- |
| **锚点强过滤** | 仅取「命中章节」内的图，章节不匹配直接不入选（见 4.2） |
| **去重** | sha256 去重，避免同图多源刷屏 |
| **置信度阈值** | caption/text 相似度低于阈值的图，默认折叠为「+N 张更多图片」，不主动展开 |
| **用户可关闭** | 每条 AI 回答提供「隐藏图片」开关（会话级偏好），关闭后仅显示引用链接 |
| **反馈闭环** | 复用现有消息 feedback，扩展「该图不相关」逐图反馈 → 回写 `knowledge_images` 关联分 → 后续排序降权 |
| **兜底** | 关联失败时不阻断主链路：图片缺失/无关联时回答文本照常展示，图片为「锦上添花」而非「必需」 |

---

## 8. 安全与性能

- **上传校验**：限制 MIME（png/jpg/webp/gif）、大小（≤10MB）、文件名清洗（防路径穿越），写入对象存储前校验 magic bytes。
- **鉴权**：图片端点复用现有 `api_security` / token 校验；生产走签名 URL。
- **性能**：懒加载 + 缩略图（对象存储生成缩略图，或前端 `width` 限流）；`knowledge_images` 按 `doc_id` 建索引；图片列表随文档检索一次查出（`IN (doc_ids)` 批量查询，避免 N+1）。

---

## 9. 分阶段实施路线（按改动点）

### 阶段一：图片「入库 + 可访问」 ✅ 打通物理链路

| 改动 | 文件 |
| --- | --- |
| 新增 `KnowledgeImage` 模型 + 迁移 | `backend/app/models/knowledge/knowledge.py`、`backend/migrations/versions/` |
| 导入时抽取 Markdown 图片、上传存储、回写稳定 URL、打锚点 | `backend/app/services/knowledge/document_importer.py` |
| 图片 CRUD/服务端点 + 列表随文档返回 | `backend/app/services/knowledge/knowledge_service.py`、`backend/app/api/knowledge/__init__.py` |
| 图片静态服务/签名 URL 端点 | `backend/app/main.py`（挂载 `StaticFiles`）或新增 endpoint |
| 文档面板渲染图片 | `apps/web/src/utils/markdown.ts`（`renderer.image`） |

### 阶段二：检索关联 + 回答附带图片

| 改动 | 文件 |
| --- | --- |
| `references` 附加 `images`（章节过滤 + 排序 + top-N） | `backend/app/services/chat/diagnostic_chat_agent.py` |
| 前端 `ChatSource.images` 类型 + SSE 消费 | `apps/web/src/api/chat.ts`、`apps/web/src/layouts/ChatLayout.vue` |
| 回答底部「关联图片」画廊 + 灯箱 + 懒加载 + 降级 | `apps/web/src/components/chat/ChatMessageList.vue`（新增 `KnowledgeImageGallery.vue` / `ImageLightbox.vue`） |

### 阶段三：体验增强

| 改动 | 说明 |
| --- | --- |
| LLM 内联引用 `ref://img/<id>`（档位 B） | `RAG_STRICT_SYSTEM_PROMPT` 约束 + 前端内联渲染 + id 校验降级 |
| 多模态检索（CLIP/BGE-VL） | 图片向量化，支持「找图」意图 |
| 逐图反馈闭环 | 前端反馈按钮 → 后端降权 → 关联更准 |

---

## 10. 数据流示例

### 10.1 SSE `sources` 事件（含图片）

```json
{
  "sources": [
    {
      "id": 123,
      "title": "SS528 USB 驱动调试手册",
      "source": "硬件",
      "excerpt": "### USB PHY 异常排查\n...",
      "images": [
        { "id": 5001, "url": "/api/v1/knowledge/images/5001", "caption": "USB PHY 寄存器读流程图", "anchor": "USB PHY 异常排查", "width": 1200, "height": 800 }
      ]
    }
  ]
}
```

### 10.2 回答内联引用（档位 B）

```markdown
按寄存器时序排查，先读 USB PHY 状态寄存器[图1](ref://img/5001)，
确认 CLK 稳定后再测数据眼图。
```

前端 `renderer.image` 将 `ref://img/5001` 解析为真实 URL 并内联渲染，其余图在底部画廊兜底。

---

> 方案完成。核心原则：**图片是回答的「证据附件」，走与文本引用同一条 `references → sources → ChatMessage.sources` 链路**，用「章节锚点」保证关联准确，用「懒加载 + 降级 + 反馈」保证体验稳健。
