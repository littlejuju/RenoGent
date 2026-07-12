// Render release gate.
//
// Generation success is not release success. A render can be written to disk
// while still being quarantined. Only releaseGate(...).pass === true can enter
// human-facing surfaces such as WhatsApp, docs galleries, or manual candidate
// lists for approval.
import { execFile } from 'child_process'
import { promisify } from 'util'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const execFileP = promisify(execFile)
const HERE = path.dirname(fileURLToPath(import.meta.url))

export function localHookForRoom(roomName = '') {
  const normalized = String(roomName).toLowerCase().replace(/&/g, 'and')
  if (/\bliving\b/.test(normalized) || /\bdining\b/.test(normalized)) {
    return path.join(HERE, 'hooks/living_dining.py')
  }
  return null
}

function parseHookJson(stdout = '') {
  const start = stdout.search(/[{\[]/)
  if (start < 0) throw new Error('local hook returned no JSON')
  return JSON.parse(stdout.slice(start))
}

function normalizeViolation(v, fallbackElement = 'release-gate') {
  return {
    layer: v.layer || 'release',
    element: v.element || fallbackElement,
    evidence: v.evidence || JSON.stringify(v),
    edit_instruction: v.edit_instruction || v.editInstruction || 'Do not release this render; regenerate or surgically edit the offending element.',
  }
}

export async function runLocalHook(roomName, renderPath) {
  const hook = localHookForRoom(roomName)
  if (!hook) {
    return {
      pass: null,
      hook: null,
      state: 'no-local-hook',
      violations: [],
      result: null,
    }
  }

  try {
    const { stdout } = await execFileP('python3', [hook, renderPath], {
      encoding: 'utf8',
      timeout: 60000,
      maxBuffer: 2 * 1024 * 1024,
    })
    const result = parseHookJson(stdout)
    return {
      pass: result.pass === true,
      hook,
      state: result.pass === true ? 'local-hook-passed' : 'local-hook-failed',
      violations: (result.violations || []).map((v) => normalizeViolation(v, 'local-hook')),
      result,
    }
  } catch (err) {
    let result = null
    try {
      result = parseHookJson(err.stdout || '')
    } catch {}
    return {
      pass: false,
      hook,
      state: 'local-hook-failed',
      violations: result?.violations?.length
        ? result.violations.map((v) => normalizeViolation(v, 'local-hook'))
        : [normalizeViolation({
            element: 'local-hook-error',
            evidence: String(err.stderr || err.message || err),
          })],
      result,
    }
  }
}

export async function releaseGate({
  roomName,
  renderPath,
  visualAudit = null,
  metaAudit = null,
  requireVisualAudit = false,
  requireMetaAudit = false,
  requireLocalHook = false,
} = {}) {
  const checks = []
  const violations = []

  if (!renderPath || !fs.existsSync(renderPath)) {
    violations.push(normalizeViolation({
      element: 'file-missing',
      evidence: `Render file does not exist: ${renderPath || '(empty)'}`,
    }))
  }

  if (requireVisualAudit && !visualAudit) {
    violations.push(normalizeViolation({
      element: 'visual-audit-missing',
      evidence: 'Primary visual audit is required before release.',
    }))
  }
  if (visualAudit && visualAudit.pass !== true) {
    violations.push(...(visualAudit.violations || []).map((v) => normalizeViolation(v, 'visual-audit-failed')))
    if (!visualAudit.violations?.length) {
      violations.push(normalizeViolation({
        element: 'visual-audit-failed',
        evidence: 'Primary visual audit did not pass.',
      }))
    }
  }

  if (requireMetaAudit && !metaAudit) {
    violations.push(normalizeViolation({
      element: 'meta-audit-missing',
      evidence: 'Meta-audit is required before release.',
    }))
  }
  if (metaAudit && metaAudit.pass !== true) {
    violations.push(...(metaAudit.violations || []).map((v) => normalizeViolation(v, 'meta-audit-failed')))
    if (!metaAudit.violations?.length) {
      violations.push(normalizeViolation({
        element: 'meta-audit-failed',
        evidence: 'Meta-audit did not pass.',
      }))
    }
  }

  const localHook = await runLocalHook(roomName, renderPath)
  checks.push(localHook)
  if (localHook.pass === false) {
    violations.push(...localHook.violations)
  }
  if (requireLocalHook && localHook.pass === null) {
    violations.push(normalizeViolation({
      element: 'local-hook-missing',
      evidence: `No local release hook is registered for room: ${roomName || '(unknown)'}`,
    }))
  }

  return {
    room: roomName || null,
    render: renderPath || null,
    pass: violations.length === 0,
    state: violations.length === 0 ? 'release-ready' : 'quarantined',
    checks,
    violations,
  }
}

export const scoreReleaseGate = (gate) => {
  if (!gate) return 1000
  if (gate.pass) return 0
  return Math.max(100, (gate.violations || []).length * 100)
}

async function main(argv) {
  const [roomName, renderPath] = argv.slice(2).filter((arg) => !arg.startsWith('--'))
  if (!roomName || !renderPath) {
    console.error('usage: node agent/factlayer/release_gate.js <room-name> <render-image> [--allow-missing-local-hook]')
    return 2
  }
  const allowMissingLocalHook = argv.includes('--allow-missing-local-hook')
  const result = await releaseGate({
    roomName,
    renderPath: path.resolve(renderPath),
    requireLocalHook: !allowMissingLocalHook,
  })
  console.log(JSON.stringify(result, null, 2))
  return result.pass ? 0 : 1
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv).then((code) => process.exit(code))
}
