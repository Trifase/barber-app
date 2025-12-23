#!/usr/bin/env python3
"""
BarberApp API Client
====================
Client per prenotare appuntamenti dal barbiere tramite API.

Reverse-engineered da: BarberApp by Softwareline
"""

import base64
import json
import requests

from datetime import datetime
from config import BARBER_ID, USERNAME, PASSWORD, PREFERRED_BARBER, PREFERRED_SERVICE_ID

from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()

# ============================================================
# CONFIGURAZIONE - Modifica questi valori
# ============================================================

# Credenziali utente
USER_ID = BARBER_ID
USERNAME = USERNAME
PASSWORD = PASSWORD

# Barbiere preferito (Giovanni)
PREFERRED_BARBER = PREFERRED_BARBER

# Servizio preferito (ID del servizio - vedi lista sotto)
# 0 = Taglio normale + shampoo (€13, 45min)
# 2 = Sopracciglia (€4, 15min)
# 3 = Barba corta (€5, 15min)
# 5 = Taglio pettine e forbice (€15, 45min)
# 10 = Taglio + barba (€18, 45min)
PREFERRED_SERVICE_ID = PREFERRED_SERVICE_ID

# ============================================================
# SEARCH FUNCTION (PUBLIC - NO AUTH)
# ============================================================

def search_nearby(lat: float, lon: float, radius: int = 10000, activity_type: int = 1) -> list[dict]:
    """
    Cerca attività nelle vicinanze (endpoint pubblico, non richiede autenticazione).
    
    Args:
        lat: Latitudine GPS
        lon: Longitudine GPS
        radius: Raggio di ricerca in metri (default 10km)
        activity_type: Tipo attività (1 = parrucchiere/barbiere)
    
    Returns:
        Lista di attività trovate con:
        - Key: ID da usare come user_id nelle richieste
        - Nome: Nome attività
        - Telefono: Numero telefono
        - Indirizzo: Indirizzo
        - Distanza: Distanza in metri
        - Lat, Lon: Coordinate GPS
    """
    url = "https://aws.bookappbusiness.com:2807/$1/0"
    
    # Payload pubblico: ///CercaAttivitaVicinaGet/tipo/lat/lon/raggio//
    payload = f"///CercaAttivitaVicinaGet/{activity_type}/{lat}/{lon}/{radius}//"
    encoded = base64.b64encode(payload.encode()).decode()
    
    response = requests.post(url, data=encoded, headers={
        "Content-Type": "text/plain; charset=utf-8",
        "User-Agent": "Dart/3.8 (dart:io)"
    })
    response.raise_for_status()
    
    # Decode response
    data = response.text
    if not data:
        return []
    
    padding = 4 - len(data) % 4
    if padding != 4:
        data += '=' * padding
    decoded = base64.b64decode(data).decode()
    
    return json.loads(decoded) if decoded else []


# ============================================================
# API CLIENT
# ============================================================

