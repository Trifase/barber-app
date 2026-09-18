---
name: barber_booking
description: Consente di controllare la disponibilità di appuntamenti dal barbiere, visualizzare gli orari liberi, effettuare prenotazioni o cancellare appuntamenti per il taglio di capelli o barba.
---

# BarberApp Booking Skill Instructions

This skill integrates with the `barber_tool.py` CLI helper in the project root directory. Use it to answer user questions about availability, book appointments, list existing bookings, or cancel them.

## Available Actions

You have a helper tool at [barber_tool.py](file:///c:/Users/User/Antigravity/barber-app/barber_tool.py). Use `uv run barber_tool.py <command> <options>` to execute actions.

### 1. List Available Slots (`list-slots`)
Run this command when the user asks if there are free spots/slots.
Options:
- `--barber`: Defaults to `config.PREFERRED_BARBER` ("Giovanni") unless specified otherwise.
- `--service`: Defaults to `config.PREFERRED_SERVICE_ID` (10) unless the user specifies a different service type.
- `--today`, `--tomorrow`, `--this-week`, `--next-week`: Use for relative dates.
- `--after-time HH:MM`, `--before-time HH:MM`: Use to filter by time of day (e.g., "dopo le sette di sera" -> `--after-time 19:00`).
- `--start-date YYYY-MM-DD`, `--end-date YYYY-MM-DD`: Use for specific date ranges.
- `--json`: Get output in JSON format for programmatical parsing.

*Example*:
`uv run barber_tool.py list-slots --next-week --after-time 19:00 --json`

### 2. Book an Appointment (`book`)
Use this command to book a slot.
Options:
- `--first-available`: Finds and books the first slot matching the filters.
- `--datetime`: Books an exact date/time (DDMMYYHHmm or YYYY-MM-DD HH:MM).
- `--dry-run`: **CRITICAL**: Always run with `--dry-run` first to preview the booking slot and confirm with the user.
- Relative date and time filters are supported when used with `--first-available`.

*Critical Workflow*:
1. If the user asks to book (e.g., "prenota il prima possibile ma dopo le 19:00"):
   Run the command with `--dry-run --json` to inspect the target slot:
   `uv run barber_tool.py book --first-available --after-time 19:00 --dry-run --json`
2. Present the target slot details (Date, Time, Barber, Service) to the user and ask for confirmation.
3. Once the user explicitly confirms (e.g. "Sì", "Procedi", "Confermo"), run the booking command without `--dry-run`:
   `uv run barber_tool.py book --first-available --after-time 19:00`

### 3. List Existing Reservations (`list-reservations`)
Use this command when the user asks what reservations they have.
*Example*:
`uv run barber_tool.py list-reservations`

### 4. Cancel a Reservation (`cancel`)
Use this command when the user asks to cancel an appointment.
Options:
- `--datetime`: Datetime of the reservation (found via `list-reservations`).
- `--dry-run`: Always use first to confirm details.

*Critical Workflow*:
1. Run `uv run barber_tool.py list-reservations` to find the correct datetime.
2. Run `uv run barber_tool.py cancel --datetime <datetime> --dry-run` to preview the cancellation.
3. Ask the user for confirmation.
4. Run without `--dry-run` to perform the actual cancellation.

## Processing Relative Time & Context
- Pay attention to the metadata provided with user prompts (e.g. current local time/date) to formulate absolute dates if relative flags are not sufficient.
- The tool natively supports `--today`, `--tomorrow`, `--this-week`, and `--next-week`. Prefer these flags for relative expressions.
