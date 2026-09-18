(() => {
  "use strict";

  const pageHosts = new Set(["prism.daoyezongzi.org"]);
  const query = new URLSearchParams(window.location.search);
  const enabled = pageHosts.has(window.location.hostname) || query.get("pages") === "1";
  if (!enabled) return;

  const SNAPSHOT_OWNER_ID = "usr-01f9f18ddf81440f80e6b97db526427d";
  const SNAPSHOT_PATH = "/static/pages-snapshot.json";
  const originalFetch = window.fetch.bind(window);
  const snapshotReady = originalFetch(SNAPSHOT_PATH).then(response => {
    if (!response.ok) throw new Error("本地快照文件读取失败");
    return response.json();
  }).then(snapshot => {
    if (snapshot.schema_version !== "prism-pages-snapshot.v1") {
      throw new Error("本地快照版本不受支持");
    }
    if (snapshot.owner_id !== SNAPSHOT_OWNER_ID) {
      throw new Error("本地快照账户标识不一致");
    }
    return snapshot;
  });

  document.body.classList.add("dev-mode");
  document.getElementById("dev-mode-badge")?.remove();
  const ownerInput = document.getElementById("owner-id");
  if (ownerInput) ownerInput.value = SNAPSHOT_OWNER_ID;
  localStorage.setItem(
    "prism_custom_user_profile_v2",
    JSON.stringify({ownerId: SNAPSHOT_OWNER_ID}),
  );
  window.PRISM_PAGES_SNAPSHOT = true;
  window.PRISM_PAGES_SNAPSHOT_READY = snapshotReady;

  const responseFromRoute = route => new Response(route.body, {
    status: route.status,
    headers: route.headers,
  });

  const unavailableResponse = (method, url) => new Response(JSON.stringify({
    schema_version: "prism-pages-snapshot-error.v1",
    status: "UNAVAILABLE",
    error_code: "SNAPSHOT_ROUTE_NOT_CAPTURED",
    message: "当前本地快照没有保存该请求的响应。",
    method,
    path: url.pathname,
  }), {
    status: 409,
    headers: {"Content-Type": "application/json; charset=utf-8"},
  });

  window.fetch = (input, init) => {
    const request = new Request(input, init);
    const url = new URL(request.url, window.location.href);
    if (!url.pathname.startsWith("/api/")) return originalFetch(input, init);
    return snapshotReady.then(snapshot => {
      const method = request.method.toUpperCase();
      const exactKey = method + " " + url.pathname + url.search;
      const pathKey = method + " " + url.pathname;
      const route = snapshot.routes[exactKey] || snapshot.routes[pathKey];
      return route ? responseFromRoute(route) : unavailableResponse(method, url);
    });
  };
})();