class BarberAppClient:
    """Client per BarberApp API"""
    
    BASE_URL = "https://aws.bookappbusiness.com:2807/$1/0"
    
    def __init__(self, user_id: str, username: str, password: str):
        self.user_id = user_id
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "text/plain; charset=utf-8",
            "User-Agent": "Dart/3.8 (dart:io)",
            "Accept-Encoding": "gzip"
        })
        
        # Cache
        self._barbers = None
        self._services = None
    
    def _encode(self, payload: str) -> str:
        """Codifica payload in Base64"""
        return base64.b64encode(payload.encode()).decode()
    
    def _decode(self, data: str) -> str:
        """Decodifica Base64 con gestione padding"""
        if not data:
            return ""
        padding = 4 - len(data) % 4
        if padding != 4:
            data += '=' * padding
        return base64.b64decode(data).decode()
    
    def _build_payload(self, action: str, *args) -> str:
        """Costruisce il payload con autenticazione"""
        parts = [self.user_id, self.username, self.password, action]
        parts.extend(str(a) for a in args)
        return "/".join(parts) + "/"
    
    def _request(self, action: str, *args) -> str:
        """Esegue richiesta API e ritorna risposta decodificata"""
        payload = self._build_payload(action, *args)
        encoded = self._encode(payload)
        
        response = self.session.post(self.BASE_URL, data=encoded)
        response.raise_for_status()
        
        return self._decode(response.text)
    
    def _request_json(self, action: str, *args) -> dict | list:
        """Esegue richiesta API e ritorna JSON parsato"""
        result = self._request(action, *args)
        if not result:
            return []
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            print(f"Action: {action}, result: {result}")
            return []
    
    # ==================== ENDPOINTS ====================
    
    def init(self) -> str:
        """Inizializza app e ottiene info negozio"""
        return self._request("InitGet", "403", "0", "A")
    
    def get_last_update(self) -> str:
        """Ottiene timestamp ultimo aggiornamento (DDMMYYHHMMSS)"""
        return self._request("LastUpdateGet", "")
    
    def get_barbers(self) -> list[dict]:
        """Ottiene lista barbieri"""
        if self._barbers is None:
            self._barbers = self._request_json("ParrucchieriGetMobile", "")
        return self._barbers
    
    def get_services(self) -> dict:
        """Ottiene lista servizi con nomi, descrizioni e prezzi"""
        if self._services is None:
            self._services = self._request_json("ServiziAppFlutter", "")
        return self._services
    
    def get_pending_reservations(self) -> dict | list:
        """Ottiene prenotazioni in coda (non confermate)"""
        return self._request_json(
            "PrenotazioniSospeseMobileGet",
            self.username, "", "", "", "", "", "", ""
        )
    
    def get_confirmed_reservations(self) -> dict | list:
        """Ottiene prenotazioni confermate"""
        return self._request_json(
            "PrenotazioniMobileGet",
            self.username, "", "", "", "", "", "", ""
        )
    
    def get_schedule(self) -> dict | list:
        """Ottiene slot disponibili per tutti i barbieri"""
        if not hasattr(self, '_schedule') or self._schedule is None:
            self._schedule = self._request_json("OrariGet", "")
        return self._schedule
    
    def join_queue(self, date: str, barber: str, service_id: int = 0) -> bool:
        """
        Mettiti in coda per un giorno specifico.
        
        Args:
            date: Data in formato DDMMYY (es. "231225" per 23/12/25)
            barber: Nome barbiere (es. "Giovanni")
            service_id: ID servizio (default 0)
        
        Returns:
            True se successo
        """
        result = self._request("PrenotaSospesoAdd", date, service_id, 0, barber)
        return result.startswith("OK")
    
    def leave_queue(self, date: str) -> bool:
        """
        Esci dalla coda per un giorno specifico.
        
        Args:
            date: Data in formato DDMMYY
        
        Returns:
            True se successo
        """
        result = self._request("PrenotazioneSospesaDelete", self.username, date, "")
        return result.startswith("OK")
    
    def book(self, datetime_str: str, service_id: int, barber: str) -> bool:
        """
        Prenota un appuntamento.
        
        Args:
            datetime_str: Data e ora in formato DDMMYYHHmm (es. "2412251115" per 24/12/25 11:15)
            service_id: ID servizio
            barber: Nome barbiere
        
        Returns:
            True se successo
        """
        result = self._request(
            "PrenotazioneAdd",
            datetime_str, service_id, barber, "", 0,
            "", "", "", "", "", "", "", "",
            service_id, "", ""
        )
        return result.startswith("OK")
    
    def cancel(self, datetime_str: str, service_id: int, barber: str, price: float = 0.0) -> bool:
        """
        Cancella un appuntamento.
        
        Args:
            datetime_str: Data e ora in formato DDMMYYHHmm
            service_id: ID servizio
            barber: Nome barbiere
            price: Prezzo del servizio
        
        Returns:
            True se successo
        """
        result = self._request(
            "PrenotazioneDelete",
            self.username, datetime_str, 0, barber, "", 0, "", price, service_id, ""
        )
        return result.startswith("OK")
    
    # ==================== HELPER METHODS ====================
    
    def get_service_name(self, service_id: int) -> str:
        """Ottiene nome servizio da ID"""
        services = self.get_services()
        try:
            if 0 <= service_id < len(services['Nome']):
                return services['Nome'][service_id]
        except Exception:
            return ""
        return f"Servizio #{service_id}"
    
    def get_service_price(self, service_id: int) -> float:
        """Ottiene prezzo servizio da ID"""
        services = self.get_services()
        if 0 <= service_id < len(services['Prezzo']):
            return services['Prezzo'][service_id]
        return 0.0
    
    def format_datetime(self, dt: datetime) -> str:
        """Formatta datetime per API (DDMMYYHHmm)"""
        return dt.strftime("%d%m%y%H%M")
    
    def format_date(self, dt: datetime) -> str:
        """Formatta data per API (DDMMYY)"""
        return dt.strftime("%d%m%y")
    
    def parse_datetime(self, api_str: str) -> datetime:
        """Parsa datetime da API (DDMMYYHHmm)"""
        return datetime.strptime(api_str, "%d%m%y%H%M")
    
    def parse_date(self, api_str: str) -> datetime:
        """Parsa data da API (DDMMYY)"""
        return datetime.strptime(api_str, "%d%m%y")
    
    def get_available_slots_for_barber(self, barber: str) -> list[dict]:
        """Ottiene giorni disponibili per un barbiere specifico"""
        schedule = self.get_schedule()
        return [s for s in schedule if s['Pa'] == barber and not s['Fe']]
    
    def get_service_duration(self, barber: str, service_id: int) -> int:
        """Ottiene durata servizio in minuti per un barbiere specifico"""
        barbers = self.get_barbers()
        for b in barbers:
            if b['Nome'] == barber:
                if 0 <= service_id < len(b['MinutiTaglioArr']):
                    return b['MinutiTaglioArr'][service_id]
                return b['MinutiTaglio']  # Default
        return 45  # Fallback
    
    def get_working_hours(self, weekday: int) -> list[tuple[int, int]]:
        """
        Ottiene orari di lavoro per giorno della settimana.
        
        Args:
            weekday: 0=lunedì, 1=martedì, ..., 6=domenica
        
        Returns:
            Lista di tuple (ora_inizio_minuti, ora_fine_minuti)
        """
        # Orari del negozio (da InitGet)
        # Lunedì: CHIUSO
        # Martedì-Venerdì: 8:30-13:00, 15:00-20:00
        # Sabato: 8:30-18:00
        # Domenica: CHIUSO
        
        if weekday == 0 or weekday == 6:  # Lunedì o Domenica
            return []
        elif weekday == 5:  # Sabato
            return [(8*60+30, 18*60)]  # 8:30 - 18:00
        else:  # Martedì-Venerdì
            return [(8*60+30, 13*60), (15*60, 20*60)]  # 8:30-13:00, 15:00-20:00
    
    def calculate_available_slots(
        self, 
        date_str: str, 
        barber: str, 
        service_id: int
    ) -> list[tuple[str, int]]:
        """
        Ottiene gli slot orari disponibili per una data specifica.
        
        NOTA: Il campo 'Pr' in OrariGet contiene gli slot DISPONIBILI,
        non le prenotazioni esistenti!
        
        Args:
            date_str: Data in formato DDMMYY
            barber: Nome barbiere
            service_id: ID servizio per filtrare per durata
        
        Returns:
            Lista di tuple (orario, durata_slot) es. [("11:15", 15), ...]
        """
        # Ottieni durata richiesta dal servizio
        required_duration = self.get_service_duration(barber, service_id)
        
        schedule = self.get_schedule()
        available = []
        
        for s in schedule:
            if s['Gi'] == date_str and s['Pa'] == barber:
                # Pr contiene gli slot DISPONIBILI
                for slot in s.get('Pr', []):
                    # slot['Or'] = DDMMYYHHmm, slot['Sl'] = durata in minuti
                    slot_duration = slot.get('Sl', 0)
                    
                    # Filtra: mostra solo slot con durata sufficiente
                    if slot_duration >= required_duration:
                        if len(slot.get('Or', '')) >= 10:
                            time_part = slot['Or'][6:10]  # HHmm
                            hours = int(time_part[:2])
                            minutes = int(time_part[2:])
                            available.append((f"{hours:02d}:{minutes:02d}", slot_duration))
        
        return available


