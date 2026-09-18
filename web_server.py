#!/usr/bin/env python3
"""
BarberApp Web Server
====================
Backend FastAPI con interfaccia web per la gestione del barbiere,
la consultazione orari, la prenotazione e il monitoraggio automatico.
"""

import os
from datetime import datetime, date as datetime_date, timedelta
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

import config
from barberapp_client import BarberAppClient
from scheduler import scheduler, send_telegram

app = FastAPI(title="BarberApp Web Interface", version="1.0.0")

# Inizializza client
def get_client() -> BarberAppClient:
    return BarberAppClient(
        user_id=config.BARBER_ID,
        username=config.USERNAME,
        password=config.PASSWORD
    )


# Modelli Pydantic
class BookRequest(BaseModel):
    datetime_str: str
    service_id: int
    barber: str

class CancelRequest(BaseModel):
    datetime_str: str
    service_id: int
    barber: str
    price: float = 0.0

class SchedulerStartRequest(BaseModel):
    barber: str | None = None
    service_id: int | None = None
    interval_minutes: int = 10
    min_hour: str | int | float | None = None
    max_hour: str | int | float | None = None
    start_date: str | None = None
    end_date: str | None = None
    dry_run: bool = False


# ==========================================
# ENDPOINT API
# ==========================================

@app.get("/api/status")
def get_status():
    """Ritorna informazioni sullo stato dell'utente e del sistema."""
    client = get_client()
    preferred_service_name = client.get_service_name(config.PREFERRED_SERVICE_ID)
    return {
        "username": config.USERNAME,
        "barber_id": config.BARBER_ID,
        "preferred_barber": config.PREFERRED_BARBER,
        "preferred_service_id": config.PREFERRED_SERVICE_ID,
        "preferred_service_name": preferred_service_name,
        "telegram_configured": bool(getattr(config, "TELEGRAM_BOT_TOKEN", None) and getattr(config, "TELEGRAM_CHAT_ID", None)),
        "scheduler_running": scheduler.status == "running"
    }


@app.get("/api/barbers")
def get_barbers():
    """Ritorna l'elenco dei barbieri."""
    client = get_client()
    try:
        raw_barbers = client.get_barbers()
        barbers = [
            {"id": b["Id"], "nome": b["Nome"], "minuti_taglio": b.get("MinutiTaglio", 45)}
            for b in raw_barbers if not b.get("Nascosto", False)
        ]
        return barbers
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore recupero barbieri: {e}")


@app.get("/api/services")
def get_services():
    """Ritorna l'elenco dei servizi con prezzo e durata stimata."""
    client = get_client()
    try:
        raw = client.get_services()
        services = []
        for i, name in enumerate(raw.get("Nome", [])):
            name_clean = name.strip() if name else ""
            if name_clean:
                price = raw.get("Prezzo", [])[i] if i < len(raw.get("Prezzo", [])) else 0.0
                duration = client.get_service_duration(config.PREFERRED_BARBER, i)
                services.append({
                    "id": i,
                    "name": name_clean,
                    "price": float(price),
                    "duration": duration
                })
        return services
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore recupero servizi: {e}")


@app.get("/api/reservations")
def get_reservations():
    """Ritorna le prenotazioni confermate e in coda."""
    client = get_client()
    try:
        confirmed_raw = client.get_confirmed_reservations()
        pending_raw = client.get_pending_reservations()

        confirmed = []
        for r in confirmed_raw:
            try:
                dt = client.parse_datetime(r["Or"])
                date_fmt = dt.strftime("%d/%m/%Y")
                time_fmt = dt.strftime("%H:%M")
                day_name = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"][dt.weekday()]
            except Exception:
                date_fmt = r.get("Or", "")
                time_fmt = ""
                day_name = ""

            service_id = r.get("Ti", 0)
            service_name = client.get_service_name(service_id)
            price = client.get_service_price(service_id)

            confirmed.append({
                "datetime_str": r.get("Or", ""),
                "date": date_fmt,
                "time": time_fmt,
                "day_name": day_name,
                "barber": r.get("Pa", ""),
                "service_id": service_id,
                "service_name": service_name,
                "price": price
            })

        pending = []
        for r in pending_raw:
            try:
                d = client.parse_date(r["Or"])
                date_fmt = d.strftime("%d/%m/%Y")
                day_name = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"][d.weekday()]
            except Exception:
                date_fmt = r.get("Or", "")
                day_name = ""

            service_id = r.get("Pe", 0)
            service_name = client.get_service_name(service_id)

            pending.append({
                "date_str": r.get("Or", ""),
                "date": date_fmt,
                "day_name": day_name,
                "barber": r.get("Pa", ""),
                "service_id": service_id,
                "service_name": service_name,
                "phone": r.get("Nm", "")
            })

        return {"confirmed": confirmed, "pending": pending}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore recupero prenotazioni: {e}")


