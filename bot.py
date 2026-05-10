import os
import re
import logging
import asyncio
from typing import Dict, Any, Optional

import aiohttp
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from motor.motor_asyncio import AsyncIOMotorClient
import ebooklib
from ebooklib import epub

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

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
GOOGLE_BOOKS_API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID")

if not all([TELEGRAM_TOKEN, MONGO_URI, CHANNEL_ID]):
    logger.error("Mancano variabili d'ambiente fondamentali. Controlla il file .env.")
    exit(1)

# Conversione di CHANNEL_ID in intero per il filtro
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

# ==========================================
# Funzioni Helper
# ==========================================

def extract_epub_metadata(file_path: str) -> Dict[str, str]:
    """
    Legge il file EPUB e ne estrae i metadati principali usando ebooklib.
    Restituisce un dizionario con titolo, autore, data e isbn (se presente).
    """
    metadata = {
        "title": None,
        "author": None,
        "date": None,
        "isbn": None
    }
    
    try:
        book = epub.read_epub(file_path)
        
        # Estrazione Titolo
        titles = book.get_metadata('DC', 'title')
        if titles:
            metadata["title"] = titles[0][0]
            
        # Estrazione Autore
        creators = book.get_metadata('DC', 'creator')
        if creators:
            metadata["author"] = creators[0][0]
            
        # Estrazione Data
        dates = book.get_metadata('DC', 'date')
        if dates:
            metadata["date"] = dates[0][0]
            
        # Estrazione Identificatore/ISBN
        identifiers = book.get_metadata('DC', 'identifier')
        if identifiers:
            for identifier in identifiers:
                if identifier[0]:
                    val = str(identifier[0]).lower()
                    # Cerchiamo un formato ISBN base (solo numeri o trattini, o prefix isbn)
                    if 'isbn' in val:
                        # Estrae solo i numeri/trattini dall'id
                        match = re.search(r'[\d\-]{10,17}', val)
                        if match:
                            metadata["isbn"] = match.group(0).replace('-', '')
                            break
                    elif re.match(r'^[\d\-]{10,17}$', val):
                        metadata["isbn"] = val.replace('-', '')
                        break
                    
    except Exception as e:
        logger.error(f"Errore durante l'estrazione metadati da {file_path}: {e}")
        
    return metadata

async def fetch_google_books_data(isbn: Optional[str], title: Optional[str], author: Optional[str]) -> Dict[str, Any]:
    """
    Esegue una chiamata asincrona alle API di Google Books per arricchire i dati.
    Usa l'ISBN se disponibile, altrimenti prova con Titolo e Autore.
    """
    api_data = {
        "genre": None,
        "page_count": None,
        "cover_url": None,
        "description": None,
        "language": None
    }
    
    query = ""
    if isbn:
        query = f"isbn:{isbn}"
    elif title and author:
        query = f"intitle:{title}+inauthor:{author}"
    elif title:
        query = f"intitle:{title}"
        
    if not query:
        return api_data
        
    url = f"https://www.googleapis.com/books/v1/volumes?q={query}"
    if GOOGLE_BOOKS_API_KEY:
        url += f"&key={GOOGLE_BOOKS_API_KEY}"
        
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if "items" in data and len(data["items"]) > 0:
                        volume_info = data["items"][0].get("volumeInfo", {})
                        
                        api_data["description"] = volume_info.get("description")
                        api_data["page_count"] = volume_info.get("pageCount")
                        api_data["language"] = volume_info.get("language")
                        
                        categories = volume_info.get("categories")
                        if categories:
                            api_data["genre"] = categories[0]
                            
                        image_links = volume_info.get("imageLinks")
                        if image_links:
                            api_data["cover_url"] = image_links.get("thumbnail")
                else:
                    logger.warning(f"Errore da Google Books API: HTTP {response.status}")
    except Exception as e:
        logger.error(f"Eccezione durante la chiamata API di Google Books: {e}")
        
    return api_data

# ==========================================
# Gestori Telegram
# ==========================================

async def handle_epub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler che si attiva quando viene ricevuto un file EPUB nel canale.
    """
    message = update.effective_message
    if not message or not message.document:
        return
        
    doc = message.document
    file_id = doc.file_id
    file_unique_id = doc.file_unique_id
    file_name = doc.file_name or f"{file_unique_id}.epub"
    
    logger.info(f"Ricevuto nuovo EPUB: {file_name} ({file_unique_id})")
    
    # Crea la directory di download se non esiste
    os.makedirs("downloads", exist_ok=True)
    temp_path = os.path.join("downloads", f"{file_unique_id}.epub")
    
    try:
        # 1. Download temporaneo
        logger.info("Scaricamento file in corso...")
        telegram_file = await context.bot.get_file(file_id)
        await telegram_file.download_to_drive(custom_path=temp_path)
        logger.info("Download completato.")
        
        # 2. Estrazione dati locali
        logger.info("Estrazione metadati locali...")
        local_metadata = extract_epub_metadata(temp_path)
        logger.info(f"Metadati estratti: {local_metadata}")
        
        # 3. Arricchimento API
        logger.info("Arricchimento tramite Google Books API...")
        api_data = await fetch_google_books_data(
            local_metadata.get("isbn"), 
            local_metadata.get("title"), 
            local_metadata.get("author")
        )
        logger.info("Arricchimento API completato.")
        
        # 4. Salvataggio su MongoDB
        # Fondiamo i dizionari
        final_data = {
            "telegram_file_id": file_id,
            "telegram_file_unique_id": file_unique_id,
            "original_file_name": file_name,
            **local_metadata,
            **api_data,
        }
        
        logger.info("Salvataggio su MongoDB...")
        result = await books_collection.update_one(
            {"telegram_file_unique_id": file_unique_id},
            {"$set": final_data},
            upsert=True
        )
        
        if result.upserted_id:
            logger.info("Nuovo libro salvato nel DB.")
        else:
            logger.info("Libro esistente aggiornato nel DB.")
            
    except Exception as e:
        logger.error(f"Errore nell'elaborazione del file {file_name}: {e}", exc_info=True)
        
    finally:
        # 5. Pulizia file temporaneo
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.info(f"File temporaneo {temp_path} eliminato.")
            except Exception as e:
                logger.error(f"Impossibile eliminare il file {temp_path}: {e}")

# ==========================================
# Main
# ==========================================

def main():
    """Punto di ingresso principale per il bot."""
    logger.info("Inizializzazione bot...")
    
    # Crea l'app Telegram
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Aggiungi l'handler per i documenti
    # Il filtro intercetta messaggi provenienti da CHANNEL_ID che sono documenti e finiscono per .epub
    epub_filter = filters.Chat(chat_id=CHANNEL_ID) & filters.Document.FileExtension("epub")
    app.add_handler(MessageHandler(epub_filter, handle_epub))
    
    logger.info("Bot in ascolto...")
    
    # Avvia il bot
    # Passiamo in polling. Visto che è un trigger passivo per un canale, il polling è sufficiente.
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
