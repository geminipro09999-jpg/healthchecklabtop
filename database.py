"""
database.py - SQLite Database for Laptop Diagnostics & Company Inventory
Handles multi-tenant company inventory, complaints, hardware specs, photos, and reports.
"""

import sqlite3
import os
import json
import uuid
import time
import tempfile
from datetime import datetime
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.environ.get("VERCEL") or not os.access(BASE_DIR, os.W_OK):
    DB_PATH = os.path.join(tempfile.gettempdir(), "laptops.db")
else:
    DB_PATH = os.path.join(BASE_DIR, "laptops.db")

def get_supabase_config():
    """Reads Supabase URL and Key from environment or config.json."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if url and key:
        return url, key
    try:
        cfg_path = os.path.join(BASE_DIR, "config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                sb = cfg.get("supabase", {})
                return sb.get("url"), sb.get("key")
    except Exception:
        pass
    return None, None

def supabase_request(method, endpoint, params=None, json_data=None, prefer=None):
    """Executes a PostgREST API request against the Supabase database."""
    url, key = get_supabase_config()
    if not url or not key:
        return None
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}"
    }
    if json_data is not None:
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer
    
    full_url = f"{url.rstrip('/')}/rest/v1/{endpoint.lstrip('/')}"
    try:
        resp = requests.request(method, full_url, headers=headers, params=params, json=json_data, timeout=8)
        if resp.ok:
            if resp.text:
                try:
                    return resp.json()
                except Exception:
                    return resp.text
            return True
        else:
            print(f"Supabase error ({resp.status_code}): {resp.text}")
            return None
    except Exception as e:
        print(f"Supabase request error: {e}")
        return None

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Companies table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        contact_person TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Laptops table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS laptops (
        id TEXT PRIMARY KEY,
        company_name TEXT NOT NULL,
        customer_name TEXT DEFAULT '',
        customer_phone TEXT DEFAULT '',
        device_name TEXT DEFAULT '',
        model TEXT DEFAULT '',
        serial_number TEXT DEFAULT '',
        cpu TEXT DEFAULT '',
        ram TEXT DEFAULT '',
        storage TEXT DEFAULT '',
        gpu TEXT DEFAULT '',
        battery_health INTEGER DEFAULT 100,
        overall_status TEXT DEFAULT 'Healthy',
        service_status TEXT DEFAULT 'Received',
        complaints TEXT DEFAULT '[]',
        photo_screen TEXT DEFAULT '',
        photo_top TEXT DEFAULT '',
        photo_base TEXT DEFAULT '',
        report_filename TEXT DEFAULT '',
        report_data TEXT DEFAULT '{}',
        gdrive_folder_url TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_laptops_company ON laptops(company_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_laptops_status ON laptops(service_status)")
    
    conn.commit()
    
    # Migration: Add report_html column if missing
    try:
        cursor.execute("ALTER TABLE laptops ADD COLUMN report_html TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE laptops ADD COLUMN battery_report_filename TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE laptops ADD COLUMN battery_report_html TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE laptops ADD COLUMN battery_cycle_count TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass

    # Seed default companies if none exist
    cursor.execute("SELECT COUNT(*) FROM companies")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT OR IGNORE INTO companies (name) VALUES (?)", ("UNICOMTIC",))
        cursor.execute("INSERT OR IGNORE INTO companies (name) VALUES (?)", ("Unassigned / Retail",))
        conn.commit()

    # Migration: Rename 'Unicom Tech Solutions' to 'UNICOMTIC'
    cursor.execute("UPDATE companies SET name = 'UNICOMTIC' WHERE name = 'Unicom Tech Solutions'")
    cursor.execute("UPDATE laptops SET company_name = 'UNICOMTIC' WHERE company_name = 'Unicom Tech Solutions'")
    cursor.execute("INSERT OR IGNORE INTO companies (name) VALUES (?)", ("UNICOMTIC",))
    conn.commit()
    
    # Seed with existing generated report if laptops table is empty
    cursor.execute("SELECT COUNT(*) FROM laptops")
    if cursor.fetchone()[0] == 0:
        seed_existing_reports(conn)
        
    conn.close()

def seed_existing_reports(conn):
    """Auto-populates DB from any existing HealthReport_*.json in the directory."""
    cursor = conn.cursor()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    for fname in os.listdir(base_dir):
        if fname.startswith("HealthReport_") and fname.endswith(".json"):
            json_path = os.path.join(base_dir, fname)
            try:
                with open(json_path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                    
                device_name = data.get("deviceName") or data.get("DeviceName", "Unknown")
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
                status = "Healthy"
                score = data.get("healthScore", 100)
                if score < 50:
                    status = "Critical"
                elif score < 80:
                    status = "Warning"
                
                # Associated HTML report filename
                html_report = fname.replace(".json", ".html")
                html_content = ""
                html_full_path = os.path.join(base_dir, html_report)
                if os.path.exists(html_full_path):
                    try:
                        with open(html_full_path, "r", encoding="utf-8") as hf:
                            html_content = hf.read()
                    except Exception:
                        pass
                else:
                    html_report = ""
                
                lap_hash = abs(hash(f"{serial}_{device_name}")) % 100000
                lap_id = f"LAP-{lap_hash:05d}"
                company = "UNICOMTIC"
                complaints_json = json.dumps(["Routine Hardware Diagnostic Check"])
                
                cursor.execute("""
                INSERT INTO laptops (
                    id, company_name, customer_name, customer_phone,
                    device_name, model, serial_number, cpu, ram, storage, gpu,
                    battery_health, overall_status, service_status, complaints,
                    report_filename, report_data, report_html, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    lap_id, company, "Internal Lab", "+94 77 123 4567",
                    device_name, model, serial, cpu, ram, storage, gpu,
                    bat, status, "Completed", complaints_json,
                    html_report, json.dumps(data), html_content,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                conn.commit()
                print(f"Seeded initial laptop from {fname} (ID: {lap_id})")
                break
            except Exception as e:
                print(f"Error seeding {fname}: {e}")

def get_companies():
    sb_cfg = get_supabase_config()
    if sb_cfg[0] and sb_cfg[1]:
        try:
            comps = supabase_request("GET", "companies?select=id,name")
            if comps is not None and isinstance(comps, list):
                laps = supabase_request("GET", "laptops?select=company_name")
                counts = {}
                if laps and isinstance(laps, list):
                    for l in laps:
                        cn = l.get("company_name", "")
                        counts[cn] = counts.get(cn, 0) + 1
                result = []
                for c in comps:
                    c_name = c.get("name", "")
                    result.append({
                        "id": c.get("id"),
                        "name": c_name,
                        "laptop_count": counts.get(c_name, 0)
                    })
                def sort_key(item):
                    n = item.get("name", "")
                    if n == "UNICOMTIC": return 0
                    if n == "Unassigned / Retail": return 2
                    return 1
                result.sort(key=lambda x: (sort_key(x), x.get("name", "")))
                return result
        except Exception as e:
            print(f"Notice: Supabase get_companies fallback: {e}")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.name, COUNT(l.id) as laptop_count
        FROM companies c
        LEFT JOIN laptops l ON c.name = l.company_name
        GROUP BY c.id, c.name
        ORDER BY 
            CASE 
                WHEN c.name = 'UNICOMTIC' THEN 0 
                WHEN c.name = 'Unassigned / Retail' THEN 2 
                ELSE 1 
            END, 
            c.name ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_company(name: str):
    name = name.strip()
    if not name:
        return False, "Company name cannot be empty"

    sb_cfg = get_supabase_config()
    if sb_cfg[0] and sb_cfg[1]:
        try:
            supabase_request("POST", "companies", json_data={"name": name}, prefer="resolution=merge-duplicates")
        except Exception:
            pass

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO companies (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
        return True, "Company added"
    except sqlite3.IntegrityError:
        conn.close()
        return True, "Company already exists"

def get_laptops(company=None, search=None, status=None):
    sb_cfg = get_supabase_config()
    if sb_cfg[0] and sb_cfg[1]:
        try:
            params = {
                "select": "*",
                "order": "created_at.desc"
            }
            if company and company.strip() and company != "All":
                params["company_name"] = f"eq.{company.strip()}"
            if status and status.strip() and status != "All":
                st = status.strip()
                params["or"] = f"(overall_status.eq.{st},service_status.eq.{st})"

            res = supabase_request("GET", "laptops", params=params)
            if res is not None and isinstance(res, list):
                result = []
                for r in res:
                    d = dict(r)
                    if isinstance(d.get("complaints"), str):
                        try:
                            d["complaints"] = json.loads(d["complaints"])
                        except Exception:
                            d["complaints"] = [d["complaints"]]
                    elif not d.get("complaints"):
                        d["complaints"] = []
                    
                    if isinstance(d.get("report_data"), str):
                        try:
                            d["report_data"] = json.loads(d["report_data"])
                        except Exception:
                            d["report_data"] = {}

                    if search and search.strip():
                        term = search.strip().lower()
                        match = (
                            term in (d.get("device_name") or "").lower() or
                            term in (d.get("model") or "").lower() or
                            term in (d.get("serial_number") or "").lower() or
                            term in (d.get("customer_name") or "").lower() or
                            any(term in str(c).lower() for c in d.get("complaints", []))
                        )
                        if not match:
                            continue

                    result.append(d)
                return result
        except Exception as e:
            print(f"Notice: Supabase get_laptops fallback: {e}")

    if os.environ.get("VERCEL"):
        sync_db_from_gdrive_if_needed()
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM laptops WHERE 1=1"
    params = []
    
    if company and company.strip() and company != "All":
        query += " AND company_name = ?"
        params.append(company.strip())
        
    if status and status.strip() and status != "All":
        query += " AND (overall_status = ? OR service_status = ?)"
        params.extend([status.strip(), status.strip()])
        
    if search and search.strip():
        term = f"%{search.strip()}%"
        query += " AND (device_name LIKE ? OR model LIKE ? OR serial_number LIKE ? OR customer_name LIKE ? OR complaints LIKE ?)"
        params.extend([term, term, term, term, term])
        
    query += " ORDER BY created_at DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["complaints"] = json.loads(d["complaints"]) if d["complaints"] else []
        except Exception:
            d["complaints"] = [d["complaints"]]
        result.append(d)
    return result

def get_laptop(laptop_id: str):
    sb_cfg = get_supabase_config()
    if sb_cfg[0] and sb_cfg[1]:
        try:
            res = supabase_request("GET", "laptops", params={"id": f"eq.{laptop_id}", "limit": "1"})
            if res and isinstance(res, list) and len(res) > 0:
                d = dict(res[0])
                if isinstance(d.get("complaints"), str):
                    try:
                        d["complaints"] = json.loads(d["complaints"])
                    except Exception:
                        d["complaints"] = [d["complaints"]]
                elif not d.get("complaints"):
                    d["complaints"] = []
                if isinstance(d.get("report_data"), str):
                    try:
                        d["report_data"] = json.loads(d["report_data"])
                    except Exception:
                        d["report_data"] = {}
                return d
        except Exception as e:
            print(f"Notice: Supabase get_laptop fallback: {e}")

    if os.environ.get("VERCEL"):
        sync_db_from_gdrive_if_needed()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM laptops WHERE id = ?", (laptop_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d["complaints"] = json.loads(d["complaints"]) if d["complaints"] else []
    except Exception:
        d["complaints"] = [d["complaints"]]
    try:
        d["report_data"] = json.loads(d["report_data"]) if d["report_data"] else {}
    except Exception:
        d["report_data"] = {}
    return d

def get_report_html_by_filename(filename: str) -> str:
    """Finds stored report_html or battery_report_html by filename or laptop id."""
    sb_cfg = get_supabase_config()
    if sb_cfg[0] and sb_cfg[1]:
        try:
            clean_id = filename.replace(".html", "")
            res = supabase_request("GET", "laptops", params={
                "or": f"(report_filename.eq.{filename},id.eq.{clean_id},battery_report_filename.eq.{filename})",
                "select": "report_html,battery_report_html,report_filename,battery_report_filename",
                "limit": "1"
            })
            if res and isinstance(res, list) and len(res) > 0:
                item = res[0]
                if filename == item.get("battery_report_filename") and item.get("battery_report_html"):
                    return item.get("battery_report_html")
                if item.get("report_html"):
                    return item.get("report_html")
        except Exception as e:
            print(f"Notice: Supabase get_report_html fallback: {e}")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT report_html FROM laptops WHERE report_filename = ? OR id = ? LIMIT 1", (filename, filename.replace(".html", "")))
    row = cursor.fetchone()
    if row and row[0]:
        conn.close()
        return row[0]
    try:
        cursor.execute("SELECT battery_report_html FROM laptops WHERE battery_report_filename = ? LIMIT 1", (filename,))
        row = cursor.fetchone()
        if row and row[0]:
            conn.close()
            return row[0]
    except Exception:
        pass
    conn.close()
    return ""

def find_duplicate_laptop(serial_number: str = None, device_name: str = None, company_name: str = None):
    """
    Checks if a machine with the same serial number (or device name within the same company) already exists.
    Returns existing laptop dict or None.
    """
    clean_serial = (serial_number or "").strip()
    clean_dev = (device_name or "").strip()
    clean_comp = (company_name or "").strip()
    generic_serials = {"", "n/a", "none", "default string", "system serial number", "to be filled by o.e.m.", "0123456789"}

    sb_cfg = get_supabase_config()
    if sb_cfg[0] and sb_cfg[1]:
        try:
            if clean_serial and clean_serial.lower() not in generic_serials:
                res = supabase_request("GET", "laptops", params={"serial_number": f"ilike.{clean_serial}", "limit": "1"})
                if res and isinstance(res, list) and len(res) > 0:
                    return res[0]
            if clean_dev:
                params = {"device_name": f"ilike.{clean_dev}", "limit": "1"}
                if clean_comp and clean_comp != "All":
                    params["company_name"] = f"ilike.{clean_comp}"
                res = supabase_request("GET", "laptops", params=params)
                if res and isinstance(res, list) and len(res) > 0:
                    return res[0]
        except Exception as e:
            print(f"Notice: Supabase find_duplicate fallback: {e}")

    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Unique match by real serial number
    if clean_serial and clean_serial.lower() not in generic_serials:
        cursor.execute("SELECT * FROM laptops WHERE LOWER(serial_number) = LOWER(?)", (clean_serial,))
        row = cursor.fetchone()
        if row:
            conn.close()
            return dict(row)
            
    # 2. Match by Device Name + Company Name
    if clean_dev:
        if clean_comp and clean_comp != "All":
            cursor.execute("SELECT * FROM laptops WHERE LOWER(device_name) = LOWER(?) AND LOWER(company_name) = LOWER(?)", (clean_dev, clean_comp))
        else:
            cursor.execute("SELECT * FROM laptops WHERE LOWER(device_name) = LOWER(?)", (clean_dev,))
        row = cursor.fetchone()
        if row:
            conn.close()
            return dict(row)
            
    conn.close()
    return None

def create_laptop(data: dict):
    lap_id = data.get("id") or f"LAP-{int(time.time() % 100000):05d}"
    company = data.get("company_name", "UNICOMTIC").strip() or "UNICOMTIC"
    
    complaints = data.get("complaints", [])
    if isinstance(complaints, list):
        complaints_json = json.dumps(complaints)
        complaints_list = complaints
    else:
        complaints_json = json.dumps([str(complaints)])
        complaints_list = [str(complaints)]
        
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Upsert to Supabase
    sb_cfg = get_supabase_config()
    if sb_cfg[0] and sb_cfg[1]:
        try:
            supabase_request("POST", "companies", json_data={"name": company}, prefer="resolution=merge-duplicates")
            rd = data.get("report_data", {})
            if isinstance(rd, str):
                try:
                    rd = json.loads(rd)
                except Exception:
                    rd = {}
            sb_row = {
                "id": lap_id,
                "company_name": company,
                "customer_name": data.get("customer_name", ""),
                "customer_phone": data.get("customer_phone", ""),
                "device_name": data.get("device_name", "Laptop"),
                "model": data.get("model", ""),
                "serial_number": data.get("serial_number", ""),
                "cpu": data.get("cpu", ""),
                "ram": data.get("ram", ""),
                "storage": data.get("storage", ""),
                "gpu": data.get("gpu", ""),
                "battery_health": int(data.get("battery_health", 100)),
                "overall_status": data.get("overall_status", "Healthy"),
                "service_status": data.get("service_status", "Received"),
                "complaints": complaints_list,
                "photo_screen": data.get("photo_screen", ""),
                "photo_top": data.get("photo_top", ""),
                "photo_base": data.get("photo_base", ""),
                "report_filename": data.get("report_filename", ""),
                "report_data": rd,
                "report_html": data.get("report_html", ""),
                "battery_report_filename": data.get("battery_report_filename", ""),
                "battery_report_html": data.get("battery_report_html", ""),
                "battery_cycle_count": str(data.get("battery_cycle_count", "")),
                "gdrive_folder_url": data.get("gdrive_folder_url", ""),
                "created_at": data.get("created_at") or now,
                "updated_at": now
            }
            supabase_request("POST", "laptops", json_data=sb_row, prefer="resolution=merge-duplicates")
        except Exception as e:
            print(f"Notice: Supabase create_laptop sync: {e}")

    # 2. Mirror to SQLite
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO companies (name) VALUES (?)", (company,))
    cursor.execute("""
    INSERT OR REPLACE INTO laptops (
        id, company_name, customer_name, customer_phone,
        device_name, model, serial_number, cpu, ram, storage, gpu,
        battery_health, overall_status, service_status, complaints,
        photo_screen, photo_top, photo_base, report_filename, report_data,
        report_html, battery_report_filename, battery_report_html, battery_cycle_count,
        gdrive_folder_url, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        lap_id,
        company,
        data.get("customer_name", ""),
        data.get("customer_phone", ""),
        data.get("device_name", "Laptop"),
        data.get("model", ""),
        data.get("serial_number", ""),
        data.get("cpu", ""),
        data.get("ram", ""),
        data.get("storage", ""),
        data.get("gpu", ""),
        int(data.get("battery_health", 100)),
        data.get("overall_status", "Healthy"),
        data.get("service_status", "Received"),
        complaints_json,
        data.get("photo_screen", ""),
        data.get("photo_top", ""),
        data.get("photo_base", ""),
        data.get("report_filename", ""),
        json.dumps(data.get("report_data", {})),
        data.get("report_html", ""),
        data.get("battery_report_filename", ""),
        data.get("battery_report_html", ""),
        str(data.get("battery_cycle_count", "")),
        data.get("gdrive_folder_url", ""),
        now,
        now
    ))
    conn.commit()
    conn.close()
    laptop = get_laptop(lap_id)
    try:
        import threading, gdrive_sync
        threading.Thread(target=gdrive_sync.update_laptop_in_master_inventory, args=(laptop,), daemon=True).start()
    except Exception as e:
        pass
    return laptop

def update_laptop(laptop_id: str, data: dict):
    updatable = [
        "company_name", "customer_name", "customer_phone", "device_name", "model",
        "serial_number", "cpu", "ram", "storage", "gpu", "battery_health",
        "overall_status", "service_status", "photo_screen", "photo_top",
        "photo_base", "report_filename", "report_html", 
        "battery_report_filename", "battery_report_html", "battery_cycle_count",
        "gdrive_folder_url"
    ]

    # 1. Update Supabase
    sb_cfg = get_supabase_config()
    if sb_cfg[0] and sb_cfg[1]:
        try:
            sb_update = {}
            for k in updatable:
                if k in data:
                    sb_update[k] = data[k]
            if "complaints" in data:
                c = data["complaints"]
                sb_update["complaints"] = c if isinstance(c, list) else [str(c)]
            if "report_data" in data:
                rd = data["report_data"]
                sb_update["report_data"] = json.loads(rd) if isinstance(rd, str) else rd
            sb_update["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            supabase_request("PATCH", f"laptops?id=eq.{laptop_id}", json_data=sb_update)
        except Exception as e:
            print(f"Notice: Supabase update_laptop sync: {e}")

    # 2. Update SQLite
    conn = get_connection()
    cursor = conn.cursor()
    
    fields = []
    values = []
    
    for k in updatable:
        if k in data:
            fields.append(f"{k} = ?")
            values.append(data[k])
            
    if "complaints" in data:
        fields.append("complaints = ?")
        val = data["complaints"]
        values.append(json.dumps(val) if isinstance(val, list) else json.dumps([str(val)]))
        
    if "report_data" in data:
        fields.append("report_data = ?")
        values.append(json.dumps(data["report_data"]))
        
    if not fields:
        conn.close()
        return get_laptop(laptop_id)
        
    fields.append("updated_at = ?")
    values.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    values.append(laptop_id)
    
    query = f"UPDATE laptops SET {', '.join(fields)} WHERE id = ?"
    cursor.execute(query, values)
    conn.commit()
    conn.close()
    laptop = get_laptop(laptop_id)
    try:
        import threading, gdrive_sync
        threading.Thread(target=gdrive_sync.update_laptop_in_master_inventory, args=(laptop,), daemon=True).start()
    except Exception as e:
        pass
    return laptop

def delete_laptop(laptop_id: str):
    laptop = get_laptop(laptop_id)

    # 1. Delete from Supabase
    sb_cfg = get_supabase_config()
    if sb_cfg[0] and sb_cfg[1]:
        try:
            supabase_request("DELETE", f"laptops?id=eq.{laptop_id}")
        except Exception as e:
            print(f"Notice: Supabase delete_laptop sync: {e}")

    # 2. Delete from SQLite
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM laptops WHERE id = ?", (laptop_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    if deleted and laptop:
        try:
            import threading, gdrive_sync
            threading.Thread(target=gdrive_sync.delete_laptop_from_drive, args=(laptop,), daemon=True).start()
        except Exception:
            pass
    return deleted

def sync_db_from_gdrive_if_needed():
    """Syncs database from Google Drive laptops_inventory.json, ensuring SQLite matches Drive."""
    try:
        import gdrive_sync
        drive_laptops = gdrive_sync.get_master_inventory_from_drive()
        if drive_laptops is None:
            return

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM laptops")
        local_ids = {row[0] for row in cursor.fetchall()}
        drive_ids = {l.get("id") for l in drive_laptops if l.get("id")}
        
        # Insert/update all laptops from Google Drive
        for lap in drive_laptops:
            create_laptop(lap)

        # Remove local laptops that have been deleted from Google Drive
        to_delete = local_ids - drive_ids
        for del_id in to_delete:
            cursor.execute("DELETE FROM laptops WHERE id = ?", (del_id,))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Notice: GDrive sync check: {e}")
