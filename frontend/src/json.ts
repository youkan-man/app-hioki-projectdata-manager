import type { JsonObject, JsonValue } from './types'

export function parseJsonValue(value: unknown, path = '$'): JsonValue {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`${path} に有限値でない数値があります。`)
    return value
  }
  if (Array.isArray(value)) return value.map((item, index) => parseJsonValue(item, `${path}[${index}]`))
  if (typeof value === 'object') {
    const result: { [key: string]: JsonValue } = {}
    for (const [key, item] of Object.entries(value)) result[key] = parseJsonValue(item, `${path}.${key}`)
    return result
  }
  throw new Error(`${path} にJSONで扱えない値があります。`)
}

export function parseJsonText(text: string): JsonValue {
  let parsed: unknown
  try { parsed = JSON.parse(text) }
  catch (error) { throw new Error(error instanceof Error ? `JSON構文エラー: ${error.message}` : 'JSON構文エラーがあります。') }
  return parseJsonValue(parsed)
}

export function formatJson(value: JsonValue): string {
  return JSON.stringify(value, null, 2)
}

export function parseJsonObject(value: unknown, label = 'JSON'): JsonObject {
  const parsed = parseJsonValue(value)
  if (parsed === null || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error(`${label}の最上位はオブジェクトである必要があります。`)
  return parsed
}

export function parseJsonObjectText(text: string, label = 'JSON'): JsonObject {
  return parseJsonObject(parseJsonText(text), label)
}
