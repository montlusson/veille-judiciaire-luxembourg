#!/bin/bash
# Double-cliquez sur ce fichier dans le Finder pour lancer l'extraction puis ouvrir le module

cd "$(dirname "$0")"

echo "═══════════════════════════════════════════════════════"
echo "  Veille judiciaire Luxembourg"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── 1. Vérifie Python ─────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 n'est pas installé."
  echo "   Téléchargez-le sur https://python.org"
  read -p "Appuyez sur Entrée pour fermer..."
  exit 1
fi
echo "✓ Python $(python3 --version | cut -d' ' -f2) détecté"

# ── 2. Installe les dépendances si nécessaire ─────────────
python3 -c "import pdfplumber, requests" 2>/dev/null
if [ $? -ne 0 ]; then
  echo "→ Installation des dépendances (première fois uniquement)..."
  pip3 install pdfplumber requests --quiet
fi

# ── 3. Lance l'extraction ─────────────────────────────────
echo "→ Extraction des décisions judiciaires..."
echo "  (cela peut prendre 20 à 40 minutes selon votre connexion)"
echo ""
python3 extract_decisions.py

echo ""
echo "→ Récupération du calendrier des audiences..."
python3 -c "import bs4" 2>/dev/null
if [ $? -ne 0 ]; then
  echo "→ Installation de beautifulsoup4..."
  pip3 install beautifulsoup4 --quiet
fi
python3 scrape_audiences.py

if [ $? -ne 0 ]; then
  echo ""
  echo "❌ L'extraction a rencontré une erreur."
  read -p "Appuyez sur Entrée pour fermer..."
  exit 1
fi

echo ""
echo "✓ decisions.json mis à jour."

# ── 4. Vérifie que le HTML est présent ────────────────────
HTML_FILE="veille-judiciaire-luxembourg.html"
if [ ! -f "$HTML_FILE" ]; then
  echo ""
  echo "⚠ Le fichier $HTML_FILE est introuvable dans ce dossier."
  echo "  Copiez-le ici pour ouvrir le module automatiquement."
  read -p "Appuyez sur Entrée pour fermer..."
  exit 0
fi

# ── 5. Arrête un éventuel serveur déjà lancé sur ce port ──
PORT=8765
lsof -ti tcp:$PORT | xargs kill -9 2>/dev/null

# ── 6. Lance un serveur HTTP local en arrière-plan ────────
echo "→ Démarrage du serveur local (port $PORT)..."
python3 -m http.server $PORT --bind 127.0.0.1 &>/dev/null &
SERVER_PID=$!
sleep 1  # laisse le serveur démarrer

# ── 7. Ouvre le navigateur ────────────────────────────────
echo "→ Ouverture du module dans le navigateur..."
open "http://127.0.0.1:$PORT/$HTML_FILE"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✓ Module disponible sur http://127.0.0.1:$PORT/$HTML_FILE"
echo ""
echo "  Partagez ce terminal ouvert avec vos collègues sur le"
echo "  même réseau : remplacez 127.0.0.1 par votre IP locale"
echo "  (ex. 192.168.1.x) pour qu'ils y accèdent depuis leur"
echo "  navigateur sans installation."
echo ""
echo "  Appuyez sur Ctrl+C pour arrêter le serveur."
echo "═══════════════════════════════════════════════════════"

# Garde le terminal ouvert et le serveur actif
wait $SERVER_PID
