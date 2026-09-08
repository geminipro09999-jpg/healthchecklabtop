# Windows Laptop & PC Health Diagnostic & Service Fleet Hub 💻

A comprehensive client-server diagnostic and inventory management solution:
- **Automated PowerShell Diagnostic Engine**: Inspects CPU, RAM, Dual GPU, NVMe SSD SMART, Battery wear %, Wi-Fi/Bluetooth, and Device Manager errors.
- **Python REST API Server**: High-performance backend with SQLite database, role-based access control (RBAC), and image file management.
- **Hashed Admin Authentication**: Zero hardcoded plain-text passwords. Passwords secured using PBKDF2-HMAC-SHA256 with 100,000 iterations and random salts.
- **Public Read-Only Mode**: Technicians and clients can browse laptops, read diagnostic health reports, view hardware specs, and inspect photos without logging in.
- **Company / Client Multi-Tenancy**: Categorize laptops by client company (e.g. *Virtusa, ABC Tech, Retail Walk-in*), with dedicated filtering and metrics.
- **Google Drive API Hierarchical Sync**: Automatically builds and syncs cloud folders: `Root / <Company> / <DeviceName_Serial> / [Photos & Reports]`.

---

## 📁 Project Architecture & Files

| File | Description |
|---|---|
| **`api_server.py`** | Production REST API server (`http://0.0.0.0:8080`) providing auth, company, laptop, and photo endpoints. |
| **`auth.py`** | PBKDF2 password hashing, salt generation, session token management. |
| **`config.json`** | Configuration storing hashed admin password, salt, session secrets, and Google Drive settings. |
| **`database.py`** | SQLite database manager (`laptops.db`) for multi-company laptop inventory. |
| **`gdrive_sync.py`** | Google Drive API handler for hierarchical folder creation and cloud sync. |
| **`Dashboard.html`** | Single-Page Web Dashboard with Public & Admin modes, 3-photo carousel, lightbox zoom, and filters. |
| **`Generate-HealthReport.ps1`** | Diagnostic PowerShell scanner with `-Company` parameter support. |
| **`Run-HealthReport.bat`** | 1-Click diagnostic launcher with company prompt. |
| **`Start-Mobile-Server.bat`** | Starts REST API server for desktop and Wi-Fi mobile devices (`http://192.168.1.45:8080`). |
| **`Open-Dashboard.bat`** | 1-Click launcher opening the dashboard in default browser. |
| **`laptop_images/`** | Hierarchically organized local photo repository: `<Company>/<DeviceName_Serial>/`. |

---

## 🚀 Quick Start / பயன்பாட்டு முறை

### 1. Start the System / சிஸ்டத்தை ஆரம்பிக்க
1. Double-click [**`Start-Mobile-Server.bat`**](file:///C:/Users/unico/Desktop/laptops%20health%20reports/Start-Mobile-Server.bat).
2. It will display your access URLs:
   - **Computer**: `http://localhost:8080/Dashboard.html`
   - **Mobile Phone (Same Wi-Fi)**: `http://192.168.1.45:8080/Dashboard.html`

### 2. Run Diagnostics on a Laptop / லேப்டாப்பை Scan செய்ய
1. Double-click [**`Run-HealthReport.bat`**](file:///C:/Users/unico/Desktop/laptops%20health%20reports/Run-HealthReport.bat).
2. Enter the Client / Company Name (e.g. `Virtusa` or press Enter for `Unassigned / Retail`).
3. The hardware scan generates:
   - `HealthReport_<DeviceName>_<Timestamp>.html` (Interactive diagnostic report)
   - `HealthReport_<DeviceName>_<Timestamp>.json` (Structured hardware data for 1-click import)

---

## 🔐 Security & Access Control (பாதுகாப்பு முறைமை)

### 🌐 Public View Mode (Read-Only)
- Anyone connected to your office Wi-Fi can open the dashboard URL.
- **Allowed actions**:
  - Filter and search laptops by company, status, or keyword.
  - View full hardware specifications (CPU, RAM, Storage, GPU, Battery).
  - Open and read the complete interactive **Health Report** (`.html`).
  - View inspection photos in fullscreen lightbox zoom.
  - View customer complaints and service status.
- **Restricted actions**: Cannot create, edit, delete, or upload photos.

### 🛡️ Admin Mode (Technician Access)
- Click **`🔐 Admin Login`** in the top right corner.
- Enter the admin password (**Default initial password**: `admin123`).
- **Passowrd is never stored in plain-text**: It is verified against a PBKDF2-HMAC-SHA256 cryptographic hash with random salt.
- Once authenticated, full controls are unlocked:
  - `📱 ➕ New Customer Job`
  - `⚡ Import Local Scan`
  - `📷 Upload Photos` (with direct mobile camera support)
  - `✏️ Edit Complaints & Status`
  - `🗑️ Delete Laptop`
  - `🔑 Password Change`

---

## 🏢 Company Multi-Tenancy (நிறுவன வாரியாக மேலாண்மை)

Each laptop is categorized under a Client or Company:
- **Top Filter Dropdown**: Easily switch between `All Companies`, `Virtusa`, `ABC Tech`, `Retail Clients`.
- **KPI Metrics**: Automatically calculate active complaints, ready laptops, and average health score.
- **Company Badges**: Prominently displayed on every card.
- **Automatic Folder Organization**: Files are grouped by company:
  ```
  laptop_images/
    ├── Virtusa Technologies/
    │     └── Dell-Latitude-5420_PF39A1B/
    │           ├── photo_screen.jpg
    │           ├── photo_top.jpg
    │           └── photo_base.jpg
    └── Unicom Tech Solutions/
          └── UNICOMTIC32_PF40A2C/
                ├── photo_screen.jpg
                ├── photo_top.jpg
                └── photo_base.jpg
  ```

---

## ☁️ Google Drive Cloud Hierarchy

When you connect Google Drive API:
1. Place your Google Cloud Service Account credentials file named `service_account.json` into this folder.
2. The system automatically creates and mirrors this exact hierarchy in Google Drive:
   ```
   [Your Google Drive Root Folder]
     └── 📁 <Company Name> (e.g. Virtusa Technologies)
           └── 📁 <DeviceName_SerialNumber> (e.g. ThinkPad-T14_PF22XK9)
                 ├── 🖼️ Screen_Keyboard.jpg
                 ├── 🖼️ Top_Lid.jpg
                 ├── 🖼️ Base_Serial.jpg
                 ├── 📄 HealthReport.html
                 └── 📊 HealthReport.json
   ```
3. Each laptop card displays a direct **`☁️ Drive`** button to open its folder in Google Drive.
