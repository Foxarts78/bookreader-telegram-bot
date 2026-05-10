# BookReader Telegram Bot 📚🤖

Un bot Telegram asincrono (event-driven) sviluppato in Python per l'indicizzazione automatica di file EPUB da un canale Telegram privato. Estrae metadati dai file, li arricchisce interrogando le API di Google Books e salva il tutto su MongoDB Atlas per futuri utilizzi.

## 🌟 Funzionalità Principali

- **Trigger Passivo Event-Driven**: Il bot non richiede comandi manuali. Resta in ascolto sul canale configurato e si attiva automaticamente solo all'arrivo di file con estensione `.epub`.
- **Estrazione Metadati Locali**: Analizza il file EPUB (usando `ebooklib`) per recuperare titolo, autore, data di pubblicazione e codici ISBN.
- **Arricchimento tramite Google Books API**: Utilizza i dati estratti per fare chiamate asincrone a Google Books, prelevando copertina (thumbnail), sinossi (description), lingua, genere e numero di pagine. Include un sistema di *Retry Intelligente* per aggirare i rate-limit di Google (Errori 429/503).
- **Integrazione MongoDB (Upsert)**: Salva i dati usando l'identificatore univoco del file Telegram (`file_unique_id`), garantendo l'assenza di duplicati anche se lo stesso file viene ricaricato.
- **Gestione dello Storico**: Include uno script dedicato (`importa_storico.py`) basato su Pyrogram (Client API) per scansionare massivamente la cronologia passata del canale e indicizzare gli EPUB pregressi.
- **Auto-Pulizia**: I file temporanei scaricati vengono eliminati immediatamente dopo l'elaborazione per non consumare spazio sul server.

## 🛠️ Tecnologie Utilizzate

- **Python 3.10+** (Librerie asincrone: `asyncio`)
- **[python-telegram-bot](https://python-telegram-bot.org/) (v20+)**: Per l'interazione con l'API Bot di Telegram.
- **[Pyrogram](https://docs.pyrogram.org/)**: Per l'indicizzazione dei messaggi storici (Client API).
- **[Motor](https://motor.readthedocs.io/)**: Driver asincrono per MongoDB.
- **[Aiohttp](https://docs.aiohttp.org/)**: Client HTTP asincrono per le chiamate a Google Books.
- **[EbookLib](https://github.com/aerkalov/ebooklib)**: Per l'estrazione metadati dai file EPUB.

---

## 🚀 Guida all'Installazione

### 1. Prerequisiti
- **Python 3.10** o superiore installato sul sistema.
- Un cluster **MongoDB Atlas** attivo.
- Le chiavi per le API (Token Bot Telegram, API Key Google Books, API ID/Hash Telegram).

### 2. Clonazione e Ambiente Virtuale
```bash
git clone https://github.com/Foxarts78/bookreader-telegram-bot.git
cd bookreader-telegram-bot

# Creazione ambiente virtuale
python -m venv venv-bookbot

# Attivazione (Windows)
venv-bookbot\Scripts\activate
# Attivazione (Linux/Mac)
source venv-bookbot/bin/activate

# Installazione dipendenze
pip install -r requirements.txt
```

### 3. Configurazione Variabili d'Ambiente
Crea un file `.env` (puoi copiare il template da `.env.example`) e inserisci i tuoi parametri:
```env
TELEGRAM_TOKEN=il_tuo_token_bot
MONGO_URI=mongodb+srv://user:pass@cluster...
GOOGLE_BOOKS_API_KEY=la_tua_api_key
CHANNEL_ID=-1001234567890

# Chiavi per importa_storico.py (da my.telegram.org)
API_ID=il_tuo_api_id
API_HASH=il_tuo_api_hash
```

---

## 🏃‍♂️ Utilizzo

### Modalità 1: Esecuzione in Tempo Reale (Bot standard)
Questa è la modalità da usare sul server in produzione. Il bot resta in ascolto per i *nuovi* file caricati.
```bash
python bot.py
```

### Modalità 2: Importazione dello Storico
Se il canale contiene già centinaia di libri caricati in passato, esegui lo script utente per recuperarli:
```bash
python importa_storico.py
```
*Al primo avvio, ti verrà richiesto il tuo numero di telefono e il codice OTP inviato da Telegram.*

---

## ☁️ Deploy su Google Cloud / Linux VM

Il repository include i file necessari per l'esecuzione come servizio di sistema (Systemd).

1. Modifica il file `bookreader-bot.service` sostituendo `tuo_utente_gcp` e i percorsi assoluti con quelli reali della tua VM.
2. Copia il file nei servizi di sistema:
   ```bash
   sudo cp bookreader-bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable bookreader-bot.service
   sudo systemctl start bookreader-bot.service
   ```
3. Usa lo script `deploy.sh` per aggiornare facilmente il codice in futuro:
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```
