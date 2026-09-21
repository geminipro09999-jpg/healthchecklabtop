"""
disk_health_provider.py - Accurate HDD / SSD / NVMe SMART Health Monitoring
Uses smartmontools / smartctl as the primary source for SMART telemetry.
Adheres strictly to NVMe and SMART specifications without faking percentages.
"""

import os
import sys
import json
import re
import subprocess
import shutil
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Tuple

logger = logging.getLogger("DiskHealthProvider")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")


@dataclass
class DiskHealthInfo:
    model: str = "Unknown Model"
    device: str = ""
    interface: str = "Unknown"                     # "NVMe", "SATA", "ATA", "SCSI", "Unknown"
    capacity: str = "Unknown"
    smartStatus: str = "UNKNOWN"                   # "PASSED", "FAILED", "UNKNOWN"
    healthPercentage: Optional[int] = None         # None if unavailable
    healthPercentageType: str = "unavailable"      # "manufacturer", "nvme_percentage_used", "calculated", "unavailable"
    healthPercentageAttribute: Optional[str] = None # e.g. "SMART 231 SSD_Life_Left"
    percentageUsed: Optional[int] = None           # NVMe official Percentage Used
    remainingEndurance: Optional[int] = None       # 100 - Percentage Used (labeled Estimated Remaining Endurance)
    availableSpare: Optional[int] = None           # NVMe Available Spare %
    availableSpareThreshold: Optional[int] = None  # NVMe Available Spare Threshold %
    temperature: Optional[int] = None              # Celsius
    warningTempThreshold: Optional[int] = None     # Celsius
    criticalTempThreshold: Optional[int] = None    # Celsius
    powerOnHours: Optional[int] = None
    powerCycles: Optional[int] = None
    unsafeShutdowns: Optional[int] = None
    dataWrittenTB: Optional[float] = None
    dataReadTB: Optional[float] = None
    mediaErrors: Optional[int] = None
    errorLogEntries: Optional[int] = None
    criticalWarning: Optional[str] = None
    status: str = "HEALTHY"                        # "HEALTHY", "WARNING", "CRITICAL", "UNKNOWN"
    warnings: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    rawError: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NvmeParser:
    """
    Parses smartctl output for NVMe SSDs (both JSON format and text format).
    Adheres to NVMe NVM Command Set Specification for Log Identifier 0x02.
    """

    @staticmethod
    def parse_json(data: dict, device_path: str = "") -> DiskHealthInfo:
        info = DiskHealthInfo(device=device_path, interface="NVMe")

        # Model & Serial
        info.model = data.get("model_name") or data.get("device", {}).get("info_name") or "NVMe Device"

        # User Capacity
        user_cap = data.get("user_capacity", {})
        bytes_val = user_cap.get("bytes")
        if bytes_val:
            gb = bytes_val / (1000 ** 3)
            info.capacity = f"{gb:.1f} GB" if gb < 1000 else f"{(gb / 1000):.2f} TB"

        # SMART overall health
        smart_st = data.get("smart_status", {})
        if "passed" in smart_st:
            info.smartStatus = "PASSED" if smart_st.get("passed") else "FAILED"

        # Temperature & Thresholds
        temp_data = data.get("temperature", {})
        if "current" in temp_data:
            info.temperature = temp_data.get("current")
        if "op_limit_max" in temp_data:
            info.warningTempThreshold = temp_data.get("op_limit_max")
        if "critical_limit_max" in temp_data:
            info.criticalTempThreshold = temp_data.get("critical_limit_max")

        # NVMe SMART Health Log
        log = data.get("nvme_smart_health_information_log", {})
        if log:
            info.criticalWarning = hex(log.get("critical_warning", 0))
            if info.temperature is None and "temperature" in log:
                info.temperature = log.get("temperature")

            info.availableSpare = log.get("available_spare")
            info.availableSpareThreshold = log.get("available_spare_threshold")

            # Official Percentage Used
            p_used = log.get("percentage_used")
            if p_used is not None:
                info.percentageUsed = int(p_used)
                # NVMe spec: Remaining endurance is estimated from Percentage Used
                rem = max(0, 100 - info.percentageUsed)
                info.remainingEndurance = rem
                info.healthPercentage = rem
                info.healthPercentageType = "nvme_percentage_used"
                info.healthPercentageAttribute = "NVMe Log 0x02 Percentage Used"

            # Data Units Read / Written
            # NVMe specification: 1 Data Unit = 1,000 blocks of 512 bytes = 512,000 bytes
            dur = log.get("data_units_read")
            if dur is not None:
                info.dataReadTB = round((dur * 512000) / (1000 ** 4), 1)

            duw = log.get("data_units_written")
            if duw is not None:
                info.dataWrittenTB = round((duw * 512000) / (1000 ** 4), 1)

            info.powerCycles = log.get("power_cycles")
            info.powerOnHours = log.get("power_on_hours")
            info.unsafeShutdowns = log.get("unsafe_shutdowns")
            info.mediaErrors = log.get("media_errors", 0)
            info.errorLogEntries = log.get("num_err_log_entries", 0)

        # Status Classification
        NvmeParser.classify_status(info)
        return info

    @staticmethod
    def parse_text(text: str, device_path: str = "") -> DiskHealthInfo:
        info = DiskHealthInfo(device=device_path, interface="NVMe")

        for line in text.splitlines():
            line_str = line.strip()
            if not line_str:
                continue

            # Model Number
            m = re.match(r"^Model Number:\s+(.+)$", line_str, re.I)
            if m:
                info.model = m.group(1).strip()
                continue

            # Namespace Capacity / Size
            m = re.match(r"^Namespace \d+ Size/Capacity:\s+[\d,]+\s+\[(.+)\]", line_str, re.I)
            if m:
                info.capacity = m.group(1).strip()
                continue
            m = re.match(r"^Total NVM Capacity:\s+[\d,]+\s+\[(.+)\]", line_str, re.I)
            if m and info.capacity == "Unknown":
                info.capacity = m.group(1).strip()
                continue

            # Overall Health
            m = re.match(r"^SMART overall-health self-assessment test result:\s+(.+)$", line_str, re.I)
            if m:
                info.smartStatus = m.group(1).strip().upper()
                continue

            # Warning Comp. Temp. Threshold
            m = re.match(r"^Warning\s+Comp\.\s+Temp\.\s+Threshold:\s+(\d+)\s+Celsius", line_str, re.I)
            if m:
                info.warningTempThreshold = int(m.group(1))
                continue

            # Critical Comp. Temp. Threshold
            m = re.match(r"^Critical\s+Comp\.\s+Temp\.\s+Threshold:\s+(\d+)\s+Celsius", line_str, re.I)
            if m:
                info.criticalTempThreshold = int(m.group(1))
                continue

            # Critical Warning
            m = re.match(r"^Critical Warning:\s+(0x[0-9a-fA-F]+|\d+)", line_str, re.I)
            if m:
                info.criticalWarning = m.group(1).strip()
                continue

            # Temperature
            m = re.match(r"^Temperature:\s+(\d+)\s+Celsius", line_str, re.I)
            if m:
                info.temperature = int(m.group(1))
                continue

            # Available Spare
            m = re.match(r"^Available Spare:\s+(\d+)%", line_str, re.I)
            if m:
                info.availableSpare = int(m.group(1))
                continue

            # Available Spare Threshold
            m = re.match(r"^Available Spare Threshold:\s+(\d+)%", line_str, re.I)
            if m:
                info.availableSpareThreshold = int(m.group(1))
                continue

            # Percentage Used
            m = re.match(r"^Percentage Used:\s+(\d+)%", line_str, re.I)
            if m:
                info.percentageUsed = int(m.group(1))
                rem = max(0, 100 - info.percentageUsed)
                info.remainingEndurance = rem
                info.healthPercentage = rem
                info.healthPercentageType = "nvme_percentage_used"
                info.healthPercentageAttribute = "NVMe Log 0x02 Percentage Used"
                continue

            # Data Units Read
            m = re.match(r"^Data Units Read:\s+[\d,]+\s+\[(.+?)\]", line_str, re.I)
            if m:
                tb_m = re.search(r"([\d.]+)\s*TB", m.group(1), re.I)
                if tb_m:
                    info.dataReadTB = float(tb_m.group(1))
                else:
                    pb_m = re.search(r"([\d.]+)\s*PB", m.group(1), re.I)
                    if pb_m:
                        info.dataReadTB = round(float(pb_m.group(1)) * 1000, 1)
            elif re.match(r"^Data Units Read:\s+([\d,]+)", line_str, re.I):
                raw_val = int(re.match(r"^Data Units Read:\s+([\d,]+)", line_str, re.I).group(1).replace(",", ""))
                info.dataReadTB = round((raw_val * 512000) / (1000 ** 4), 1)

            # Data Units Written
            m = re.match(r"^Data Units Written:\s+[\d,]+\s+\[(.+?)\]", line_str, re.I)
            if m:
                tb_m = re.search(r"([\d.]+)\s*TB", m.group(1), re.I)
                if tb_m:
                    info.dataWrittenTB = float(tb_m.group(1))
                else:
                    pb_m = re.search(r"([\d.]+)\s*PB", m.group(1), re.I)
                    if pb_m:
                        info.dataWrittenTB = round(float(pb_m.group(1)) * 1000, 1)
            elif re.match(r"^Data Units Written:\s+([\d,]+)", line_str, re.I):
                raw_val = int(re.match(r"^Data Units Written:\s+([\d,]+)", line_str, re.I).group(1).replace(",", ""))
                info.dataWrittenTB = round((raw_val * 512000) / (1000 ** 4), 1)

            # Power Cycles
            m = re.match(r"^Power Cycles:\s+([\d,]+)", line_str, re.I)
            if m:
                info.powerCycles = int(m.group(1).replace(",", ""))
                continue

            # Power On Hours
            m = re.match(r"^Power On Hours:\s+([\d,]+)", line_str, re.I)
            if m:
                info.powerOnHours = int(m.group(1).replace(",", ""))
                continue

            # Unsafe Shutdowns
            m = re.match(r"^Unsafe Shutdowns:\s+([\d,]+)", line_str, re.I)
            if m:
                info.unsafeShutdowns = int(m.group(1).replace(",", ""))
                continue

            # Media and Data Integrity Errors
            m = re.match(r"^Media and Data Integrity Errors:\s+([\d,]+)", line_str, re.I)
            if m:
                info.mediaErrors = int(m.group(1).replace(",", ""))
                continue

            # Error Information Log Entries
            m = re.match(r"^Error Information Log Entries:\s+([\d,]+)", line_str, re.I)
            if m:
                info.errorLogEntries = int(m.group(1).replace(",", ""))
                continue

        NvmeParser.classify_status(info)
        return info

    @staticmethod
    def classify_status(info: DiskHealthInfo):
        """
        Classifies status strictly according to specification:
        HEALTHY / WARNING / CRITICAL
        """
        # Critical checks
        if info.smartStatus == "FAILED":
            info.status = "CRITICAL"
            info.warnings.append("SMART overall health self-assessment FAILED")

        cw_int = 0
        if info.criticalWarning:
            try:
                cw_int = int(info.criticalWarning, 16) if info.criticalWarning.startswith("0x") else int(info.criticalWarning)
            except Exception:
                cw_int = 0

        if cw_int != 0:
            info.status = "CRITICAL"
            info.warnings.append(f"NVMe Critical Warning flag active ({info.criticalWarning})")

        if info.mediaErrors and info.mediaErrors > 0:
            info.status = "CRITICAL"
            info.warnings.append(f"Media and Data Integrity Errors detected: {info.mediaErrors}")

        # Temperature checks
        if info.temperature is not None:
            if info.criticalTempThreshold and info.temperature >= info.criticalTempThreshold:
                info.status = "CRITICAL"
                info.warnings.append(f"Drive temperature ({info.temperature}°C) reached critical threshold ({info.criticalTempThreshold}°C)")
            elif info.warningTempThreshold and info.temperature >= info.warningTempThreshold:
                if info.status != "CRITICAL":
                    info.status = "WARNING"
                info.warnings.append(f"Drive temperature ({info.temperature}°C) reached warning threshold ({info.warningTempThreshold}°C)")
            elif info.temperature >= 70:
                if info.status != "CRITICAL":
                    info.status = "WARNING"
                info.warnings.append(f"High drive temperature ({info.temperature}°C)")

        # If SMART status is UNKNOWN and no critical telemetry could be retrieved
        if info.smartStatus == "UNKNOWN" and info.percentageUsed is None and info.temperature is None:
            info.status = "UNKNOWN"
            return

        # Spare checks
        if info.availableSpare is not None and info.availableSpareThreshold is not None:
            if info.availableSpare < info.availableSpareThreshold:
                if info.status != "CRITICAL":
                    info.status = "WARNING"
                info.warnings.append(f"Available spare ({info.availableSpare}%) is below threshold ({info.availableSpareThreshold}%)")

        # Wear checks
        if info.percentageUsed is not None:
            if info.percentageUsed >= 100:
                if info.status != "CRITICAL":
                    info.status = "WARNING"
                info.warnings.append(f"Drive reached or exceeded 100% of manufacturer estimated endurance ({info.percentageUsed}%)")
            elif info.percentageUsed >= 90:
                if info.status != "CRITICAL":
                    info.status = "WARNING"
                info.warnings.append(f"High endurance wear ({info.percentageUsed}% used, {info.remainingEndurance}% remaining)")

        # Error log entries
        if info.errorLogEntries and info.errorLogEntries > 0 and info.status == "HEALTHY":
            info.warnings.append(f"Error log contains {info.errorLogEntries} entry/entries")


