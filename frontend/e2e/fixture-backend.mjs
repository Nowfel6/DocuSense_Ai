import { createServer } from "node:http";

const port = 3101;

function send(response, status, payload, headers = {}) {
  response.writeHead(status, {
    "content-type": "application/json",
    "x-request-id": "req_e2e_auth",
    ...headers,
  });
  response.end(JSON.stringify(payload));
}

createServer((request, response) => {
  if (request.method === "GET" && request.url === "/health") {
    send(response, 200, { status: "ok" });
    return;
  }
  if (request.method !== "POST" || request.url !== "/api/v1/auth/login") {
    send(response, 404, { success: false });
    return;
  }

  let raw = "";
  request.setEncoding("utf8");
  request.on("data", (chunk) => {
    raw += chunk;
    if (raw.length > 16_384) request.destroy();
  });
  request.on("end", () => {
    let body;
    try {
      body = JSON.parse(raw);
    } catch {
      send(response, 422, { detail: { code: "INVALID_REQUEST" } });
      return;
    }

    if (body.email === "rate@example.test") {
      send(response, 429, { detail: { code: "RATE_LIMITED" } }, { "retry-after": "30" });
      return;
    }
    if (body.email !== "operator@example.test" || body.password !== "correct password") {
      send(response, 401, {
        detail: { code: "INVALID_CREDENTIALS", message: "Authentication request was rejected." },
      });
      return;
    }

    send(response, 200, {
      success: true,
      data: {
        access_token: "fixture-token-never-sent-to-browser",
        token_type: "bearer",
        user: {
          id: "8fe77ea8-eebb-4e31-bcb2-e69467064708",
          company_id: "3cf4b83f-ebd9-449f-8756-d8cc190dfde2",
          email: "operator@example.test",
          full_name: "Example Operator",
          role: "operator",
          company_name: "Example Workspace",
        },
      },
      message: "Login successful.",
    });
  });
}).listen(port, "127.0.0.1", () => {
  process.stdout.write("Auth fixture backend listening on http://127.0.0.1:3101\n");
});
