#!/usr/bin/env bash
# =============================================================================
# PlaceUp — one-time host bootstrap for Ubuntu / Debian / WSL 2.
#
#     bash scripts/bootstrap-ubuntu.sh
#
# Installs everything the host needs and nothing it doesn't: Docker Engine,
# the Compose v2 plugin, make, git and curl. PostgreSQL, Redis, Java, Node,
# Python, Playwright, Ollama and the models all live inside containers — this
# script deliberately does not install any of them onto your machine.
#
# Safe to re-run. Every step checks first and skips what is already correct.
#
# After this finishes, the application itself is one command:
#
#     make up
# =============================================================================

set -Eeuo pipefail

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C_RESET=$'\033[0m'; C_RED=$'\033[31m'; C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'; C_BLUE=$'\033[36m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
else
  C_RESET=''; C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''; C_BOLD=''; C_DIM=''
fi

step() { printf '\n%s==> %s%s\n' "$C_BLUE$C_BOLD" "$*" "$C_RESET"; }
ok()   { printf '%s  ok%s    %s\n' "$C_GREEN" "$C_RESET" "$*"; }
skip() { printf '%s  skip%s  %s\n' "$C_DIM" "$C_RESET" "$*"; }
warn() { printf '%s  warn%s  %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
die()  { printf '%s  FAIL%s  %s\n' "$C_RED" "$C_RESET" "$*" >&2; exit 1; }

trap 'die "bootstrap failed on line $LINENO — nothing was left half-installed that a re-run will not fix"' ERR

# -----------------------------------------------------------------------------
# 0. Sanity
# -----------------------------------------------------------------------------
step "Checking this machine"

[[ -r /etc/os-release ]] || die "cannot read /etc/os-release — this script targets Ubuntu and Debian."
# shellcheck disable=SC1091
. /etc/os-release

DISTRO_ID="${ID:-unknown}"
DISTRO_LIKE="${ID_LIKE:-}"
CODENAME="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"

case "$DISTRO_ID" in
  ubuntu) REPO_DISTRO=ubuntu ;;
  debian) REPO_DISTRO=debian ;;
  linuxmint|pop|elementary|zorin|neon) REPO_DISTRO=ubuntu ;;
  *)
    if [[ "$DISTRO_LIKE" == *ubuntu* ]]; then REPO_DISTRO=ubuntu
    elif [[ "$DISTRO_LIKE" == *debian* ]]; then REPO_DISTRO=debian
    else die "unsupported distribution '$DISTRO_ID'. Install Docker Engine + Compose v2 manually, then run: make up"
    fi
    ;;
esac
[[ -n "$CODENAME" ]] || die "could not determine the release codename from /etc/os-release."

ok "distribution: ${PRETTY_NAME:-$DISTRO_ID} (using Docker's $REPO_DISTRO/$CODENAME repository)"

if [[ $EUID -eq 0 ]]; then
  warn "running as root. Docker will be installed system-wide, but no user is added to the 'docker' group."
  TARGET_USER="${SUDO_USER:-root}"
  SUDO=""
else
  TARGET_USER="$(id -un)"
  command -v sudo >/dev/null 2>&1 || die "'sudo' is required when not running as root."
  SUDO="sudo"
  printf '%s  This script uses sudo. You may be prompted for your password.%s\n' "$C_DIM" "$C_RESET"
fi

IS_WSL=false
if grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null; then
  IS_WSL=true
  ok "WSL detected — will start Docker with 'service' if systemd is unavailable"
fi

# -----------------------------------------------------------------------------
# 1. Base packages
# -----------------------------------------------------------------------------
step "Installing base packages (git, make, curl, ca-certificates, gnupg)"

export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq ca-certificates curl gnupg git make lsb-release >/dev/null
ok "git $(git --version | awk '{print $3}') · make $(make --version | head -1 | awk '{print $3}') · curl present"

# -----------------------------------------------------------------------------
# 2. Docker Engine + Compose v2
# -----------------------------------------------------------------------------
step "Installing Docker Engine and the Compose v2 plugin"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  skip "Docker $(docker --version | awk '{print $3}' | tr -d ,) with Compose $(docker compose version --short) already installed"
else
  # Distro packages ship an old engine and sometimes no Compose v2 plugin.
  # Remove them so apt does not have to resolve a conflict later.
  for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
    $SUDO apt-get remove -y -qq "$pkg" >/dev/null 2>&1 || true
  done

  $SUDO install -m 0755 -d /etc/apt/keyrings
  $SUDO curl -fsSL "https://download.docker.com/linux/${REPO_DISTRO}/gpg" -o /etc/apt/keyrings/docker.asc
  $SUDO chmod a+r /etc/apt/keyrings/docker.asc

  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${REPO_DISTRO} ${CODENAME} stable" \
    | $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null

  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
                               docker-buildx-plugin docker-compose-plugin >/dev/null

  ok "Docker $(docker --version | awk '{print $3}' | tr -d ,) installed"
  ok "Compose $(docker compose version --short) installed"
