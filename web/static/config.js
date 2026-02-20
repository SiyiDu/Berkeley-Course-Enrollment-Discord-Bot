(function () {
  const fromRuntime =
    (window.RUNTIME_CONFIG && window.RUNTIME_CONFIG.ENGINE_BASE_URL) ||
    (window.RUNTIME_CONFIG && window.RUNTIME_CONFIG.engineBaseUrl);
  const fromMeta = document.querySelector('meta[name="engine-base-url"]')?.content;
  if (fromRuntime || fromMeta) {
    window.ENGINE_BASE_URL = (fromRuntime || fromMeta || "").replace(/\/$/, "");
  }
})();
