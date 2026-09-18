#!/usr/bin/env python3
"""
BarberApp Background Scheduler
==============================
Worker in background per il monitoraggio e la prenotazione automatica degli slot
secondo le preferenze specificate dall'utente.
"""

import threading
import time
from datetime import datetime, timedelta, date as datetime_date
import requests as http_requests

import config
from barberapp_client import BarberAppClient


def send_telegram(message: str) -> bool:
    """Invia notifica Telegram se il bot e la chat sono configurati."""
    token = getattr(config, "TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(config, "TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = http_requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=10
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[Telegram Error] {e}")
def _parse_time_to_minutes(val: str | int | float | None) -> int | None:
    """Converte un valore orario (es. 18, '18', '18:30', '24:00') in minuti da mezzanotte."""
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return int(val * 60)
    val_str = str(val).strip()
    if not val_str:
        return None
    if ":" in val_str:
        parts = val_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    try:
        return int(val_str) * 60
    except ValueError:
        return None


class AutoBookScheduler:
    """Gestore del monitoraggio in background per l'auto-booking."""

    def __init__(self):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        # Configurazione corrente del task
        self.config_data = {
            "barber": config.PREFERRED_BARBER,
            "service_id": config.PREFERRED_SERVICE_ID,
            "interval_minutes": 10,
            "min_hour": None,
            "max_hour": None,
            "start_date": None,
            "end_date": None,
            "dry_run": False
        }

        # Stato di esecuzione
        self.status = "idle"  # idle | running | success | error | stopped
        self.last_check: str | None = None
        self.next_check: str | None = None
        self.checks_count = 0
        self.found_slot: dict | None = None
        self.booking_result: dict | None = None
        self.logs: list[dict] = []

    def _add_log(self, message: str, level: str = "info"):
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": message,
            "level": level
        }
        with self._lock:
            self.logs.append(entry)
            if len(self.logs) > 100:
                self.logs.pop(0)

    def get_status(self) -> dict:
        with self._lock:
            return {
                "status": self.status,
                "config": dict(self.config_data),
                "last_check": self.last_check,
                "next_check": self.next_check,
                "checks_count": self.checks_count,
                "found_slot": self.found_slot,
                "booking_result": self.booking_result,
                "logs": list(self.logs)
            }

    def start(
        self,
        barber: str | None = None,
        service_id: int | None = None,
        interval_minutes: int = 10,
        min_hour: int | None = None,
        max_hour: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        dry_run: bool = False
    ) -> bool:
        """Avvia il monitoraggio in un thread separato."""
        with self._lock:
            if self.status == "running":
                return False

            self.config_data = {
                "barber": barber or config.PREFERRED_BARBER,
                "service_id": service_id if service_id is not None else config.PREFERRED_SERVICE_ID,
                "interval_minutes": max(1, interval_minutes),
                "min_hour": min_hour,
                "max_hour": max_hour,
                "start_date": start_date,
                "end_date": end_date,
                "dry_run": dry_run
            }

            self.status = "running"
            self.checks_count = 0
            self.found_slot = None
            self.booking_result = None
            self._stop_event.clear()

        self._add_log(
            f"Monitor avviato per {self.config_data['barber']} (Servizio #{self.config_data['service_id']}) "
            f"ogni {self.config_data['interval_minutes']}m. Fascia oraria: "
            f"{self.config_data['min_hour'] or 'qualsiasi'}-{self.config_data['max_hour'] or 'qualsiasi'}."
            f"{' [MODALITÀ DRY-RUN]' if dry_run else ''}",
            "info"
        )

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> bool:
        """Ferma il monitoraggio attivo."""
        with self._lock:
            if self.status != "running":
                return False
            self.status = "stopped"
            self.next_check = None
            self._stop_event.set()

        self._add_log("Monitor arrestato manualmente dall'utente.", "warning")
        return True

    def _run_loop(self):
        """Loop di controllo in background."""
        client = BarberAppClient(
            user_id=config.BARBER_ID,
            username=config.USERNAME,
            password=config.PASSWORD
        )

        barber = self.config_data["barber"]
        service_id = self.config_data["service_id"]
        interval_secs = self.config_data["interval_minutes"] * 60
        min_mins = _parse_time_to_minutes(self.config_data["min_hour"])
        max_mins = _parse_time_to_minutes(self.config_data["max_hour"])
        dry_run = self.config_data["dry_run"]

        start_d: datetime_date | None = None
        end_d: datetime_date | None = None
        if self.config_data["start_date"]:
            try:
                start_d = datetime.strptime(self.config_data["start_date"], "%Y-%m-%d").date()
            except ValueError:
                pass
        if self.config_data["end_date"]:
            try:
                end_d = datetime.strptime(self.config_data["end_date"], "%Y-%m-%d").date()
            except ValueError:
                pass

        while not self._stop_event.is_set():
            now = datetime.now()
            with self._lock:
                self.last_check = now.strftime("%Y-%m-%d %H:%M:%S")
                self.checks_count += 1
                next_time = now + timedelta(seconds=interval_secs)
                self.next_check = next_time.strftime("%Y-%m-%d %H:%M:%S")

            self._add_log(f"Controllo #{self.checks_count} in corso...", "info")

            # Cerca gli slot
            try:
                client._schedule = None
                days = client.get_available_slots_for_barber(barber)
                found = None

                for day in days:
                    date_str = day["Gi"]
                    try:
                        day_date = client.parse_date(date_str).date()
                    except Exception:
                        continue

                    # Filtro date
                    if start_d and day_date < start_d:
                        continue
                    if end_d and day_date > end_d:
                        continue

                    slots = client.calculate_available_slots(date_str, barber, service_id)
                    for time_str, slot_duration in slots:
                        parts = time_str.split(":")
                        slot_mins = int(parts[0]) * 60 + int(parts[1])
                        if min_mins is not None and slot_mins < min_mins:
                            continue
                        if max_mins is not None and slot_mins >= max_mins:
                            continue

                        # Trovato!
                        found = {
                            "date_str": date_str,
                            "date": day_date.strftime("%Y-%m-%d"),
                            "time": time_str,
                            "datetime_str": date_str + time_str.replace(":", ""),
                            "barber": barber,
                            "service_id": service_id,
                            "duration": slot_duration
                        }
                        break
                    if found:
                        break

                if found:
                    service_name = client.get_service_name(service_id)
                    found["service_name"] = service_name
                    dt_formatted = f"{found['date']} alle {found['time']}"

                    if dry_run:
                        self._add_log(
                            f"[DRY-RUN] Trovato slot disponibile: {dt_formatted} con {barber} ({service_name}).",
                            "success"
                        )
                        send_telegram(
                            f"🔔 <b>[BarberApp - Dry Run] Slot Trovato!</b>\n\n"
                            f"📅 Data/Ora: <b>{dt_formatted}</b>\n"
                            f"💇 Barbiere: <b>{barber}</b>\n"
                            f"✂️ Servizio: <b>{service_name}</b>\n\n"
                            f"ℹ️ <i>Modalità simulazione attiva, nessuna prenotazione effettuata.</i>"
                        )
                        with self._lock:
                            self.status = "success"
                            self.found_slot = found
                            self.next_check = None
                        break
                    else:
                        self._add_log(
                            f"Slot trovato ({dt_formatted})! Tentativo di prenotazione in corso...",
                            "info"
                        )
                        success = client.book(found["datetime_str"], service_id, barber)
                        if success:
                            self._add_log(
                                f"PRENOTAZIONE EFFETTUATA CON SUCCESSO per {dt_formatted}!",
                                "success"
                            )
                            send_telegram(
                                f"🎉 <b>[BarberApp] Prenotazione Effettuata!</b>\n\n"
                                f"📅 Data e Ora: <b>{dt_formatted}</b>\n"
                                f"💇 Barbiere: <b>{barber}</b>\n"
                                f"✂️ Servizio: <b>{service_name}</b>\n\n"
                                f"✅ Il tuo appuntamento è stato confermato."
                            )
                            with self._lock:
                                self.status = "success"
                                self.found_slot = found
                                self.booking_result = {"success": True, "slot": found}
                                self.next_check = None
                            break
                        else:
                            self._add_log(
                                f"Lo slot {dt_formatted} non era più disponibile. Riprovo al prossimo ciclo.",
                                "warning"
                            )

                else:
                    self._add_log(f"Nessuno slot libero corrispondente ai criteri.", "info")

            except Exception as e:
                self._add_log(f"Errore durante il controllo API: {e}", "error")

            # Attesa per il prossimo ciclo (interrompibile via stop_event)
            if self._stop_event.wait(timeout=interval_secs):
                break


# Istanza singleton globale
scheduler = AutoBookScheduler()
