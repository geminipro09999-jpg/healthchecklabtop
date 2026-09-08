import os
import sys
from http.server import SimpleHTTPRequestHandler

# Ensure project root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from api_server import LaptopApiHandler

# Top-level handler class recognized by Vercel's Python runtime
class handler(LaptopApiHandler):
    pass
