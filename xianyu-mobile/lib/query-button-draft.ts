// 查询配置编辑态 ⇄ QueryButton 结构的序列化/反序列化（与 web 端弹窗同格式）。
// 提取为共享模块，供商品编辑页(item-edit)与素材编辑页(material-edit)复用。
// 请求头：每行 `Key: Value`；结果字段：每行 `标签=路径`，行尾 `*` 表高亮，`|前缀` 表前缀。

import type { QueryButton, QueryResultField } from '@/api/wrappers/item-query-config';

export interface QueryButtonDraft {
  key: string;
  name: string;
  method: 'GET' | 'POST';
  url: string;
  headersText: string;
  body: string;
  successPath: string;
  successValue: string;
  errorPath: string;
  fieldsText: string;
}

let draftSeq = 0;
export function nextDraftKey(): string {
  draftSeq += 1;
  return `qb-${Date.now()}-${draftSeq}`;
}

export function emptyDraft(): QueryButtonDraft {
  return {
    key: nextDraftKey(),
    name: '',
    method: 'GET',
    url: '',
    headersText: '',
    body: '',
    successPath: '',
    successValue: '',
    errorPath: '',
    fieldsText: '',
  };
}

export function headersToText(headers?: Record<string, string> | null): string {
  if (!headers) return '';
  return Object.entries(headers)
    .map(([k, v]) => `${k}: ${v}`)
    .join('\n');
}

export function textToHeaders(text: string, buttonName: string): Record<string, string> | null {
  const out: Record<string, string> = {};
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i].trim();
    if (!line) continue;
    const idx = line.indexOf(':');
    if (idx <= 0) {
      throw new Error(`按钮「${buttonName}」请求头第 ${i + 1} 行格式应为 Key: Value`);
    }
    out[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
  }
  return Object.keys(out).length > 0 ? out : null;
}

export function fieldsToText(fields: QueryResultField[]): string {
  return fields
    .map((f) => `${f.label}=${f.path}${f.prefix ? `|${f.prefix}` : ''}${f.highlight ? '*' : ''}`)
    .join('\n');
}

export function textToFields(text: string, buttonName: string): QueryResultField[] {
  const out: QueryResultField[] = [];
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i += 1) {
    let line = lines[i].trim();
    if (!line) continue;
    let highlight = false;
    if (line.endsWith('*')) {
      highlight = true;
      line = line.slice(0, -1).trimEnd();
    }
    let prefix: string | undefined;
    const pipeIdx = line.indexOf('|');
    if (pipeIdx >= 0) {
      prefix = line.slice(pipeIdx + 1).trim() || undefined;
      line = line.slice(0, pipeIdx);
    }
    const eqIdx = line.indexOf('=');
    const label = eqIdx > 0 ? line.slice(0, eqIdx).trim() : '';
    const path = eqIdx > 0 ? line.slice(eqIdx + 1).trim() : '';
    if (!label || !path) {
      throw new Error(`按钮「${buttonName}」结果字段第 ${i + 1} 行格式应为 标签=路径`);
    }
    out.push({
      label,
      path,
      ...(highlight ? { highlight: true } : {}),
      ...(prefix ? { prefix } : {}),
    });
  }
  return out;
}

export function draftFromButton(b: QueryButton): QueryButtonDraft {
  return {
    key: nextDraftKey(),
    name: b.name ?? '',
    method: b.method === 'POST' ? 'POST' : 'GET',
    url: b.url ?? '',
    headersText: headersToText(b.headers),
    body: b.body ?? '',
    successPath: b.success_path ?? '',
    successValue: b.success_value ?? '',
    errorPath: b.error_path ?? '',
    fieldsText: fieldsToText(b.result_fields ?? []),
  };
}

/** 编辑态 → QueryButton[]，契约校验：name/url/result_fields 必填、method 枚举、url 必须 http(s) */
export function serializeQueryButtons(drafts: QueryButtonDraft[]): QueryButton[] {
  return drafts.map((d, i) => {
    const name = d.name.trim();
    if (!name) throw new Error(`第 ${i + 1} 个按钮请填写名称`);
    const url = d.url.trim();
    if (!url) throw new Error(`按钮「${name}」请填写 URL`);
    if (!/^https?:\/\//i.test(url)) {
      throw new Error(`按钮「${name}」URL 必须以 http:// 或 https:// 开头`);
    }
    const resultFields = textToFields(d.fieldsText, name);
    if (resultFields.length === 0) {
      throw new Error(`按钮「${name}」至少需要一个结果字段`);
    }
    return {
      name,
      method: d.method,
      url,
      headers: textToHeaders(d.headersText, name),
      body: d.method === 'POST' && d.body.trim() ? d.body : null,
      success_path: d.successPath.trim() || null,
      success_value: d.successValue.trim() || null,
      error_path: d.errorPath.trim() || null,
      result_fields: resultFields,
    };
  });
}