fi

# -----------------------------------------------------------------------------
# 3. Start the daemon
# -----------------------------------------------------------------------------
step "Starting the Docker daemon"

start_daemon() {
  if $SUDO docker info >/dev/null 2>&1; then
    ok "daemon already running"
    return 0
  fi
  if command -v systemctl >/dev/null 2>&1 && systemctl list-units >/dev/null 2>&1; then
    if $SUDO systemctl enable --now docker >/dev/null 2>&1; then
      ok "daemon started and enabled at boot (systemd)"
      return 0
    fi
  fi
  if $SUDO service docker start >/dev/null 2>&1; then
    ok "daemon started (sysvinit)"
    return 0
  fi
  return 1
}

if start_daemon; then
  if $IS_WSL && ! (command -v systemctl >/dev/null 2>&1 && systemctl list-units >/dev/null 2>&1); then
    warn "WSL without systemd will not restart Docker automatically on the next session."
    printf '        Enable it once: add the two lines below to /etc/wsl.conf, then run\n'
    printf '        "wsl --shutdown" in Windows PowerShell.\n'
    printf '          [boot]\n          systemd=true\n'
  fi
else
  printf '\n'
  warn "could not start the Docker daemon automatically."
  cat <<'EOS'
        This is normal inside an unprivileged container, and unusual on a real
        Ubuntu host. Try, in order:

          sudo systemctl status docker        # what does it say?
          sudo systemctl enable --now docker
          sudo journalctl -u docker -n 50 --no-pager

        On WSL 2 without systemd:
          sudo service docker start

        Docker itself is installed correctly — only the daemon is not up. Once
        it starts, run this script again (it is safe to re-run) or go straight
        to: make doctor
EOS
  exit 1
fi

# -----------------------------------------------------------------------------
# 4. Rootless access for your user
# -----------------------------------------------------------------------------
step "Granting '$TARGET_USER' access to Docker without sudo"

NEEDS_RELOGIN=false
if [[ "$TARGET_USER" == "root" ]]; then
  skip "running as root — no group change needed"
elif id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx docker; then
  if docker info >/dev/null 2>&1; then
    ok "already in the 'docker' group and it is active in this shell"
  else
    ok "already in the 'docker' group, but this shell predates it"
    NEEDS_RELOGIN=true
  fi
else
  $SUDO groupadd -f docker
  $SUDO usermod -aG docker "$TARGET_USER"
  ok "added '$TARGET_USER' to the 'docker' group"
  NEEDS_RELOGIN=true
fi

# -----------------------------------------------------------------------------
# 5. Prove it works
# -----------------------------------------------------------------------------
step "Verifying the installation"

if docker info >/dev/null 2>&1; then
  if docker run --rm hello-world >/dev/null 2>&1; then
    ok "docker run hello-world succeeded"
  else
    warn "the daemon is reachable but 'docker run hello-world' failed — check your network or DNS"
  fi
else
  skip "cannot verify from this shell until the group change takes effect (see below)"
fi

DISK_GB="$(df -BG --output=avail "$PWD" 2>/dev/null | tail -1 | tr -dc '0-9' || echo 0)"
MEM_GB="$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo 0)"
if (( MEM_GB >= 6 )); then
  ok "RAM: ${MEM_GB} GiB"
else
  warn "RAM: ${MEM_GB} GiB — the core stack wants 6 GiB or more"
fi
if (( DISK_GB >= 15 )); then
  ok "free disk: ${DISK_GB} GiB"
else
  warn "free disk: ${DISK_GB} GiB — images alone need about 15 GiB"
fi

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
printf '\n%sHost bootstrap complete.%s\n\n' "$C_BOLD$C_GREEN" "$C_RESET"

if $NEEDS_RELOGIN; then
  cat <<EOS
${C_YELLOW}One more step:${C_RESET} your shell does not have the new 'docker' group yet.

  Pick either:
    ${C_BOLD}newgrp docker${C_RESET}          apply it to this shell right now
    ${C_BOLD}exit${C_RESET} and log back in   apply it everywhere (WSL: run 'wsl --shutdown' from Windows)

Then:

  ${C_BOLD}make doctor${C_RESET}    confirm the host is ready
  ${C_BOLD}make up${C_RESET}        run the complete application

EOS
else
  cat <<EOS
Next:

  ${C_BOLD}make doctor${C_RESET}    confirm the host is ready
  ${C_BOLD}make up${C_RESET}        run the complete application

The first ${C_BOLD}make up${C_RESET} pulls about 6 GiB of images and builds the backend, so
expect 5-15 minutes. Every run after that starts in under a minute.

EOS
fi
