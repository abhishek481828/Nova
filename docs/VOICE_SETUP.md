# Nova Voice Interface Setup Guide

This document describes how to configure and install the required Python packages and native system libraries to enable Voice Mode support in Nova.

## Python Packages Installation

Activate your virtual environment and install the required voice-related dependencies:

```bash
source .venv/bin/activate
python -m pip install -r requirements-voice.txt
```

## Native NixOS Dependencies

Because Nova runs on NixOS, native system packages required for audio recording, media handling, and waveform manipulation must be supplied by the Nix environment. The required native dependencies are:

- `portaudio` (for audio input/output via `sounddevice`)
- `libsndfile` (for reading and writing audio files via `soundfile`)
- `ffmpeg` (for media processing / format conversion)

### Setup via `shell.nix`

If you are using a development shell (`shell.nix`), you can add these native libraries to your environment. Here is a sample `shell.nix` that configures both Python and the necessary system library paths:

```nix
{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    python3
    portaudio
    libsndfile
    ffmpeg
    mpg123 # Optional, used for playing text-to-speech audio
  ];

  shellHook = ''
    # Ensure system shared libraries can be loaded by Python packages (like sounddevice and soundfile)
    export LD_LIBRARY_PATH="${pkgs.portaudio}/lib:${pkgs.libsndfile}/lib:${pkgs.ffmpeg}/lib:$LD_LIBRARY_PATH"
    
    # Auto-activate your virtual environment if it exists
    if [ -d .venv ]; then
      source .venv/bin/activate
    fi
  '';
}
```

To enter this environment, simply run:

```bash
nix-shell
```

### Setup via `flake.nix`

If you are using Nix Flakes, you can define a development environment like this:

```nix
{
  description = "Nova Development Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = with pkgs; [
          python3
          portaudio
          libsndfile
          ffmpeg
          mpg123
        ];

        shellHook = ''
          export LD_LIBRARY_PATH="${pkgs.portaudio}/lib:${pkgs.libsndfile}/lib:${pkgs.ffmpeg}/lib:$LD_LIBRARY_PATH"
          if [ -d .venv ]; then
            source .venv/bin/activate
          fi
        '';
      };
    };
}
```

To enter the flake environment, run:

```bash
nix develop
```