# ============================================================
# FUNZIONI DI UTILITÀ - Ritornano tabelle per il dashboard
# ============================================================

def get_services_table(client: BarberAppClient) -> Table:
    """Crea tabella servizi disponibili"""
    services = client.get_services()
    barbers = client.get_barbers()
    durations = barbers[0]['MinutiTaglioArr'] if barbers else []
    
    table = Table(title="📋 Servizi", box=box.SIMPLE, expand=True)
    table.add_column("ID", justify="right", style="cyan", width=3)
    table.add_column("Servizio", style="white", no_wrap=False)
    table.add_column("€", justify="right", style="green")
    table.add_column("Min", justify="right", style="yellow")
    
    try:
        for i, (name, price) in enumerate(zip(services['Nome'], services['Prezzo'])):
            if name and price > 0:
                duration = durations[i] if i < len(durations) else 0
                table.add_row(str(i), name.strip()[:50], f"{price:.0f} €", str(duration) + " min")
    except Exception:
        return Table()
    return table


def get_barbers_table(client: BarberAppClient) -> Table:
    """Crea tabella barbieri"""
    barbers = client.get_barbers()
    
    table = Table(title="💇 Barbieri", box=box.SIMPLE, expand=True)
    table.add_column("ID", justify="right", style="cyan", width=3)
    table.add_column("Nome", style="white")
    # table.add_column("Min", justify="right", style="yellow", width=4)
    
    for b in barbers:
        if not b['Nascosto']:
            table.add_row(str(b['Id']), b['Nome'])
    
    return table


