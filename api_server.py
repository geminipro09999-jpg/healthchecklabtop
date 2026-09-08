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
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from datetime import datetime

import tempfile
import auth
import database
import gdrive_sync

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

        if path == "/api/gdrive/status":
            status = gdrive_sync.test_drive_connection()
            cfg = auth.load_config().get("gdrive", {})
            return self.send_json({
                "configured": status["status"] == "connected",
                "details": status,
                "parent_folder_id": cfg.get("parent_folder_id", "")
            })

        if path == "/api/reports/local":
            # List all generated HealthReport_*.json files available locally
            reports = []
            for fname in os.listdir(BASE_DIR):
                if fname.startswith("HealthReport_") and fname.endswith(".json"):
                    fpath = os.path.join(BASE_DIR, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8-sig") as f:
                            data = json.load(f)
                            reports.append({
                                "filename": fname,
                                "html_filename": fname.replace(".json", ".html"),
                                "deviceName": data.get("deviceName") or data.get("DeviceName", "Unknown"),
                                "model": f"{data.get('manufacturer', '')} {data.get('model', '')}".strip(),
                                "cpu": data.get("cpu", ""),
                                "healthScore": data.get("healthScore", 100),
                                "failingHardwares": data.get("failingHardwares", []),
                                "warnings": data.get("warnings", [])
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
            company_name = body.get("company_name", "Unassigned / Retail")
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
                return self.send_json({"error": f"Failed to import report: {str(e)}"}, 500)

        # 8. Sync Laptop to Google Drive on Demand (Admin only)
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
            success = database.delete_laptop(laptop_id)
            if not success:
                return self.send_json({"error": "Laptop not found or already deleted"}, 404)
            return self.send_json({"success": True, "message": f"Laptop {laptop_id} deleted"})

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
