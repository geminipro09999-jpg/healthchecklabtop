"""
gdrive_sync.py - Ultra-Reliable Google Drive API v3 Integration
Uses Python `requests` for fast, direct REST operations without httplib2 timeouts.
Folder Structure:
Root Folder (1cfYrNewvM1tmCumcV5pKEsq0fPvq-fGZ)
  └── <Company Name> (e.g. Unicom Tech Solutions)
        └── <DeviceName_SerialNumber> (e.g. UNICOMTIC32_Default string)
              ├── Photo_Screen.jpg
              ├── Photo_TopLid.jpg
              ├── Photo_BaseSerial.jpg
              ├── HealthReport.html
              └── HealthReport.json
"""

import os
import json
import base64
import zlib
import mimetypes
import logging
import requests
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from auth import load_config

logger = logging.getLogger("gdrive_sync")
logging.basicConfig(level=logging.INFO)

SCOPES = ['https://www.googleapis.com/auth/drive']
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'token.json')
VAULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gdrive_vault.dat')
VAULT_KEY = b"unicomtic_drive_key_2026"

_cached_token = None
_cached_creds = None

def get_access_token():
    """Returns a valid Google OAuth2 access token (prioritizes user token.json/vault, falls back to service_account.json)."""
    global _cached_token, _cached_creds

    # 1. Prioritize personal Google Account OAuth token from disk
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(TOKEN_FILE, "w") as tf:
                    tf.write(creds.to_json())
            if creds and creds.valid:
                _cached_creds = creds
                _cached_token = creds.token
                return _cached_token, None
        except Exception as e:
            logger.warning(f"OAuth token refresh error: {e}")

    # 1b. Prioritize encrypted vault on disk (Works automatically on Vercel without environment variables)
    if os.path.exists(VAULT_FILE):
        try:
            with open(VAULT_FILE, "rb") as vf:
                raw_enc = vf.read()
            dec = zlib.decompress(bytes(b ^ VAULT_KEY[i % len(VAULT_KEY)] for i, b in enumerate(raw_enc)))
            token_data = json.loads(dec.decode("utf-8"))
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            if creds and creds.valid:
                _cached_creds = creds
                _cached_token = creds.token
                return _cached_token, None
        except Exception as e:
            logger.warning(f"Vault OAuth token error: {e}")

    # 1b. Prioritize personal Google Account OAuth token from env (Base64 or JSON)
    b64_token = os.environ.get("GDRIVE_TOKEN_B64")
    token_data = None
    if b64_token:
        try:
            token_data = json.loads(base64.b64decode(b64_token).decode("utf-8"))
        except Exception:
            pass
    if not token_data:
        cfg = load_config().get("gdrive", {})
        token_data = cfg.get("token_info") or (json.loads(os.environ["GDRIVE_TOKEN_JSON"]) if "GDRIVE_TOKEN_JSON" in os.environ else None)

    if token_data:
        try:
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            if creds and creds.valid:
                _cached_creds = creds
                _cached_token = creds.token
                return _cached_token, None
        except Exception as e:
            logger.warning(f"OAuth token info error: {e}")

    # 2. Fallback to Service Account from disk
    json_path = cfg.get("service_account_json", "service_account.json")
    if not os.path.isabs(json_path):
        json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), json_path)

    if os.path.exists(json_path):
        try:
            if _cached_creds is None or not isinstance(_cached_creds, service_account.Credentials):
                _cached_creds = service_account.Credentials.from_service_account_file(
                    json_path, scopes=SCOPES
                )

            if not _cached_creds.valid:
                _cached_creds.refresh(Request())

            _cached_token = _cached_creds.token
            return _cached_token, None
        except Exception as e:
            logger.warning(f"Service account file error: {e}")

    # 2b. Fallback to Service Account from config/env
    sa_data = cfg.get("service_account_info") or (json.loads(os.environ["GDRIVE_SERVICE_ACCOUNT_JSON"]) if "GDRIVE_SERVICE_ACCOUNT_JSON" in os.environ else None)
    if sa_data:
        try:
            _cached_creds = service_account.Credentials.from_service_account_info(sa_data, scopes=SCOPES)
            if not _cached_creds.valid:
                _cached_creds.refresh(Request())
            _cached_token = _cached_creds.token
            return _cached_token, None
        except Exception as e:
            return None, f"Service account info error: {e}"

    return None, "Neither token.json nor service_account.json found. Run Connect-GoogleDrive.bat."

