{ pkgs, ... }:

{
  home.username      = "nixos";
  home.homeDirectory = "/home/nixos";
  home.stateVersion  = "25.05";

  programs.home-manager.enable = true;

  home.packages = with pkgs; [
    onlyoffice-desktopeditors
    google-chrome
    vlc
    cloudflare-warp
    antigravity-ide

    # Clipboard history (text + images) — GNOME Shell extension.
    gnomeExtensions.pano
  ];

  # systemd user service for Nova AI Assistant
  systemd.user.services.nova = {
    Unit = {
      Description = "Nova AI Desktop Assistant Daemon";
      After = [ "graphical-session.target" ];
      PartOf = [ "graphical-session.target" ];
    };
    Service = {
      Type = "simple";
      ExecStart = "/run/current-system/sw/bin/nix-shell /home/nixos/Projects/Nova/shell.nix --run \"/home/nixos/Projects/Nova/.venv/bin/python -m nova.main --daemon\"";
      WorkingDirectory = "/home/nixos/Projects/Nova";
      EnvironmentFile = [ "/home/nixos/Projects/Nova/.env" ];
      Environment = [
        "PYTHONUNBUFFERED=1"
        "PYTHONPATH=/home/nixos/Projects/Nova"
      ];
      Restart = "on-failure";
      RestartSec = "5s";
    };
    Install = {
      WantedBy = [ "graphical-session.target" ];
    };
  };

  # .desktop application entry for Nova
  xdg.desktopEntries.nova = {
    name = "Nova";
    genericName = "AI Desktop Assistant";
    comment = "Voice and Text Desktop Assistant";
    exec = "/home/nixos/.local/bin/nova";
    icon = "/home/nixos/Projects/Nova/nova.png";
    terminal = false;
    categories = [ "Utility" ];
    startupNotify = true;
  };

  # .desktop application entry for Nova Dashboard
  xdg.desktopEntries.nova-dashboard = {
    name = "Nova Dashboard";
    genericName = "Mission Control Dashboard";
    comment = "Open the Nova Mission Control Dashboard";
    exec = "xdg-open http://127.0.0.1:11436";
    icon = "/home/nixos/Projects/Nova/nova.png";
    terminal = false;
    categories = [ "Utility" ];
    startupNotify = true;
  };

  # GNOME keyboard shortcuts
  dconf.settings = {
    "org/gnome/settings-daemon/plugins/media-keys" = {
      custom-keybindings = [
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/"
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom1/"
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom2/"
        "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom3/"
      ];
    };
    "org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0" = {
      name = "suspend";
      binding = "<Shift><Control>Delete";
      command = "systemctl suspend";
    };
    "org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom1" = {
      name = "WARP Toggle";
      binding = "<Shift><Super>w";
      command = "/home/nixos/.local/bin/warp-toggle.sh";
    };
    "org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom2" = {
      name = "Nova Voice Assistant";
      binding = "<Control><Alt>space";
      command = "/home/nixos/.local/bin/nova";
    };
    "org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom3" = {
      name = "Nova Dashboard";
      binding = "<Control><Alt>d";
      command = "xdg-open http://127.0.0.1:11436";
    };
  };
}
