(function (root) {
  const downloads = {
    android: {
      label: "ANDROID",
      button: "DOWNLOAD FOR ANDROID (.APK)",
      href: "https://github.com/Gr33nOps/sonkip/releases/download/v2.7.0/Sonkip-2.7.0.apk",
      commandLabel: "",
      command: "",
    },
    windows: {
      label: "WINDOWS",
      button: "DOWNLOAD FOR WINDOWS (.ZIP)",
      href: "https://github.com/Gr33nOps/sonkip/archive/refs/heads/main.zip",
      commandLabel: "WINDOWS POWERSHELL · ONE-COMMAND SETUP",
      command:
        "irm https://raw.githubusercontent.com/Gr33nOps/sonkip/main/install.ps1 | iex",
    },
    macos: {
      label: "MACOS",
      button: "DOWNLOAD FOR MAC (.ZIP)",
      href: "https://github.com/Gr33nOps/sonkip/archive/refs/heads/main.zip",
      commandLabel: "MACOS TERMINAL · ONE-COMMAND SETUP",
      command:
        "curl -fsSL https://raw.githubusercontent.com/Gr33nOps/sonkip/main/install.sh | bash",
    },
    linux: {
      label: "LINUX",
      button: "DOWNLOAD FOR LINUX (.TAR.GZ)",
      href: "https://github.com/Gr33nOps/sonkip/archive/refs/heads/main.tar.gz",
      commandLabel: "LINUX TERMINAL · ONE-COMMAND SETUP",
      command:
        "curl -fsSL https://raw.githubusercontent.com/Gr33nOps/sonkip/main/install.sh | bash",
    },
    unknown: {
      label: "YOUR DEVICE",
      button: "DOWNLOAD SONKIP (.ZIP)",
      href: "https://github.com/Gr33nOps/sonkip/archive/refs/heads/main.zip",
      commandLabel: "",
      command: "",
    },
  };

  function detectPlatform(info) {
    const source = [
      info && info.userAgentData && info.userAgentData.platform,
      info && info.platform,
      info && info.userAgent,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    if (source.includes("android")) return "android";
    if (source.includes("windows") || source.includes("win32"))
      return "windows";
    if (
      source.includes("macintosh") ||
      source.includes("macintel") ||
      source.includes("mac os")
    )
      return "macos";
    if (source.includes("linux") || source.includes("x11")) return "linux";
    return "unknown";
  }

  function getPlatformDownload(platform) {
    return downloads[platform] || downloads.unknown;
  }

  function isLocalAppHost(hostname) {
    const host = String(hostname || "")
      .trim()
      .toLowerCase()
      .replace(/^\[(.*)\]$/, "$1");
    return host === "localhost" || host === "127.0.0.1" || host === "::1";
  }

  const api = { detectPlatform, getPlatformDownload, isLocalAppHost };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.SonkipPlatform = api;
})(typeof window !== "undefined" ? window : globalThis);
