(async function () {
  function log() {
    console.log.apply(console, ["[graviton-bridge-debug]"].concat(Array.from(arguments)));
  }

  log("window.app?", !!window.app);
  log("vueAppReady?", !!(window.app && window.app.vueAppReady));
  log("app.canvas?", !!(window.app && window.app.canvas));
  log("app.graph?", !!(window.app && window.app.graph));
  log("graph canvas DOM?", !!document.querySelector("#graph-canvas-container canvas"));

  var piniaCanvas = null;
  try {
    piniaCanvas = window.__pinia && window.__pinia._s && window.__pinia._s.get("canvas");
  } catch (e) {
    piniaCanvas = null;
  }
  log("canvasStore exists?", !!piniaCanvas);
  log("canvasStore.canvas?", !!(piniaCanvas && piniaCanvas.canvas));

  if (!(window.app && typeof window.app.handleFile === "function")) {
    log("app.handleFile unavailable");
    return;
  }

  var prompt = {
    "1": {
      class_type: "CheckpointLoaderSimple",
      inputs: { ckpt_name: "anything.safetensors" }
    }
  };

  var file = new File(
    [JSON.stringify(prompt)],
    "graviton-bridge-debug.json",
    { type: "application/json" }
  );

  try {
    await window.app.handleFile(file, "file_drop");
    log("handleFile ok");
  } catch (e) {
    log("handleFile failed:", e && e.message ? e.message : String(e));
    console.error(e);
  }
})();
