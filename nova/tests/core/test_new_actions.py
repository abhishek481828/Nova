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
    def test_desktop_control_unlock(self, mock_run_shell):
        mock_run_shell.return_value = (0, "", "")
        action = DesktopControlAction()
        result = action.execute({"operation": "unlock"})
        self.assertEqual(result, "Desktop screen unlocked successfully.")
        mock_run_shell.assert_called_with(
            [
                "gdbus", "call",
                "--session",
                "--dest", "org.gnome.ScreenSaver",
                "--object-path", "/org/gnome/ScreenSaver",
                "--method", "org.gnome.ScreenSaver.SetActive",
                "false"
            ],
            require_confirmation=False,
            extra_env=unittest.mock.ANY
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

    @patch("nova.core.executor.CommandExecutor.run_shell")
    def test_brightness_control_get_dbus(self, mock_run_shell):
        mock_run_shell.return_value = (0, "(<50>,)\n", "")
        from nova.actions.brightness import BrightnessControlAction
        action = BrightnessControlAction()
        result = action.execute({"operation": "get"})
        self.assertIn("50%", result)
        self.assertIn("D-Bus", result)
        mock_run_shell.assert_called_with(
            ["gdbus", "call", "--session", "--dest", "org.gnome.SettingsDaemon.Power",
             "--object-path", "/org/gnome/SettingsDaemon/Power",
             "--method", "org.freedesktop.DBus.Properties.Get",
             "org.gnome.SettingsDaemon.Power.Screen", "Brightness"],
            shell=False,
            require_confirmation=False
        )

    @patch("nova.core.executor.CommandExecutor.run_shell")
    def test_brightness_control_set_dbus(self, mock_run_shell):
        mock_run_shell.side_effect = [
            (0, "(<50>,)\n", ""),
            (0, "()\n", "")
        ]
        from nova.actions.brightness import BrightnessControlAction
        action = BrightnessControlAction()
        result = action.execute({"operation": "set", "level": 80})
        self.assertIn("80%", result)
        self.assertIn("Previous: 50%", result)
        self.assertEqual(mock_run_shell.call_count, 2)

    @patch("nova.core.executor.CommandExecutor.run_shell")
    def test_brightness_control_fallback_sysfs(self, mock_run_shell):
        mock_run_shell.side_effect = [
            (1, "", "D-Bus not available"),
            (0, "", "")
        ]
        from nova.actions.brightness import BrightnessControlAction
        action = BrightnessControlAction()
        
        with patch.object(action, "_get_brightness_values", return_value=(450, 1000)), \
             patch.object(action, "_get_backlight_device", return_value="amdgpu_bl1"):
            result = action.execute({"operation": "set", "level": 70})
            self.assertIn("70%", result)
            self.assertIn("Previous: 45%", result)

    @patch("nova.core.executor.CommandExecutor.run_shell")
    def test_charge_control_get(self, mock_run_shell):
        from nova.actions.charge_control import ChargeControlAction
        action = ChargeControlAction()
        
        with patch.object(action, "_find_charge_limit_files", return_value=["/sys/class/power_supply/BAT0/charge_control_end_threshold"]), \
             patch("builtins.open", unittest.mock.mock_open(read_data="80\n")):
            result = action.execute({"operation": "get"})
            self.assertIn("BAT0: 80%", result)

    @patch("nova.core.executor.CommandExecutor.run_shell")
    def test_charge_control_set(self, mock_run_shell):
        mock_run_shell.return_value = (0, "", "")
        from nova.actions.charge_control import ChargeControlAction
        action = ChargeControlAction()
        
        with patch.object(action, "_find_charge_limit_files", return_value=["/sys/class/power_supply/BAT0/charge_control_end_threshold"]), \
             patch("builtins.open", unittest.mock.mock_open(read_data="80\n")):
            result = action.execute({"operation": "set", "level": 90})
            self.assertIn("BAT0 set to 90%", result)
            self.assertIn("Previous: 80%", result)
            mock_run_shell.assert_called_with(
                "echo 90 | sudo tee /sys/class/power_supply/BAT0/charge_control_end_threshold",
                shell=True,
                require_confirmation=False
            )

    @patch("nova.core.executor.CommandExecutor.run_shell")
    @patch("nova.core.state.StateManager.set_charge_limit")
    def test_charge_control_set_saves_state(self, mock_set_charge_limit, mock_run_shell):
        mock_run_shell.return_value = (0, "", "")
        from nova.actions.charge_control import ChargeControlAction
        action = ChargeControlAction()
        
        with patch.object(action, "_find_charge_limit_files", return_value=["/sys/class/power_supply/BAT0/charge_control_end_threshold"]), \
             patch("builtins.open", unittest.mock.mock_open(read_data="80\n")):
            result = action.execute({"operation": "set", "level": 85})
            self.assertIn("BAT0 set to 85%", result)
            mock_set_charge_limit.assert_called_once_with(85)

    @patch("nova.core.executor.ask_confirmation", return_value=True)
    @patch("subprocess.run")
    def test_executor_one_time_confirmation(self, mock_subprocess_run, mock_ask_confirmation):
        from nova.core.executor import CommandExecutor
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "ok"
        mock_res.stderr = ""
        mock_subprocess_run.return_value = mock_res
        
        CommandExecutor.clear_last_commands()
        
        code, out, err = CommandExecutor.run_shell("test-cmd", require_confirmation=True)
        self.assertEqual(code, 0)
        self.assertEqual(mock_ask_confirmation.call_count, 1)
        
        code2, out2, err2 = CommandExecutor.run_shell("test-cmd", require_confirmation=True)
        self.assertEqual(code2, 0)
        self.assertEqual(mock_ask_confirmation.call_count, 1)
        
        CommandExecutor.clear_last_commands()
        
        code3, out3, err3 = CommandExecutor.run_shell("test-cmd", require_confirmation=True)
        self.assertEqual(code3, 0)
        self.assertEqual(mock_ask_confirmation.call_count, 2)

    @patch("nova.core.executor.CommandExecutor.run_shell")
    def test_system_action_suspend_error_message(self, mock_run_shell):
        mock_run_shell.return_value = (1, "", "Failed to execute: Call to Suspend failed: Access denied")
        from nova.actions.system import SystemAction
        action = SystemAction()
        result = action.execute({"operation": "suspend"})
        self.assertIn("Access Denied error occurs because", result)
        self.assertIn("security.polkit.extraConfig", result)
        self.assertEqual(mock_run_shell.call_count, 2)
        self.assertEqual(mock_run_shell.call_args_list[0][0][0], ["systemctl", "suspend", "-i"])
        self.assertEqual(mock_run_shell.call_args_list[1][0][0], ["sudo", "-n", "systemctl", "suspend", "-i"])

    @patch("nova.core.executor.CommandExecutor.run_shell")
    def test_system_action_suspend_sudo_fallback_success(self, mock_run_shell):
        mock_run_shell.side_effect = [
            (1, "", "Failed to execute: Call to Suspend failed: Access denied"),
            (0, "Success", "")
        ]
        from nova.actions.system import SystemAction
        action = SystemAction()
        result = action.execute({"operation": "suspend"})
        self.assertIn("initiated successfully (via passwordless sudo)", result)
        self.assertEqual(mock_run_shell.call_count, 2)

    @patch("nova.core.executor.CommandExecutor.run_shell")
    def test_system_action_suspend_password_error_message(self, mock_run_shell):
        mock_run_shell.return_value = (1, "", "sudo: a password is required")
        from nova.actions.system import SystemAction
        action = SystemAction()
        result = action.execute({"operation": "suspend"})
        self.assertIn("Access Denied error occurs because", result)
        self.assertIn("security.polkit.extraConfig", result)
        self.assertEqual(mock_run_shell.call_count, 2)

    @patch("sys.stdin.isatty")
    @patch("threading.current_thread")
    def test_ask_confirmation_remote_auto_approve(self, mock_current_thread, mock_isatty):
        mock_isatty.return_value = False
        
        # Test 1: Telegram thread name
        mock_thread = MagicMock()
        mock_thread.name = "telegram_polling_thread"
        mock_current_thread.return_value = mock_thread
        
        from nova.utils import ask_confirmation
        self.assertTrue(ask_confirmation("Test message"))
        
        # Test 2: Non-telegram thread, not autonomous
        mock_thread.name = "some_other_thread"
        from nova.core.state import StateManager
        StateManager.set_autonomous_mode(False)
        self.assertFalse(ask_confirmation("Test message"))
        
        # Test 3: Non-telegram thread, autonomous
        StateManager.set_autonomous_mode(True)
        self.assertTrue(ask_confirmation("Test message"))
        StateManager.set_autonomous_mode(False) # Reset

if __name__ == "__main__":
    unittest.main()