class AtaSmartParser:
    """
    Parses smartctl output for ATA/SATA HDDs and SSDs.
    Extracts standard SMART attributes (Reallocated sectors, Pending sectors, Uncorrectable, UDMA CRC)
    and searches for official manufacturer endurance/life attributes (231, 233, 177, 202).
    """

    # Attribute IDs that represent normalized manufacturer SSD life/endurance remaining (out of 100)
    SSD_LIFE_ATTRIBUTES = {
        231: ("SSD_Life_Left", "manufacturer"),
        233: ("Media_Wearout_Indicator", "manufacturer"),
        202: ("Percent_Lifetime_Remain", "manufacturer"),
        177: ("Wear_Range_Delta", "manufacturer"),
    }

    @staticmethod
    def parse_json(data: dict, device_path: str = "") -> DiskHealthInfo:
        info = DiskHealthInfo(device=device_path, interface="SATA")

        # Model & Capacity
        info.model = data.get("model_name") or data.get("device", {}).get("info_name") or "ATA/SATA Device"
        user_cap = data.get("user_capacity", {})
        bytes_val = user_cap.get("bytes")
        if bytes_val:
            gb = bytes_val / (1000 ** 3)
            info.capacity = f"{gb:.1f} GB" if gb < 1000 else f"{(gb / 1000):.2f} TB"

        # Rotation Rate: SSD vs HDD
        rot = data.get("rotation_rate", 0)
        if rot == 0:
            info.interface = "SATA SSD"
        else:
            info.interface = f"SATA HDD ({rot} RPM)"

        # SMART Status
        smart_st = data.get("smart_status", {})
        if "passed" in smart_st:
            info.smartStatus = "PASSED" if smart_st.get("passed") else "FAILED"

        # Temperature
        temp_data = data.get("temperature", {})
        if "current" in temp_data:
            info.temperature = temp_data.get("current")

        # Power On Time & Power Cycles
        pot = data.get("power_on_time", {})
        if "hours" in pot:
            info.powerOnHours = pot.get("hours")
        if "power_cycle_count" in data:
            info.powerCycles = data.get("power_cycle_count")

        # ATA SMART Attributes Table
        ata_table = data.get("ata_smart_attributes", {}).get("table", [])
        raw_attrs = {}

        for attr in ata_table:
            aid = attr.get("id")
            aname = attr.get("name")
            val = attr.get("value")
            raw = attr.get("raw", {}).get("value", 0)
            raw_str = attr.get("raw", {}).get("string", str(raw))

            raw_attrs[str(aid)] = {
                "id": aid,
                "name": aname,
                "value": val,
                "worst": attr.get("worst"),
                "thresh": attr.get("thresh"),
                "raw": raw,
                "raw_str": raw_str
            }

            # Temperature from attributes (ID 194 or 190)
            if aid in (194, 190) and info.temperature is None:
                # Raw value often has temperature in lower byte
                info.temperature = raw & 0xFF

            # Power on hours (ID 9)
            if aid == 9 and info.powerOnHours is None:
                info.powerOnHours = raw

            # Power cycles (ID 12)
            if aid == 12 and info.powerCycles is None:
                info.powerCycles = raw

            # Total LBAs Written (ID 241) -> Convert to TB (1 LBA = 512 bytes)
            if aid == 241:
                try:
                    info.dataWrittenTB = round((raw * 512) / (1000 ** 4), 1)
                except Exception:
                    pass

            # Manufacturer SSD Life / Endurance attribute
            if aid in AtaSmartParser.SSD_LIFE_ATTRIBUTES and info.healthPercentage is None:
                attr_name, attr_type = AtaSmartParser.SSD_LIFE_ATTRIBUTES[aid]
                # Normalized value represents remaining life (0-100)
                if 0 <= val <= 100:
                    info.healthPercentage = val
                    info.healthPercentageType = attr_type
                    info.healthPercentageAttribute = f"SMART {aid} {aname or attr_name}"
                    info.remainingEndurance = val
                    info.percentageUsed = max(0, 100 - val)

        info.attributes = raw_attrs
        AtaSmartParser.classify_status(info)
        return info

    @staticmethod
    def parse_text(text: str, device_path: str = "") -> DiskHealthInfo:
        info = DiskHealthInfo(device=device_path, interface="SATA")

        in_attributes = False
        raw_attrs = {}

        for line in text.splitlines():
            line_str = line.strip()
            if not line_str:
                continue

            # Device Model
            m = re.match(r"^Device Model:\s+(.+)$", line_str, re.I)
            if m:
                info.model = m.group(1).strip()
                continue
            m = re.match(r"^Model Family:\s+(.+)$", line_str, re.I)
            if m and info.model == "Unknown Model":
                info.model = m.group(1).strip()
                continue

            # User Capacity
            m = re.match(r"^User Capacity:\s+[\d,]+\s+bytes\s+\[(.+?)\]", line_str, re.I)
            if m:
                info.capacity = m.group(1).strip()
                continue

            # Rotation Rate
            m = re.match(r"^Rotation Rate:\s+(.+)$", line_str, re.I)
            if m:
                rate_str = m.group(1).strip()
                if "solid state" in rate_str.lower():
                    info.interface = "SATA SSD"
                else:
                    info.interface = f"SATA HDD ({rate_str})"
                continue

            # Overall Health Result
            m = re.match(r"^SMART overall-health self-assessment test result:\s+(.+)$", line_str, re.I)
            if m:
                info.smartStatus = m.group(1).strip().upper()
                continue

            # SMART Attributes Table header
            if "ID# ATTRIBUTE_NAME" in line_str:
                in_attributes = True
                continue

            if in_attributes:
                # Format: ID# ATTRIBUTE_NAME FLAG VALUE WORST THRESH TYPE UPDATED WHEN_FAILED RAW_VALUE
                parts = line_str.split()
                if len(parts) >= 10 and parts[0].isdigit():
                    aid = int(parts[0])
                    aname = parts[1]
                    try:
                        val = int(parts[3])
                        worst = int(parts[4])
                        thresh = int(parts[5])
                        raw_str = " ".join(parts[9:])
                        # Extract first integer from raw_str
                        raw_int_m = re.search(r"^\d+", raw_str)
                        raw_val = int(raw_int_m.group(0)) if raw_int_m else 0

                        raw_attrs[str(aid)] = {
                            "id": aid,
                            "name": aname,
                            "value": val,
                            "worst": worst,
                            "thresh": thresh,
                            "raw": raw_val,
                            "raw_str": raw_str
                        }

                        # Temperature (194 or 190)
                        if aid in (194, 190) and info.temperature is None:
                            temp_m = re.search(r"(\d+)", raw_str)
                            if temp_m:
                                info.temperature = int(temp_m.group(1))

                        # Power On Hours (9)
                        if aid == 9 and info.powerOnHours is None:
                            info.powerOnHours = raw_val

                        # Power Cycles (12)
                        if aid == 12 and info.powerCycles is None:
                            info.powerCycles = raw_val

                        # Total LBAs Written (241)
                        if aid == 241 and info.dataWrittenTB is None:
                            info.dataWrittenTB = round((raw_val * 512) / (1000 ** 4), 1)

                        # Manufacturer Life Remaining (231, 233, 202, 177)
                        if aid in AtaSmartParser.SSD_LIFE_ATTRIBUTES and info.healthPercentage is None:
                            attr_name, attr_type = AtaSmartParser.SSD_LIFE_ATTRIBUTES[aid]
                            if 0 <= val <= 100:
                                info.healthPercentage = val
                                info.healthPercentageType = attr_type
                                info.healthPercentageAttribute = f"SMART {aid} {aname}"
                                info.remainingEndurance = val
                                info.percentageUsed = max(0, 100 - val)

                    except Exception:
                        pass

        info.attributes = raw_attrs
        AtaSmartParser.classify_status(info)
        return info

    @staticmethod
    def classify_status(info: DiskHealthInfo):
        """
        Classifies status for SATA/ATA drives:
        Monitors bad sectors (Reallocated, Pending, Uncorrectable) and SMART passed/failed.
        """
        # Critical: SMART Failed
        if info.smartStatus == "FAILED":
            info.status = "CRITICAL"
            info.warnings.append("SMART overall-health self-assessment test result: FAILED")

        # If SMART status is UNKNOWN and no attributes could be read (e.g. SCSI pass-through restricted)
        if info.smartStatus == "UNKNOWN" and not info.attributes:
            info.status = "UNKNOWN"
            return

        attrs = info.attributes

        # Helper to get raw attribute value
        def get_raw(aid: int) -> int:
            return attrs.get(str(aid), {}).get("raw", 0)

        # Attribute 5: Reallocated Sector Count
        reallocated = get_raw(5)
        # Attribute 197: Current Pending Sector Count
        pending = get_raw(197)
        # Attribute 198: Offline Uncorrectable Sector Count
        uncorrectable = get_raw(198)
        # Attribute 187: Reported Uncorrectable Errors
        reported_uncorrectable = get_raw(187)
        # Attribute 199: UDMA CRC Error Count
        crc_errors = get_raw(199)

        # Critical threshold: High pending or uncorrectable sectors
        if pending >= 5 or uncorrectable >= 5 or reallocated >= 50 or reported_uncorrectable >= 10:
            info.status = "CRITICAL"
            if pending > 0:
                info.warnings.append(f"Critical Current Pending Sectors: {pending}")
            if uncorrectable > 0:
                info.warnings.append(f"Critical Offline Uncorrectable Sectors: {uncorrectable}")
            if reallocated > 0:
                info.warnings.append(f"High Reallocated Sectors: {reallocated}")
            if reported_uncorrectable > 0:
                info.warnings.append(f"Reported Uncorrectable Errors: {reported_uncorrectable}")

        # Warning threshold: Any bad sectors detected
        elif pending > 0 or uncorrectable > 0 or reallocated > 0:
            if info.status != "CRITICAL":
                info.status = "WARNING"
            if pending > 0:
                info.warnings.append(f"Current Pending Sectors: {pending} (Risk of unreadable data)")
            if reallocated > 0:
                info.warnings.append(f"Reallocated Sectors: {reallocated}")
            if uncorrectable > 0:
                info.warnings.append(f"Offline Uncorrectable Sectors: {uncorrectable}")

        # CRC Interface Errors (cable / connection issue, not necessarily bad disk)
        if crc_errors > 0:
            info.warnings.append(f"UDMA CRC Errors: {crc_errors} (Check SATA cable/connection)")

        # Temperature check
        if info.temperature is not None:
            if info.temperature >= 60:
                if info.status != "CRITICAL":
                    info.status = "WARNING"
                info.warnings.append(f"High drive temperature ({info.temperature}°C)")

        # Manufacturer wear check if available
        if info.healthPercentage is not None and info.healthPercentage <= 10:
            if info.status != "CRITICAL":
                info.status = "WARNING"
            info.warnings.append(f"Low remaining endurance ({info.healthPercentage}%)")


