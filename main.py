import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
from keep_alive import keep_alive
import sys
import time
import random
import logging
from database import initialize_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('bot')

# Start serwera keep-alive
keep_alive()

# Załaduj zmienne środowiskowe
load_dotenv()
TOKEN = os.getenv("TOKEN")

# Ustawienie intencji
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

class SupremeCourtBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        self.connection_attempts = 0
        self.max_reconnect_delay = 900  # 15 minutes in seconds
    
    # Override zamiast dekoratora
    async def setup_hook(self):
        # 1) Ładowanie wszystkich cogs
        cogs_dir_contents = os.listdir("./cogs")
        logger.info(f"Zawartość folderu cogs: {cogs_dir_contents}")
        for fname in cogs_dir_contents:
            if not fname.endswith(".py") or fname.startswith("__"):
                continue
            ext = f"cogs.{fname[:-3]}"
            try:
                await self.load_extension(ext)
                logger.info(f"✅ Załadowano coga: {ext}")
            except Exception as e:
                logger.error(f"❌ Błąd ładowania {ext}: {e}")
        
        # 2) Synchronizacja slash-komend tylko jeśli użyto flagi --sync
        try:
            if "--sync" in sys.argv:
                logger.info("🔄 Synchronizacja komend slash...")
                synced = await self.tree.sync()
                logger.info(f"🔁 Zsynchronizowano {len(synced)} komend")
                logger.warning("⚠️ Synchronizacja wykonana. Uruchom ponownie bez flagi --sync")
                # Zakończ program po synchronizacji
                await self.close()
        except Exception as e:
            logger.error(f"❌ Błąd sync: {e}")
    
    async def on_ready(self):
        # Reset connection attempts on successful connection
        self.connection_attempts = 0
        logger.info(f"🚀 Zalogowano jako {self.user} (ID: {self.user.id})")
        logger.info(f"Bot działa na {len(self.guilds)} serwerach")
        # Pokaż listę dostępnych slash-komend
        logger.info("📋 Dostępne komendy slash:")
        for cmd in self.tree.get_commands():
            logger.info(f" - /{cmd.name}: {cmd.description}")

    # Add custom error handler for HTTP exceptions
    async def on_error(self, event_method, *args, **kwargs):
        logger.error(f"Error in {event_method}: {sys.exc_info()[1]}")
        if isinstance(sys.exc_info()[1], discord.errors.HTTPException):
            error = sys.exc_info()[1]
            if error.status == 429:  # Rate limit error
                logger.warning(f"Rate limit hit, details: {error.response}")

if __name__ == "__main__":
    # Inicjalizacja bazy danych przy starcie
    initialize_db()

    bot = SupremeCourtBot()
    
    # Add reconnection logic with exponential backoff
    retry = True
    attempt = 0
    
    while retry:
        try:
            if attempt > 0:
                # Calculate backoff time (exponential with jitter)
                backoff = min(bot.max_reconnect_delay, (2 ** attempt) + random.uniform(0, 1))
                logger.info(f"Reconnection attempt {attempt}. Waiting {backoff:.2f} seconds...")
                time.sleep(backoff)
            
            logger.info("Starting bot...")
            bot.run(TOKEN)
            retry = False  # If run completed without errors, exit the loop
            
        except discord.errors.HTTPException as e:
            attempt += 1
            if e.status == 429:  # Rate limit error
                logger.warning(f"Rate limit exceeded (attempt {attempt}). Bot will try again after backoff.")
            else:
                logger.error(f"HTTP Error: {e}")
        except Exception as e:
            attempt += 1
            logger.error(f"Unexpected error: {e}")
            if attempt >= 5:  # After 5 attempts, give up
                logger.critical("Too many failed attempts. Giving up.")
                retry = False