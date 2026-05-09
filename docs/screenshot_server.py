"""Tiny HTTP server that receives base64 image data and saves to files."""
from http.server import HTTPServer, BaseHTTPRequestHandler
import base64, json, os, threading, time

SAVE_DIR = os.path.join(os.path.dirname(__file__), 'screenshots')
os.makedirs(SAVE_DIR, exist_ok=True)

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            filename = data.get('filename', 'screenshot.jpg')
            b64data = data.get('data', '').split(',')[-1]
            with open(os.path.join(SAVE_DIR, filename), 'wb') as f:
                f.write(base64.b64decode(b64data))
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            self.wfile.write(b'OK')
            print(f'Saved: {filename}')
        except Exception as e:
            self.send_response(500)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(str(e).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.end_headers()

    def log_message(self, *args): pass  # Suppress log spam

from http.server import ThreadingHTTPServer
server = ThreadingHTTPServer(('localhost', 9989), Handler)
print('Screenshot server listening on port 9989')
server.serve_forever()
