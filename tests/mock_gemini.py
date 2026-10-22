"""Máy chủ giả lập Gemini để kiểm thử (không dùng khóa thật)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def start(responder):
    """responder(model, key, body) -> (status, dict). Trả về (server, base_url, log)."""
    log = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            model = self.path.split("/models/")[-1].split(":")[0]
            key = self.headers.get("x-goog-api-key", "")
            log.append({"path": self.path, "key": key, "body": body, "model": model, "query": "?" in self.path})
            status, payload = responder(model, key, body)
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}", log


def ok(text, **usage):
    return 200, {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 400, **usage}}
