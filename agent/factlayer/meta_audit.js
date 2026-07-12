// Meta-audit layer for the floor-plan render pipeline.
//
// The first audit checks an image against the fact layer. This layer checks the
// checker and the inputs to the checker:
//   1. render contract: what may be visible from this camera, what must not be
//   2. prompt preflight: the generation prompt must not leak off-camera facts as
//      drawable objects
//   3. audit audit: a "pass" from the visual audit must itself be structurally
//      coherent before an image can be released

const OFF_CAMERA_RE = /\b(behind|outside|out[- ]of[- ]view|outside the view cone)\b/i
const DOOR_RE = /\b(door|doorway|opening|threshold|frame|handle|bi[- ]?fold|bifold|entrance)\b/i
const WINDOW_RE = /\b(window|glazing|casement|sliding|sill|parapet)\b/i
const NEGATIVE_CONTEXT_RE = /\b(no|not|never|must not|do not|forbid|forbidden|outside|behind|out[- ]of[- ]view|crop it out|not visible)\b/i

const STOPWORDS = new Set([
  'the', 'and', 'with', 'from', 'this', 'that', 'room', 'wall', 'plan', 'notes',
  'near', 'mid', 'far', 'left', 'right', 'ahead', 'only', 'must', 'visible',
  'camera', 'distance', 'bearing', 'into', 'under', 'over', 'side',
])
const WEAK_COMPONENT_WORDS = new Set(['door', 'doorway', 'opening', 'threshold', 'frame', 'handle', 'bi-fold', 'bifold'])

export const isOffCamera = (component) =>
  OFF_CAMERA_RE.test(`${component?.bearing || ''} ${component?.notes || ''}`)

export const visibleComponents = (room) =>
  (room.expected_components || []).filter((c) => !isOffCamera(c))

export const offCameraComponents = (room) =>
  (room.expected_components || []).filter(isOffCamera)

const componentText = (component) =>
  `${component?.what || ''} ${component?.notes || ''}`.trim()

const isDoorLike = (component) => DOOR_RE.test(componentText(component))
const isWindowLike = (component) => WINDOW_RE.test(componentText(component))

const wordsFor = (component) => {
  const base = componentText(component)
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, ' ')
    .split(/\s+/)
    .filter((w) => w.length > 3 && !STOPWORDS.has(w))
  const extra = []
  if (isDoorLike(component)) extra.push('door', 'doorway', 'opening', 'threshold', 'frame', 'handle', 'bi-fold', 'bifold')
  if (/kitchen/i.test(componentText(component))) extra.push('kitchen')
  if (/study/i.test(componentText(component))) extra.push('study')
  if (/hall/i.test(componentText(component))) extra.push('hall')
  return [...new Set([...base, ...extra])]
}

const mentionsComponent = (text, component) => {
  const lower = String(text || '').toLowerCase()
  const hasWord = (word) => {
    const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    return new RegExp(`(^|[^a-z0-9-])${escaped}([^a-z0-9-]|$)`, 'i').test(lower)
  }
  const strongWords = wordsFor(component)
    .filter((w) => !WEAK_COMPONENT_WORDS.has(w))
  const hasStrongWord = strongWords.some(hasWord)
  if (!hasStrongWord) return false
  if (isDoorLike(component)) return DOOR_RE.test(lower)
  return true
}

const splitText = (text, mode) =>
  String(text || '')
    .split(mode === 'style' ? /\s*[,;]\s*|\.\s+/ : /\.\s+|;\s+/)
    .map((s) => s.trim())
    .filter(Boolean)

export function scopeTextToView(text, room, mode = 'sentence') {
  const outOfView = offCameraComponents(room)
  if (!text || !outOfView.length) return text || ''
  return splitText(text, mode)
    .filter((piece) => !outOfView.some((component) =>
      mentionsComponent(piece, component) && !NEGATIVE_CONTEXT_RE.test(piece)))
    .join(mode === 'style' ? ', ' : ' ')
}

export function styleVetoes(style = '') {
  const s = String(style).toLowerCase()
  const vetoes = []
  if (/\bno\s+(grid|grille|muntin|louvre|louver|bars?)\b/.test(s) && /window/.test(s)) {
    vetoes.push({
      id: 'no-window-grid',
      element: 'window',
      fatal: false,
      evidence: 'Homeowner brief forbids window grids/grilles.',
      edit_instruction: 'Remove all visible window grilles, muntins, louvres and extra horizontal bars; keep one clean HDB window band with plain glass panes.',
    })
  }
  if (/\bno\s+false\s+ceiling\b/.test(s)) {
    vetoes.push({
      id: 'no-false-ceiling',
      element: 'ceiling',
      fatal: false,
      evidence: 'Homeowner brief forbids false ceiling.',
      edit_instruction: 'Remove false ceiling features and keep a flat HDB concrete ceiling with simple surface lighting.',
    })
  }
  return vetoes
}

