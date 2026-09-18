# BarberApp Client

Client Python per prenotare appuntamenti dal barbiere tramite API reverse-engineered.

## Installazione

```bash
# Clona il repository
cd barberapp

# Installa dipendenze
pip install requests rich
```
oppure usa uv che è meglio.

## Setup

### 1. Trova la tua parrucchieria

```python
from barberapp_client import search_nearby

# Cerca per coordinate GPS (usa le tue coordinate)
results = search_nearby(lat=37.1905, lon=13.7697, radius=10000)

for shop in results:
    print(f"{shop['Nome']} - ID: {shop['Key']}")
    print(f"  Indirizzo: {shop['Indirizzo']}")
    print(f"  Tel: {shop['Telefono']}")
    print(f"  Distanza: {shop['Distanza']}m")
```

### 2. Configura le credenziali

Modifica `config.py`:

```python
# Credenziali utente (ottieni ID da search_nearby)

USER_ID = "12345678"          # Il 'Key' della parrucchieria
USERNAME = "TuoUsername"        # Username dell'app
PASSWORD = "TuaPassword"        # Password dell'app

# Preferenze
PREFERRED_BARBER = "Giovanni"   # Nome del tuo barbiere preferito
PREFERRED_SERVICE_ID = 10       # ID servizio preferito
```

## Uso

```bash
python barberapp_client.py
```

### Comandi CLI

| Tasto | Azione |
|-------|--------|
| `s` | ✂️ Cambia servizio |
| `b` | 📅 Prenota appuntamento |
| `c` | ❌ Cancella prenotazione |
| `r` | 🔄 Aggiorna dati |
| `q` | 🚪 Esci |

## Interfaccia Web & Docker (Porta 7525)

È disponibile una web interface completa (FastAPI + SPA moderna a tema chiaro):
- **Consultazione slot** con filtri orari e prenotazione con un click
- **Gestione prenotazioni** attive e cancellazione con conferma
- **Auto-Booking Bot**: monitoraggio automatico in background con notifica Telegram e prenotazione immediata del primo slot utile nella fascia oraria scelta.

### Avvio con Docker (Home Server)

Grazie al volume persistente `./:/app`, qualsiasi modifica ai file Python o configurazioni sul server ha effetto immediato senza dover ricostruire l'immagine.

```bash
docker compose up -d
```
L'interfaccia sarà disponibile all'indirizzo `http://<IP_SERVER>:7525`.

### Avvio Locale con uv

```bash
uv run uvicorn web_server:app --host 0.0.0.0 --port 7525 --reload
```

## API Endpoints

Vedi [API_DOCUMENTATION.md](API_DOCUMENTATION.md) per la documentazione completa degli endpoint.

## Esempi

### Cerca parrucchierie nelle vicinanze

```python
from barberapp_client import search_nearby

shops = search_nearby(lat=41.9028, lon=12.4964)  # Roma
print(shops)
```

### Prenotazione programmatica

```python
from barberapp_client import BarberAppClient

client = BarberAppClient(
    user_id="12341234",
    username="TuoUsername",
    password="TuaPassword"
)

# Prenota
success = client.book(
    datetime_str="2512251115",  # 25/12/25 11:15
    service_id=2,               # Sopracciglia
    barber="Giovanni"
)
```

## Note

- Le credenziali sono quelle usate nell'app BarberApp
- L'ID parrucchieria (`Key`) si ottiene con `search_nearby()`
- Gli slot disponibili cambiano in tempo reale
