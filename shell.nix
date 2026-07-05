{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    python3
    portaudio
    libsndfile
    ffmpeg
    mpg123
    stdenv.cc.cc.lib
    rnnoise
    speexdsp
    python3Packages.webrtcvad
    python3Packages.mypy
    python3Packages.flake8
    zlib
    nodejs
    scrot
    playerctl
  ];

  shellHook = ''
    # Add native libraries to linker path so python packages from .venv can find them
    export LD_LIBRARY_PATH="${pkgs.portaudio}/lib:${pkgs.libsndfile}/lib:${pkgs.ffmpeg}/lib:${pkgs.rnnoise}/lib:${pkgs.speexdsp}/lib:${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
    export PLAYWRIGHT_NODEJS_PATH="${pkgs.nodejs}/bin/node"
  '';
}