export function buildRenderContract(room, style = '') {
  const inView = visibleComponents(room)
  const outOfView = offCameraComponents(room)
  const visibleSummary = inView.map((c) => {
    const bearing = c.bearing ? ` (${c.bearing}${c.distance ? `, ${c.distance}` : ''})` : ''
    return `${c.what}${bearing}`
  }).join('; ')
  const visibleDoors = inView
    .filter(isDoorLike)
    .map((c) => `${c.what}${c.bearing ? ` (${c.bearing})` : ''}`)
    .join('; ')
  const scopedStyle = scopeTextToView(style, room, 'style') || style
  return {
    room: room.name,
    inView,
    outOfView,
    visibleSummary,
    visibleDoors,
    hasVisibleWindow: inView.some(isWindowLike) || WINDOW_RE.test(`${room.visible_from_camera || ''}`) && !/zero visible windows/i.test(`${room.visible_from_camera || ''}`),
    scopedCamera: scopeTextToView(room.camera, room) || 'standing at the marked camera point for this room, looking toward the in-view component manifest',
    scopedActualFunction: scopeTextToView(room.actual_function, room),
    scopedDesignNotes: scopeTextToView(room.design_notes, room),
    scopedRenderBrief: scopeTextToView(room.render_brief, room),
    scopedStyle,
    vetoes: styleVetoes(style),
  }
}

export function renderGuard(room, style = '') {
  const contract = buildRenderContract(room, style)
  const lines = []
  if (contract.outOfView.length) {
    lines.push(
      `META-AUDIT RENDER GUARD: the following plan facts are outside this camera view and are non-drawable context only: ${JSON.stringify(contract.outOfView)}. Do not render them, their frames, handles, trim, shadows or reflections.`
    )
  }
  if (contract.vetoes.some((v) => v.id === 'no-window-grid')) {
    lines.push(
      'META-AUDIT RENDER GUARD: no-grid window means no security grille, no muntins, no louvres, no decorative slats and no extra horizontal bars; use plain clear glass panes only.'
    )
  }
  if (contract.vetoes.some((v) => v.id === 'no-false-ceiling')) {
    lines.push(
      'META-AUDIT RENDER GUARD: no false ceiling means a flat HDB concrete ceiling, no recessed cove, no dropped perimeter tray and no L-box unless the room-specific fact layer explicitly requires it.'
    )
  }
  return lines.join(' ')
}

export function auditPromptContract(room, style = '', prompt = '') {
  const contract = buildRenderContract(room, style)
  const violations = []
  const text = String(prompt || '')

  if (/\bDoors:\s/i.test(text)) {
    violations.push({
      layer: 'meta',
      element: 'legacy-door-leak',
      fatal: true,
      evidence: 'Prompt contains a legacy all-doors field. Door facts must be scoped to the camera view.',
      edit_instruction: 'Replace raw room.doors text with the in-view door/opening manifest only.',
    })
  }

  if (contract.outOfView.length && !/MUST NOT be visible|non-drawable|outside this camera view|outside the view cone/i.test(text)) {
    violations.push({
      layer: 'meta',
      element: 'missing-off-camera-guard',
      fatal: true,
      evidence: 'Prompt has off-camera components but no explicit non-visibility guard.',
      edit_instruction: 'Add a guard that off-camera components must not be rendered.',
    })
  }

  for (const component of contract.outOfView) {
    const unsafe = splitText(text, 'sentence').find((piece) =>
      !/^The view must contain EXACTLY\b/.test(piece) &&
      mentionsComponent(piece, component) && !NEGATIVE_CONTEXT_RE.test(piece))
    if (unsafe) {
      violations.push({
        layer: 'meta',
        element: 'off-camera-positive-leak',
        fatal: true,
        evidence: `Off-camera component "${component.what}" is mentioned as drawable context: ${unsafe.slice(0, 220)}`,
        edit_instruction: `Remove or rephrase positive render instructions for off-camera component "${component.what}".`,
      })
    }
  }

  if (contract.vetoes.some((v) => v.id === 'no-window-grid') &&
      !/no security grille|no visible security grille|no extra horizontal bars|plain clear glass/i.test(text)) {
    violations.push({
      layer: 'meta',
      element: 'missing-window-grid-veto',
      fatal: false,
      evidence: 'Brief says no grid on window, but prompt does not expand that veto into model-resistant terms.',
      edit_instruction: 'Expand no-grid into no security grille, no muntins, no louvres and no horizontal bars.',
    })
  }

  if (contract.vetoes.some((v) => v.id === 'no-false-ceiling') &&
      !/flat HDB concrete ceiling|no recessed cove|no dropped perimeter tray/i.test(text)) {
    violations.push({
      layer: 'meta',
      element: 'missing-false-ceiling-veto',
      fatal: false,
      evidence: 'Brief says no false ceiling, but prompt does not expand that veto into model-resistant terms.',
      edit_instruction: 'Expand no-false-ceiling into a flat HDB concrete ceiling instruction.',
    })
  }

  return {
    pass: violations.every((v) => !v.fatal),
    violations,
    contract: {
      room: contract.room,
      inView: contract.inView,
      outOfView: contract.outOfView,
      vetoes: contract.vetoes.map((v) => v.id),
    },
  }
}

