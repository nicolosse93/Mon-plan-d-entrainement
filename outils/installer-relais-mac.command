#!/bin/bash
# Installe le relais montre sur Mac : libmtp (Homebrew), copie dans ~/Library/Application Support/MonPlan,
# jeton secret, démarrage automatique avec la session (LaunchAgent).
# À lancer une fois d'un double-clic dans le Finder. Relançable : garde le jeton existant.
set -e
cd "$(dirname "$0")"

BASE="$HOME/Library/Application Support/MonPlan"
SCRIPT="$BASE/montre-relais-mac.py"
CONFIG="$BASE/relais.json"
LABEL="com.monplan.relais"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PORT=47812

# Homebrew : nécessaire pour libmtp (lecture de la montre en MTP)
BREW="$(command -v brew || true)"
for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [ -z "$BREW" ] && [ -x "$candidate" ]; then BREW="$candidate"; fi
done
if [ -z "$BREW" ]; then
    echo "Homebrew est nécessaire : installe-le depuis https://brew.sh, puis relance ce fichier."
    read -r -p "Entrée pour fermer"
    exit 1
fi
PREFIX="$("$BREW" --prefix)"
"$BREW" list libmtp >/dev/null 2>&1 || "$BREW" install libmtp
# Python 3 : celui de Homebrew s'il existe, sinon celui de macOS, sinon installé
PY="$PREFIX/bin/python3"
if ! "$PY" -c 'import sys' >/dev/null 2>&1; then PY=/usr/bin/python3; fi
if ! "$PY" -c 'import sys; assert sys.version_info >= (3, 8)' >/dev/null 2>&1; then
    "$BREW" install python
    PY="$PREFIX/bin/python3"
fi

mkdir -p "$BASE" "$HOME/Library/LaunchAgents"
cp montre-relais-mac.py "$SCRIPT"

# Jeton conservé s'il existe déjà (l'app n'a pas à être reconfigurée), adresse du site par défaut l'ancienne
OLD_TOKEN="$("$PY" -c 'import json,sys
try: print(json.load(open(sys.argv[1], encoding="utf-8-sig")).get("token") or "")
except Exception: print("")' "$CONFIG")"
OLD_SITE="$("$PY" -c 'import json,sys
try: print((json.load(open(sys.argv[1], encoding="utf-8-sig")).get("origins") or [""])[0])
except Exception: print("")' "$CONFIG")"
TOKEN="${OLD_TOKEN:-$("$PY" -c 'import secrets; print(secrets.token_hex(32))')}"

# Adresse du site (seule origine en ligne autorisée à parler au relais ; localhost l'est toujours)
if [ -n "$OLD_SITE" ]; then
    read -r -p "Adresse de ton site (ex. https://monsite.github.io) [Entrée = $OLD_SITE] : " SITE
else
    read -r -p "Adresse de ton site (ex. https://monsite.github.io), ou Entrée si tu l'utilises seulement en local : " SITE
fi
SITE="${SITE:-$OLD_SITE}"

"$PY" - "$CONFIG" "$TOKEN" "$SITE" "$PORT" "$PREFIX/lib/libmtp.dylib" <<'EOF'
import json, sys
from urllib.parse import urlparse
config, token, site, port, libmtp = sys.argv[1:]
origins = []
if site.strip():
    u = urlparse(site.strip())
    origins.append('{}://{}'.format(u.scheme, u.netloc))
with open(config, 'w', encoding='utf-8') as f:
    json.dump({'token': token, 'origins': origins, 'port': int(port), 'libmtp': libmtp}, f, indent=2)
EOF
chmod 600 "$CONFIG"

# LaunchAgent : relais lancé à chaque ouverture de session et relancé s'il s'arrête
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PY</string>
        <string>$SCRIPT</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardErrorPath</key><string>$BASE/relais-erreurs.log</string>
</dict>
</plist>
EOF
launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

sleep 2
if STATUS="$(curl -fsS -H "X-Relais-Jeton: $TOKEN" "http://localhost:$PORT/status")"; then
    printf '\033[32mRelais démarré.\033[0m\n'
    case "$STATUS" in
        *'"watch": true'*) echo "Montre détectée." ;;
        *) echo "Montre non branchée pour l'instant (normal)." ;;
    esac
else
    printf '\033[33mLe relais ne répond pas encore. Détails dans %s\033[0m\n' "$BASE/relais.log"
fi

printf '%s' "$TOKEN" | pbcopy
echo
printf "\033[36mJeton (déjà copié dans le presse-papiers) : colle-le dans l'app, Profil > Synchro de la montre.\033[0m\n"
echo "$TOKEN"
echo
echo "Le relais démarrera tout seul à chaque ouverture de session."
echo "Avant chaque synchro, ferme Garmin Express : il bloque l'accès à la montre."
read -r -p "Entrée pour fermer"
