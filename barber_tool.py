#!/usr/bin/env python3
"""
BarberApp CLI Helper Tool
=========================
Interfaccia a riga di comando per consultare e prenotare tramite BarberAppClient.
Ideato per essere utilizzato sia da utenti che come strumento per l'agente Antigravity.
"""

import argparse
import sys
import json
from datetime import datetime, timedelta, time as datetime_time
import config
from barberapp_client import BarberAppClient

from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

def parse_date(date_str):
    for fmt in ("%Y-%m-%d", "%d%m%y", "%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(f"Invalid date format: {date_str}. Use YYYY-MM-DD or DDMMYY.")

def parse_time(time_str):
    for fmt in ("%H:%M", "%H%M"):
        try:
            return datetime.strptime(time_str, fmt).time()
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(f"Invalid time format: {time_str}. Use HH:MM.")

def get_date_range(args):
    # Determine the target timezone or local time context.
    # We will perform calculations relative to the current local date.
    today = datetime.now().date()
    start_date = None
    end_date = None

    if args.today:
        start_date = today
        end_date = today
    elif args.tomorrow:
        start_date = today + timedelta(days=1)
        end_date = today + timedelta(days=1)
    elif args.this_week:
        start_date = today
        # weekday() is 0 for Monday, 6 for Sunday
        days_to_sunday = 6 - today.weekday()
        end_date = today + timedelta(days=days_to_sunday)
    elif args.next_week:
        # Calculate next Monday (weekday=0)
        days_to_next_monday = 7 - today.weekday()
        start_date = today + timedelta(days=days_to_next_monday)
        end_date = start_date + timedelta(days=6)
    else:
        if args.start_date:
            start_date = args.start_date
        if args.end_date:
            end_date = args.end_date

    # Default start_date to today if not set
    if start_date is None:
        start_date = today

    return start_date, end_date

def get_matching_slots(client, args):
    start_date, end_date = get_date_range(args)
    
    # Reset schedule cache to get fresh slots
    client._schedule = None
    
    try:
        days = client.get_available_slots_for_barber(args.barber)
    except Exception as e:
        console.print(f"[bold red]Errore nel recupero degli orari dal server: {e}[/bold red]", file=sys.stderr)
        sys.exit(1)
        
    matching_slots = []
    
    # Get service info to display
    try:
        service_name = client.get_service_name(args.service)
    except Exception:
        service_name = f"Servizio #{args.service}"
        
    for day in days:
        date_str = day['Gi']
        try:
            day_date = client.parse_date(date_str).date()
        except Exception:
            continue
            
        # Filter by date
        if start_date and day_date < start_date:
            continue
        if end_date and day_date > end_date:
            continue
            
        slots = client.calculate_available_slots(date_str, args.barber, args.service)
        for time_str, slot_duration in slots:
            try:
                slot_time = datetime.strptime(time_str, "%H:%M").time()
            except Exception:
                continue
                
            # Filter by time
            if args.after_time and slot_time < args.after_time:
                continue
            if args.before_time and slot_time > args.before_time:
                continue
                
            time_hhmm = time_str.replace(":", "")
            datetime_str = date_str + time_hhmm
            
            matching_slots.append({
                "date": day_date.strftime("%Y-%m-%d"),
                "time": time_str,
                "datetime_str": datetime_str,
                "barber": args.barber,
                "service_id": args.service,
                "service_name": service_name,
                "duration": slot_duration
            })
            
    # Sort slots chronologically
    matching_slots.sort(key=lambda s: (s["date"], s["time"]))
    return matching_slots

def handle_list_slots(client, args):
    slots = get_matching_slots(client, args)
    
    if args.json:
        print(json.dumps(slots, indent=2))
        return
        
    if not slots:
        console.print("[yellow]Nessuno slot disponibile corrispondente ai criteri inseriti.[/yellow]")
        return
        
    table = Table(title=f"Slot Disponibili - Barbiere: {args.barber}", box=box.ROUNDED)
    table.add_column("Data", style="cyan")
    table.add_column("Giorno", style="magenta")
    table.add_column("Ora", style="green")
    table.add_column("Servizio", style="white")
    table.add_column("Durata Min", justify="right", style="yellow")
    table.add_column("Codice Prenotazione (datetime_str)", style="dim")
    
    for s in slots:
        dt = datetime.strptime(s["date"], "%Y-%m-%d")
        day_name = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'][dt.weekday()]
        table.add_row(
            dt.strftime("%d/%m/%Y"),
            day_name,
            s["time"],
            s["service_name"],
            str(s["duration"]),
            s["datetime_str"]
        )
        
    console.print(table)

def handle_book(client, args):
    target_slot = None
    
    if args.datetime:
        # User specified an exact datetime. Let's parse it.
        # Format can be DDMMYYHHmm or YYYY-MM-DD HH:MM
        val = args.datetime.replace(" ", "").replace("-", "").replace(":", "")
        if len(val) == 10:  # DDMMYYHHmm
            datetime_str = val
        else:
            try:
                # Try YYYY-MM-DD HH:MM
                dt = datetime.strptime(args.datetime, "%Y-%m-%d %H:%M")
                datetime_str = dt.strftime("%d%m%y%H%M")
            except ValueError:
                try:
                    # Try DD/MM/YYYY HH:MM
                    dt = datetime.strptime(args.datetime, "%d/%m/%Y %H:%M")
                    datetime_str = dt.strftime("%d%m%y%H%M")
                except ValueError:
                    console.print("[bold red]Formato datetime non valido. Usa DDMMYYHHmm o 'YYYY-MM-DD HH:MM'[/bold red]", file=sys.stderr)
                    sys.exit(1)
                    
        # Check if it is in available slots
        # For simplicity, parse it back to date/time to retrieve name and service details
        try:
            parsed_dt = datetime.strptime(datetime_str, "%d%m%y%H%M")
            date_part = parsed_dt.strftime("%Y-%m-%d")
            time_part = parsed_dt.strftime("%H:%M")
        except ValueError:
            console.print("[bold red]Errore nel parsing della data inserita.[/bold red]", file=sys.stderr)
            sys.exit(1)
            
        # Get service name
        try:
            service_name = client.get_service_name(args.service)
        except Exception:
            service_name = f"Servizio #{args.service}"
            
        target_slot = {
            "date": date_part,
            "time": time_part,
            "datetime_str": datetime_str,
            "barber": args.barber,
            "service_id": args.service,
            "service_name": service_name
        }
    elif args.first_available:
        # Search for first matching slot
        slots = get_matching_slots(client, args)
        if not slots:
            if args.json:
                print(json.dumps({"success": False, "error": "No matching slots found"}, indent=2))
            else:
                console.print("[red]Nessuno slot disponibile corrispondente ai criteri inseriti.[/red]")
            sys.exit(1)
        target_slot = slots[0]
    else:
        console.print("[bold red]Errore: specificare --datetime o --first-available[/bold red]", file=sys.stderr)
        sys.exit(1)
        
    # Output target slot details
    if args.json:
        if args.dry_run:
            print(json.dumps({"success": True, "dry_run": True, "slot": target_slot}, indent=2))
            return
    else:
        dt = datetime.strptime(target_slot["date"], "%Y-%m-%d")
        day_name = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'][dt.weekday()]
        console.print(f"[cyan]Riepilogo slot selezionato per la prenotazione:[/cyan]")
        console.print(f"  [bold]Data:[/bold] {day_name} {dt.strftime('%d/%m/%Y')}")
        console.print(f"  [bold]Ora:[/bold] {target_slot['time']}")
        console.print(f"  [bold]Barbiere:[/bold] {target_slot['barber']}")
        console.print(f"  [bold]Servizio:[/bold] [{target_slot['service_id']}] {target_slot['service_name']}")
        
    if args.dry_run:
        if not args.json:
            console.print("[yellow][DRY RUN] Prenotazione simulata. Nessuna richiesta inviata.[/yellow]")
        return
        
    # Book the slot
    success = client.book(target_slot["datetime_str"], target_slot["service_id"], target_slot["barber"])
    
    if args.json:
        print(json.dumps({"success": success, "slot": target_slot}))
    else:
        if success:
            console.print("[bold green]PRENOTAZIONE EFFETTUATA CON SUCCESSO![/bold green]")
        else:
            console.print("[bold red]ERRORE - Prenotazione fallita. Lo slot potrebbe non essere più disponibile.[/bold red]", file=sys.stderr)
            sys.exit(1)

def handle_list_reservations(client, args):
    try:
        pending = client.get_pending_reservations()
        confirmed = client.get_confirmed_reservations()
    except Exception as e:
        console.print(f"[bold red]Errore nel recupero delle prenotazioni: {e}[/bold red]", file=sys.stderr)
        sys.exit(1)
        
    if args.json:
        print(json.dumps({
            "pending": pending,
            "confirmed": confirmed
        }, indent=2))
        return
        
    if not pending and not confirmed:
        console.print("[yellow]Nessuna prenotazione attiva trovata.[/yellow]")
        return
        
    if pending:
        table_p = Table(title="Prenotazioni in Coda (Non Confermate)", box=box.ROUNDED)
        table_p.add_column("Data", style="cyan")
        table_p.add_column("Barbiere", style="white")
        table_p.add_column("Servizio", style="yellow")
        table_p.add_column("Telefono", style="dim")
        for r in pending:
            try:
                date = client.parse_date(r['Or'])
                date_str = date.strftime('%d/%m/%Y')
            except Exception:
                date_str = r['Or']
            
            service_id = r.get('Pe', 0)
            service_name = client.get_service_name(service_id) if hasattr(client, 'get_service_name') else f"Servizio #{service_id}"
            
            table_p.add_row(date_str, r['Pa'], service_name, r.get('Nm', ''))
        console.print(table_p)
        
    if confirmed:
        table_c = Table(title="Prenotazioni Confermate", box=box.ROUNDED)
        table_c.add_column("Data", style="cyan")
        table_c.add_column("Ora", style="green")
        table_c.add_column("Barbiere", style="white")
        table_c.add_column("Servizio", style="yellow")
        table_c.add_column("Codice (datetime_str)", style="dim")
        for r in confirmed:
            try:
                dt = client.parse_datetime(r['Or'])
                date_str = dt.strftime('%d/%m/%Y')
                time_str = dt.strftime('%H:%M')
            except Exception:
                date_str = r['Or']
                time_str = "-"
            
            service_id = r.get('Ti', 0)
            service_name = client.get_service_name(service_id) if hasattr(client, 'get_service_name') else f"Servizio #{service_id}"
            
            table_c.add_row(date_str, time_str, r['Pa'], service_name, r['Or'])
        console.print(table_c)

def handle_cancel(client, args):
    # Format code to cancel
    val = args.datetime.replace(" ", "").replace("-", "").replace(":", "")
    if len(val) == 10:  # DDMMYYHHmm
        datetime_str = val
    else:
        try:
            dt = datetime.strptime(args.datetime, "%Y-%m-%d %H:%M")
            datetime_str = dt.strftime("%d%m%y%H%M")
        except ValueError:
            try:
                dt = datetime.strptime(args.datetime, "%d/%m/%Y %H:%M")
                datetime_str = dt.strftime("%d%m%y%H%M")
            except ValueError:
                console.print("[bold red]Formato datetime non valido. Usa DDMMYYHHmm o 'YYYY-MM-DD HH:MM'[/bold red]", file=sys.stderr)
                sys.exit(1)
                
    try:
        service_name = client.get_service_name(args.service)
        price = client.get_service_price(args.service)
    except Exception:
        service_name = f"Servizio #{args.service}"
        price = 0.0
        
    if args.json:
        if args.dry_run:
            print(json.dumps({"success": True, "dry_run": True, "datetime": datetime_str}, indent=2))
            return
    else:
        console.print(f"[cyan]Riepilogo prenotazione da cancellare:[/cyan]")
        console.print(f"  [bold]Data/Ora (datetime_str):[/bold] {datetime_str}")
        console.print(f"  [bold]Barbiere:[/bold] {args.barber}")
        console.print(f"  [bold]Servizio:[/bold] [{args.service}] {service_name}")
        
    if args.dry_run:
        if not args.json:
            console.print("[yellow][DRY RUN] Cancellazione simulata. Nessuna richiesta inviata.[/yellow]")
        return
        
    success = client.cancel(datetime_str, args.service, args.barber, price)
    
    if args.json:
        print(json.dumps({"success": success}))
    else:
        if success:
            console.print("[bold green]PRENOTAZIONE CANCELLATA CON SUCCESSO![/bold green]")
        else:
            console.print("[bold red]ERRORE - Cancellazione fallita.[/bold red]", file=sys.stderr)
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="BarberApp CLI Helper Tool")
    subparsers = parser.add_subparsers(dest='command', required=True, help='Comando da eseguire')
    
    # list-slots subparser
    parser_list = subparsers.add_parser('list-slots', help='Visualizza gli slot liberi')
    parser_list.add_argument('--barber', default=config.PREFERRED_BARBER, help='Nome del barbiere')
    parser_list.add_argument('--service', type=int, default=config.PREFERRED_SERVICE_ID, help='ID del servizio')
    parser_list.add_argument('--today', action='store_true', help='Filtra per oggi')
    parser_list.add_argument('--tomorrow', action='store_true', help='Filtra per domani')
    parser_list.add_argument('--this-week', action='store_true', help='Filtra per questa settimana')
    parser_list.add_argument('--next-week', action='store_true', help='Filtra per la prossima settimana')
    parser_list.add_argument('--start-date', type=parse_date, help='Data inizio (YYYY-MM-DD o DDMMYY)')
    parser_list.add_argument('--end-date', type=parse_date, help='Data fine (YYYY-MM-DD o DDMMYY)')
    parser_list.add_argument('--after-time', type=parse_time, help='Solo dopo questa ora (HH:MM)')
    parser_list.add_argument('--before-time', type=parse_time, help='Solo prima di questa ora (HH:MM)')
    parser_list.add_argument('--json', action='store_true', help='Output in formato JSON')
    
    # book subparser
    parser_book = subparsers.add_parser('book', help='Prenota un appuntamento')
    parser_book.add_argument('--datetime', help='Data e ora (DDMMYYHHmm o YYYY-MM-DD HH:MM)')
    parser_book.add_argument('--first-available', action='store_true', help='Prenota il primo slot disponibile')
    parser_book.add_argument('--barber', default=config.PREFERRED_BARBER, help='Nome del barbiere')
    parser_book.add_argument('--service', type=int, default=config.PREFERRED_SERVICE_ID, help='ID del servizio')
    parser_book.add_argument('--today', action='store_true', help='Filtra per oggi')
    parser_book.add_argument('--tomorrow', action='store_true', help='Filtra per domani')
    parser_book.add_argument('--this-week', action='store_true', help='Filtra per questa settimana')
    parser_book.add_argument('--next-week', action='store_true', help='Filtra per la prossima settimana')
    parser_book.add_argument('--start-date', type=parse_date, help='Data inizio (YYYY-MM-DD o DDMMYY)')
    parser_book.add_argument('--end-date', type=parse_date, help='Data fine (YYYY-MM-DD o DDMMYY)')
    parser_book.add_argument('--after-time', type=parse_time, help='Solo dopo questa ora (HH:MM)')
    parser_book.add_argument('--before-time', type=parse_time, help='Solo prima di questa ora (HH:MM)')
    parser_book.add_argument('--dry-run', action='store_true', help='Simula la prenotazione senza effettuarla')
    parser_book.add_argument('--json', action='store_true', help='Output in formato JSON')
    
    # list-reservations subparser
    parser_res = subparsers.add_parser('list-reservations', help='Visualizza le prenotazioni esistenti')
    parser_res.add_argument('--json', action='store_true', help='Output in formato JSON')
    
    # cancel subparser
    parser_cancel = subparsers.add_parser('cancel', help='Cancella una prenotazione')
    parser_cancel.add_argument('--datetime', required=True, help='Data e ora della prenotazione da cancellare')
    parser_cancel.add_argument('--barber', default=config.PREFERRED_BARBER, help='Nome del barbiere')
    parser_cancel.add_argument('--service', type=int, default=config.PREFERRED_SERVICE_ID, help='ID del servizio')
    parser_cancel.add_argument('--dry-run', action='store_true', help='Simula la cancellazione')
    parser_cancel.add_argument('--json', action='store_true', help='Output in formato JSON')
    
    args = parser.parse_args()
    
    # Instantiate client
    client = BarberAppClient(
        user_id=config.BARBER_ID,
        username=config.USERNAME,
        password=config.PASSWORD
    )
    
    if args.command == 'list-slots':
        handle_list_slots(client, args)
    elif args.command == 'book':
        handle_book(client, args)
    elif args.command == 'list-reservations':
        handle_list_reservations(client, args)
    elif args.command == 'cancel':
        handle_cancel(client, args)

if __name__ == '__main__':
    main()