def test_drive_connection():
    """Tests if Google Drive API is reachable and credentials are valid."""
    token, err = get_access_token()
    if not token:
        return {"status": "unconfigured", "message": err or "Credentials not provided."}

    cfg = load_config().get("gdrive", {})
    parent_id = cfg.get("parent_folder_id", "")
    headers = {"Authorization": f"Bearer {token}"}

    try:
        # Check folder accessibility
        if parent_id:
            url = f"https://www.googleapis.com/drive/v3/files/{parent_id}?fields=id,name,webViewLink"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                folder_data = r.json()
                return {
                    "status": "connected",
                    "message": f"Connected to folder '{folder_data.get('name')}'",
                    "email": "laptop-health-report@laptop-health-reports.iam.gserviceaccount.com",
                    "parent_folder_id": parent_id,
                    "folder_url": folder_data.get("webViewLink")
                }

        # Fallback test: list 1 file
        r = requests.get("https://www.googleapis.com/drive/v3/files?pageSize=1&fields=files(id)", headers=headers, timeout=10)
        if r.status_code == 200:
            return {
                "status": "connected",
                "message": "Connected to Google Drive API",
                "email": "laptop-health-report@laptop-health-reports.iam.gserviceaccount.com",
                "parent_folder_id": parent_id
            }
        return {"status": "error", "message": f"Drive API returned HTTP {r.status_code}: {r.text}"}
    except Exception as e:
        return {"status": "error", "message": f"Connection error: {str(e)}"}

def find_or_create_folder(folder_name: str, parent_id: str = None) -> tuple[str, str]:
    """Finds an existing folder with given name under parent_id, or creates it."""
    token, err = get_access_token()
    if not token:
        raise Exception(err)

    headers = {"Authorization": f"Bearer {token}"}
    folder_name = "".join(c for c in folder_name if c not in r'\/:*?"<>|').strip() or "General"

    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    # Search for existing folder
    list_url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&fields=files(id,name,webViewLink)"
    r = requests.get(list_url, headers=headers, timeout=10)
    if r.status_code == 200:
        files = r.json().get("files", [])
        if files:
            return files[0]["id"], files[0].get("webViewLink")

    # Create new folder
    create_url = "https://www.googleapis.com/drive/v3/files?fields=id,name,webViewLink"
    body = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    if parent_id:
        body["parents"] = [parent_id]

    r = requests.post(create_url, headers={**headers, "Content-Type": "application/json"}, json=body, timeout=10)
    if r.status_code in (200, 201):
        data = r.json()
        return data["id"], data.get("webViewLink")

    raise Exception(f"Failed to create folder '{folder_name}': {r.text}")

def upload_or_update_file(file_path: str, parent_folder_id: str, file_title: str = None) -> dict:
    """Uploads or updates a file into a specific Drive folder using multipart upload."""
    if not os.path.exists(file_path):
        return None

    token, err = get_access_token()
    if not token:
        return None

    headers = {"Authorization": f"Bearer {token}"}
    file_name = file_title or os.path.basename(file_path)
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "application/octet-stream"

    # Check if file already exists
    query = f"name='{file_name}' and '{parent_folder_id}' in parents and trashed=false"
    list_url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&fields=files(id,name,webViewLink)"
    r = requests.get(list_url, headers=headers, timeout=10)
    existing_id = None
    if r.status_code == 200:
        files = r.json().get("files", [])
        if files:
            existing_id = files[0]["id"]

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    metadata = {"name": file_name}
    if not existing_id:
        metadata["parents"] = [parent_folder_id]

    files = {
        "data": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
        "file": (file_name, file_bytes, mime_type)
    }

    if existing_id:
        upload_url = f"https://www.googleapis.com/upload/drive/v3/files/{existing_id}?uploadType=multipart&fields=id,name,webViewLink,webContentLink"
        resp = requests.patch(upload_url, headers=headers, files=files, timeout=20)
    else:
        upload_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,webViewLink,webContentLink"
        resp = requests.post(upload_url, headers=headers, files=files, timeout=20)

    if resp.status_code in (200, 201):
        res_data = resp.json()
        if res_data.get("id"):
            try:
                perm_url = f"https://www.googleapis.com/drive/v3/files/{res_data['id']}/permissions"
                requests.post(perm_url, headers=headers, json={"role": "reader", "type": "anyone"}, timeout=10)
            except Exception:
                pass
        return res_data
    logger.error(f"File upload error for {file_name}: {resp.text}")
    return None

