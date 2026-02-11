import { app } from "/scripts/app.js"

const BRIDGE_NS = 'graviton-bridge'
let debugLoggedOnce = false

function postToParent(type, payload = {}) {
  window.parent?.postMessage(
    {
      source: BRIDGE_NS,
      type,
      payload
    },
    '*'
  )
}

function safeGraphSnapshot() {
  try {
    return app.graph?.serialize?.() ?? null
  } catch {
    return null
  }
}

function isApiPromptFormat(workflow) {
  if (!workflow || typeof workflow !== 'object' || Array.isArray(workflow)) {
    return false
  }
  const values = Object.values(workflow)
  if (!values.length) return false
  return values.every((node) => {
    if (!node || typeof node !== 'object' || Array.isArray(node)) return false
    return (
      typeof node.class_type === 'string' &&
      node.inputs &&
      typeof node.inputs === 'object' &&
      !Array.isArray(node.inputs)
    )
  })
}

function normalizeApiPrompt(workflow) {
  if (!workflow || typeof workflow !== 'object' || Array.isArray(workflow)) {
    return workflow
  }
  const normalized = {}
  for (const [key, value] of Object.entries(workflow)) {
    if (
      value &&
      typeof value === 'object' &&
      !Array.isArray(value) &&
      typeof value.class_type === 'string' &&
      value.inputs &&
      typeof value.inputs === 'object' &&
      !Array.isArray(value.inputs)
    ) {
      normalized[key] = value
    }
  }
  return normalized
}

function extractWorkflowPayload(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    return input
  }
  if (input.workflow && typeof input.workflow === 'object') {
    return input.workflow
  }
  return input
}

async function exportPromptSnapshot() {
  try {
    if (typeof app.graphToPrompt === 'function') {
      const promptResult = await app.graphToPrompt(app.rootGraph ?? app.graph)
      return promptResult?.output ?? null
    }
    return null
  } catch {
    return null
  }
}

async function importWorkflow(workflow) {
  if (!workflow) throw new Error('Missing workflow payload')
  if (typeof app.handleFile !== 'function') {
    throw new Error('Comfy app.handleFile is unavailable')
  }

  const extractedWorkflow = extractWorkflowPayload(workflow)
  const normalizedWorkflow = isApiPromptFormat(extractedWorkflow)
    ? normalizeApiPrompt(extractedWorkflow)
    : extractedWorkflow

  if (!debugLoggedOnce) {
    debugLoggedOnce = true
    const keys = normalizedWorkflow && typeof normalizedWorkflow === 'object'
      ? Object.keys(normalizedWorkflow).slice(0, 10)
      : []
    const looksLikePrompt = isApiPromptFormat(normalizedWorkflow)
    console.log('[graviton-bridge] import debug', {
      looksLikePrompt,
      keyCount: keys.length,
      sampleKeys: keys,
      hasWorkflowWrapper:
        !!(workflow && typeof workflow === 'object' && workflow.workflow)
    })
    try {
      const preview = JSON.stringify(normalizedWorkflow).slice(0, 400)
      console.log('[graviton-bridge] import preview', preview)
    } catch (_e) {
      console.log('[graviton-bridge] import preview unavailable')
    }
  }

  const json = JSON.stringify(normalizedWorkflow)
  const file = new File([json], 'graviton-bridge.json', {
    type: 'application/json'
  })
  await app.handleFile(file, 'file_drop')

  app.graph?.setDirtyCanvas?.(true, true)
  return (await exportPromptSnapshot()) ?? safeGraphSnapshot()
}

app.registerExtension({
  name: `${BRIDGE_NS}.iframe`,
  async setup() {
    postToParent('ready', { version: 1, hasGraph: Boolean(app.graph) })

    window.addEventListener('message', async (event) => {
      const data = event?.data || {}
      if (data.source !== 'graviton-host') return

      if (data.type === 'ping') {
        postToParent('pong', {
          now: Date.now(),
          ready: Boolean(
            window.app &&
            window.app.vueAppReady &&
            app.graph &&
            (app.canvas || app.graph?.canvas)
          ),
          hasApp: Boolean(window.app),
          vueAppReady: Boolean(window.app && window.app.vueAppReady),
          hasGraph: Boolean(app.graph),
          hasCanvas: Boolean(app.canvas || app.graph?.canvas),
          hasHandleFile: typeof app.handleFile === 'function'
        })
        return
      }

      if (data.type === 'export-workflow') {
        const workflow = (await exportPromptSnapshot()) ?? safeGraphSnapshot()
        postToParent('workflow-exported', { workflow })
        return
      }

      if (data.type === 'import-workflow') {
        try {
          const workflow = data.payload?.workflow
          const applied = await importWorkflow(workflow)
          postToParent('workflow-imported', { workflow: applied })
        } catch (error) {
          postToParent('error', {
            stage: 'import-workflow',
            message: String(error?.message || error)
          })
        }
      }
    })
  }
})
