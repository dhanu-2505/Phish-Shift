const API_PATHS = new Set([
  "/api/auth/csrf",
  "/api/auth/register",
  "/api/auth/login",
  "/api/auth/me",
  "/api/auth/logout",
  "/api/predict",
  "/api/scans",
  "/api/dashboard/summary",
  "/api/model/evaluation",
]);

function backendOrigin() {
  const configured = process.env.PHISHSHIFT_BACKEND_URL;
  if (!configured) {
    throw new Error("Backend URL is not configured.");
  }

  const origin = new URL(configured);
  if (
    origin.protocol !== "https:" ||
    origin.username ||
    origin.password ||
    origin.pathname !== "/" ||
    origin.search ||
    origin.hash
  ) {
    throw new Error("Backend URL configuration is invalid.");
  }
  return origin;
}

function isAllowedPath(pathname, prefix) {
  if (prefix === "/api") {
    return API_PATHS.has(pathname) || /^\/api\/scans\/[1-9]\d*$/.test(pathname);
  }
  return pathname === "/health/db" || pathname === "/health/model";
}

async function readBody(request) {
  if (request.body !== undefined) {
    const body = Buffer.isBuffer(request.body)
      ? request.body
      : Buffer.from(
          typeof request.body === "string"
            ? request.body
            : JSON.stringify(request.body),
        );
    if (body.length > 256 * 1024) {
      throw new Error("Request body exceeds the allowed size.");
    }
    return body;
  }

  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 256 * 1024) {
      throw new Error("Request body exceeds the allowed size.");
    }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

export async function proxy(request, response, prefix) {
  const method = request.method ?? "GET";
  if (!["GET", "POST"].includes(method)) {
    response.setHeader("Allow", "GET, POST");
    response.status(405).json({ detail: "Method not allowed." });
    return;
  }

  let requestUrl;
  let destination;
  try {
    requestUrl = new URL(request.url ?? "/", "https://vercel.invalid");
    if (!isAllowedPath(requestUrl.pathname, prefix)) {
      response.status(404).json({ detail: "Not found." });
      return;
    }
    destination = new URL(requestUrl.pathname + requestUrl.search, backendOrigin());
  } catch {
    response.status(503).json({ detail: "Backend service is not configured." });
    return;
  }

  const headers = new Headers();
  for (const name of ["accept", "content-type", "cookie", "x-csrf-token"]) {
    const value = request.headers[name];
    if (typeof value === "string") headers.set(name, value);
  }

  let body;
  if (method === "POST") {
    try {
      body = await readBody(request);
    } catch {
      response.status(413).json({ detail: "Request body is too large." });
      return;
    }
  }

  try {
    const upstream = await fetch(destination, {
      method,
      headers,
      body,
      redirect: "manual",
    });
    response.status(upstream.status);
    response.setHeader(
      "Content-Type",
      upstream.headers.get("content-type") ?? "application/json",
    );
    response.setHeader(
      "Cache-Control",
      upstream.headers.get("cache-control") ?? "no-store",
    );
    const cookies = upstream.headers.getSetCookie?.();
    if (cookies?.length) response.setHeader("Set-Cookie", cookies);
    response.end(Buffer.from(await upstream.arrayBuffer()));
  } catch {
    response.status(502).json({ detail: "Backend service is temporarily unavailable." });
  }
}