def get_reservations_table(client: BarberAppClient) -> Table:
    """Crea tabella prenotazioni"""
    pending = client.get_pending_reservations()
    confirmed = client.get_confirmed_reservations()
    
    table = Table(title="📌 Prenotazioni", box=box.SIMPLE, expand=True)
    table.add_column("", width=2)
    table.add_column("Data", style="cyan")
    table.add_column("Ora", style="cyan", width=5)
    table.add_column("Barbiere", style="white")
    
    if not pending and not confirmed:
        table.add_row("[dim]-[/dim]", "[dim]Nessuna[/dim]", "", "")
        return table
    
    for r in pending:
        date = client.parse_date(r['Or'])
        table.add_row("⏳", date.strftime('%d/%m'), "-", r['Pa'])
    
    for r in confirmed:
        dt = client.parse_datetime(r['Or'])
        table.add_row("✅", dt.strftime('%d/%m'), dt.strftime('%H:%M'), r['Pa'])
    
    return table


def get_slots_table(client: BarberAppClient, barber: str, service_id: int) -> Table:
    """Crea tabella slot disponibili"""
    table = Table(title="🕐 Slot Disponibili", box=box.SIMPLE, expand=True)
    table.add_column("Giorno", style="cyan", width=10)
    table.add_column("Mattina", style="white")
    table.add_column("Pomeriggio", style="white")
    
    days = client.get_available_slots_for_barber(barber)
    
    if not days:
        table.add_row("[dim]-[/dim]", "[dim]Nessun giorno[/dim]", "")
        return table
    
    for day in days:
        date_str = day['Gi']
        date = client.parse_date(date_str)
        day_name = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'][date.weekday()]
        
        slots = client.calculate_available_slots(date_str, barber, service_id)
        
        if slots:
            morning = [t for t, d in slots if int(t[:2]) < 13]
            afternoon = [t for t, d in slots if int(t[:2]) >= 15]
            
            table.add_row(
                f"{day_name} {date.strftime('%d/%m')}",
                ", ".join(morning) if morning else "[dim]-[/dim]",
                ", ".join(afternoon) if afternoon else "[dim]-[/dim]"
            )
        else:
            table.add_row(
                f"{day_name} {date.strftime('%d/%m')}",
                "[red]Occupato[/red]",
                "[red]Occupato[/red]"
            )
    
    return table


