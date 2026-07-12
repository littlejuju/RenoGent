// Additional render assets.
//
// Primary renders must match the current fact-layer camera contract. A render
// that is useful as a design reference but fails that primary viewpoint contract
// is registered here instead of being discarded or mislabeled as passed.

import { execFile } from 'child_process'
import { promisify } from 'util'
import { createHash } from 'crypto'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const execFileP = promisify(execFile)
const HERE = path.dirname(fileURLToPath(import.meta.url))

const shortHash = (file) => createHash('sha256').update(fs.readFileSync(file)).digest('hex').slice(0, 8)

const slugFor = (name = 'asset') =>
  name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'asset'

export async function annotateAlternateView(planPath, roomName, hash, alternateCamera) {
  if (!alternateCamera?.camera_px || !alternateCamera?.look_at_px) return null
  const slug = slugFor(roomName)
  const out = planPath.replace(/\.[a-z]+$/i, `-${slug}-alt-cam-${hash}.jpg`)
  await execFileP('python3', [
    path.join(HERE, 'annotate.py'),
    planPath,
    out,
    String(alternateCamera.camera_px.x),
    String(alternateCamera.camera_px.y),
    String(alternateCamera.look_at_px.x),
    String(alternateCamera.look_at_px.y),
    alternateCamera.label || `${roomName} · alternate asset #${hash}`,
  ], { timeout: 30000 })
  return out
}

export async function registerAdditionalAsset({
  planPath,
  renderPath,
  roomName,
  sourceStatus = 'blocked',
  reason,
  primaryCameraPlan = null,
  alternateCamera = null,
  manualJudgement = null,
}) {
  if (!fs.existsSync(planPath)) throw new Error(`Plan not found: ${planPath}`)
  if (!fs.existsSync(renderPath)) throw new Error(`Render not found: ${renderPath}`)
  const hash = shortHash(renderPath)
  const alternateCameraPlan = await annotateAlternateView(planPath, roomName, hash, alternateCamera)
  const record = {
    ts: new Date().toISOString(),
    type: 'additional_asset',
    room: roomName,
    hash,
    render: path.resolve(renderPath),
    source_status: sourceStatus,
    reason,
    primary_camera_plan: primaryCameraPlan ? path.resolve(primaryCameraPlan) : null,
    alternate_camera_plan: alternateCameraPlan ? path.resolve(alternateCameraPlan) : null,
    alternate_camera: alternateCamera,
    manual_judgement: manualJudgement,
    release_policy: 'May be shown as a design reference or alternate-view asset; must not be counted as a primary fact-layer pass.',
  }
  const logPath = path.join(path.dirname(planPath), 'additional-assets.jsonl')
  fs.appendFileSync(logPath, JSON.stringify(record) + '\n')
  const sidecar = renderPath.replace(/\.[a-z]+$/i, '-additional-asset.json')
  fs.writeFileSync(sidecar, JSON.stringify(record, null, 2))
  return { record, logPath, sidecar }
}
