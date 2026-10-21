import os
import re
import json
import shutil
from typing import Dict, List, Tuple
from nova.core.executor import CommandExecutor
from nova.logger import log_error

class PackageManager:
    @staticmethod
    def search_packages(query: str) -> List[Dict[str, str]]:
        """
        Searches for packages via winget on Windows or nix search on Linux.
        Each package dict has: 'name', 'pname', 'version', 'description'.
        """
        if not query:
            return []

        if os.name == "nt":
            if not shutil.which("winget"):
                return []
            exit_code, stdout, stderr = CommandExecutor.run_shell(
                ["winget", "search", query, "--accept-source-agreements"],
                require_confirmation=False
            )
            if exit_code != 0:
                log_error(f"winget search failed for query: {query}. Stderr: {stderr}")
                return []

            packages = []
            lines = stdout.splitlines()
            start_parsing = False
            for line in lines:
                if line.startswith("---"):
                    start_parsing = True
                    continue
                if not start_parsing or not line.strip():
                    continue
                parts = [p.strip() for p in re.split(r'\s{2,}', line.strip()) if p.strip()]
                if len(parts) >= 2:
                    name = parts[0]
                    pkg_id = parts[1]
                    version = parts[2] if len(parts) > 2 else ""
                    packages.append({
                        "name": pkg_id,
                        "pname": name,
                        "version": version,
                        "description": f"Windows package ({name})"
                    })
            return packages

        # Run command synchronously on Linux/NixOS
        if not shutil.which("nix"):
            return []
        exit_code, stdout, stderr = CommandExecutor.run_shell(
            ["nix", "search", "nixpkgs", query, "--json"],
            require_confirmation=False
        )

        if exit_code != 0:
            log_error(f"Nix search failed for query: {query}. Stderr: {stderr}")
            return []

        try:
            results = json.loads(stdout)
            packages = []
            for key, val in results.items():
                parts = key.split(".")
                if len(parts) > 2 and parts[0] == "legacyPackages":
                    name = ".".join(parts[2:])
                else:
                    name = key

                packages.append({
                    "name": name,
                    "pname": val.get("pname", ""),
                    "version": val.get("version", ""),
                    "description": val.get("description", "")
                })
            return packages
        except Exception as e:
            log_error("Failed to parse nix search json output", e)
            return []

    @staticmethod
    def get_installed_packages() -> List[str]:
        """
        Runs 'winget list' on Windows or 'nix profile list' on Linux to get names of installed packages.
        """
        if os.name == "nt":
            if not shutil.which("winget"):
                return []
            exit_code, stdout, stderr = CommandExecutor.run_shell(
                ["winget", "list", "--accept-source-agreements"],
                require_confirmation=False
            )
            if exit_code != 0:
                return []
            installed = []
            start_parsing = False
            for line in stdout.splitlines():
                if line.startswith("---"):
                    start_parsing = True
                    continue
                if not start_parsing or not line.strip():
                    continue
                parts = [p.strip() for p in re.split(r'\s{2,}', line.strip()) if p.strip()]
                if len(parts) >= 2:
                    installed.append(parts[0])
                    installed.append(parts[1])
            return installed

        if not shutil.which("nix"):
            return []
        exit_code, stdout, stderr = CommandExecutor.run_shell(
            ["nix", "profile", "list"],
            require_confirmation=False
        )

        if exit_code != 0:
            log_error(f"Failed to list nix profile packages. Stderr: {stderr}")
            return []

        installed = []
        for line in stdout.splitlines():
            if line.strip().startswith("Name:"):
                name = line.split(":", 1)[1].strip()
                if name:
                    installed.append(name)
        return installed

NixPackageManager = PackageManager
