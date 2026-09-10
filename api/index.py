import os
import sys
import json
import io
import urllib.parse
from http.server import SimpleHTTPRequestHandler

# Ensure project root is on sys.path so api_server can be imported
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Import the existing request handler implementation
from api_server import LaptopApiHandler

# Create a singleton instance of the handler class (no server socket needed)
_api_handler = LaptopApiHandler

def _build_request(event):
    """Convert Vercel event dict into a minimal request object compatible with LaptopApiHandler."""
    class Req:
        def __init__(self):
            self.command = event.get("httpMethod", "GET")
            self.path = event.get("path", "/")
            self.headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
            body = event.get("body", "")
            if isinstance(body, str):
                self.rfile = io.BytesIO(body.encode("utf-8"))
            else:
                self.rfile = io.BytesIO()
            self.wfile = io.BytesIO()
            self.response_code = 200
        def send_response(self, code, message=None):
            self.response_code = code
        def send_header(self, key, value):
            pass
        def end_headers(self):
            pass
    return Req()

def _handler(event, context):
    """Vercel entry point.
    Delegates request handling to the existing :class:`LaptopApiHandler`.
    Returns a Vercel‑compatible response dictionary.
    """
    req = _build_request(event)
    # Instantiate the handler (it inherits SimpleHTTPRequestHandler)
    # Pass dummy socket arguments because the base class expects them.
    handler_instance = _api_handler(req, client_address=("0.0.0.0", 0), server=None)
    method = req.command.upper()
    if method == "GET":
        handler_instance.do_GET()
    elif method == "POST":
        handler_instance.do_POST()
    elif method == "PUT":
        handler_instance.do_PUT()
    elif method == "DELETE":
        handler_instance.do_DELETE()
    elif method == "OPTIONS":
        handler_instance.do_OPTIONS()
    else:
        return {
            "statusCode": 405,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Method not allowed"})
        }
    # Retrieve response body written by the handler
    req.wfile.seek(0)
    body_bytes = req.wfile.read()
    try:
        body = body_bytes.decode()
    except Exception:
        body = ""
    return {
        "statusCode": getattr(req, "response_code", 200),
        "headers": {"Content-Type": "application/json"},
        "body": body
    }
handler = _handler  # expose for Vercel
