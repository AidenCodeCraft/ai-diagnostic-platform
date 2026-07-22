/** Shared types for Chat components */

export interface ChatRecord {
  id: number
  title: string
  pinned?: boolean
  model?: string
}

export interface FileAttachment {
  id: string
  file: File
  name: string
  progress: number
  status: 'pending' | 'uploading' | 'parsing' | 'done' | 'error'
  error?: string
}

export interface MsgAttachment {
  name: string
  size: number
  type: string
}