@app.get("/api/slots")
def get_slots(
    barber: str = Query(default=config.PREFERRED_BARBER),
    service_id: int = Query(default=config.PREFERRED_SERVICE_ID),
    date_preset: str = Query(default="all"),  # all | today | tomorrow | this-week | next-week | custom
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    time_preset: str | None = Query(default=None)  # morning | afternoon | evening | after-19
):
    """Cerca e filtra gli slot liberi."""
    client = get_client()
    today = datetime.now().date()

    # Calcolo intervallo date
    start_d: datetime_date | None = today
    end_d: datetime_date | None = None

    if date_preset == "today":
        start_d = today
        end_d = today
    elif date_preset == "tomorrow":
        start_d = today + timedelta(days=1)
        end_d = today + timedelta(days=1)
    elif date_preset == "this-week":
        start_d = today
        days_to_sunday = 6 - today.weekday()
        end_d = today + timedelta(days=days_to_sunday)
    elif date_preset == "next-week":
        days_to_next_monday = 7 - today.weekday()
        start_d = today + timedelta(days=days_to_next_monday)
        end_d = start_d + timedelta(days=6)
    elif date_preset == "custom":
        if start_date:
            try:
                start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                pass
        if end_date:
            try:
                end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                pass

    try:
        client._schedule = None
        days = client.get_available_slots_for_barber(barber)
        service_name = client.get_service_name(service_id)

        matching_slots = []
        for day in days:
            date_str = day["Gi"]
            try:
                day_date = client.parse_date(date_str).date()
            except Exception:
                continue

            if start_d and day_date < start_d:
                continue
            if end_d and day_date > end_d:
                continue

            slots = client.calculate_available_slots(date_str, barber, service_id)
            day_name = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"][day_date.weekday()]

            for time_str, duration in slots:
                hour = int(time_str.split(":")[0])

                if time_preset == "morning" and (hour < 8 or hour >= 13):
                    continue
                elif time_preset == "afternoon" and (hour < 13 or hour >= 18):
                    continue
                elif time_preset == "evening" and hour < 18:
                    continue
                elif time_preset == "after-19" and hour < 19:
                    continue

                matching_slots.append({
                    "date": day_date.strftime("%Y-%m-%d"),
                    "date_formatted": day_date.strftime("%d/%m/%Y"),
                    "day_name": day_name,
                    "time": time_str,
                    "datetime_str": date_str + time_str.replace(":", ""),
                    "barber": barber,
                    "service_id": service_id,
                    "service_name": service_name,
                    "duration": duration
                })

        matching_slots.sort(key=lambda s: (s["date"], s["time"]))
        return matching_slots
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore ricerca slot: {e}")


@app.post("/api/book")
def book_slot(req: BookRequest):
    """Prenota manualmente uno slot."""
    client = get_client()
    try:
        success = client.book(req.datetime_str, req.service_id, req.barber)
        if success:
            service_name = client.get_service_name(req.service_id)
            dt = client.parse_datetime(req.datetime_str)
            dt_formatted = dt.strftime("%d/%m/%Y alle %H:%M")
            send_telegram(
                f"✅ <b>[BarberApp] Prenotazione Manuale Eseguita!</b>\n\n"
                f"📅 Data/Ora: <b>{dt_formatted}</b>\n"
                f"💇 Barbiere: <b>{req.barber}</b>\n"
                f"✂️ Servizio: <b>{service_name}</b>"
            )
            return {"success": True, "message": "Prenotazione effettuata con successo!"}
        else:
            raise HTTPException(status_code=400, detail="Impossibile prenotare: slot non più disponibile.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore prenotazione: {e}")


@app.delete("/api/reservations")
def cancel_reservation(req: CancelRequest):
    """Cancella una prenotazione esistente."""
    client = get_client()
    try:
        success = client.cancel(req.datetime_str, req.service_id, req.barber, req.price)
        if success:
            dt = client.parse_datetime(req.datetime_str)
            dt_formatted = dt.strftime("%d/%m/%Y alle %H:%M")
            send_telegram(
                f"❌ <b>[BarberApp] Prenotazione Cancellata</b>\n\n"
                f"📅 Data/Ora: <b>{dt_formatted}</b>\n"
                f"💇 Barbiere: <b>{req.barber}</b>\n\n"
                f"ℹ️ La prenotazione è stata annullata dall'interfaccia web."
            )
            return {"success": True, "message": "Prenotazione cancellata con successo!"}
        else:
            raise HTTPException(status_code=400, detail="Impossibile cancellare la prenotazione.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore cancellazione: {e}")


# ==========================================
# ENDPOINT SCHEDULER
# ==========================================

@app.get("/api/scheduler/status")
def get_scheduler_status():
    """Ritorna lo stato del monitor di auto-booking e il log dei controlli."""
    return scheduler.get_status()


@app.post("/api/scheduler/start")
def start_scheduler(req: SchedulerStartRequest):
    """Avvia il monitor di auto-booking."""
    started = scheduler.start(
        barber=req.barber,
        service_id=req.service_id,
        interval_minutes=req.interval_minutes,
        min_hour=req.min_hour,
        max_hour=req.max_hour,
        start_date=req.start_date,
        end_date=req.end_date,
        dry_run=req.dry_run
    )
    if not started:
        raise HTTPException(status_code=400, detail="Il monitor è già attivo o non è stato possibile avviarlo.")
    return {"success": True, "message": "Monitor avviato con successo!", "status": scheduler.get_status()}


@app.post("/api/scheduler/stop")
def stop_scheduler():
    """Arresta il monitor di auto-booking."""
    stopped = scheduler.stop()
    if not stopped:
        raise HTTPException(status_code=400, detail="Il monitor non è attualmente in esecuzione.")
    return {"success": True, "message": "Monitor arrestato con successo!", "status": scheduler.get_status()}


# ==========================================
# STATIC FILES & UI
# ==========================================

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_ui():
    """Serve la pagina web principale."""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Interfaccia web non trovata. Creare static/index.html"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_server:app", host="0.0.0.0", port=7525, reload=True)
