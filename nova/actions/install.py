from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.packages import NixPackageManager
from nova.executor import CommandExecutor
from nova.utils import ask_confirmation, print_info, print_warning, COLOR_BOLD, COLOR_CYAN, COLOR_RESET

class InstallPackageAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "install_package"

    def execute(self, params: Dict[str, Any]) -> str:
        package = params.get("package", "").strip()
        if not package:
            return "Error: No package name provided to install."

        # Check if already installed
        installed = NixPackageManager.get_installed_packages()
        if package in installed:
            print_info(f"Package '{package}' is already in the nix profile.")
            if not ask_confirmation("Do you want to reinstall it?"):
                return f"Skipped installation of '{package}' (already installed)."

        # Search for matches
        print_info(f"Searching nixpkgs for package candidates matching '{package}'...")
        results = NixPackageManager.search_packages(package)

        if not results:
            return f"Error: No package found matching '{package}'."

        # Find exact matches (either exact name or pname matches input package name)
        exact_matches = [p for p in results if p["name"] == package or p["pname"] == package]
        
        target_package = ""
        if len(exact_matches) == 1:
            target_package = exact_matches[0]["name"]
            print_info(f"Found exact match: {target_package} ({exact_matches[0]['version']})")
        else:
            # Show interactive menu of candidates
            print_warning(f"Multiple matches found. Select package to install:")
            limit = min(len(results), 10)
            for idx in range(limit):
                pkg = results[idx]
                print(f"  [{idx + 1}] {COLOR_CYAN}{pkg['name']}{COLOR_RESET} ({pkg['version']}) - {pkg['description']}")
            
            print(f"  [c] Cancel")
            
            while True:
                choice = input(f"{COLOR_BOLD}Enter choice (1-{limit} or c): {COLOR_RESET}").strip().lower()
                if choice == "c":
                    return "Installation cancelled."
                try:
                    num = int(choice)
                    if 1 <= num <= limit:
                        target_package = results[num - 1]["name"]
                        break
                except ValueError:
                    pass
                print("Invalid choice, try again.")

        # Ask if system-wide installation is preferred
        if ask_confirmation(f"Do you want to install '{target_package}' system-wide (globally in /etc/nixos/nova-packages.nix)?"):
            import os
            from nova.nixos_editor import (
                CONFIG_PATH,
                NOVA_PACKAGES_PATH,
                get_system_packages,
                add_system_package,
                generate_diff,
                write_configuration,
                ensure_nova_packages_imported,
                ensure_nova_packages_file_exists
            )
            
            # Read configuration.nix
            config_content = ""
            if os.path.exists(CONFIG_PATH):
                try:
                    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                        config_content = f.read()
                except Exception as e:
                    return f"Error reading configuration file: {e}"
            else:
                return f"Configuration file {CONFIG_PATH} not found."

            # Check if already installed in configuration.nix
            if target_package in get_system_packages(config_content):
                return f"Package '{target_package}' is already installed system-wide in {CONFIG_PATH}."

            # Check if already installed in nova-packages.nix
            nova_pkgs_content = ""
            if os.path.exists(NOVA_PACKAGES_PATH):
                try:
                    with open(NOVA_PACKAGES_PATH, "r", encoding="utf-8") as f:
                        nova_pkgs_content = f.read()
                    if target_package in get_system_packages(nova_pkgs_content):
                        return f"Package '{target_package}' is already installed system-wide in {NOVA_PACKAGES_PATH}."
                except Exception:
                    pass

            # 1. Ensure nova-packages.nix is imported in configuration.nix
            new_config, modified = ensure_nova_packages_imported(config_content)
            if modified:
                diff_str = generate_diff(config_content, new_config)
                print(f"\n{COLOR_CYAN}Proposed changes to import nova-packages.nix in {CONFIG_PATH}:{COLOR_RESET}\n")
                print(diff_str)
                print("=" * 60)
                if not ask_confirmation(f"STRICT CONFIRMATION: Import ./nova-packages.nix in {CONFIG_PATH}?"):
                    return "Installation aborted by user (imports not updated)."
                if not write_configuration(new_config):
                    return "Failed to update configuration imports."
                # Keep local config content variable up-to-date
                config_content = new_config

            # 2. Ensure nova-packages.nix file exists
            if not ensure_nova_packages_file_exists():
                return f"Failed to initialize packages file at {NOVA_PACKAGES_PATH}."

            # 3. Read current nova-packages.nix content
            try:
                with open(NOVA_PACKAGES_PATH, "r", encoding="utf-8") as f:
                    nova_pkgs_content = f.read()
            except Exception as e:
                return f"Error reading packages file: {e}"

            # Add package to nova-packages.nix
            new_nova_pkgs, ok = add_system_package(nova_pkgs_content, target_package)
            if not ok:
                return f"Failed to modify system packages file for package: {target_package}"

            # Show diff of nova-packages.nix
            diff_str = generate_diff(nova_pkgs_content, new_nova_pkgs, NOVA_PACKAGES_PATH)
            print(f"\n{COLOR_CYAN}Proposed Changes to {NOVA_PACKAGES_PATH}:{COLOR_RESET}\n")
            print(diff_str)
            print("=" * 60)

            # Request strict confirmation to write nova-packages.nix
            if not ask_confirmation(f"STRICT CONFIRMATION: Apply these changes to {NOVA_PACKAGES_PATH}?"):
                return "Installation aborted by user (packages not written)."

            # Write changes to nova-packages.nix
            if not write_configuration(new_nova_pkgs, NOVA_PACKAGES_PATH):
                return "Failed to write packages configuration changes."

            # Rebuild confirmation
            if ask_confirmation("Do you want to run 'sudo nixos-rebuild switch' to apply the changes now?"):
                print_info("Rebuilding NixOS system...")
                exit_code = CommandExecutor.run_interactive(["sudo", "nixos-rebuild", "switch"])
                if exit_code == 0:
                    return f"Successfully installed system package: {target_package} and rebuilt system."
                else:
                    return f"System packages updated in config, but 'nixos-rebuild switch' failed with exit code: {exit_code}"
            else:
                return f"Successfully added package '{target_package}' to packages configuration. Please run 'sudo nixos-rebuild switch' manually to apply."

        # Confirm before execution (standard user profile installation fallback)
        confirm_message = f"Install Nix package 'nixpkgs#{target_package}' using nix profile"
        
        # Run command with safety prompt
        exit_code, stdout, stderr = CommandExecutor.run_shell(
            ["nix", "profile", "install", f"nixpkgs#{target_package}"],
            require_confirmation=True,
            confirm_message=confirm_message
        )

        if exit_code == 0:
            return f"Successfully installed package: {target_package}"
        elif exit_code == -1:
            return "Installation aborted by user."
        else:
            return f"Failed to install package: {target_package}. Error: {stderr}"
