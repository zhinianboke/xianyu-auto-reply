/**
 * API 同步脚本：从 openapi.json 生成 TypeScript 类型。
 *
 * 用法: npx tsx scripts/sync-api.ts [--url URL]
 */
import { execSync } from 'child_process';
import { existsSync } from 'fs';
import { resolve } from 'path';

const SPEC_FILE = resolve('api/generated/openapi.json');
const OUTPUT_FILE = resolve('api/generated/types.ts');

function main() {
  const urlArg = process.argv.find((a) => a.startsWith('--url='));
  const url = urlArg ? urlArg.split('=')[1] : null;

  if (!existsSync(SPEC_FILE) || url) {
    console.log('提取 OpenAPI spec...');
    const cmd = url
      ? `python scripts/extract-openapi.py --url ${url}`
      : 'python scripts/extract-openapi.py';
    execSync(cmd, { stdio: 'inherit', cwd: process.cwd() });
  }

  if (!existsSync(SPEC_FILE)) {
    console.error('OpenAPI spec 文件不存在，无法继续');
    process.exit(1);
  }

  console.log('生成 TypeScript 类型...');
  execSync(
    `npx openapi-typescript "${SPEC_FILE}" -o "${OUTPUT_FILE}"`,
    { stdio: 'inherit' }
  );

  console.log('✓ API 类型已生成到', OUTPUT_FILE);

  console.log('TypeScript 编译检查...');
  try {
    execSync('npx tsc --noEmit', { stdio: 'inherit' });
    console.log('✓ 编译通过，无类型错误');
  } catch {
    console.log('⚠ 存在类型错误，需要修复 wrappers 中的调用');
  }
}

main();