def show_dashboard(client: BarberAppClient, selected_service_id: int):  # pragma: no cover
    """Mostra dashboard principale"""
    console.clear()
    
    # Header
    service_name = client.get_service_name(selected_service_id)
    if service_name is None:
        service_name = "Servizio #" + str(selected_service_id)
    header = Panel(
        f"[bold white]👤 {USERNAME}[/bold white] • "
        f"[cyan]💇 {PREFERRED_BARBER}[/cyan] • "
        f"[yellow]✂️  [{selected_service_id}] {service_name}[/yellow]",
        title="🏪 BARBERAPP CLIENT",
        box=box.DOUBLE
    )
    console.print(header)
    
    # Layout principale usando Table per controllo migliore
    services_table = get_services_table(client)
    barbers_table = get_barbers_table(client)
    reservations_table = get_reservations_table(client)
    slots_table = get_slots_table(client, PREFERRED_BARBER, selected_service_id)
    
    # Right side: barbers + reservations + slots stacked
    right_content = Group(barbers_table, Text(""), slots_table, Text(""), reservations_table)
    
    # Menu commands
    menu = Table(box=box.SIMPLE, show_header=False, expand=True)
    menu.add_column("Cmd", style="bold cyan", width=1)
    menu.add_column("Descrizione", style="white", justify="left")
    menu.add_row("s", "✂️  Cambia servizio")
    menu.add_row("b", "📅 Prenota appuntamento")
    menu.add_row("c", "❌ Cancella prenotazione")
    menu.add_row("r", "🔄 Aggiorna")
    menu.add_row("q", "🚪 Esci")
    
    # Layout con Table (2 colonne affiancate senza spazio)
    layout_table = Table.grid(padding=(0, 1))
    layout_table.add_column("left", ratio=2)
    layout_table.add_column("right", ratio=1)
    
    layout_table.add_row(
        Panel(services_table, title="Servizi", box=box.ROUNDED, padding=(0, 1)),
        Panel(right_content, title="Info", box=box.ROUNDED, padding=(0, 1))
    )
    
    # Menu row spans both columns
    layout_table.add_row(
        Panel(menu, title="📌 Comandi", box=box.ROUNDED, padding=(0, 1)),
        ""
    )
    
    console.print(layout_table)


def select_service(client: BarberAppClient, current_service_id: int) -> int:  # pragma: no cover
    """Seleziona un nuovo servizio"""
    console.print("\n[bold]Inserisci l'ID del nuovo servizio:[/bold]")
    try:
        new_id = int(console.input("[cyan]Nuovo ID servizio:[/cyan] ").strip())
        
        # Verifica se il servizio esiste
        services = client.get_services()
        if 0 <= new_id < len(services['Nome']) and services['Nome'][new_id]:
            console.print(f"[green]✅ Servizio cambiato: {services['Nome'][new_id]}[/green]")
            return new_id
        else:
            console.print("[red]❌ ID servizio non valido[/red]")
            return current_service_id
    except ValueError:
        console.print("[red]❌ Inserisci un numero valido[/red]")
        return current_service_id


