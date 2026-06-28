#!/usr/bin/env python3
"""
Kindle Display — HTTP Image Server
Serves weather.png and news.png over HTTP.
The Kindle fetches these with wget.
"""

import os
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE = os.path.dirname(__file__)
ROUTES = {
    "/weather.png": os.path.join(BASE, "kindle_weather.png"),
    "/news.png":    os.path.join(BASE, "kindle_news.png"),
}
PORT = 8765


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = ROUTES.get(self.path)
        if path:
            try:
                with open(path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Image not found")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        # Log Kindle accesses (for diagnostics)
        import datetime
        line = "%s %s %s\n" % (
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            self.address_string(),
            (fmt % args),
        )
        try:
            with open(os.path.join(BASE, "access.log"), "a") as f:
                f.write(line)
        except Exception:
            pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Serving {list(ROUTES.keys())} on port {PORT}")
    server.serve_forever()