def upload_or_update_bytes(file_bytes: bytes, file_name: str, parent_folder_id: str, mime_type: str = "text/html; charset=UTF-8") -> dict:
    """Uploads or updates a file directly from byte content into a specific Drive folder."""
    token, err = get_access_token()
    if not token:
        return None

    headers = {"Authorization": f"Bearer {token}"}

    # Check if file already exists
    query = f"name='{file_name}' and '{parent_folder_id}' in parents and trashed=false"
    list_url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&fields=files(id,name,webViewLink)"
    r = requests.get(list_url, headers=headers, timeout=10)
    existing_id = None
    if r.status_code == 200:
        files = r.json().get("files", [])
        if files:
            existing_id = files[0]["id"]

    metadata = {"name": file_name}
    if not existing_id:
        metadata["parents"] = [parent_folder_id]

    files = {
        "data": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
        "file": (file_name, file_bytes, mime_type)
    }

    if existing_id:
        upload_url = f"https://www.googleapis.com/upload/drive/v3/files/{existing_id}?uploadType=multipart&fields=id,name,webViewLink,webContentLink"
        resp = requests.patch(upload_url, headers=headers, files=files, timeout=20)
    else:
        upload_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,webViewLink,webContentLink"
        resp = requests.post(upload_url, headers=headers, files=files, timeout=20)

    if resp.status_code in (200, 201):
        res_data = resp.json()
        if res_data.get("id"):
            try:
                perm_url = f"https://www.googleapis.com/drive/v3/files/{res_data['id']}/permissions"
                requests.post(perm_url, headers=headers, json={"role": "reader", "type": "anyone"}, timeout=10)
            except Exception:
                pass
        return res_data
    logger.error(f"Byte upload error for {file_name}: {resp.text}")
    return None