def book_appointment(client: BarberAppClient, current_service_id: int) -> int:  # pragma: no cover
    """
    Flusso prenotazione multi-step:
    1. Seleziona/conferma servizio
    2. Seleziona data con slot disponibili
    3. Seleziona orario
    4. Conferma e prenota
    
    Returns:
        Il service_id selezionato (per aggiornare il dashboard)
    """
    console.print("\n[bold]📅 NUOVA PRENOTAZIONE[/bold]\n")
    
    # Step 1: Servizio
    service_id = current_service_id
    service_name = client.get_service_name(service_id)
    duration = client.get_service_duration(PREFERRED_BARBER, service_id)
    price = client.get_service_price(service_id)
    
    console.print(f"[cyan]Servizio attuale:[/cyan] [{service_id}] {service_name} (€{price:.0f}, {duration}min)")
    change = console.input("[dim]Cambiare servizio? (s/n, default n):[/dim] ").strip().lower()
    
    if change == 's':
        try:
            new_id = int(console.input("[cyan]Nuovo ID servizio:[/cyan] ").strip())
            services = client.get_services()
            if 0 <= new_id < len(services['Nome']) and services['Nome'][new_id]:
                service_id = new_id
                service_name = client.get_service_name(service_id)
                duration = client.get_service_duration(PREFERRED_BARBER, service_id)
                price = client.get_service_price(service_id)
                console.print(f"[green]✅ Servizio: {service_name}[/green]")
            else:
                console.print("[yellow]ID non valido, uso servizio attuale[/yellow]")
        except ValueError:
            console.print("[yellow]Input non valido, uso servizio attuale[/yellow]")
    
    # Step 2: Mostra date disponibili
    console.print(f"\n[cyan]Cercando slot disponibili per {PREFERRED_BARBER}...[/cyan]\n")
    
    # Refresh schedule
    client._schedule = None
    days = client.get_available_slots_for_barber(PREFERRED_BARBER)
    
    available_days = []
    for day in days:
        date_str = day['Gi']
        slots = client.calculate_available_slots(date_str, PREFERRED_BARBER, service_id)
        if slots:
            date = client.parse_date(date_str)
            day_name = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'][date.weekday()]
            available_days.append({
                'date_str': date_str,
                'date': date,
                'day_name': day_name,
                'slots': slots
            })
    
    if not available_days:
        console.print("[red]❌ Nessun giorno disponibile per questo servizio[/red]")
        return service_id
    
    # Mostra date
    console.print("[bold]Date disponibili:[/bold]")
    for i, d in enumerate(available_days):
        slot_count = len(d['slots'])
        console.print(f"  [{i}] {d['day_name']} {d['date'].strftime('%d/%m/%Y')} ({slot_count} slot)")
    
    # Selezione data
    try:
        day_idx = int(console.input("\n[cyan]Seleziona data (numero):[/cyan] ").strip())
        if day_idx < 0 or day_idx >= len(available_days):
            console.print("[red]❌ Selezione non valida[/red]")
            return service_id
    except ValueError:
        console.print("[red]❌ Input non valido[/red]")
        return service_id
    
    selected_day = available_days[day_idx]
    
    # Step 3: Mostra orari
    console.print(f"\n[bold]Orari disponibili per {selected_day['day_name']} {selected_day['date'].strftime('%d/%m')}:[/bold]")
    slots = selected_day['slots']
    
    for i, (time_str, slot_duration) in enumerate(slots):
        console.print(f"  [{i}] {time_str}")
    
    # Selezione orario
    try:
        slot_idx = int(console.input("\n[cyan]Seleziona orario (numero):[/cyan] ").strip())
        if slot_idx < 0 or slot_idx >= len(slots):
            console.print("[red]❌ Selezione non valida[/red]")
            return service_id
    except ValueError:
        console.print("[red]❌ Input non valido[/red]")
        return service_id
    
    selected_time, _ = slots[slot_idx]
    time_hhmm = selected_time.replace(":", "")  # "11:15" -> "1115"
    datetime_str = selected_day['date_str'] + time_hhmm
    
    # Step 4: Conferma
    console.print("\n[bold]📋 RIEPILOGO PRENOTAZIONE[/bold]")
    console.print(f"  [cyan]Data:[/cyan] {selected_day['day_name']} {selected_day['date'].strftime('%d/%m/%Y')}")
    console.print(f"  [cyan]Ora:[/cyan] {selected_time}")
    console.print(f"  [cyan]Servizio:[/cyan] {service_name}")
    console.print(f"  [cyan]Prezzo:[/cyan] €{price:.0f}")
    console.print(f"  [cyan]Barbiere:[/cyan] {PREFERRED_BARBER}")
    
    confirm = console.input("\n[yellow]Confermi la prenotazione? (s/n):[/yellow] ").strip().lower()
    
    if confirm != 's':
        console.print("[dim]Prenotazione annullata[/dim]")
        return service_id
    
    # Prenota
    console.print("\n[cyan]Invio richiesta...[/cyan]")
    success = client.book(datetime_str, service_id, PREFERRED_BARBER)
    
    if success:
        console.print("[bold green]✅ PRENOTAZIONE EFFETTUATA![/bold green]")
        # Refresh schedule cache
        client._schedule = None
    else:
        console.print("[bold red]❌ ERRORE - Orario non più disponibile[/bold red]")
    
    return service_id


