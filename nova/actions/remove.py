from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.packages import NixPackageManager
from nova.core.executor import CommandExecutor
from nova.utils import ask_confirmation, print_info, print_warning, COLOR_BOLD, COLOR_CYAN, COLOR_RESET

class RemovePackageAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "remove_package"

    def execute(self, params: Dict[str, Any]) -> str:
        package = params.get("package", "").strip()
        if not package:
            return "Error: No package name provided to remove."

        # Check system-wide packages in configuration.nix and nova-packages.nix
        import os
        from nova.nixos_editor import (
            CONFIG_PATH,
            NOVA_PACKAGES_PATH,
            get_system_packages,
            remove_system_package,
            generate_diff,
            write_configuration
        )
        
        in_config = False
        config_content = ""
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    config_content = f.read()
                if package in get_system_packages(config_content):
                    in_config = True
            except Exception:
                pass

        in_nova_pkgs = False
        nova_pkgs_content = ""
        if os.path.exists(NOVA_PACKAGES_PATH):
            try:
                with open(NOVA_PACKAGES_PATH, "r", encoding="utf-8") as f:
                    nova_pkgs_content = f.read()
                if package in get_system_packages(nova_pkgs_content):
                    in_nova_pkgs = True
            except Exception:
                pass

        if in_nova_pkgs:
            print_warning(f"Package '{package}' is installed system-wide in {NOVA_PACKAGES_PATH}.")
            if ask_confirmation(f"Do you want to remove it from the system-wide packages configuration?"):
                # Remove in-memory
                new_content, ok = remove_system_package(nova_pkgs_content, package)
                if not ok:
                    return f"Failed to modify packages configuration for package: {package}"
                
                # Show unified diff
                diff_str = generate_diff(nova_pkgs_content, new_content, NOVA_PACKAGES_PATH)
                print(f"\n{COLOR_CYAN}Proposed Changes to {NOVA_PACKAGES_PATH}:{COLOR_RESET}\n")
                print(diff_str)
                print("=" * 60)
                
                # Request strict confirmation to write
                if not ask_confirmation(f"STRICT CONFIRMATION: Apply these changes to {NOVA_PACKAGES_PATH}?"):
                    return "Removal aborted by user (changes not written)."
                
                # Write changes
                if not write_configuration(new_content, NOVA_PACKAGES_PATH):
                    return "Failed to write packages configuration changes."
                    
                # Rebuild confirmation
                if ask_confirmation("Do you want to run 'sudo nixos-rebuild switch' to apply the changes now?"):
                    print_info("Rebuilding NixOS system...")
                    exit_code = CommandExecutor.run_interactive(["sudo", "nixos-rebuild", "switch"])
                    if exit_code == 0:
                        return f"Successfully removed system package: {package} and rebuilt system."
                    else:
                        return f"System packages updated in config, but 'nixos-rebuild switch' failed with exit code: {exit_code}"
                else:
                    return f"Successfully removed package '{package}' from packages configuration. Please run 'sudo nixos-rebuild switch' manually to apply."
            else:
                print_info(f"Skipping system-wide removal from {NOVA_PACKAGES_PATH}. Checking user profile...")

        elif in_config:
            print_warning(f"Package '{package}' is installed system-wide in {CONFIG_PATH}.")
            if ask_confirmation(f"Do you want to remove it from the system-wide configuration?"):
                # Remove in-memory
                new_content, ok = remove_system_package(config_content, package)
                if not ok:
                    return f"Failed to modify system configuration for package: {package}"
                
                # Show unified diff
                diff_str = generate_diff(config_content, new_content, CONFIG_PATH)
                print(f"\n{COLOR_CYAN}Proposed Changes to {CONFIG_PATH}:{COLOR_RESET}\n")
                print(diff_str)
                print("=" * 60)
                
                # Request strict confirmation to write
                if not ask_confirmation(f"STRICT CONFIRMATION: Apply these changes to {CONFIG_PATH}?"):
                    return "Removal aborted by user (changes not written)."
                
                # Write changes
                if not write_configuration(new_content, CONFIG_PATH):
                    return "Failed to write configuration changes."
                    
                # Rebuild confirmation
                if ask_confirmation("Do you want to run 'sudo nixos-rebuild switch' to apply the changes now?"):
                    print_info("Rebuilding NixOS system...")
                    exit_code = CommandExecutor.run_interactive(["sudo", "nixos-rebuild", "switch"])
                    if exit_code == 0:
                        return f"Successfully removed system package: {package} and rebuilt system."
                    else:
                        return f"System packages updated in config, but 'nixos-rebuild switch' failed with exit code: {exit_code}"
                else:
                    return f"Successfully removed package '{package}' from configuration. Please run 'sudo nixos-rebuild switch' manually to apply."
            else:
                print_info(f"Skipping system-wide removal from {CONFIG_PATH}. Checking user profile...")

        # Fetch currently installed packages
        installed = NixPackageManager.get_installed_packages()
        if not installed:
            return "No packages currently installed in user profile."

        # Find matching installed packages (case insensitive substring match)
        matches = [name for name in installed if package.lower() in name.lower()]
        
        target_package = ""
        if len(matches) == 1:
            target_package = matches[0]
            print_info(f"Found matching installed package: {target_package}")
        elif len(matches) > 1:
            print_warning(f"Multiple installed packages match '{package}'. Select one to remove:")
            for idx, name in enumerate(matches):
                print(f"  [{idx + 1}] {COLOR_CYAN}{name}{COLOR_RESET}")
            print(f"  [c] Cancel")
            
            while True:
                choice = input(f"{COLOR_BOLD}Enter choice (1-{len(matches)} or c): {COLOR_RESET}").strip().lower()
                if choice == "c":
                    return "Removal cancelled."
                try:
                    num = int(choice)
                    if 1 <= num <= len(matches):
                        target_package = matches[num - 1]
                        break
                except ValueError:
                    pass
                print("Invalid choice, try again.")
        else:
            print_warning(f"Package '{package}' not found in installed packages.")
            if ask_confirmation(f"Do you want to attempt removing the exact name '{package}' anyway?"):
                target_package = package
            else:
                return f"Skipped removal of '{package}'."

        confirm_message = f"Remove Nix package '{target_package}' from user profile"
        
        # Execute nix profile remove with confirmation
        exit_code, stdout, stderr = CommandExecutor.run_shell(
            ["nix", "profile", "remove", target_package],
            require_confirmation=True,
            confirm_message=confirm_message
        )

        if exit_code == 0:
            return f"Successfully removed package: {target_package}"
        elif exit_code == -1:
            return "Removal aborted by user."
        else:
            return f"Failed to remove package: {target_package}. Error: {stderr}"
