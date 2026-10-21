from typing import Set

# Reference set of valid/canonical words within the Nova domain.
VALID_WORDS: Set[str] = {
    # Action verbs and nouns
    "open", "close", "install", "remove", "search", "update", "run", "git", "file", "browser", "system", "adb", "diagnose", "check",
    "package", "app", "apps", "application", "applications", "project", "problem", "mirroring", "device", "phonenotify", "notify",
    # Verb variations to prevent incorrect spell-corrections
    "devices", "connected", "connecting", "connection", "connections", "installed", "installing", "removed", "removing", "searching",
    "updated", "updating", "running", "checking", "mirrored", "opening", "opened", "closing", "closed",
    # Operations & Targets
    "devices", "connect", "disconnect", "setup", "mirror", "shutdown", "suspend", "push", "pull", "commit", "status", "create", "delete", "list", "read",
    # Common applications & system components
    "chrome", "chromium", "firefox", "vscode", "code", "terminal", "phone", "scrcpy", "tailscale", "vlc", "python", "explorer", "nautilus",
    # Linux system, commands, and service manager terms
    "systemctl", "journalctl", "systemd", "service", "services", "daemon",
    "stop", "start", "enable", "disable", "restart", "reload", "active", "inactive",
    # Network & VPN terms
    "warp", "cloudflare", "warp-cli", "vpn",
    # Package & OS environment terms
    "winget", "powershell", "cmd", "windows", "notepad", "calc", "taskmgr", "packages", "profile",
    # Common shell commands and keywords
    "config", "shell", "bash", "terminal",
    # Common conversational greetings & help terms
    "hello", "hi", "hey", "greetings", "help", "please", "yes", "no", "fine", "everything", "things", "working", "extension",
    # System resources, CPU, and memory keywords
    "load", "resources", "cpu", "temp", "temperatures", "ram", "memory", "storage", "capacity", "processor",
    # Common data keywords
    "pandas", "numpy", "ports", "tcp", "udp", "packages", "python3",
    # Volume control keywords
    "volume", "mute", "unmute", "audio", "sound",
    # Brightness control keywords
    "brightness", "dim", "brighter", "screen", "light",
    # Desktop and Wifi control keywords
    "wifi", "lock", "media", "song", "play", "pause", "playpause", "next", "prev", "previous", "stop", "skip", "neofetch", "specs", "dashboard", "ssid", "hotspot", "nightlight", "night-light",
    # Browser automation and YouTube keywords
    "chrome", "chromium", "browser", "tab", "url", "website", "webpage", "youtube", "wikipedia", "search", "navigate", "open", "click", "type", "fill", "form", "input", "button", "submit", "select", "chatgpt", "meaning",
    # Music genre and mood terms (prevent hip->hi, lofi->log etc.)
    "hip", "hop", "lofi", "jazz", "rock", "pop", "classical", "beats", "chill", "remix", "live", "music", "playlist", "album", "track", "video",
    # External APIs and domains
    "openai", "weather", "crypto", "news", "coingecko", "tavily", "bitcoin", "ethereum", "solana", "ocr", "ipinfo", "ip_info", "tmdb", "fmp",
    # Currency / rates terms
    "rate", "rates", "currency", "exchange", "convert", "conversion", "value", "dollar", "dollars", "euro", "euros", "finance", "stock", "stocks", "aapl", "tsla", "msft",
    # Common conversational, query, and pronouns/articles
    "now", "cover", "can", "you", "tell", "about", "today", "all", "the", "apple", "market", "bbc",
    "show", "how", "what", "where", "who", "why", "when", "more", "look", "give", "get", "say", "me",
    "him", "her", "them", "us", "this", "that", "these", "those", "here", "there", "then", "soon",
    "day", "night", "time", "week", "month", "year", "tomorrow", "yesterday", "okay", "are", "listening",
    "perfectly", "good", "morning", "afternoon", "evening", "doing", "well",
    # Name
    "nova"
}
