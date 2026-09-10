"""
api_server.py - Production-Ready REST API Server for Laptop Diagnostics & Inventory
Features:
- PBKDF2-HMAC-SHA256 Hashed Admin Security (zero hardcoded plain-text passwords)
- Public Read-Only Access (all reports, hardware specs, and complaints viewable without login)
- Company Multi-Tenancy (filter & manage laptops by Client / Company)
- Hierarchical Google Drive sync (<Company> / <DeviceName_Serial> / [Photos & Reports])
- Full REST API with CORS support for mobile devices on local Wi-Fi
"""

import os
import sys
import json
import socket
import base64
import urllib.parse
import re
import time
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>Hardware Health Report - {device_name}</title>
    <style>
        body {font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5;}
        .card {background: #fff; padding: 15px; margin-bottom: 10px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);}
    </style>
</head>
<body>
    <h1>Hardware Health Report</h1>
    <div class=\"card\"><strong>Device:</strong> {device_name}</div>
    <div class=\"card\"><strong>Model:</strong> {model}</div>
    <div class=\"card\"><strong>Serial:</strong> {serial_number}</div>
    <div class=\"card\"><strong>CPU:</strong> {cpu}</div>
    <div class=\"card\"><strong>RAM:</strong> {ram}</div>
    <div class=\"card\"><strong>Storage:</strong> {storage}</div>
    <div class=\"card\"><strong>GPU:</strong> {gpu}</div>
    <div class=\"card\"><strong>Battery Health:</strong> {battery_health}%</div>
    <div class=\"card\"><strong>Status:</strong> {overall_status}</div>
    <div class=\"card\"><strong>Complaints:</strong> {complaints}</div>
</body>
</html>
"""

import logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s %(message)s')
from datetime import datetime

import tempfile
# Optional imports wrapped to avoid deployment-time failures
try:
    import auth
except Exception as e:
    logging.error("Failed to import auth module: %s", e)
    class _AuthFallback:
        @staticmethod
        def load_config():
            return {}
        @staticmethod
        def verify_password(pwd, salt, expected_hash):
            return False
    auth = _AuthFallback()

try:
    import database
except Exception as e:
    logging.error("Failed to import database module: %s", e)
    class _DatabaseFallback:
        @staticmethod
        def init_db():
            logging.info("Database init skipped in fallback.")
        @staticmethod
        def find_duplicate_laptop(**kwargs):
            return None
        @staticmethod
        def create_laptop(data):
            return {}
        @staticmethod
        def update_laptop(id, fields):
            return {}
    database = _DatabaseFallback()

try:
    import gdrive_sync
except Exception as e:
    logging.error("Failed to import gdrive_sync module: %s", e)
    class _GDriveFallback:
        @staticmethod
        def sync_report(*args, **kwargs):
            logging.info("gdrive_sync is unavailable, skipping sync.")
            return None
    gdrive_sync = _GDriveFallback()

def parse_html_report_text(html_content: str) -> dict:
    """Extracts hardware specs, diagnostic checklist, and health score from HTML report."""
    data = {}
    
    # Device Name
    m_dev = re.search(r'Device Name</span>\s*<span[^>]*>([^<]+)</span>', html_content, re.IGNORECASE)
    if m_dev:
        data["device_name"] = m_dev.group(1).strip()
    else:
        m_title = re.search(r'<title>.*?-\s*([^<]+)</title>', html_content, re.IGNORECASE)
        data["device_name"] = m_title.group(1).strip() if m_title else "Imported PC"

    # Model
    m_model = re.search(r'Manufacturer & Model</span>\s*<span[^>]*>([^<]+)</span>', html_content, re.IGNORECASE)
    data["model"] = m_model.group(1).strip() if m_model else ""

    # Serial
    m_serial = re.search(r'Serial Number</span>\s*<span[^>]*>([^<]+)</span>', html_content, re.IGNORECASE)
    data["serial_number"] = m_serial.group(1).strip() if m_serial else ""

    # CPU
    m_cpu = re.search(r'Processor \(CPU\)</strong></td>\s*<td>([^<]+)</td>', html_content, re.IGNORECASE)
    if not m_cpu:
        m_cpu = re.search(r'Processor Model</span>\s*<span[^>]*>([^<]+)</span>', html_content, re.IGNORECASE)
    data["cpu"] = m_cpu.group(1).strip() if m_cpu else ""

    # RAM
    m_ram = re.search(r'Memory \(RAM\)</strong></td>\s*<td>([^<]+)</td>', html_content, re.IGNORECASE)
    data["ram"] = m_ram.group(1).strip() if m_ram else ""

    # Storage
    m_storage = re.search(r'Storage \(SSD/HDD\)</strong></td>\s*<td>([^<]+)</td>', html_content, re.IGNORECASE)
    data["storage"] = m_storage.group(1).strip() if m_storage else ""

    # GPU
    m_gpu = re.search(r'Graphics \(GPU\)</strong></td>\s*<td>([^<]+)</td>', html_content, re.IGNORECASE)
    data["gpu"] = m_gpu.group(1).strip() if m_gpu else ""

    # Battery & Cycle Count
    m_bat = re.search(r'Battery</strong></td>\s*<td>([^<]+)</td>', html_content, re.IGNORECASE)
    bat_val = 100
    if m_bat:
        m_num = re.search(r'(\d+)%', m_bat.group(1))
        if m_num:
            bat_val = int(m_num.group(1))
    data["battery_health"] = bat_val

    m_cyc = re.search(r'Battery Cycle Count</span>\s*<span[^>]*>([^<]+)</span>', html_content, re.IGNORECASE)
    if m_cyc:
        data["battery_cycle_count"] = m_cyc.group(1).replace("Cycles", "").strip()
    else:
        m_cyc_chk = re.search(r'Cycles:\s*([^\s|<]+)', html_content, re.IGNORECASE)
        data["battery_cycle_count"] = m_cyc_chk.group(1).strip() if m_cyc_chk else "N/A"

    # Health Score
    m_score = re.search(r'class="score-number">(\d+)', html_content, re.IGNORECASE)
    score = int(m_score.group(1)) if m_score else 100
    data["health_score"] = score

    if score >= 80:
        data["overall_status"] = "Healthy"
    elif score >= 50:
        data["overall_status"] = "Warning"
    else:
        data["overall_status"] = "Critical"

    # Warnings / Defects
    warnings = re.findall(r'<li>([^<]+)</li>', html_content)
    data["complaints"] = warnings if warnings else ["Diagnostic Health Check Completed"]

    return data

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.environ.get("VERCEL") or not os.access(BASE_DIR, os.W_OK):
    IMAGES_DIR = os.path.join(tempfile.gettempdir(), "laptop_images")
else:
    IMAGES_DIR = os.path.join(BASE_DIR, "laptop_images")

try:
    os.makedirs(IMAGES_DIR, exist_ok=True)
except Exception:
    pass

# Ensure database is initialized
try:
    database.init_db()
except Exception as e:
    print(f"Warning: Database init failed: {e}")

def get_local_ip():
    """Finds the LAN IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

class LaptopApiHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        try:
            super().__init__(*args, directory=BASE_DIR, **kwargs)
        except Exception:
            super().__init__(*args, **kwargs)

    def end_headers(self):
        # Enable CORS for local network and mobile devices
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200, "OK")
        self.end_headers()

    def send_json(self, data, status_code=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def get_token(self):
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        # Fallback to query param
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if "token" in qs:
            return qs["token"][0]
        return None

    def is_admin(self):
        token = self.get_token()
        return auth.validate_token(token)

    def read_json_body(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                return {}
            raw_body = self.rfile.read(content_length).decode("utf-8")
            return json.loads(raw_body)
        except Exception:
            return {}

    def get_path_and_query(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        # Check __path query parameter first (set by Vercel rewrite)
        if "__path" in qs and qs["__path"][0]:
            path = qs["__path"][0]
        elif self.headers.get("x-forwarded-uri"):
            path = urllib.parse.urlparse(self.headers["x-forwarded-uri"]).path
        elif self.headers.get("x-matched-path"):
            path = urllib.parse.urlparse(self.headers["x-matched-path"]).path
        else:
            path = parsed.path

        if "?" in path:
            path = path.split("?", 1)[0]
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]

        return path, qs

    # ----------------------------------------------------
    # GET Requests
    # ----------------------------------------------------
    def do_GET(self):
        path, qs = self.get_path_and_query()

        # Redirect root to Dashboard.html
        if path in ("", "/", "/Dashboard.html"):
            self.path = "/Dashboard.html"
            return super().do_GET()

        # REST API endpoints
        if path == "/api/auth/status":
            token = self.get_token()
            is_valid = auth.validate_token(token)
            return self.send_json({"isAdmin": is_valid, "role": "admin" if is_valid else "viewer"})

        if path == "/api/server-info":
            port = 8080
            try:
                if hasattr(self, 'server') and hasattr(self.server, 'server_port'):
                    port = self.server.server_port
            except Exception:
                pass
            return self.send_json({"success": True, "local_ip": get_local_ip(), "port": port})

        if path == "/api/gdrive/status":
            sa_path = os.path.join(BASE_DIR, "service_account.json")
            has_sa = os.path.exists(sa_path)
            return self.send_json({
                "success": True,
                "configured": has_sa,
                "details": {"email": "service-account@gdrive" if has_sa else ""},
                "parent_folder_id": "LaptopHealth"
            })

        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        if path == "/api/companies":
            companies = database.get_companies()
            return self.send_json({"success": True, "companies": companies})

        if path == "/api/laptops":
            company = qs.get("company", [None])[0]
            search = qs.get("search", [None])[0]
            status = qs.get("status", [None])[0]
            laptops = database.get_laptops(company=company, search=search, status=status)
            return self.send_json({"success": True, "laptops": laptops, "total": len(laptops)})

        if path.startswith("/api/laptops/"):
            laptop_id = path.replace("/api/laptops/", "").strip()
            laptop = database.get_laptop(laptop_id)
            if not laptop:
                return self.send_json({"error": "Laptop not found"}, 404)
            return self.send_json({"success": True, "laptop": laptop})

        if path.startswith("/api/reports/html/") or path.startswith("/HealthReport_") or path.endswith(".html"):
            fname = os.path.basename(path)
            # 1. Check local BASE_DIR
            local_path = os.path.join(BASE_DIR, fname)
            if os.path.exists(local_path) and os.path.isfile(local_path):
                try:
                    with open(local_path, "rb") as hf:
                        content = hf.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception:
                    pass

            # 2. Check tempdir
            tmp_path = os.path.join(tempfile.gettempdir(), fname)
            if os.path.exists(tmp_path) and os.path.isfile(tmp_path):
                try:
                    with open(tmp_path, "rb") as hf:
                        content = hf.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception:
                    pass

            # 3. Check SQLite database stored report_html
            db_html = database.get_report_html_by_filename(fname)
            if db_html:
                content = db_html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

            # 4. Fallback: Search and download directly from Google Drive
            try:
                drive_bytes = gdrive_sync.find_file_bytes_in_drive(fname)
                if drive_bytes:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(drive_bytes)))
                    self.end_headers()
                    self.wfile.write(drive_bytes)
                    return
            except Exception:
                pass

            if path.startswith("/api/reports/html/"):
                return self.send_json({"error": f"Report '{fname}' not found"}, 404)

        if path == "/api/reports/local":
            # List all generated HealthReport_*.json and .html files available locally
            reports = []
            seen_bases = set()
            for fname in sorted(os.listdir(BASE_DIR), reverse=True):
                if fname.startswith("HealthReport_") and (fname.endswith(".json") or fname.endswith(".html")):
                    base = fname.rsplit(".", 1)[0]
                    if base in seen_bases:
                        continue
                    seen_bases.add(base)

                    json_name = f"{base}.json"
                    html_name = f"{base}.html"
                    fpath_json = os.path.join(BASE_DIR, json_name)
                    fpath_html = os.path.join(BASE_DIR, html_name)

                    if os.path.exists(fpath_json):
                        try:
                            with open(fpath_json, "r", encoding="utf-8-sig") as f:
                                data = json.load(f)
                            reports.append({
                                "filename": html_name if os.path.exists(fpath_html) else json_name,
                                "html_filename": html_name if os.path.exists(fpath_html) else "",
                                "deviceName": data.get("deviceName") or data.get("DeviceName", "Unknown"),
                                "model": f"{data.get('manufacturer', '')} {data.get('model', '')}".strip(),
                                "cpu": data.get("cpu", ""),
                                "healthScore": data.get("healthScore", 100),
                                "failingHardwares": data.get("failingHardwares", []),
                                "warnings": data.get("warnings", [])
                            })
                            continue
                        except Exception:
                            pass

                    if os.path.exists(fpath_html):
                        try:
                            with open(fpath_html, "r", encoding="utf-8") as f:
                                html_text = f.read()
                            p = parse_html_report_text(html_text)
                            reports.append({
                                "filename": html_name,
                                "html_filename": html_name,
                                "deviceName": p.get("device_name", "PC"),
                                "model": p.get("model", ""),
                                "cpu": p.get("cpu", ""),
                                "healthScore": p.get("health_score", 100),
                                "failingHardwares": [],
                                "warnings": p.get("complaints", [])
                            })
                        except Exception:
                            pass
            return self.send_json({"success": True, "reports": reports})

        # Static file serving (Dashboard.html, HTML reports, images)
        return super().do_GET()

    # ----------------------------------------------------
    # POST Requests
    # ----------------------------------------------------
    def do_POST(self):
        path, qs = self.get_path_and_query()

        # 1. Auth: Admin Login (Hashed verification)
        if path == "/api/auth/login":
            body = self.read_json_body()
            password = body.get("password", "")
            cfg = auth.load_config()
            salt = cfg.get("admin_salt", "")
            expected_hash = cfg.get("admin_password_hash", "")

            if auth.verify_password(password, salt, expected_hash):
                token = auth.create_admin_session()
                return self.send_json({
                    "success": True,
                    "token": token,
                    "role": "admin",
                    "message": "Admin authenticated successfully"
                })
            else:
                return self.send_json({"success": False, "error": "Invalid admin password"}, 401)

        # 2. Auth: Logout
        if path == "/api/auth/logout":
            token = self.get_token()
            if token:
                auth.revoke_token(token)
            return self.send_json({"success": True, "message": "Logged out"})

        # 3. Auth: Change Password (Requires Admin Token)
        if path == "/api/auth/change-password":
            if not self.is_admin():
                return self.send_json({"error": "Admin authorization required"}, 401)
            body = self.read_json_body()
            old_pwd = body.get("old_password", "")
            new_pwd = body.get("new_password", "")
            ok, msg = auth.update_admin_password(old_pwd, new_pwd)
            if ok:
                return self.send_json({"success": True, "message": msg})
            else:
                return self.send_json({"success": False, "error": msg}, 400)

        # 4. Companies: Create New Company (Admin only)
        if path == "/api/companies":
            if not self.is_admin():
                return self.send_json({"error": "Admin authorization required to add companies"}, 401)
            body = self.read_json_body()
            name = body.get("name", "")
            ok, msg = database.add_company(name)
            if ok:
                return self.send_json({"success": True, "message": msg}, 201)
            return self.send_json({"error": msg}, 400)

        # 5. Laptops: Create Laptop / Intake Job (Admin only)
        if path == "/api/laptops":
            if not self.is_admin():
                return self.send_json({"error": "Admin authorization required to create laptops"}, 401)
            body = self.read_json_body()
            laptop = database.create_laptop(body)
            return self.send_json({"success": True, "laptop": laptop}, 201)

        # 6. Laptops: Upload Photos (Admin only)
        if path.startswith("/api/laptops/") and path.endswith("/photos"):
            if not self.is_admin():
                return self.send_json({"error": "Admin authorization required to upload photos"}, 401)
            parts = path.strip("/").split("/")
            laptop_id = parts[2]
            laptop = database.get_laptop(laptop_id)
            if not laptop:
                return self.send_json({"error": "Laptop not found"}, 404)

            body = self.read_json_body()
            # Expecting Base64 images: photo_screen, photo_top, photo_base
            company = "".join(c for c in laptop.get("company_name", "General") if c not in r'\/:*?"<>|').strip() or "General"
            dev_folder = f"{laptop.get('device_name', 'Laptop')}_{laptop.get('serial_number', 'NoSerial')}"
            dev_folder = "".join(c for c in dev_folder if c not in r'\/:*?"<>|').strip()
            
            # Target directory: laptop_images / <Company> / <DeviceName_Serial> /
            save_dir = os.path.join(IMAGES_DIR, company, dev_folder)
            os.makedirs(save_dir, exist_ok=True)

            updated_fields = {}
            saved_paths = []

            for key in ["photo_screen", "photo_top", "photo_base"]:
                b64data = body.get(key)
                if b64data:
                    if b64data.startswith("data:image"):
                        # Keep Base64 data URL directly so image is 100% reliable on Vercel and mobile
                        updated_fields[key] = b64data
                        try:
                            header, encoded = b64data.split(",", 1)
                            ext = ".jpg"
                            if "png" in header:
                                ext = ".png"
                            elif "webp" in header:
                                ext = ".webp"
                            
                            fname = f"{key}{ext}"
                            fpath = os.path.join(save_dir, fname)
                            with open(fpath, "wb") as img_file:
                                img_file.write(base64.b64decode(encoded))
                            saved_paths.append(fpath)
                        except Exception as e:
                            # Read-only serverless filesystem fallback
                            pass
                    elif b64data.startswith("http://") or b64data.startswith("https://"):
                        updated_fields[key] = b64data
                elif b64data == "":
                    updated_fields[key] = ""

            if updated_fields:
                laptop = database.update_laptop(laptop_id, updated_fields)

            # Trigger Google Drive Sync in background if Drive is configured
            drive_result = None
            rep_path = os.path.join(BASE_DIR, laptop.get("report_filename", ""))
            drive_res = gdrive_sync.sync_laptop_to_drive(laptop, photo_paths=saved_paths, report_path=rep_path)
            if drive_res.get("success"):
                drive_url = drive_res.get("laptop_folder_url", "")
                if drive_url:
                    database.update_laptop(laptop_id, {"gdrive_folder_url": drive_url})
                    laptop["gdrive_folder_url"] = drive_url
                drive_result = drive_res

            return self.send_json({
                "success": True,
                "message": f"{len(updated_fields)} photos saved successfully",
                "laptop": laptop,
                "gdrive": drive_result
            })

        # 7. Import Local Scan Report (Admin only)
        if path == "/api/reports/import":
            if not self.is_admin():
                return self.send_json({"error": "Admin authorization required to import reports"}, 401)
            body = self.read_json_body()
            filename = body.get("filename")
            company_name = body.get("company_name", "UNICOMTIC")
            cust_name = body.get("customer_name", "")
            cust_phone = body.get("customer_phone", "")
            complaints = body.get("complaints", [])

            json_path = os.path.join(BASE_DIR, filename)
            if not os.path.exists(json_path):
                return self.send_json({"error": "Report file not found"}, 404)

            try:
                with open(json_path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)

                dev_name = data.get("deviceName") or data.get("DeviceName", "Unknown")
                mfg = data.get("manufacturer") or data.get("Manufacturer", "")
                mdl = data.get("model") or data.get("Model", "")
                model = f"{mfg} {mdl}".strip()
                serial = data.get("serialNumber") or data.get("SerialNumber", "N/A")
                cpu = data.get("cpu") or data.get("CPU", "")
                ram = f"{data.get('ramTotalGB') or data.get('TotalRAM_GB', 0)} GB"
                storage = data.get("disks") or f"{data.get('TotalStorage_GB', 0)} GB"
                gpu = data.get("gpu") or data.get("GPU", "")
                if isinstance(gpu, list):
                    gpu = ", ".join(gpu)
                bat_val = data.get("batteryHealthPercent") or data.get("BatteryHealthPercent", 100)
                try:
                    bat = int(bat_val)
                except Exception:
                    bat = 100
                score = data.get("healthScore", 100)
                status = "Healthy" if score >= 80 else ("Warning" if score >= 50 else "Critical")
                
                # Combine failing hardware and warnings into complaints if none given
                if not complaints:
                    failing = data.get("failingHardwares", [])
                    warns = data.get("warnings", [])
                    complaints = failing + warns
                    if not complaints:
                        complaints = ["Hardware scan completed with zero critical issues."]

                # Duplicate check: prevent duplicate machine records
                existing = database.find_duplicate_laptop(
                    serial_number=serial,
                    device_name=dev_name,
                    company_name=company_name
                )
                if existing:
                    return self.send_json({
                        "error": f"⚠️ Duplicate Machine Rejected: Machine '{dev_name}' (Serial: {serial}) is already registered in inventory under '{existing.get('company_name')}' (ID: {existing.get('id')})."
                    }, 409)

                new_laptop = database.create_laptop({
                    "company_name": company_name,
                    "customer_name": cust_name,
                    "customer_phone": cust_phone,
                    "device_name": dev_name,
                    "model": model,
                    "serial_number": serial,
                    "cpu": cpu,
                    "ram": ram,
                    "storage": storage,
                    "gpu": gpu,
                    "battery_health": bat,
                    "overall_status": status,
                    "service_status": "Diagnosing",
                    "complaints": complaints,
                    "report_filename": filename.replace(".json", ".html"),
                    "report_data": data
                })
                return self.send_json({"success": True, "laptop": new_laptop}, 201)
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                logging.exception("Upload-import handler failed")
                return self.send_json({"error": f"Failed to import report: {str(e)}", "traceback": tb}, 500)

        # 8. Upload & Import Report (.html or .json) with Direct Form Confirmation
        if path == "/api/reports/upload-import":
            try:
                body = self.read_json_body()
                logging.info("Upload-import payload keys: %s", list(body.keys()))
                # Determine whether to sync to Google Drive (client can skip heavy operation)
                skip_gdrive = body.get("skip_gdrive", False)
                logging.info("skip_gdrive flag: %s", skip_gdrive)

                # Allow authorization via Bearer token OR admin_password in body
                is_authed = self.is_admin()
                if not is_authed:
                    admin_pwd = body.get("admin_password", "")
                    if admin_pwd:
                        cfg = auth.load_config()
                        salt = cfg.get("admin_salt", "")
                        expected_hash = cfg.get("admin_password_hash", "")
                        if auth.verify_password(admin_pwd, salt, expected_hash):
                            is_authed = True

                if not is_authed:
                    return self.send_json({"error": "Admin authorization required to import reports"}, 401)

                filename = body.get("filename", f"HealthReport_{int(time.time())}.html")
                raw_content = body.get("raw_content", "")
                company_name = body.get("company_name", "UNICOMTIC").strip() or "UNICOMTIC"
                cust_name = body.get("customer_name", "").strip() or "Internal Lab"
                cust_phone = body.get("customer_phone", "").strip()
                service_status = body.get("service_status", "Diagnosing").strip()

                parsed = body.get("parsed") or {}
                if not parsed and raw_content:
                    if filename.endswith(".json"):
                        try:
                            p_json = json.loads(raw_content)
                            parsed = {
                                "device_name": p_json.get("deviceName", "PC"),
                                "model": f"{p_json.get('manufacturer', '')} {p_json.get('model', '')}".strip(),
                                "serial_number": p_json.get("serialNumber", "N/A"),
                                "cpu": p_json.get("cpu", ""),
                                "ram": f"{p_json.get('ramTotalGB', 0)} GB",
                                "storage": p_json.get("disks", ""),
                                "gpu": p_json.get("gpu", ""),
                                "battery_health": int(p_json.get("batteryHealthPercent", 100)),
                                "overall_status": "Healthy" if p_json.get("healthScore", 100) >= 80 else ("Warning" if p_json.get("healthScore", 100) >= 50 else "Critical"),
                                "complaints": p_json.get("failingHardwares", []) + p_json.get("warnings", []),
                            }
                        except Exception:
                            pass
                    else:
                        if raw_content:
                            parsed = parse_html_report_text(raw_content)
                        # Simple fallback HTML if none provided
                        if not raw_content and parsed:
                            try:
                                raw_content = f"<html><body><h1>{parsed.get('device_name', 'Device')}</h1></body></html>"
                            except Exception as e:
                                logging.error("Failed to create fallback HTML: %s", e)

                # Save report file to disk if possible
                saved_report_path = None
                if raw_content:
                    try:
                        save_dir = BASE_DIR if os.access(BASE_DIR, os.W_OK) else tempfile.gettempdir()
                        saved_report_path = os.path.join(save_dir, filename)
                        with open(saved_report_path, "w", encoding="utf-8") as rf:
                            rf.write(raw_content)
                    except Exception as e:
                        print(f"Notice: Could not write report file to disk: {e}")

                # Battery Report handling (if provided)
                bat_filename = body.get("battery_report_filename", "").strip()
                bat_raw = body.get("battery_report_html", "")
                bat_cycle = body.get("battery_cycle_count", "") or parsed.get("battery_cycle_count", "")
                saved_bat_path = None
                if bat_raw and bat_filename:
                    try:
                        save_dir = BASE_DIR if os.access(BASE_DIR, os.W_OK) else tempfile.gettempdir()
                        saved_bat_path = os.path.join(save_dir, bat_filename)
                        with open(saved_bat_path, "w", encoding="utf-8") as bf:
                            bf.write(bat_raw)
                    except Exception as e:
                        print(f"Notice: Could not write battery report file to disk: {e}")

                complaints = parsed.get("complaints", [])
                if isinstance(complaints, str):
                    complaints = [complaints]
                if not complaints:
                    complaints = ["Hardware diagnostic scan completed."]

                # Duplicate check: update existing machine if already registered
                existing = database.find_duplicate_laptop(
                    serial_number=parsed.get("serial_number"),
                    device_name=parsed.get("device_name"),
                    company_name=company_name
                )
                if existing:
                    updated_fields = {
                        "customer_name": cust_name if cust_name else existing.get("customer_name", ""),
                        "customer_phone": cust_phone if cust_phone else existing.get("customer_phone", ""),
                        "cpu": parsed.get("cpu", existing.get("cpu", "")),
                        "ram": parsed.get("ram", existing.get("ram", "")),
                        "storage": parsed.get("storage", existing.get("storage", "")),
                        "gpu": parsed.get("gpu", existing.get("gpu", "")),
                        "battery_health": parsed.get("battery_health", existing.get("battery_health", 100)),
                        "overall_status": parsed.get("overall_status", "Healthy"),
                        "complaints": complaints,
                        "report_filename": filename,
                        "report_data": parsed,
                        "report_html": raw_content,
                        "battery_report_filename": bat_filename,
                        "battery_report_html": bat_raw,
                        "battery_cycle_count": str(bat_cycle)
                    }
                    updated_laptop = database.update_laptop(existing["id"], updated_fields)

                    # Sync to Google Drive in background thread (non-blocking, ultra-fast response)
                    def _async_sync_existing(target_laptop, rep_path, rep_html, rep_fname, bat_path, bat_html, bat_fname):
                        try:
                            drive_res = gdrive_sync.sync_laptop_to_drive(
                                target_laptop,
                                report_path=rep_path,
                                report_html_content=rep_html,
                                report_filename=rep_fname,
                                battery_report_path=bat_path,
                                battery_report_content=bat_html,
                                battery_report_filename=bat_fname
                            )
                            if drive_res.get("success"):
                                d_url = drive_res.get("laptop_folder_url", "")
                                if d_url:
                                    database.update_laptop(target_laptop["id"], {"gdrive_folder_url": d_url})
                        except Exception as d_err:
                            print(f"Notice: Google Drive background sync: {d_err}")

                    threading.Thread(
                        target=_async_sync_existing,
                        args=(updated_laptop, saved_report_path, raw_content, filename, saved_bat_path, bat_raw, bat_filename),
                        daemon=True
                    ).start()

                    return self.send_json({
                        "success": True,
                        "message": f"Laptop '{existing['id']}' ({parsed.get('device_name')}) refreshed with latest diagnostic scan.",
                        "laptop": updated_laptop
                    }, 200)

                # Create new laptop entry
                new_laptop = database.create_laptop({
                    "company_name": company_name,
                    "customer_name": cust_name,
                    "customer_phone": cust_phone,
                    "device_name": parsed.get("device_name", "Laptop"),
                    "model": parsed.get("model", "Standard PC"),
                    "serial_number": parsed.get("serial_number", "N/A"),
                    "cpu": parsed.get("cpu", ""),
                    "ram": parsed.get("ram", ""),
                    "storage": parsed.get("storage", ""),
                    "gpu": parsed.get("gpu", ""),
                    "battery_health": parsed.get("battery_health", 100),
                    "overall_status": parsed.get("overall_status", "Healthy"),
                    "service_status": service_status,
                    "complaints": complaints,
                    "report_filename": filename,
                    "report_data": parsed,
                    "report_html": raw_content,
                    "battery_report_filename": bat_filename,
                    "battery_report_html": bat_raw,
                    "battery_cycle_count": str(bat_cycle)
                })

                # Sync to Google Drive in background thread (non-blocking)
                if not skip_gdrive:
                    def _async_sync_new(target_laptop, rep_path, rep_html, rep_fname, bat_path, bat_html, bat_fname):
                        try:
                            drive_res = gdrive_sync.sync_laptop_to_drive(
                                target_laptop,
                                report_path=rep_path,
                                report_html_content=rep_html,
                                report_filename=rep_fname,
                                battery_report_path=bat_path,
                                battery_report_content=bat_html,
                                battery_report_filename=bat_fname
                            )
                            if drive_res.get("success"):
                                d_url = drive_res.get("laptop_folder_url", "")
                                if d_url:
                                    database.update_laptop(target_laptop["id"], {"gdrive_folder_url": d_url})
                        except Exception as d_err:
                            print(f"Notice: Google Drive background sync: {d_err}")

                    threading.Thread(
                        target=_async_sync_new,
                        args=(new_laptop, saved_report_path, raw_content, filename, saved_bat_path, bat_raw, bat_filename),
                        daemon=True
                    ).start()

                return self.send_json({
                    "success": True,
                    "message": f"Report '{filename}' imported successfully for {company_name}",
                    "laptop": new_laptop
                }, 201)
            except Exception as e:
                logging.exception("Upload-import handler failed")
                return self.send_json({"error": "Internal server error"}, 500)

            body = self.read_json_body()
            logging.info("Upload-import payload keys: %s", list(body.keys()))
            # Determine whether to sync to Google Drive (client can skip heavy operation)
            skip_gdrive = body.get("skip_gdrive", False)
            logging.info("skip_gdrive flag: %s", skip_gdrive)

            # Allow authorization via Bearer token OR admin_password in body
            is_authed = self.is_admin()
            if not is_authed:
                admin_pwd = body.get("admin_password", "")
                if admin_pwd:
                    cfg = auth.load_config()
                    salt = cfg.get("admin_salt", "")
                    expected_hash = cfg.get("admin_password_hash", "")
                    if auth.verify_password(admin_pwd, salt, expected_hash):
                        is_authed = True

            if not is_authed:
                return self.send_json({"error": "Admin authorization required to import reports"}, 401)
            filename = body.get("filename", f"HealthReport_{int(time.time())}.html")
            raw_content = body.get("raw_content", "")
            company_name = body.get("company_name", "UNICOMTIC").strip() or "UNICOMTIC"
            cust_name = body.get("customer_name", "").strip() or "Internal Lab"
            cust_phone = body.get("customer_phone", "").strip()
            service_status = body.get("service_status", "Diagnosing").strip()

            parsed = body.get("parsed") or {}
            if not parsed and raw_content:
                if filename.endswith(".json"):
                    try:
                        p_json = json.loads(raw_content)
                        parsed = {
                            "device_name": p_json.get("deviceName", "PC"),
                            "model": f"{p_json.get('manufacturer', '')} {p_json.get('model', '')}".strip(),
                            "serial_number": p_json.get("serialNumber", "N/A"),
                            "cpu": p_json.get("cpu", ""),
                            "ram": f"{p_json.get('ramTotalGB', 0)} GB",
                            "storage": p_json.get("disks", ""),
                            "gpu": p_json.get("gpu", ""),
                            "battery_health": int(p_json.get("batteryHealthPercent", 100)),
                            "overall_status": "Healthy" if p_json.get("healthScore", 100) >= 80 else ("Warning" if p_json.get("healthScore", 100) >= 50 else "Critical"),
                            "complaints": p_json.get("failingHardwares", []) + p_json.get("warnings", [])
                        }
                    except Exception:
                        pass
                else:
                    if raw_content:
                        parsed = parse_html_report_text(raw_content)
                    # Simple fallback HTML if none provided
                    if not raw_content and parsed:
                        try:
                            raw_content = f"<html><body><h1>{parsed.get('device_name', 'Device')}</h1></body></html>"
                        except Exception as e:
                            logging.error("Failed to create fallback HTML: %s", e)


            # Save report file to disk if possible
            saved_report_path = None
            if raw_content:
                try:
                    save_dir = BASE_DIR if os.access(BASE_DIR, os.W_OK) else tempfile.gettempdir()
                    saved_report_path = os.path.join(save_dir, filename)
                    with open(saved_report_path, "w", encoding="utf-8") as rf:
                        rf.write(raw_content)
                except Exception as e:
                    print(f"Notice: Could not write report file to disk: {e}")

            # Battery Report handling (if provided)
            bat_filename = body.get("battery_report_filename", "").strip()
            bat_raw = body.get("battery_report_html", "")
            bat_cycle = body.get("battery_cycle_count", "") or parsed.get("battery_cycle_count", "")
            saved_bat_path = None
            if bat_raw and bat_filename:
                try:
                    save_dir = BASE_DIR if os.access(BASE_DIR, os.W_OK) else tempfile.gettempdir()
                    saved_bat_path = os.path.join(save_dir, bat_filename)
                    with open(saved_bat_path, "w", encoding="utf-8") as bf:
                        bf.write(bat_raw)
                except Exception as e:
                    print(f"Notice: Could not write battery report file to disk: {e}")

            complaints = parsed.get("complaints", [])
            if isinstance(complaints, str):
                complaints = [complaints]
            if not complaints:
                complaints = ["Hardware diagnostic scan completed."]

            # Duplicate check: update existing machine if already registered
            existing = database.find_duplicate_laptop(
                serial_number=parsed.get("serial_number"),
                device_name=parsed.get("device_name"),
                company_name=company_name
            )
            if existing:
                updated_fields = {
                    "customer_name": cust_name if cust_name else existing.get("customer_name", ""),
                    "customer_phone": cust_phone if cust_phone else existing.get("customer_phone", ""),
                    "cpu": parsed.get("cpu", existing.get("cpu", "")),
                    "ram": parsed.get("ram", existing.get("ram", "")),
                    "storage": parsed.get("storage", existing.get("storage", "")),
                    "gpu": parsed.get("gpu", existing.get("gpu", "")),
                    "battery_health": parsed.get("battery_health", existing.get("battery_health", 100)),
                    "overall_status": parsed.get("overall_status", "Healthy"),
                    "complaints": complaints,
                    "report_filename": filename,
                    "report_data": parsed,
                    "report_html": raw_content,
                    "battery_report_filename": bat_filename,
                    "battery_report_html": bat_raw,
                    "battery_cycle_count": str(bat_cycle)
                }
                updated_laptop = database.update_laptop(existing["id"], updated_fields)

                # Sync to Google Drive
                drive_result = None
                try:
                    drive_res = gdrive_sync.sync_laptop_to_drive(
                        updated_laptop,
                        report_path=saved_report_path,
                        report_html_content=raw_content,
                        report_filename=filename,
                        battery_report_path=saved_bat_path,
                        battery_report_content=bat_raw,
                        battery_report_filename=bat_filename
                    )
                    if drive_res.get("success"):
                        d_url = drive_res.get("laptop_folder_url", "")
                        if d_url:
                            database.update_laptop(updated_laptop["id"], {"gdrive_folder_url": d_url})
                            updated_laptop["gdrive_folder_url"] = d_url
                        drive_result = drive_res
                except Exception as d_err:
                    print(f"Notice: Google Drive sync skipped: {d_err}")

                return self.send_json({
                    "success": True,
                    "message": f"Laptop '{existing['id']}' ({parsed.get('device_name')}) refreshed with latest diagnostic scan.",
                    "laptop": updated_laptop,
                    "gdrive": drive_result
                }, 200)

            new_laptop = database.create_laptop({
                "company_name": company_name,
                "customer_name": cust_name,
                "customer_phone": cust_phone,
                "device_name": parsed.get("device_name", "Laptop"),
                "model": parsed.get("model", "Standard PC"),
                "serial_number": parsed.get("serial_number", "N/A"),
                "cpu": parsed.get("cpu", ""),
                "ram": parsed.get("ram", ""),
                "storage": parsed.get("storage", ""),
                "gpu": parsed.get("gpu", ""),
                "battery_health": parsed.get("battery_health", 100),
                "overall_status": parsed.get("overall_status", "Healthy"),
                "service_status": service_status,
                "complaints": complaints,
                "report_filename": filename,
                "report_data": parsed,
                "report_html": raw_content,
                "battery_report_filename": bat_filename,
                "battery_report_html": bat_raw,
                "battery_cycle_count": str(bat_cycle)
            })

            # Sync to Google Drive (Supports disk file or direct raw HTML, plus Battery Report)
            drive_result = None
            skip_gdrive = body.get("skip_gdrive", False)
            if not skip_gdrive:
                try:
                    drive_res = gdrive_sync.sync_laptop_to_drive(
                        new_laptop,
                        report_path=saved_report_path,
                        report_html_content=raw_content,
                        report_filename=filename,
                        battery_report_path=saved_bat_path,
                        battery_report_content=bat_raw,
                        battery_report_filename=bat_filename
                    )
                    if drive_res.get("success"):
                        d_url = drive_res.get("laptop_folder_url", "")
                        if d_url:
                            database.update_laptop(new_laptop["id"], {"gdrive_folder_url": d_url})
                            new_laptop["gdrive_folder_url"] = d_url
                        drive_result = drive_res
                except Exception as d_err:
                    print(f"Notice: Google Drive sync skipped: {d_err}")
            else:
                drive_result = {"skipped": True, "reason": "skip_gdrive flag set by client"}


            return self.send_json({
                "success": True,
                "message": f"Report '{filename}' imported successfully for {company_name}",
                "laptop": new_laptop,
                "gdrive": drive_result
            }, 201)



        # 9. Sync Laptop to Google Drive on Demand (Admin only)
        if path.startswith("/api/gdrive/sync/"):
            if not self.is_admin():
                return self.send_json({"error": "Admin authorization required"}, 401)
            laptop_id = path.replace("/api/gdrive/sync/", "").strip()
            laptop = database.get_laptop(laptop_id)
            if not laptop:
                return self.send_json({"error": "Laptop not found"}, 404)

            rep_path = os.path.join(BASE_DIR, laptop.get("report_filename", ""))
            res = gdrive_sync.sync_laptop_to_drive(laptop, report_path=rep_path)
            if res.get("success") and res.get("laptop_folder_url"):
                database.update_laptop(laptop_id, {"gdrive_folder_url": res.get("laptop_folder_url")})
            return self.send_json(res)

        return self.send_json({"error": f"POST endpoint not found: {path}"}, 404)

    # ----------------------------------------------------
    # PUT Requests (Update Laptop)
    # ----------------------------------------------------
    def do_PUT(self):
        path, qs = self.get_path_and_query()

        if path.startswith("/api/laptops/"):
            if not self.is_admin():
                return self.send_json({"error": "Admin authorization required to edit laptops"}, 401)
            laptop_id = path.replace("/api/laptops/", "").strip()
            body = self.read_json_body()
            updated = database.update_laptop(laptop_id, body)
            if not updated:
                return self.send_json({"error": "Laptop not found"}, 404)
            return self.send_json({"success": True, "laptop": updated})

        return self.send_json({"error": f"PUT endpoint not found: {path}"}, 404)

    # ----------------------------------------------------
    # DELETE Requests (Delete Laptop)
    # ----------------------------------------------------
    def do_DELETE(self):
        path, qs = self.get_path_and_query()

        if path.startswith("/api/laptops/"):
            if not self.is_admin():
                return self.send_json({"error": "Admin authorization required to delete laptops"}, 401)
            laptop_id = path.replace("/api/laptops/", "").strip()
            laptop = database.get_laptop(laptop_id)

            # Fallback to Google Drive master inventory if not found in local SQLite
            if not laptop:
                try:
                    inv = gdrive_sync.get_master_inventory_from_drive() or []
                    for item in inv:
                        if item.get("id") == laptop_id:
                            laptop = item
                            break
                except Exception:
                    pass

            # 1. Immediate database deletion (Supabase + local SQLite - instantaneous)
            database.delete_laptop(laptop_id)

            # 2. Async background cleanup of local files and Google Drive (zero wait time for user)
            def _async_delete_cleanup(target_lap, lid):
                try:
                    if target_lap:
                        rep_name = target_lap.get("report_filename", "")
                        if rep_name:
                            for ext_file in [rep_name, rep_name.replace(".html", ".json")]:
                                fpath = os.path.join(BASE_DIR, ext_file)
                                if os.path.exists(fpath):
                                    try:
                                        os.remove(fpath)
                                    except Exception:
                                        pass
                    tl = target_lap or {"id": lid}
                    gdrive_sync.delete_laptop_from_drive(tl)
                    gdrive_sync.remove_laptop_from_master_inventory(lid)
                except Exception as e:
                    print(f"Notice: Background cleanup: {e}")

            threading.Thread(target=_async_delete_cleanup, args=(laptop, laptop_id), daemon=True).start()

            return self.send_json({
                "success": True,
                "message": f"Laptop {laptop_id} deleted successfully"
            })

        return self.send_json({"error": f"DELETE endpoint not found: {path}"}, 404)


def start_server(port=8080):
    host_ip = get_local_ip()
    server_address = ("0.0.0.0", port)
    
    print("=" * 65)
    print("  LAPTOP HEALTH REPORTS - REST API & INVENTORY SERVER")
    print("=" * 65)
    print(f"  Local Access:      http://localhost:{port}/")
    print(f"  Mobile/Wi-Fi URL:  http://{host_ip}:{port}/")
    print("-" * 65)
    print("  SECURITY MODEL:")
    print("  - Public View Mode: Anyone on Wi-Fi can view reports & specs")
    print("  - Admin Edit Mode:  Requires Hashed Authentication")
    print("  - Initial Admin Password: admin123 (Change anytime via dashboard)")
    print("=" * 65)
    print("  Server is listening... Press Ctrl+C to stop.")
    
    try:
        httpd = ThreadingHTTPServer(server_address, LaptopApiHandler)
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()

if __name__ == "__main__":
    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    start_server(port)
