"""
test_disk_health_provider.py - Unit tests for smartctl SMART health parsing and classification.
Uses realistic smartctl outputs for NVMe SSDs, SATA SSDs, and HDDs.
"""

import unittest
from disk_health_provider import NvmeParser, AtaSmartParser, DiskHealthInfo, SmartctlProvider

SAMPLE_NVME_TEXT = """smartctl 7.5 2025-04-30 r5714 [x86_64-w64-mingw32-w11-24H2] (AppVeyor)
=== START OF INFORMATION SECTION ===
Model Number:                       Dahua E900 M.2 2280 NVMe 512GB SSD
Serial Number:                      N9YL13A00A01816
Firmware Version:                   V0808A0
Namespace 1 Size/Capacity:          512,110,190,592 [512 GB]
Warning  Comp. Temp. Threshold:     83 Celsius
Critical Comp. Temp. Threshold:     85 Celsius

=== START OF SMART DATA SECTION ===
SMART overall-health self-assessment test result: PASSED

SMART/Health Information (NVMe Log 0x02, NSID 0xffffffff)
Critical Warning:                   0x00
Temperature:                        52 Celsius
Available Spare:                    100%
Available Spare Threshold:          10%
Percentage Used:                    7%
Data Units Read:                    95,078,634 [48.6 TB]
Data Units Written:                 82,924,349 [42.4 TB]
Host Read Commands:                 2,309,747,003
Host Write Commands:                1,917,910,882
Controller Busy Time:               56,844
Power Cycles:                       1,666
Power On Hours:                     6,123
Unsafe Shutdowns:                   531
Media and Data Integrity Errors:    0
Error Information Log Entries:      0
"""

SAMPLE_NVME_CRITICAL_TEXT = """smartctl 7.5
Model Number:                       Failing NVMe SSD 1TB
Namespace 1 Size/Capacity:          1,000,204,886,016 [1.00 TB]
SMART overall-health self-assessment test result: FAILED
Critical Warning:                   0x04
Temperature:                        86 Celsius
Warning  Comp. Temp. Threshold:     80 Celsius
Critical Comp. Temp. Threshold:     85 Celsius
Available Spare:                    5%
Available Spare Threshold:          10%
Percentage Used:                    105%
Data Units Written:                 300,000,000 [153.6 TB]
Power On Hours:                     15,000
Media and Data Integrity Errors:    42
Error Information Log Entries:      120
"""

SAMPLE_SATA_SSD_TEXT = """smartctl 7.5
Device Model:     Crucial_CT500MX500SSD1
Serial Number:    1942E224F1A0
User Capacity:    500,107,862,016 bytes [500 GB]
Rotation Rate:    Solid State Device
SMART overall-health self-assessment test result: PASSED

ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE
  5 Reallocated_Sector_Ct   0x0033   100   100   010    Pre-fail  Always       -       0
  9 Power_On_Hours          0x0032   100   100   000    Old_age   Always       -       8230
 12 Power_Cycle_Count       0x0032   100   100   000    Old_age   Always       -       1240
194 Temperature_Celsius     0x0022   068   052   000    Old_age   Always       -       32 (Min/Max 14/48)
197 Current_Pending_Sector  0x0032   100   100   000    Old_age   Always       -       0
198 Offline_Uncorrectable   0x0030   100   100   000    Old_age   Offline      -       0
199 UDMA_CRC_Error_Count    0x0032   100   100   000    Old_age   Always       -       0
202 Percent_Lifetime_Remain 0x0030   091   091   001    Old_age   Offline      -       9
241 Total_LBAs_Written      0x0032   100   100   000    Old_age   Always       -       38240592810
"""

SAMPLE_SATA_HDD_FAILING_TEXT = """smartctl 7.5
Device Model:     WDC WD10EZEX-00WN4A0
Serial Number:    WD-WCC6Y1234567
User Capacity:    1,000,204,886,016 bytes [1.00 TB]
Rotation Rate:    7200 rpm
SMART overall-health self-assessment test result: PASSED

ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE
  5 Reallocated_Sector_Ct   0x0033   080   080   036    Pre-fail  Always       -       128
  9 Power_On_Hours          0x0032   072   072   000    Old_age   Always       -       24500
 12 Power_Cycle_Count       0x0032   095   095   000    Old_age   Always       -       3200
194 Temperature_Celsius     0x0022   110   090   000    Old_age   Always       -       38
197 Current_Pending_Sector  0x0032   060   060   000    Old_age   Always       -       48
198 Offline_Uncorrectable   0x0030   060   060   000    Old_age   Offline      -       32
199 UDMA_CRC_Error_Count    0x0032   200   200   000    Old_age   Always       -       3
"""


