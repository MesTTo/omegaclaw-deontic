#!/usr/bin/env bash
# Thin wrapper around installer/install.py. Usage:
#   ./install.sh /path/to/OmegaClaw-Core            # install (source clone)
#   ./install.sh /path/to/OmegaClaw-Core --uninstall
# All flags pass through to install.py (see --help).
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$here/installer/install.py" "$@"
