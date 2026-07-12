// Register a useful render as an additional/alternate-view asset.
//
// Usage:
//   node demo/register_additional_asset.js <renderPath> <roomName> <reason> <cx> <cy> <lx> <ly> [primaryCameraPlan]

import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import { registerAdditionalAsset } from '../agent/factlayer/additional_assets.js'

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..')

const [
  renderArg,
  roomName,
  reason,
  cx,
  cy,
  lx,
  ly,
  primaryCameraPlanArg,
] = process.argv.slice(2)

if (!renderArg || !roomName || !reason || !cx || !cy || !lx || !ly) {
  console.error('Usage: node demo/register_additional_asset.js <renderPath> <roomName> <reason> <cx> <cy> <lx> <ly> [primaryCameraPlan]')
  process.exit(1)
}

const lastPlan = JSON.parse(fs.readFileSync(path.join(ROOT, 'demo/lastplan.json'), 'utf8'))
const renderPath = path.resolve(ROOT, renderArg)
const primaryCameraPlan = primaryCameraPlanArg ? path.resolve(ROOT, primaryCameraPlanArg) : null

const { record, logPath, sidecar } = await registerAdditionalAsset({
  planPath: lastPlan.file,
  renderPath,
  roomName,
  reason,
  sourceStatus: 'blocked_primary_viewpoint',
  primaryCameraPlan,
  alternateCamera: {
    camera_px: { x: Number(cx), y: Number(cy) },
    look_at_px: { x: Number(lx), y: Number(ly) },
    label: `${roomName} · alternate view`,
  },
  manualJudgement: {
    design_reference_usable: true,
    primary_fact_layer_pass: false,
  },
})

console.log(JSON.stringify({ record, logPath, sidecar }, null, 2))
