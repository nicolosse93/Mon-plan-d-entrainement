#!/bin/bash
# Désinstalle le relais montre sur Mac : arrêt, LaunchAgent et fichiers supprimés.
# Les séances retirées de la montre (dossier « retires ») sont conservées, libmtp aussi (brew uninstall libmtp).
BASE="$HOME/Library/Application Support/MonPlan"
PLIST="$HOME/Library/LaunchAgents/com.monplan.relais.plist"

launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
rm -f "$PLIST"
for name in montre-relais-mac.py relais.json relais.log relais-erreurs.log; do
    rm -f "$BASE/$name"
done
printf '\033[32mRelais désinstallé.\033[0m\n'
echo "Séances retirées de la montre conservées dans : $BASE/retires"
read -r -p "Entrée pour fermer"
