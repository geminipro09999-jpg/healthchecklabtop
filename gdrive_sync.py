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

_cached_token = None
_cached_creds = None

def get_access_token():
    """Returns a valid Google OAuth2 access token (prioritizes user token.json, falls back to service_account.json)."""
    global _cached_token, _cached_creds

    # 1. Prioritize personal Google Account OAuth token (unlimited personal quota)
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

    # 2. Fallback to Service Account
    cfg = load_config().get("gdrive", {})
    json_path = cfg.get("service_account_json", "service_account.json")
    if not os.path.isabs(json_path):
        json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), json_path)

    if not os.path.exists(json_path):
        return None, "Neither token.json nor service_account.json found. Run Connect-GoogleDrive.bat."

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
        return None, f"Authentication error: {str(e)}"

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

def sync_laptop_to_drive(laptop_data: dict, photo_paths: list = None, report_path: str = None, report_html_content: str = None, report_filename: str = None) -> dict:
    """
    Syncs laptop record, photos, and HTML diagnostic report to the folder structure:
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

