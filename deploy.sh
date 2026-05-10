#!/bin/bash
# Script per il deploy e l'aggiornamento del bot sulla VM

echo "Inizio procedura di deploy per BookReader Bot..."

# Assicurati di essere nella cartella corretta
# cd /percorso/assoluto/alla/cartella/del/bot/bookreader-telegram-bot

# 1. Recupera le ultime modifiche dal repository
echo "Esecuzione git pull..."
git pull origin main

# 2. Aggiorna le dipendenze (opzionale, ma consigliato se cambia requirements.txt)
echo "Aggiornamento dipendenze..."
source venv-bookbot/bin/activate
pip install -r requirements.txt
deactivate

# 3. Riavvia il servizio systemd
echo "Riavvio del servizio bookreader-bot..."
sudo systemctl restart bookreader-bot.service

# 4. Controlla lo stato del servizio
echo "Stato del servizio:"
sudo systemctl status bookreader-bot.service --no-pager

echo "Deploy completato con successo!"
