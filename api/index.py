import os
import sys

# Ensure root directory is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from api_server import LaptopApiHandler

# Vercel Python Serverless handler
handler = LaptopApiHandler