def cancel_appointment(client: BarberAppClient):  # pragma: no cover
    """
    Cancella una prenotazione esistente:
    1. Mostra prenotazioni attive
    2. Seleziona quale cancellare
    3. Conferma e cancella
    """
    console.print("\n[bold]❌ CANCELLA PRENOTAZIONE[/bold]\n")
    
    # Ottieni prenotazioni confermate
    confirmed = client.get_confirmed_reservations()
    
    if not confirmed:
        console.print("[yellow]Non hai prenotazioni da cancellare[/yellow]")
        return
    
    # Mostra prenotazioni
    console.print("[bold]Le tue prenotazioni:[/bold]")
    for i, r in enumerate(confirmed):
        dt = client.parse_datetime(r['Or'])
        service_name = client.get_service_name(r['Ti'])
        day_name = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'][dt.weekday()]
        console.print(f"  [{i}] {day_name} {dt.strftime('%d/%m/%Y %H:%M')} - {r['Pa']} - {service_name}")
    
    # Selezione
    try:
        idx = int(console.input("\n[cyan]Seleziona prenotazione da cancellare (numero):[/cyan] ").strip())
        if idx < 0 or idx >= len(confirmed):
            console.print("[red]❌ Selezione non valida[/red]")
            return
    except ValueError:
        console.print("[red]❌ Input non valido[/red]")
        return
    
    selected = confirmed[idx]
    dt = client.parse_datetime(selected['Or'])
    service_name = client.get_service_name(selected['Ti'])
    price = client.get_service_price(selected['Ti'])
    
    # Conferma
    console.print("\n[bold]Stai per cancellare:[/bold]")
    console.print(f"  [cyan]Data:[/cyan] {dt.strftime('%d/%m/%Y %H:%M')}")
    console.print(f"  [cyan]Servizio:[/cyan] {service_name}")
    console.print(f"  [cyan]Barbiere:[/cyan] {selected['Pa']}")
    
    confirm = console.input("\n[yellow]Confermi la cancellazione? (s/n):[/yellow] ").strip().lower()
    
    if confirm != 's':
        console.print("[dim]Cancellazione annullata[/dim]")
        return
    
    # Cancella
    console.print("\n[cyan]Invio richiesta...[/cyan]")
    datetime_str = selected['Or']  # Already in DDMMYYHHmm format
    success = client.cancel(datetime_str, selected['Ti'], selected['Pa'], price)
    
    if success:
        console.print("[bold green]✅ PRENOTAZIONE CANCELLATA![/bold green]")
        # Refresh cache
        client._schedule = None
    else:
        console.print("[bold red]❌ ERRORE nella cancellazione[/bold red]")


def interactive_menu(client: BarberAppClient):  # pragma: no cover
    """Menu interattivo"""
    current_service_id = PREFERRED_SERVICE_ID
    
    while True:
        show_dashboard(client, current_service_id)
        
        choice = console.input("\n[bold cyan]Comando:[/bold cyan] ").strip().lower()
        
        if choice == 's':
            current_service_id = select_service(client, current_service_id)
            console.input("\n[dim]Premi INVIO per continuare...[/dim]")
        
        elif choice == 'b':
            result = book_appointment(client, current_service_id)
            if result:
                current_service_id = result  # Update service if changed during booking
            console.input("\n[dim]Premi INVIO per continuare...[/dim]")
        
        elif choice == 'c':
            cancel_appointment(client)
            console.input("\n[dim]Premi INVIO per continuare...[/dim]")
        
        elif choice == 'r':
            # Refresh - clear cache
            client._barbers = None
            client._services = None
            client._schedule = None
            console.print("[green]✅ Dati aggiornati![/green]")
        
        elif choice == 'q':
            console.print("[bold]Arrivederci! 👋[/bold]")
            break
        
        else:
            pass  # Ignora comandi non validi, ricarica dashboard



# ============================================================
# MAIN
# ============================================================

def main():  # pragma: no cover
    """Entry point"""
    client = BarberAppClient(
        user_id=USER_ID,
        username=USERNAME,
        password=PASSWORD
    )
    
    interactive_menu(client)


# Per testare la prenotazione, decommenta la riga seguente:
# test_booking()

if __name__ == "__main__":
    main()
