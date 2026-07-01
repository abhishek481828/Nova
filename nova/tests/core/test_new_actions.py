import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from nova.actions.rich_system_info import RichSystemInfoAction
from nova.actions.desktop_control import DesktopControlAction
from nova.actions.wifi_control import WifiControlAction
from nova.utils import COLOR_GREEN, COLOR_CYAN, COLOR_RESET

class TestNewActions(unittest.TestCase):

    def test_strip_ansi(self):
        action = RichSystemInfoAction()
        text_with_ansi = "\x1b[1m\x1b[36mTest\x1b[0m Text"
        stripped = action._strip_ansi(text_with_ansi)
        self.assertEqual(stripped, "Test Text")

    @patch("nova.packages.NixPackageManager.get_installed_packages")
    @patch("nova.core.executor.CommandExecutor.run_shell")
    def test_rich_system_info_execute(self, mock_run_shell, mock_get_pkgs):
        mock_get_pkgs.return_value = ["vlc", "git"]
        # Mock commands run inside rich_system_info
        # 1. uname -srm
        # 2. lspci | grep -i -e "vga|3d|display"
        # 3. df -h /
        mock_run_shell.side_effect = [
            (0, "Linux 6.6.32-x86_64 x86_64", ""), # uname
            (0, "00:02.0 VGA compatible controller: Intel Corporation UHD Graphics (rev 02)", ""), # lspci
            (0, "Filesystem      Size  Used Avail Use% Mounted on\n/dev/sda1       118G   32G   86G  28% /", "") # df
        ]

        action = RichSystemInfoAction()
        result = action.execute({})
        
        # Verify result contains typical system fields
        self.assertIn("OS", result)
        self.assertIn("Kernel", result)
        self.assertIn("Uptime", result)
        self.assertIn("Shell", result)
        self.assertIn("Packages", result)
        self.assertIn("Memory", result)
        self.assertIn("Disk (/) ", result)

    @patch("nova.core.executor.CommandExecutor.run_shell")
    def test_desktop_control_lock(self, mock_run_shell):
        mock_run_shell.return_value = (0, "", "")
        action = DesktopControlAction()
        result = action.execute({"operation": "lock"})
        self.assertEqual(result, "Desktop screen locked successfully.")
        mock_run_shell.assert_called_with(
            ["dbus-send", "--type=method_call", "--dest=org.gnome.ScreenSaver", 
             "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver.Lock"],
            require_confirmation=False
        )

    @patch("nova.core.executor.CommandExecutor.run_shell")
    def test_wifi_control_status(self, mock_run_shell):
        # 1. nmcli radio wifi
        # 2. nmcli -t -f active,ssid,signal,bars dev wifi
        mock_run_shell.side_effect = [
            (0, "enabled", ""),
            (0, "no:OtherWifi:50:▂▄__\nyes:MyHomeWifi:85:▂▄▆_\n", "")
        ]
        action = WifiControlAction()
        result = action.execute({"operation": "status"})
        self.assertIn(f"Wi-Fi Radio: {COLOR_GREEN}ENABLED{COLOR_RESET}", result)
        self.assertIn(f"SSID: {COLOR_CYAN}MyHomeWifi{COLOR_RESET}", result)
        self.assertIn(f"Signal Strength: {COLOR_GREEN}85% (▂▄▆_){COLOR_RESET}", result)

if __name__ == "__main__":
    unittest.main()
