/**
 * 对话分支管理 composable
 *
 * 支持：
 * - 从任意节点创建新分支（通过 regen / edit 操作）
 * - 分支间切换
 * - 分支状态的干净隔离
 */

import { ref, reactive, computed } from 'vue'

export interface BranchNode {
  /** 分支 ID */
  branchId: string
  /** 分支名称（自动生成） */
  name: string
  /** 该分支在消息列表中的截断位置（消息索引，截断点之后为新分支的内容） */
  truncateIndex: number
  /** 截断前的消息快照（用于回退） */
  savedMessages: any[]
  /** 分支创建时间 */
  createdAt: number
}

export interface BranchState {
  branches: BranchNode[]
  currentBranchId: string | null
  /** 截断前的原始消息（当前分支的基线） */
  baseMessages: any[]
}

export function useChatBranch() {
  const state = reactive<BranchState>({
    branches: [],
    currentBranchId: null,
    baseMessages: [],
  })

  const currentBranch = computed(() =>
    state.branches.find(b => b.branchId === state.currentBranchId) || null
  )

  const branchCount = computed(() => state.branches.length)

  /**
   * 当执行 regen 或 edit 操作前调用，保存分支信息
   * @param messages 当前完整消息列表
   * @param truncateIndex 要截断的消息索引
   * @param branchName 分支名称
   */
  function createBranch(messages: any[], truncateIndex: number, branchName?: string) {
    const branchId = `branch-${Date.now()}`
    const savedMessages = messages.slice(0, truncateIndex)
    const branch: BranchNode = {
      branchId,
      name: branchName || `分支 ${state.branches.length + 1}`,
      truncateIndex,
      savedMessages: JSON.parse(JSON.stringify(savedMessages)),
      createdAt: Date.now(),
    }
    state.branches.push(branch)
    state.currentBranchId = branchId
    state.baseMessages = savedMessages
    return { branchId, baseMessages: savedMessages }
  }

  /**
   * 切换到指定分支
   * @returns 该分支的基线消息列表
   */
  function switchBranch(branchId: string): any[] | null {
    const branch = state.branches.find(b => b.branchId === branchId)
    if (!branch) return null
    state.currentBranchId = branchId
    state.baseMessages = JSON.parse(JSON.stringify(branch.savedMessages))
    return JSON.parse(JSON.stringify(branch.savedMessages))
  }

  /**
   * 获取所有分支（按创建时间倒序）
   */
  function getBranches(): BranchNode[] {
    return [...state.branches].sort((a, b) => b.createdAt - a.createdAt)
  }

  /**
   * 重置分支状态（切换对话时调用）
   */
  function reset() {
    state.branches = []
    state.currentBranchId = null
    state.baseMessages = []
  }

  /**
   * 删除分支
   */
  function deleteBranch(branchId: string) {
    state.branches = state.branches.filter(b => b.branchId !== branchId)
    if (state.currentBranchId === branchId) {
      // 切换到最新分支
      const latest = state.branches[state.branches.length - 1]
      state.currentBranchId = latest?.branchId || null
      state.baseMessages = latest ? JSON.parse(JSON.stringify(latest.savedMessages)) : []
    }
  }

  return {
    state,
    currentBranch,
    branchCount,
    createBranch,
    switchBranch,
    getBranches,
    reset,
    deleteBranch,
  }
}
