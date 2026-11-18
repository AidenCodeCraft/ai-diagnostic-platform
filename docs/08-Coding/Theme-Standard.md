# 主题与深色模式规范

本规范约束前端所有涉及颜色的样式实现，避免深色模式出现浅色残留或不可读文本。

## 1. 令牌来源

- 全局令牌统一定义在 `apps/web/src/styles/chat-theme.css`：
  - 浅色：`:root, [data-theme='light']`
  - 深色：`[data-theme='dark']`
- 管理后台专属令牌：`--adm-page-bg`、`--adm-draft-danger`、`--adm-draft-warn` 等，同样在该文件成对定义。
- 知识库局部令牌：`--kb-*`，定义在 `KnowledgeBase.vue` 的全局样式块中（`.kb-container` / `.guide-body` / `.validation-body`）。

## 2. 取值约束

1. **禁止裸色值**：样式块中不得出现 `#fff`、`#1f2937`、`#e5e7eb` 等硬编码颜色（`rgba()` 阴影/遮罩除外，且需在深色下提供更深的替代）。
2. **语义优先**：面板用 `--chat-popup-*`，正文用 `--chat-msg-*`，侧栏/导航用 `--chat-sidebar-*`，来源区用 `--chat-source-*`。
3. **浅色不变**：改用令牌时保证浅色取值与改造前一致，不引入视觉回归。

## 3. Teleport 组件规则

`Teleport to="body"` 的弹层（抽屉、浮框、弹窗）不会继承局部容器变量，必须：

- 引用定义在 `:root` / `html` 上的全局令牌；或
- 在弹层根节点自带 `--xx-*` 浅/深成对定义。

Element Plus 弹窗统一加 `class="admin-dialog"`（后台）或复用既有弹窗样式，由 `chat-theme.css` 提供深色变量兜底。

## 4. 回归防护

`apps/web/src/__tests__/themeGuard.spec.ts` 对以下文件做静态断言：

- `src/layouts/AdminLayout.vue`
- `src/components/chat/ChatMessageList.vue`（`.doc-panel` / `.ref-tooltip`）
- `src/views/admin/OperationLogs.vue`

新增同类组件时，请同步加入该守卫测试。
