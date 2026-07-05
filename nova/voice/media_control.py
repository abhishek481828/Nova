"""
Media pause/resume and volume ducking utility using playerctl (MPRIS).

Behaviour:
  - duck_all_media()   → lowers all playing media to DUCK_VOLUME (20%)
  - unduck_players()   → restores saved volume per player
  - pause_all_media()  → pauses all playing media (used after wake detected)
  - resume_players()   → resumes previously paused players
"""
import subprocess
import shutil
from nova.logger import logger

_PLAYERCTL = shutil.which("playerctl")
DUCK_VOLUME = 0.15   # 15% during wake-word listening


def _run(args: list[str]) -> str:
    """Run playerctl command, return stdout or empty string."""
    if not _PLAYERCTL:
        return ""
    try:
        result = subprocess.run(
            [_PLAYERCTL] + args,
            capture_output=True, text=True, timeout=2
        )
        return result.stdout.strip()
    except Exception as e:
        logger.debug(f"playerctl error: {e}")
        return ""


def get_playing_players() -> list[str]:
    """Return list of players that are currently Playing."""
    all_players = _run(["--list-all"]).splitlines()
    playing = []
    for player in all_players:
        player = player.strip()
        if not player:
            continue
        status = _run(["--player", player, "status"])
        if status == "Playing":
            playing.append(player)
    return playing


def duck_all_media() -> dict[str, float]:
    """
    Lower volume of all currently playing media to DUCK_VOLUME.
    Returns {player: original_volume} dict so we can restore later.
    """
    if not _PLAYERCTL:
        return {}
    saved = {}
    for player in get_playing_players():
        try:
            vol_str = _run(["--player", player, "volume"])
            orig_vol = float(vol_str) if vol_str else 1.0
        except (ValueError, TypeError):
            orig_vol = 1.0
        saved[player] = orig_vol
        _run(["--player", player, "volume", str(DUCK_VOLUME)])
        logger.debug(f"Ducked {player}: {orig_vol:.2f} → {DUCK_VOLUME}")
    return saved


def unduck_players(saved_volumes: dict[str, float]) -> None:
    """Restore volumes saved by duck_all_media()."""
    for player, vol in saved_volumes.items():
        _run(["--player", player, "volume", str(vol)])
        logger.debug(f"Unducked {player}: restored to {vol:.2f}")


def pause_all_media() -> list[str]:
    """
    Pause all currently playing MPRIS media players.
    Returns the list of players that were paused (so we can resume them later).
    """
    paused = get_playing_players()
    for player in paused:
        _run(["--player", player, "pause"])
        logger.debug(f"Media paused: {player}")
    return paused


def resume_players(players: list[str]) -> None:
    """Resume a specific list of players that were previously paused."""
    for player in players:
        _run(["--player", player, "play"])
        logger.debug(f"Media resumed: {player}")
