import { app } from "/scripts/app.js"

const BRIDGE_NS = 'graviton-bridge'

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

async function waitForCanvasReady(timeoutMs = 10000) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    const hasGraph = Boolean(app.graph)
    const hasCanvas = Boolean(app.canvas || app.graph?.canvas)
    if (hasGraph && hasCanvas) return
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
  throw new Error('Timed out waiting for Comfy canvas initialization')
}

async function waitForUiRuntimeReady(timeoutMs = 10000) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    const hasWindowApp = Boolean(window.app)
    const hasWindowGraph = Boolean(window.graph)
    if (hasWindowApp && hasWindowGraph) return
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
  throw new Error('Timed out waiting for Comfy UI runtime initialization')
}

async function importWorkflow(workflow) {
  if (!workflow) throw new Error('Missing workflow payload')
  await waitForCanvasReady()
  await waitForUiRuntimeReady()
  if (typeof app.handleFile !== 'function') {
    throw new Error('Comfy app.handleFile is unavailable')
  }

  const json = JSON.stringify(workflow)
  const file = new File([json], 'graviton-bridge.json', {
    type: 'application/json'
  })

  const importOnce = async () => {
    await app.handleFile(file, 'file_drop')
  }

  const maxAttempts = 30
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      await importOnce()
      break
    } catch (error) {
      const message = String(error?.message || error)
      const isCanvasStoreRace = message.includes('getCanvas: canvas is null')
      const isLastAttempt = attempt === maxAttempts
      if (!isCanvasStoreRace || isLastAttempt) {
        throw error
      }
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
  }

  app.graph?.setDirtyCanvas?.(true, true)
  return (await exportPromptSnapshot()) ?? safeGraphSnapshot()
}

app.registerExtension({
  name: `${BRIDGE_NS}.iframe`,
  async setup() {
    try {
      await waitForCanvasReady()
      await waitForUiRuntimeReady()
      postToParent('ready', { version: 1, hasGraph: Boolean(app.graph) })
    } catch (error) {
      postToParent('error', {
        stage: 'setup',
        message: String(error?.message || error)
      })
    }

    window.addEventListener('message', async (event) => {
      const data = event?.data || {}
      if (data.source !== 'graviton-host') return

      if (data.type === 'ping') {
        postToParent('pong', { now: Date.now() })
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
