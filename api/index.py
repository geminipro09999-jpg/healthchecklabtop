import os
import sys
import json
import traceback

# Ensure project root is on sys.path so api_server can be imported
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask, request, jsonify

app = Flask(__name__)

# Lazy-load LaptopApiHandler to avoid import errors at module level
_laptop_handler = None

def _get_handler():
    global _laptop_handler
    if _laptop_handler is None:
        from api_server import LaptopApiHandler
        _laptop_handler = LaptopApiHandler
    return _laptop_handler


@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
def catch_all(path):
    """Catch-all route that delegates to LaptopApiHandler."""
    import io

    if request.method == "OPTIONS":
        resp = jsonify({})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return resp, 200

    try:
        HandlerClass = _get_handler()

        # Build a shim request object compatible with LaptopApiHandler
        class ShimRequest:
            pass

        shim = ShimRequest()
        # Reconstruct full path with query string
        full_path = request.full_path if request.query_string else request.path
        shim.command = request.method
        shim.path = full_path
        shim.headers = dict(request.headers)
        shim.rfile = io.BytesIO(request.get_data())

        # Capture response
        response_wfile = io.BytesIO()
        response_status = [200]
        response_headers = {}

        # Monkey-patch the handler instance
        class VercelHandler(HandlerClass):
            def __init__(self):
                # Skip SimpleHTTPRequestHandler.__init__ (it tries to handle the request via socket)
                self.command = shim.command
                self.path = shim.path
                self.headers = shim.headers
                self.rfile = shim.rfile
                self.wfile = response_wfile
                self.requestline = f"{shim.command} {shim.path} HTTP/1.1"
                self.request_version = "HTTP/1.1"
                self.close_connection = True

            def send_response(self, code, message=None):
                response_status[0] = code

            def send_header(self, key, value):
                response_headers[key] = value

            def end_headers(self):
                pass

            def log_message(self, format, *args):
                pass  # Suppress logs

        handler_instance = VercelHandler()

        # Dispatch
        method = request.method.upper()
        method_func = getattr(handler_instance, f"do_{method}", None)
        if method_func:
            method_func()
        else:
            return jsonify({"error": "Method not allowed"}), 405

        # Get response body
        response_wfile.seek(0)
        body = response_wfile.read()

        from flask import Response
        content_type = response_headers.get("Content-Type", "application/json; charset=utf-8")
        resp = Response(body, status=response_status[0], content_type=content_type)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    except Exception as e:
        tb = traceback.format_exc()
        return jsonify({"error": str(e), "traceback": tb}), 500

