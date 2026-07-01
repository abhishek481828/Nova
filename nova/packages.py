import json
from typing import Dict, List, Tuple
from nova.core.executor import CommandExecutor
from nova.logger import log_error

class NixPackageManager:
    @staticmethod
    def search_packages(query: str) -> List[Dict[str, str]]:
        """
        Runs 'nix search nixpkgs QUERY --json 2>/dev/null' and returns a list of matching packages.
        Each package dict has: 'name', 'pname', 'version', 'description'.
        """
        if not query:
            return []

        # Run command synchronously
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
                # Key is typically legacyPackages.x86_64-linux.package_name
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
        Runs 'nix profile list' and parses the output to get names of installed packages.
        """
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