class SmartctlProvider:
    """
    Manages discovery and safe execution of smartctl.
    Enumerates disks and executes appropriate commands per disk.
    """

    COMMON_PATHS = [
        r"C:\Program Files\smartmontools\bin\smartctl.exe",
        r"C:\Program Files (x86)\smartmontools\bin\smartctl.exe",
        r"C:\ProgramData\chocolatey\bin\smartctl.exe",
        r"C:\smartmontools\bin\smartctl.exe"
    ]

    def __init__(self, custom_path: Optional[str] = None):
        self.smartctl_path = self.detect_smartctl(custom_path)

    @classmethod
    def detect_smartctl(cls, custom_path: Optional[str] = None) -> Optional[str]:
        """Detects smartctl binary in custom path, known system locations, or PATH."""
        if custom_path and os.path.exists(custom_path) and os.path.isfile(custom_path):
            return custom_path

        for p in cls.COMMON_PATHS:
            if os.path.exists(p) and os.path.isfile(p):
                return p

        # Check PATH
        which_path = shutil.which("smartctl") or shutil.which("smartctl.exe")
        if which_path:
            return which_path

        return None

    def is_available(self) -> bool:
        return bool(self.smartctl_path and os.path.exists(self.smartctl_path))

    def run_command(self, args: List[str], timeout_sec: int = 12) -> Tuple[int, str, str]:
        """
        Safely executes smartctl without shell command concatenation.
        Returns: (return_code, stdout_str, stderr_str)
        """
        if not self.is_available():
            return -1, "", "smartctl binary not found"

        cmd = [self.smartctl_path] + args
        try:
            # Set creationflags=subprocess.CREATE_NO_WINDOW on Windows to prevent console popup
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                creationflags=creation_flags
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            logger.warning("smartctl command timed out: %s", " ".join(cmd))
            return -2, "", "Command timed out"
        except Exception as e:
            logger.error("Error executing smartctl: %s", e)
            return -3, "", str(e)

    def scan_disks(self) -> List[Dict[str, str]]:
        """
        Runs `smartctl --scan` and parses detected disks with their device types.
        Example output:
            /dev/sda -d ata # /dev/sda, ATA device
            /dev/sdb -d nvme # /dev/sdb, NVMe device
        """
        code, out, err = self.run_command(["--scan"])
        disks = []
        if not out:
            return disks

        for line in out.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue

            # Regex to match: /dev/xxx -d type
            m = re.match(r"^(\S+)\s+-d\s+(\S+)", line_str)
            if m:
                dev = m.group(1)
                dtype = m.group(2)
                disks.append({"device": dev, "type": dtype, "raw_scan": line_str})
            else:
                # Fallback: single device token
                parts = line_str.split()
                if parts:
                    disks.append({"device": parts[0], "type": "auto", "raw_scan": line_str})

        return disks

    def query_disk(self, device: str, device_type: str = "auto") -> DiskHealthInfo:
        """
        Queries a single disk using smartctl and parses into structured DiskHealthInfo.
        First tries JSON output (`-j`), falls back to standard text output.
        Handles access denied, missing attributes, and device-specific quirks.
        """
        args_type = ["-d", device_type] if device_type and device_type != "auto" else []

        # 1. Try modern JSON output (-j)
        cmd_args = ["-a"] + args_type + [device, "-j"]
        code, out, err = self.run_command(cmd_args)

        if out and out.strip().startswith("{"):
            try:
                data = json.loads(out)
                # Check for fatal open/identity errors in JSON
                if "error" in data:
                    err_msg = data.get("error", {}).get("message", "smartctl reported error")
                    return DiskHealthInfo(device=device, interface=device_type, status="UNKNOWN", rawError=err_msg)

                # Determine whether to use NVMe or ATA parser
                dev_protocol = data.get("device", {}).get("protocol", "").upper()
                dev_type_str = data.get("device", {}).get("type", "").lower()

                if "NVME" in dev_protocol or dev_type_str == "nvme" or device_type == "nvme":
                    return NvmeParser.parse_json(data, device_path=device)
                else:
                    return AtaSmartParser.parse_json(data, device_path=device)
            except Exception as json_err:
                logger.debug("JSON parse failed for %s, falling back to text: %s", device, json_err)

        # 2. Text output fallback
        cmd_args_text = ["-a"] + args_type + [device]
        code, out_text, err_text = self.run_command(cmd_args_text)

        # Check for permission or access errors
        combined = (out_text + "\n" + err_text).lower()
        if "error=5" in combined or "access denied" in combined or "permission denied" in combined:
            return DiskHealthInfo(
                device=device,
                interface=device_type.upper(),
                status="UNKNOWN",
                rawError="Permission Denied (Administrator privileges required to query drive pass-through)",
                warnings=["Administrator privileges required to query physical SMART device."]
            )

        if "read device identity failed" in combined or "input/output error" in combined:
            # If -d ata failed with IO error, try without -d or with -d sat
            if device_type == "ata":
                alt_code, alt_out, _ = self.run_command(["-a", "-d", "sat", device])
                if alt_out and "device model" in alt_out.lower():
                    return AtaSmartParser.parse_text(alt_out, device_path=device)

            return DiskHealthInfo(
                device=device,
                interface=device_type.upper(),
                status="UNKNOWN",
                rawError="Read Device Identity failed (Device busy or controller unsupported)"
            )

        if "nvme" in device_type.lower() or "nvme" in combined:
            return NvmeParser.parse_text(out_text, device_path=device)
        else:
            return AtaSmartParser.parse_text(out_text, device_path=device)