def sync_laptop_to_drive(laptop_data: dict, photo_paths: list = None, report_path: str = None, report_html_content: str = None, report_filename: str = None, battery_report_path: str = None, battery_report_content: str = None, battery_report_filename: str = None) -> dict:
    """
    Syncs laptop record, photos, HTML diagnostic report, and official battery report to the folder structure:
    Root / <Company> / <DeviceName_Serial> /
    """
    token, err = get_access_token()
    if not token:
        return {
            "success": False,
            "error": err,
            "fallback": "Saved locally in laptop_images/"
        }

    cfg = load_config().get("gdrive", {})
    parent_id = cfg.get("parent_folder_id") or None

    company_name = laptop_data.get("company_name") or laptop_data.get("company") or "Unassigned"
    company_name = company_name.strip() or "General"

    device_name = laptop_data.get("device_name", "Laptop").strip()
    serial_no = laptop_data.get("serial_number", "NoSerial").strip()
    laptop_folder_name = f"{device_name}_{serial_no}"

    try:
        # 1. Get or create Company Folder
        company_folder_id, company_link = find_or_create_folder(company_name, parent_id)

        # 2. Get or create Laptop Subfolder
        laptop_folder_id, laptop_link = find_or_create_folder(laptop_folder_name, company_folder_id)

        uploaded_files = []

        # 3. Upload photos
        if photo_paths:
            for p_idx, p_path in enumerate(photo_paths):
                if p_path and os.path.exists(p_path):
                    ext = os.path.splitext(p_path)[1]
                    labels = ["Screen_Keyboard", "Top_Lid", "Base_Serial"]
                    label = labels[p_idx] if p_idx < 3 else f"Photo_{p_idx+1}"
                    file_res = upload_or_update_file(p_path, laptop_folder_id, f"{label}{ext}")
                    if file_res:
                        uploaded_files.append(file_res)

        # 4. Upload HTML report if exists on disk
        if report_path and os.path.exists(report_path) and os.path.isfile(report_path):
            rep_res = upload_or_update_file(report_path, laptop_folder_id, os.path.basename(report_path))
            if rep_res:
                uploaded_files.append(rep_res)
        # 4b. Or upload directly from raw HTML string
        elif report_html_content and report_filename:
            rep_res = upload_or_update_bytes(report_html_content.encode("utf-8"), report_filename, laptop_folder_id)
            if rep_res:
                uploaded_files.append(rep_res)

        # 5. Upload Battery Report if exists
        if battery_report_path and os.path.exists(battery_report_path) and os.path.isfile(battery_report_path):
            bat_res = upload_or_update_file(battery_report_path, laptop_folder_id, os.path.basename(battery_report_path))
            if bat_res:
                uploaded_files.append(bat_res)
        elif battery_report_content and battery_report_filename:
            bat_res = upload_or_update_bytes(battery_report_content.encode("utf-8"), battery_report_filename, laptop_folder_id)
            if bat_res:
                uploaded_files.append(bat_res)

        # 6. Update Master Inventory file in Google Drive Root
        try:
            update_laptop_in_master_inventory(laptop_data)
        except Exception as inv_err:
            logger.warning(f"Notice: Master inventory update error: {inv_err}")

        return {
            "success": True,
            "company_folder_id": company_folder_id,
            "laptop_folder_id": laptop_folder_id,
            "laptop_folder_url": laptop_link,
            "uploaded_count": len(uploaded_files),
            "files": uploaded_files
        }
    except Exception as e:
        logger.error(f"Error syncing to Google Drive: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def delete_laptop_from_drive(laptop_data: dict) -> dict:
    """
    Deletes the laptop's dedicated folder from Google Drive when a laptop record is deleted.
    Looks up Root / <Company> / <DeviceName_Serial> or parses laptop_folder_url.
    """
    token, err = get_access_token()
    if not token:
        return {"success": False, "error": err}

    cfg = load_config().get("gdrive", {})
    parent_id = cfg.get("parent_folder_id") or None
    company_name = laptop_data.get("company_name") or laptop_data.get("company") or "General"
    device_name = laptop_data.get("device_name", "Laptop").strip()
    serial_no = laptop_data.get("serial_number", "NoSerial").strip()
    laptop_folder_name = f"{device_name}_{serial_no}"

    # Also remove from master inventory
    try:
        remove_laptop_from_master_inventory(laptop_data.get("id"), laptop_data.get("device_name"))
    except Exception:
        pass

    headers = {"Authorization": f"Bearer {token}"}
    target_folder_id = None

    # Try extracting ID from gdrive_folder_url if stored
    folder_url = laptop_data.get("gdrive_folder_url", "")
    if "folders/" in folder_url:
        target_folder_id = folder_url.split("folders/")[-1].split("?")[0].strip()

    try:
        if not target_folder_id:
            # Search by path: parent -> company -> laptop
            company_folder_id, _ = find_or_create_folder(company_name, parent_id)
            query = f"mimeType='application/vnd.google-apps.folder' and name='{laptop_folder_name}' and '{company_folder_id}' in parents and trashed=false"
            list_url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&fields=files(id)"
            r = requests.get(list_url, headers=headers, timeout=10)
            if r.status_code == 200:
                files = r.json().get("files", [])
                if files:
                    target_folder_id = files[0]["id"]

        if target_folder_id:
            del_url = f"https://www.googleapis.com/drive/v3/files/{target_folder_id}"
            del_resp = requests.delete(del_url, headers=headers, timeout=15)
            if del_resp.status_code in (200, 204):
                return {"success": True, "deleted_folder_id": target_folder_id}
            else:
                return {"success": False, "error": f"Drive API returned HTTP {del_resp.status_code}: {del_resp.text}"}

        return {"success": True, "message": "No folder found on Drive to delete"}
    except Exception as e:
        logger.error(f"Error deleting laptop folder from Google Drive: {e}")
        return {"success": False, "error": str(e)}

# =========================================================
# MASTER INVENTORY & FILE RETRIEVAL (DRIVE AS CLOUD DB)
# =========================================================
INVENTORY_FILE_NAME = "laptops_inventory.json"

def download_file_bytes(file_id: str) -> bytes:
    """Downloads raw file content by file ID from Google Drive."""
    token, err = get_access_token()
    if not token:
        return None
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    try:
        r = requests.get(url, headers=headers, timeout=25)
        if r.status_code == 200:
            return r.content
    except Exception as e:
        logger.error(f"Error downloading file {file_id}: {e}")
    return None

def get_master_inventory_from_drive() -> list:
    """Reads laptops_inventory.json from the Root folder on Google Drive."""
    token, err = get_access_token()
    if not token:
        return []
    cfg = load_config().get("gdrive", {})
    parent_id = cfg.get("parent_folder_id") or "1cfYrNewvM1tmCumcV5pKEsq0fPvq-fGZ"
    headers = {"Authorization": f"Bearer {token}"}
    query = f"name='{INVENTORY_FILE_NAME}' and '{parent_id}' in parents and trashed=false"
    list_url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&fields=files(id)"
    try:
        r = requests.get(list_url, headers=headers, timeout=10)
        if r.status_code == 200:
            files = r.json().get("files", [])
            if files:
                raw = download_file_bytes(files[0]["id"])
                if raw:
                    return json.loads(raw.decode("utf-8"))
    except Exception as e:
        logger.error(f"Error fetching master inventory from Drive: {e}")
    return []

def save_master_inventory_to_drive(laptops_list: list) -> bool:
    """Saves laptops_inventory.json into the Root folder on Google Drive."""
    cfg = load_config().get("gdrive", {})
    parent_id = cfg.get("parent_folder_id") or "1cfYrNewvM1tmCumcV5pKEsq0fPvq-fGZ"
    try:
        inv_bytes = json.dumps(laptops_list, indent=2, ensure_ascii=False).encode("utf-8")
        res = upload_or_update_bytes(inv_bytes, INVENTORY_FILE_NAME, parent_id, mime_type="application/json; charset=UTF-8")
        return bool(res)
    except Exception as e:
        logger.error(f"Error saving master inventory to Drive: {e}")
        return False

def update_laptop_in_master_inventory(laptop_data: dict) -> bool:
    """Adds or updates a laptop record inside laptops_inventory.json in Google Drive."""
    try:
        inv = get_master_inventory_from_drive()
        lap_id = laptop_data.get("id")
        serial = (laptop_data.get("serial_number") or "").strip().lower()
        dev_name = (laptop_data.get("device_name") or "").strip().lower()
        
        generic_serials = {"", "n/a", "none", "default string", "system serial number", "to be filled by o.e.m.", "0123456789"}
        
        found_idx = -1
        for idx, item in enumerate(inv):
            if lap_id and item.get("id") == lap_id:
                found_idx = idx
                break
            if serial and serial not in generic_serials and (item.get("serial_number") or "").strip().lower() == serial:
                found_idx = idx
                break
            if dev_name and (item.get("device_name") or "").strip().lower() == dev_name:
                comp = (laptop_data.get("company_name") or "").strip().lower()
                if comp and (item.get("company_name") or "").strip().lower() == comp:
                    found_idx = idx
                    break

        clean_data = dict(laptop_data)
        # Avoid huge strings in summary JSON
        if "report_html" in clean_data and len(clean_data.get("report_html") or "") > 300:
            clean_data["report_html"] = ""
        if "battery_report_html" in clean_data and len(clean_data.get("battery_report_html") or "") > 300:
            clean_data["battery_report_html"] = ""

        if found_idx >= 0:
            inv[found_idx].update(clean_data)
        else:
            inv.append(clean_data)

        return save_master_inventory_to_drive(inv)
    except Exception as e:
        logger.error(f"Error updating laptop in master inventory: {e}")
        return False

def remove_laptop_from_master_inventory(laptop_id: str, device_name: str = None) -> bool:
    """Removes a laptop from laptops_inventory.json in Google Drive."""
    if not laptop_id and not device_name:
        return True
    try:
        inv = get_master_inventory_from_drive() or []
        new_inv = [
            item for item in inv 
            if item.get("id") != laptop_id and (
                not device_name or (item.get("device_name") or "").strip().lower() != device_name.strip().lower()
            )
        ]
        if len(new_inv) != len(inv):
            return save_master_inventory_to_drive(new_inv)
        return True
    except Exception as e:
        logger.error(f"Error removing laptop from master inventory: {e}")
        return False

def find_file_bytes_in_drive(file_name: str) -> bytes:
    """Finds any file by name in the Drive hierarchy and returns its bytes."""
    token, err = get_access_token()
    if not token or not file_name:
        return None
    headers = {"Authorization": f"Bearer {token}"}
    query = f"name='{file_name}' and trashed=false"
    list_url = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(query)}&fields=files(id,name)"
    try:
        r = requests.get(list_url, headers=headers, timeout=10)
        if r.status_code == 200:
            files = r.json().get("files", [])
            if files:
                return download_file_bytes(files[0]["id"])
    except Exception:
        pass
    return None