export function auditAuditResult(audit, contractOrRoom, style = '') {
  const contract = contractOrRoom?.inView
    ? contractOrRoom
    : buildRenderContract(contractOrRoom || {}, style)
  const violations = []

  if (!audit) {
    violations.push({
      layer: 'meta',
      element: 'audit-unavailable',
      fatal: true,
      evidence: 'Primary visual audit did not return a result.',
      edit_instruction: 'Do not release the image as passed; rerun audit or mark it as manually reviewed.',
    })
    return { pass: false, violations }
  }

  if (typeof audit.pass !== 'boolean') {
    violations.push({
      layer: 'meta',
      element: 'audit-schema',
      fatal: true,
      evidence: 'Audit result is missing a boolean pass field.',
      edit_instruction: 'Reject this audit result and rerun with the strict JSON schema.',
    })
  }

  if (!Array.isArray(audit.violations)) {
    violations.push({
      layer: 'meta',
      element: 'audit-schema',
      fatal: true,
      evidence: 'Audit result is missing a violations array.',
      edit_instruction: 'Reject this audit result and rerun with the strict JSON schema.',
    })
  }

  if (audit.pass && /unverifiable/i.test(String(audit.room || ''))) {
    violations.push({
      layer: 'meta',
      element: 'audit-contradiction',
      fatal: true,
      evidence: 'Audit claims pass while room identity is unverifiable.',
      edit_instruction: 'Set pass=false or rerun the audit with the marked camera plan.',
    })
  }

  if (audit.pass && Array.isArray(audit.violations) && audit.violations.some((v) => Number(v.layer) === 1 || Number(v.layer) === 2)) {
    violations.push({
      layer: 'meta',
      element: 'audit-contradiction',
      fatal: true,
      evidence: 'Audit claims pass while still listing L1/L2 fatal violations.',
      edit_instruction: 'Set pass=false when any L1/L2 violation remains.',
    })
  }

  if (audit.pass && contract.inView?.length && !audit.components_seen?.length) {
    violations.push({
      layer: 'meta',
      element: 'audit-incomplete',
      fatal: true,
      evidence: 'Audit claims pass without listing components_seen.',
      edit_instruction: 'Rerun audit and require an explicit component list before accepting pass.',
    })
  }

  if (audit.pass && contract.vetoes?.length) {
    const auditText = JSON.stringify(audit).toLowerCase()
    for (const veto of contract.vetoes) {
      if (veto.id === 'no-window-grid' && !/window|grid|grille|muntin|louvre|bar/.test(auditText)) {
        violations.push({
          layer: 'meta',
          element: 'audit-veto-coverage',
          fatal: false,
          evidence: 'Audit pass does not mention checking the no-grid window veto.',
          edit_instruction: 'Rerun or manually verify the no-grid window veto.',
        })
      }
      if (veto.id === 'no-false-ceiling' && !/ceiling|l-box|false/.test(auditText)) {
        violations.push({
          layer: 'meta',
          element: 'audit-veto-coverage',
          fatal: false,
          evidence: 'Audit pass does not mention checking the no-false-ceiling veto.',
          edit_instruction: 'Rerun or manually verify the ceiling veto.',
        })
      }
    }
  }

  return { pass: violations.every((v) => !v.fatal), violations }
}

export const metaFatalCount = (metaAudit) =>
  (metaAudit?.violations || []).filter((v) => v.fatal).length

export const scoreMetaAudit = (metaAudit) => {
  if (!metaAudit) return 1000
  if (metaAudit.pass && !metaAudit.violations?.length) return 0
  return (metaAudit.violations || []).reduce((sum, v) => sum + (v.fatal ? 100 : 5), 0)
}
