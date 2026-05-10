import os
import asyncio
import logging
from dotenv import load_dotenv

from pyrogram import Client
from motor.motor_asyncio import AsyncIOMotorClient

# Importiamo le logiche che abbiamo già scritto per l'estrazione e le chiamate API
from bot import extract_epub_metadata, fetch_google_books_data

# ==========================================
# Configurazione Logging
# ==========================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==========================================
# Caricamento Variabili d'Ambiente
# ==========================================
load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
MONGO_URI = os.getenv("MONGO_URI")
CHANNEL_ID = os.getenv("CHANNEL_ID")

if not all([API_ID, API_HASH, MONGO_URI, CHANNEL_ID]):
    logger.error("Mancano variabili d'ambiente fondamentali (.env). Assicurati di avere API_ID e API_HASH.")
    exit(1)

try:
    CHANNEL_ID = int(CHANNEL_ID)
except ValueError:
    logger.error("CHANNEL_ID deve essere un numero intero valido.")
    exit(1)

# ==========================================
# Connessione MongoDB
# ==========================================
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["library_db"]
books_collection = db["books"]

async def main():
    # Inizializziamo il Client Pyrogram per accedere come utente
    # Verrà creato un file "my_account.session" in locale
    app = Client("my_account", api_id=API_ID, api_hash=API_HASH)
    
    os.makedirs("downloads", exist_ok=True)
    
    async with app:
        logger.info(f"Connesso con successo! Inizio scansione del canale {CHANNEL_ID}...")
        
        # Scorriamo la cronologia (dall'ultimo al primo o viceversa, iter_history scorre dalla fine)
        # Limit a 0 significa scarica tutto, modificalo per testare su un campione più piccolo se vuoi.
        processed_count = 0
        
        async for message in app.get_chat_history(CHANNEL_ID):
            if message.document and message.document.file_name and message.document.file_name.lower().endswith(".epub"):
                file_id = message.document.file_id
                file_unique_id = message.document.file_unique_id
                file_name = message.document.file_name
                
                logger.info(f"Trovato EPUB: {file_name} (Msg ID: {message.id})")
                
                # Controlliamo se esiste già nel db per saltarlo e risparmiare API Google
                existing = await books_collection.find_one({"telegram_file_unique_id": file_unique_id})
                if existing:
                    logger.info(f"File {file_name} già presente nel database. Salto...")
                    continue
                
                temp_path = os.path.join("downloads", f"{file_unique_id}.epub")
                
                try:
                    # 1. Download
                    logger.info("Scaricamento file in corso...")
                    await app.download_media(message, file_name=temp_path)
                    
                    # 2. Estrazione dati locali
                    local_metadata = extract_epub_metadata(temp_path)
                    
                    # 3. Arricchimento API
                    api_data = await fetch_google_books_data(
                        local_metadata.get("isbn"), 
                        local_metadata.get("title"), 
                        local_metadata.get("author")
                    )
                    
                    # 4. Salvataggio su MongoDB
                    final_data = {
                        "telegram_file_id": file_id,
                        "telegram_file_unique_id": file_unique_id,
                        "original_file_name": file_name,
                        **local_metadata,
                        **api_data,
                    }
                    
                    await books_collection.update_one(
                        {"telegram_file_unique_id": file_unique_id},
                        {"$set": final_data},
                        upsert=True
                    )
                    logger.info(f"Salvato con successo: {local_metadata.get('title') or file_name}")
                    processed_count += 1
                    
                except Exception as e:
                    logger.error(f"Errore durante l'elaborazione del file {file_name}: {e}")
                    
                finally:
                    # 5. Pulizia file temporaneo
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception as e:
                            logger.error(f"Impossibile eliminare il file {temp_path}: {e}")
                            
        logger.info(f"Scansione completata! Nuovi libri indicizzati: {processed_count}")

if __name__ == "__main__":
    # Avvia l'event loop di Pyrogram/Asyncio
    asyncio.run(main())
