/**
 * 敏感信息脱敏处理器
 *
 * 在日志入队前自动过滤敏感字段，
 * 确保内存、传输、存储中都不会出现明文敏感信息。
 */

// ── 脱敏规则 ────────────────────────────────────────────────

interface SanitizeRule {
  /** 正则匹配模式 */
  pattern: RegExp
  /** 替换文本 */
  replacement: string
}

const SENSITIVE_RULES: SanitizeRule[] = [
  // JWT / Bearer Token
  { pattern: /Bearer\s+[^\s"'}\]>,;]+/gi, replacement: 'Bearer ***' },
  // JSON 中的 token 字段
  { pattern: /"token"\s*:\s*"[^"]+"/gi, replacement: '"token":"***"' },
  // JSON 中的 access_token
  { pattern: /"access_token"\s*:\s*"[^"]+"/gi, replacement: '"access_token":"***"' },
  // JSON 中的 password
  { pattern: /"password"\s*:\s*"[^"]+"/gi, replacement: '"password":"***"' },
  // JSON 中的 secret
  { pattern: /"secret"\s*:\s*"[^"]+"/gi, replacement: '"secret":"***"' },
  // JSON 中的 api_key
  { pattern: /"api_key"\s*:\s*"[^"]+"/gi, replacement: '"api_key":"***"' },
  // 中国大陆手机号
  { pattern: /1[3-9]\d{9}/g, replacement: '***PHONE***' },
  // 邮箱地址
  { pattern: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g, replacement: '***EMAIL***' },
  // 中国大陆身份证号 (18位)
  { pattern: /\b\d{17}[\dXx]\b/g, replacement: '***ID***' },
  // URL 中的 token 参数
  { pattern: /([?&])(token|access_token|api_key)=[^&\s"'}\]>]+/gi, replacement: '$1$2=***' },
]

// ── 键名脱敏 ───────────────────────────────────────────────

const SENSITIVE_KEYS = new Set([
  'token', 'access_token', 'password', 'secret',
  'api_key', 'apikey', 'authorization',
  'credit_card', 'ssn', 'passport',
])

/**
 * 递归脱敏对象中的敏感键值
 */
function sanitizeObject(obj: unknown, depth = 0): unknown {
  if (depth > 5 || obj == null || typeof obj !== 'object') return obj

  if (Array.isArray(obj)) {
    return obj.map((item) => sanitizeObject(item, depth + 1))
  }

  const result: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
    const lowerKey = key.toLowerCase()
    if (SENSITIVE_KEYS.has(lowerKey)) {
      result[key] = '***'
    } else if (typeof value === 'object' && value !== null) {
      result[key] = sanitizeObject(value, depth + 1)
    } else {
      result[key] = value
    }
  }
  return result
}

// ── 公开 API ────────────────────────────────────────────────

/**
 * 对字符串进行脱敏
 */
export function sanitizeText(input: string): string {
  let result = input
  for (const rule of SENSITIVE_RULES) {
    result = result.replace(rule.pattern, rule.replacement)
  }
  return result
}

/**
 * 对任意值进行深度脱敏
 * - 字符串：正则匹配替换
 * - 对象：递归处理敏感 key
 * - 其他类型：原样返回
 */
export function sanitize(input: unknown): unknown {
  if (typeof input === 'string') {
    return sanitizeText(input)
  }
  if (typeof input === 'object' && input !== null) {
    return sanitizeObject(input)
  }
  return input
}