class TestDiskHealthProvider(unittest.TestCase):

    def test_nvme_text_parsing_healthy(self):
        info = NvmeParser.parse_text(SAMPLE_NVME_TEXT, "/dev/sdb")
        self.assertEqual(info.model, "Dahua E900 M.2 2280 NVMe 512GB SSD")
        self.assertEqual(info.interface, "NVMe")
        self.assertEqual(info.capacity, "512 GB")
        self.assertEqual(info.smartStatus, "PASSED")
        self.assertEqual(info.criticalWarning, "0x00")
        self.assertEqual(info.temperature, 52)
        self.assertEqual(info.warningTempThreshold, 83)
        self.assertEqual(info.criticalTempThreshold, 85)
        self.assertEqual(info.availableSpare, 100)
        self.assertEqual(info.availableSpareThreshold, 10)
        self.assertEqual(info.percentageUsed, 7)
        self.assertEqual(info.remainingEndurance, 93)
        self.assertEqual(info.healthPercentage, 93)
        self.assertEqual(info.healthPercentageType, "nvme_percentage_used")
        self.assertEqual(info.dataWrittenTB, 42.4)
        self.assertEqual(info.dataReadTB, 48.6)
        self.assertEqual(info.powerCycles, 1666)
        self.assertEqual(info.powerOnHours, 6123)
        self.assertEqual(info.unsafeShutdowns, 531)
        self.assertEqual(info.mediaErrors, 0)
        self.assertEqual(info.errorLogEntries, 0)
        self.assertEqual(info.status, "HEALTHY")
        self.assertEqual(len(info.warnings), 0)

    def test_nvme_text_parsing_critical(self):
        info = NvmeParser.parse_text(SAMPLE_NVME_CRITICAL_TEXT, "/dev/nvme0")
        self.assertEqual(info.smartStatus, "FAILED")
        self.assertEqual(info.status, "CRITICAL")
        self.assertEqual(info.percentageUsed, 105)
        self.assertEqual(info.remainingEndurance, 0)
        self.assertEqual(info.mediaErrors, 42)
        # Should have critical warning and temperature breach warnings
        self.assertTrue(any("FAILED" in w for w in info.warnings))
        self.assertTrue(any("Media and Data Integrity Errors" in w for w in info.warnings))
        self.assertTrue(any("critical threshold" in w for w in info.warnings))

    def test_sata_ssd_manufacturer_endurance(self):
        info = AtaSmartParser.parse_text(SAMPLE_SATA_SSD_TEXT, "/dev/sda")
        self.assertEqual(info.model, "Crucial_CT500MX500SSD1")
        self.assertEqual(info.interface, "SATA SSD")
        self.assertEqual(info.smartStatus, "PASSED")
        self.assertEqual(info.status, "HEALTHY")
        # Attribute 202 Percent_Lifetime_Remain = 91%
        self.assertEqual(info.healthPercentage, 91)
        self.assertEqual(info.healthPercentageType, "manufacturer")
        self.assertIn("SMART 202 Percent_Lifetime_Remain", info.healthPercentageAttribute)
        self.assertEqual(info.temperature, 32)
        self.assertEqual(info.powerOnHours, 8230)
        self.assertEqual(info.powerCycles, 1240)

    def test_sata_hdd_bad_sectors_critical(self):
        info = AtaSmartParser.parse_text(SAMPLE_SATA_HDD_FAILING_TEXT, "/dev/sdc")
        self.assertEqual(info.model, "WDC WD10EZEX-00WN4A0")
        self.assertIn("SATA HDD", info.interface)
        self.assertEqual(info.smartStatus, "PASSED") # Drive has not yet officially tripped SMART threshold
        self.assertEqual(info.status, "CRITICAL")    # But sector reallocation & pending are high
        self.assertEqual(info.healthPercentageType, "unavailable") # No fake percentage
        self.assertIsNone(info.healthPercentage)
        self.assertTrue(any("Pending Sectors: 48" in w for w in info.warnings))
        self.assertTrue(any("Reallocated Sectors: 128" in w for w in info.warnings))

    def test_nvme_json_parsing(self):
        sample_json = {
            "model_name": "Samsung SSD 980 PRO 1TB",
            "device": {"type": "nvme", "protocol": "NVMe"},
            "user_capacity": {"bytes": 1000204886016},
            "smart_status": {"passed": True},
            "temperature": {"current": 44, "op_limit_max": 82, "critical_limit_max": 85},
            "nvme_smart_health_information_log": {
                "critical_warning": 0,
                "temperature": 44,
                "available_spare": 100,
                "available_spare_threshold": 10,
                "percentage_used": 3,
                "data_units_read": 20000000,
                "data_units_written": 15000000,
                "power_cycles": 420,
                "power_on_hours": 3200,
                "unsafe_shutdowns": 12,
                "media_errors": 0,
                "num_err_log_entries": 0
            }
        }
        info = NvmeParser.parse_json(sample_json, "/dev/nvme0n1")
        self.assertEqual(info.model, "Samsung SSD 980 PRO 1TB")
        self.assertEqual(info.remainingEndurance, 97)
        self.assertEqual(info.healthPercentage, 97)
        self.assertEqual(info.healthPercentageType, "nvme_percentage_used")
        self.assertEqual(info.dataWrittenTB, 7.7) # 15000000 * 512000 / 1e12 = 7.68 TB -> 7.7 TB
        self.assertEqual(info.status, "HEALTHY")

    def test_smartctl_detection(self):
        provider = SmartctlProvider()
        # System has smartctl installed
        self.assertTrue(provider.is_available())
        self.assertIn("smartctl.exe", provider.smartctl_path.lower())


if __name__ == "__main__":
    unittest.main()
