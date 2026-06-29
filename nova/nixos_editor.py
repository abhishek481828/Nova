import re
import os
import difflib
import tempfile
from typing import List, Tuple
from nova.executor import CommandExecutor
from nova.utils import print_info, print_warning

CONFIG_PATH = "/etc/nixos/configuration.nix"
NOVA_PACKAGES_PATH = "/etc/nixos/nova-packages.nix"

def get_system_packages(content: str) -> List[str]:
    match = re.search(r'environment\.systemPackages\s*=\s*(?:with\s+pkgs\s*;\s*)?\[(.*?)\]\s*;', content, re.DOTALL)
    if not match:
        return []
    packages_text = match.group(1)
    packages = []
    for line in packages_text.splitlines():
        line_clean = line.split('#')[0].strip()
        if line_clean:
            packages.extend(line_clean.split())
    return packages

def remove_system_package(content: str, package_name: str) -> Tuple[str, bool]:
    match = re.search(r'(environment\.systemPackages\s*=\s*(?:with\s+pkgs\s*;\s*)?\[)(.*?)(\]\s*;)', content, re.DOTALL)
    if not match:
        return content, False
    
    header, packages_text, footer = match.groups()
    new_lines = []
    removed = False
    
    lines = packages_text.split('\n')
    for line in lines:
        line_clean = line.split('#')[0].strip()
        tokens = line_clean.split()
        if package_name in tokens:
            tokens.remove(package_name)
            removed = True
            if tokens:
                comment_part = line.split('#', 1)[1] if '#' in line else ""
                new_line = "  " + " ".join(tokens) + (f" # {comment_part.strip()}" if comment_part else "")
                new_lines.append(new_line)
        else:
            new_lines.append(line)
            
    if removed:
        new_block = header + "\n".join(new_lines) + footer
        new_content = content.replace(match.group(0), new_block)
        return new_content, True
    return content, False

def add_system_package(content: str, package_name: str) -> Tuple[str, bool]:
    match = re.search(r'(environment\.systemPackages\s*=\s*(?:with\s+pkgs\s*;\s*)?\[)(.*?)(\]\s*;)', content, re.DOTALL)
    if not match:
        return content, False
    
    header, packages_text, footer = match.groups()
    
    current_packages = get_system_packages(content)
    if package_name in current_packages:
        return content, False
        
    lines = packages_text.splitlines()
    closing_indent = ""
    if lines:
        if not lines[-1].strip():
            closing_indent = lines[-1]
            lines = lines[:-1]
            
    pkg_indent = "  "
    for line in reversed(lines):
        if line.strip():
            pkg_indent = line[:len(line) - len(line.lstrip())]
            break
            
    lines.append(f"{pkg_indent}{package_name}")
    new_packages_text = "\n".join(lines) + "\n" + closing_indent
    
    new_block = header + new_packages_text + footer
    new_content = content.replace(match.group(0), new_block)
    return new_content, True

def generate_diff(old_content: str, new_content: str, filename: str = CONFIG_PATH) -> str:
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=filename + " (current)",
        tofile=filename + " (proposed)"
    )
    return "".join(diff)

def write_configuration(new_content: str, dest_path: str = CONFIG_PATH) -> bool:
    """Writes the new content to dest_path safely using sudo cp."""
    # Write to a temporary file first
    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
        tmp.write(new_content)
        tmp_path = tmp.name
        
    try:
        # Copy temporary file to system destination with sudo
        exit_code, stdout, stderr = CommandExecutor.run_shell(
            ["sudo", "cp", tmp_path, dest_path],
            require_confirmation=False
        )
        if exit_code == 0:
            # Ensure permissions are standard 644 (world readable) so the user process can read it
            CommandExecutor.run_shell(
                ["sudo", "chmod", "644", dest_path],
                require_confirmation=False
            )
            print_info(f"Successfully wrote changes to {dest_path}")
            return True
        else:
            print_warning(f"Failed to copy config file. Error: {stderr}")
            return False
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def ensure_nova_packages_imported(config_content: str) -> Tuple[str, bool]:
    """Ensures `./nova-packages.nix` is in the imports list of configuration.nix."""
    match = re.search(r'(imports\s*=\s*\[)(.*?)(\]\s*;)', config_content, re.DOTALL)
    if not match:
        return config_content, False
        
    header, imports_text, footer = match.groups()
    
    # Check if already imported
    imported_list = []
    for line in imports_text.splitlines():
        line_clean = line.split('#')[0].strip()
        if line_clean:
            imported_list.extend(line_clean.split())
            
    has_import = False
    for imp in imported_list:
        if "nova-packages.nix" in imp:
            has_import = True
            break
            
    if has_import:
        return config_content, False
        
    lines = imports_text.split('\n')
    closing_indent = ""
    if lines:
        if not lines[-1].strip():
            closing_indent = lines[-1]
            lines = lines[:-1]
            
    pkg_indent = "  "
    for line in reversed(lines):
        if line.strip():
            pkg_indent = line[:len(line) - len(line.lstrip())]
            break
            
    lines.append(f"{pkg_indent}./nova-packages.nix")
    new_imports_text = "\n".join(lines) + "\n" + closing_indent
    
    new_block = header + new_imports_text + footer
    new_config = config_content.replace(match.group(0), new_block)
    return new_config, True

def ensure_nova_packages_file_exists() -> bool:
    """Checks if NOVA_PACKAGES_PATH exists, if not creates it with standard template."""
    if os.path.exists(NOVA_PACKAGES_PATH):
        return True
        
    template = """{ pkgs, ... }:

{
  environment.systemPackages = with pkgs; [
  ];
}
"""
    return write_configuration(template, NOVA_PACKAGES_PATH)
