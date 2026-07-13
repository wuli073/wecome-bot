import { readdir, readFile, stat } from 'node:fs/promises'
import { join } from 'node:path'

const root = new URL('..', import.meta.url)
const targetDirs = ['src', 'tests']
const failures = []

async function walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const file = join(dir, entry.name)
    if (entry.isDirectory()) {
      await walk(file)
      continue
    }
    if (!file.endsWith('.ts') && !file.endsWith('.html') && !file.endsWith('.css')) {
      continue
    }
    const content = await readFile(file, 'utf8')
    if (content.includes('\t')) {
      failures.push(`${file}: contains tab characters`)
    }
    if (content.includes('runtime-info.json')) {
      failures.push(`${file}: forbidden runtime-info.json reference`)
    }
  }
}

for (const folder of targetDirs) {
  const dir = new URL(folder, root)
  const filePath = dir.pathname
  try {
    const meta = await stat(filePath)
    if (meta.isDirectory()) {
      await walk(filePath)
    }
  } catch {
    // ignore missing directories during bootstrap
  }
}

if (failures.length > 0) {
  console.error(failures.join('\n'))
  process.exit(1)
}