class DiskHealthProvider:
    """
    High-level abstraction for hardware disk health monitoring.
    Coordinates device discovery, querying, structured reporting, and fallback mechanisms.
    """

    def __init__(self, custom_smartctl_path: Optional[str] = None):
        self.provider = SmartctlProvider(custom_smartctl_path)

    def is_available(self) -> bool:
        return self.provider.is_available()

    def get_smartctl_path(self) -> Optional[str]:
        return self.provider.smartctl_path

    def get_all_disks_health(self) -> List[DiskHealthInfo]:
        """
        Scans all physical disks and retrieves complete, accurate SMART telemetry.
        """
        if not self.is_available():
            logger.warning("smartctl is not installed or detected on this system.")
            return []

        scanned = self.provider.scan_disks()
        results = []

        for item in scanned:
            dev = item["device"]
            dtype = item["type"]
            try:
                disk_info = self.provider.query_disk(dev, dtype)
                results.append(disk_info)
            except Exception as e:
                logger.error("Failed querying disk %s (%s): %s", dev, dtype, e)
                results.append(DiskHealthInfo(device=dev, interface=dtype, status="UNKNOWN", rawError=str(e)))

        return results

    def format_cli_report(self, disks: List[DiskHealthInfo]) -> str:
        """
        Formats disk health into the clean, human-readable UI layout requested in the specification.
        """
        lines = []
        for d in disks:
            lines.append("=" * 60)
            lines.append(f"{d.model}")
            lines.append(f"Device: {d.device} | Interface: {d.interface} | Capacity: {d.capacity}")
            lines.append("-" * 60)
            lines.append(f"SMART Status:                   {d.smartStatus}")
            lines.append(f"Overall Condition:             {d.status}")

            if d.criticalWarning is not None:
                lines.append(f"Critical Warning:              {d.criticalWarning}")

            # Health / Endurance formatting
            if d.healthPercentageType == "nvme_percentage_used":
                lines.append(f"Estimated Remaining Endurance: {d.remainingEndurance}%")
                lines.append(f"Percentage Used:               {d.percentageUsed}%")
                if d.availableSpare is not None:
                    lines.append(f"Available Spare:               {d.availableSpare}% (Threshold: {d.availableSpareThreshold}%)")
            elif d.healthPercentageType == "manufacturer":
                attr_desc = f" ({d.healthPercentageAttribute})" if d.healthPercentageAttribute else ""
                lines.append(f"Manufacturer Health Indicator: {d.healthPercentage}%{attr_desc}")
            else:
                lines.append(f"Health Percentage:             Unavailable (Based on SMART attributes)")

            if d.temperature is not None:
                temp_thresh = ""
                if d.warningTempThreshold or d.criticalTempThreshold:
                    temp_thresh = f" (Warn: {d.warningTempThreshold or 'N/A'}°C, Crit: {d.criticalTempThreshold or 'N/A'}°C)"
                lines.append(f"Temperature:                   {d.temperature}°C{temp_thresh}")

            if d.powerOnHours is not None:
                days = round(d.powerOnHours / 24, 1)
                lines.append(f"Power On Hours:                {d.powerOnHours:,} ({days} days)")

            if d.powerCycles is not None:
                lines.append(f"Power Cycles:                  {d.powerCycles:,}")

            if d.unsafeShutdowns is not None:
                lines.append(f"Unsafe Shutdowns:              {d.unsafeShutdowns:,}")

            if d.dataWrittenTB is not None:
                lines.append(f"Data Written:                  {d.dataWrittenTB} TB")

            if d.dataReadTB is not None:
                lines.append(f"Data Read:                     {d.dataReadTB} TB")

            if d.mediaErrors is not None:
                lines.append(f"Media/Data Errors:             {d.mediaErrors}")

            if d.errorLogEntries is not None:
                lines.append(f"Error Log Entries:             {d.errorLogEntries}")

            if d.rawError:
                lines.append(f"Diagnostic Notice:             {d.rawError}")

            if d.warnings:
                lines.append("Warnings / Alerts:")
                for w in d.warnings:
                    lines.append(f"  [!] {w}")

        lines.append("=" * 60)
        return "\n".join(lines)


if __name__ == "__main__":
    provider = DiskHealthProvider()
    if not provider.is_available():
        if "--json" in sys.argv:
            print("[]")
        else:
            print("[!] smartctl not detected on this system.")
            print("    Please install smartmontools (https://www.smartmontools.org/)")
            print("    Standard path: C:\\Program Files\\smartmontools\\bin\\smartctl.exe")
        sys.exit(1)

    if "--json" not in sys.argv:
        print(f"[*] Detected smartctl at: {provider.get_smartctl_path()}")
    disks = provider.get_all_disks_health()
    if "--json" in sys.argv:
        print(json.dumps([d.to_dict() for d in disks], indent=2))
    else:
        print(provider.format_cli_report(disks))
