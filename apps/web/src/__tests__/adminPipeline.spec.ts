import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import Pipeline from '@/views/admin/Pipeline.vue'

const health = vi.hoisted(() => ({
  ingest: {
    total: 4,
    by_status: { succeeded: 3, failed: 1 },
    by_stage: {
      parse: { succeeded: 2 },
      template: { failed: 1, running: 1 },
    },
    failed: [{ task_id: '1:template:0', stage: 'template', error: 'boom' }],
    running_oldest_seconds: 130,
    healthy: false,
  },
  retrieval: {
    window_hours: 24,
    count: 10,
    zero_hit_rate: 0.2,
    latency_ms: { p50: 120, p95: 480, max: 900 },
    conclusions: { answered: 8, ask_slot: 2 },
  },
  vector: {
    embedding_provider: 'HashingEmbedder',
    is_semantic: false,
    milvus_available: true,
    schema_error: null,
    entities: 292,
  },
  image_cost: {
    window_hours: 24,
    images: 3,
    by_status: { succeeded: 2, failed: 1 },
    by_path: { ocr: 2 },
    ocr_pages: 3,
    vision_input_tokens: 1300,
    vision_output_tokens: 300,
    estimated_cost_yuan: 0.0079,
    unit_prices: {},
  },
  generated_at: '2026-11-20T00:00:00Z',
}))

vi.mock('@/api/pipeline', () => ({
  pipelineApi: { health: vi.fn().mockResolvedValue({ data: health }) },
}))

// 页面只依赖 Element Plus 的容器/提示组件，这里给最小实现，
// 表格类组件不参与断言（数据用 metrics 区块展示）
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
  ElCard: { template: '<section class="el-card"><slot name="header" /><slot /></section>' },
  ElAlert: { props: ['title'], template: '<div class="el-alert">{{ title }}</div>' },
  ElTag: { template: '<span class="el-tag"><slot /></span>' },
  ElButton: { template: '<button><slot /></button>' },
  ElSelect: { template: '<div><slot /></div>' },
  ElOption: { props: ['label'], template: '<div>{{ label }}</div>' },
  ElTable: { props: ['data'], template: '<div class="el-table" />' },
  ElTableColumn: { template: '<div />' },
}))

const stubs = {
  'el-card': { template: '<div class="el-card"><slot name="header" /><slot /></div>' },
  'el-alert': { props: ['title'], template: '<div class="el-alert">{{ title }}</div>' },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-button': { template: '<button><slot /></button>' },
  'el-select': { template: '<div><slot /></div>' },
  'el-option': true,
  'el-table': true,
  'el-table-column': true,
}

describe('运行监控页', () => {
  it('渲染预处理链、检索质量与成本', async () => {
    const wrapper = mount(Pipeline, { global: { stubs } })
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('预处理链')
    expect(text).toContain('检索质量')
    expect(text).toContain('截图识别成本')
    expect(text).toContain('20.0%')          // 零命中率
    expect(text).toContain('1600')           // 视觉 tokens 合计（输入 1300 + 输出 300）
    expect(text).toContain('¥0.0079')        // 估算费用
    expect(text).toContain('1:template:0')   // 失败任务
  })

  it('embedding 是哈希兜底时给出明确告警', async () => {
    const wrapper = mount(Pipeline, { global: { stubs } })
    await flushPromises()
    expect(wrapper.text()).toContain('哈希兜底')
  })
})
