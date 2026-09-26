from jev.services.paths import Settings
from jev.services.storage import Storage

settings = Settings.load()
storage = Storage(settings.db_path)
storage.initialize()
with storage.connect() as connection:
    rules = connection.execute("DELETE FROM rules").rowcount
    events = connection.execute("DELETE FROM events").rowcount
print(f"Cleared {rules} rules and {events} events from {settings.db_path}")
