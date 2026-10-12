#!/usr/bin/env bash
set -euo pipefail

archive_url="https://github.com/Gr33nOps/sonkip/archive/refs/heads/main.tar.gz"
install_dir="${SONKIP_INSTALL_DIR:-${HOME}/.local/share/sonkip}"
bin_dir="${HOME}/.local/bin"
temp_dir="$(mktemp -d)"

cleanup() {
  rm -rf -- "${temp_dir}"
}
trap cleanup EXIT

if ! command -v python3 >/dev/null 2>&1; then
  echo "Sonkip requires Python 3.10 or newer." >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "Sonkip requires curl." >&2
  exit 1
fi

echo ""
echo "  SONKIP / LOCAL INSTALL"
echo "  Installing to ${install_dir}"
echo ""

echo "  [1/4] Downloading Sonkip..."
curl --fail --location --silent --show-error "${archive_url}" --output "${temp_dir}/sonkip.tar.gz"
mkdir -p "${temp_dir}/source"
tar -xzf "${temp_dir}/sonkip.tar.gz" -C "${temp_dir}/source"
source_dir="$(find "${temp_dir}/source" -mindepth 1 -maxdepth 1 -type d | head -n 1)"

echo "  [2/4] Installing app files..."
mkdir -p "${install_dir}"
cp -R "${source_dir}/." "${install_dir}/"

echo "  [3/4] Creating private Python environment..."
python3 -m venv "${install_dir}/.venv"

echo "  [4/4] Installing dependencies..."
"${install_dir}/.venv/bin/python" -m pip install --disable-pip-version-check -r "${install_dir}/requirements.txt"

mkdir -p "${bin_dir}"
cat > "${bin_dir}/sonkip" <<EOF
#!/usr/bin/env bash
cd "${install_dir}"
exec "${install_dir}/.venv/bin/python" "${install_dir}/run.py"
EOF
chmod +x "${bin_dir}/sonkip"

echo ""
echo "  Sonkip is installed. Run it anytime with: ${bin_dir}/sonkip"
echo ""

if [[ "${SONKIP_NO_LAUNCH:-0}" != "1" ]]; then
  nohup "${bin_dir}/sonkip" >"${temp_dir}/sonkip.log" 2>&1 &
  sleep 2
  if command -v open >/dev/null 2>&1; then
    open "http://127.0.0.1:8000"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://127.0.0.1:8000" >/dev/null 2>&1 || true
  else
    echo "  Open http://127.0.0.1:8000 in your browser."
  fi
fi
