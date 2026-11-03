#!/usr/bin/env bash
set -euo pipefail

plugin_id="eprom.gmail-notifier"
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
install_home="${GMAIL_NOTIFIER_INSTALL_HOME:-$HOME}"
plugin_dir="$install_home/.config/omarchy/plugins/$plugin_id"

for command_name in omarchy python3 secret-tool notify-send; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$command_name" >&2
    if [[ "$command_name" == "secret-tool" ]]; then
      printf 'Install libsecret and ensure a Secret Service is available in the desktop session.\n' >&2
    elif [[ "$command_name" == "notify-send" ]]; then
      printf 'Install libnotify to enable desktop notifications.\n' >&2
    fi
    exit 1
  fi
done

for required_file in manifest.json BarWidget.qml Panel.qml Model.js helper/main.py assets/envelope.svg; do
  if [[ ! -f "$source_dir/$required_file" ]]; then
    printf 'Plugin source is incomplete; missing %s\n' "$required_file" >&2
    exit 1
  fi
done

is_update=false
if [[ -d "$plugin_dir" && -f "$plugin_dir/manifest.json" ]]; then
  is_update=true
fi

mkdir -p "$plugin_dir"
if [[ "$(realpath "$source_dir")" != "$(realpath -m "$plugin_dir")" ]]; then
  for file in manifest.json BarWidget.qml Panel.qml Model.js README.md LICENSE install-local.sh; do
    cp -a "$source_dir/$file" "$plugin_dir/"
  done
  mkdir -p "$plugin_dir/helper" "$plugin_dir/assets"
  cp -a "$source_dir/helper/main.py" "$plugin_dir/helper/"
  cp -a "$source_dir/assets/envelope.svg" "$plugin_dir/assets/"
  
  # Clean up legacy root script and stale pycache if present
  rm -f "$plugin_dir/main.py"
  rm -rf "$plugin_dir/helper/__pycache__"
fi

# Refresh Omarchy's local plugin registry so a newly copied plugin is known
# before enabling it. This command is present on supported Omarchy installs.
if command -v omarchy-shell >/dev/null 2>&1; then
  omarchy-shell shell rescanPlugins
fi

omarchy plugin validate "$plugin_dir"
omarchy plugin enable "$plugin_id" --section left
omarchy restart shell

if [[ "$is_update" == true ]]; then
  printf 'Successfully updated %s to the latest version and restarted shell.\n' "$plugin_id"
else
  printf 'Successfully installed and enabled %s in the left bar.\n' "$plugin_id"
fi
