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

async function importWorkflow(workflow) {
  if (!workflow) throw new Error('Missing workflow payload')
  await waitForCanvasReady()
  await app.loadGraphData(workflow)
  app.graph?.setDirtyCanvas?.(true, true)
  return safeGraphSnapshot()
}

app.registerExtension({
  name: `${BRIDGE_NS}.iframe`,
  async setup() {
    try {
      await waitForCanvasReady()
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
        postToParent('workflow-exported', { workflow: safeGraphSnapshot() })
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
