/** Shared types for Chat components */

export interface ChatRecord {
  id: number
  title: string
  pinned?: boolean
  model?: string
  /** 最近更新时间（ISO 字符串），用于侧边栏按时间分组 */
  updatedAt?: string
}

export interface FileAttachment {
  id: string
  file: File
  name: string
  progress: number
  status: 'pending' | 'uploading' | 'parsing' | 'done' | 'error'
  error?: string
}

/** 对话界面截图（OCR 识别文本作为现场证据参与诊断） */
export interface ImageAttachment {
  id: string
  file: File
  name: string
  previewUrl: string
  status: 'uploading' | 'done' | 'error'
  /** 后端 chat_images.id（发送消息时用于绑定会话） */
  imageId?: number
  /** ocr | vision | ocr+vision */
  path?: string
  text?: string
  error?: string
}

export interface MsgAttachment {
  name: string
  size: number
  type: string
}

export interface ThinkingData {
  text: string
  elapsed: number
  active: boolean
}
