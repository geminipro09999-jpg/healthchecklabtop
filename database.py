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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.environ.get("VERCEL") or not os.access(BASE_DIR, os.W_OK):
    DB_PATH = os.path.join(tempfile.gettempdir(), "laptops.db")
else:
    DB_PATH = os.path.join(BASE_DIR, "laptops.db")

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
    
    # Seed default company if none exist
    cursor.execute("SELECT COUNT(*) FROM companies")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT OR IGNORE INTO companies (name) VALUES (?)", ("Unassigned / Retail",))
        cursor.execute("INSERT OR IGNORE INTO companies (name) VALUES (?)", ("Unicom Tech Solutions",))
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
                if not os.path.exists(os.path.join(base_dir, html_report)):
                    html_report = ""
                
                lap_id = f"LAP-{int(time.time() % 100000):05d}"
                company = "Unicom Tech Solutions"
                complaints_json = json.dumps(["Routine Hardware Diagnostic Check"])
                
                cursor.execute("""
                INSERT INTO laptops (
                    id, company_name, customer_name, customer_phone,
                    device_name, model, serial_number, cpu, ram, storage, gpu,
                    battery_health, overall_status, service_status, complaints,
                    report_filename, report_data, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    lap_id, company, "Internal Lab", "+94 77 123 4567",
                    device_name, model, serial, cpu, ram, storage, gpu,
                    bat, status, "Completed", complaints_json,
                    html_report, json.dumps(data),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                conn.commit()
                print(f"Seeded initial laptop from {fname} (ID: {lap_id})")
                break
            except Exception as e:
                print(f"Error seeding {fname}: {e}")

def get_companies():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.name, COUNT(l.id) as laptop_count
        FROM companies c
        LEFT JOIN laptops l ON c.name = l.company_name
        GROUP BY c.id, c.name
        ORDER BY c.name ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_company(name: str):
    name = name.strip()
    if not name:
        return False, "Company name cannot be empty"
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO companies (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
        return True, "Company added"
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Company already exists"

def get_laptops(company=None, search=None, status=None):
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

def create_laptop(data: dict):
    conn = get_connection()
    cursor = conn.cursor()
    
    lap_id = data.get("id") or f"LAP-{int(time.time() % 100000):05d}"
    company = data.get("company_name", "Unassigned / Retail").strip() or "Unassigned / Retail"
    
    # Auto-add company if doesn't exist
    cursor.execute("INSERT OR IGNORE INTO companies (name) VALUES (?)", (company,))
    
    complaints = data.get("complaints", [])
    if isinstance(complaints, list):
        complaints_json = json.dumps(complaints)
    else:
        complaints_json = json.dumps([str(complaints)])
        
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
    INSERT INTO laptops (
        id, company_name, customer_name, customer_phone,
        device_name, model, serial_number, cpu, ram, storage, gpu,
        battery_health, overall_status, service_status, complaints,
        photo_screen, photo_top, photo_base, report_filename, report_data,
        gdrive_folder_url, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        data.get("gdrive_folder_url", ""),
        now,
        now
    ))
    conn.commit()
    conn.close()
    return get_laptop(lap_id)

def update_laptop(laptop_id: str, data: dict):
    conn = get_connection()
    cursor = conn.cursor()
    
    fields = []
    values = []
    
    updatable = [
        "company_name", "customer_name", "customer_phone", "device_name", "model",
        "serial_number", "cpu", "ram", "storage", "gpu", "battery_health",
        "overall_status", "service_status", "photo_screen", "photo_top",
        "photo_base", "report_filename", "gdrive_folder_url"
    ]
    
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
    return get_laptop(laptop_id)

def delete_laptop(laptop_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM laptops WHERE id = ?", (laptop_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted
