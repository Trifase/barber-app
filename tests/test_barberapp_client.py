"""
Unit tests for BarberAppClient.

These tests use mocked HTTP responses and don't require real credentials.
"""
import base64
import json
from datetime import datetime

import barberapp_client as client_module

import pytest
import responses
from rich.console import Console


# =============================================================================
# MOCK DATA (duplicated from conftest.py for direct import)
# =============================================================================

MOCK_BARBERS = [
    {
        "Id": 1,
        "Nome": "Giovanni",
        "Nascosto": False,
        "MinutiTaglio": 45,
        "MinutiTaglioArr": [45, 15, 15, 15, 30, 45, 30, 30, 60, 30, 45]
    },
    {
        "Id": 2,
        "Nome": "Marco",
        "Nascosto": False,
        "MinutiTaglio": 45,
        "MinutiTaglioArr": [45, 15, 15, 15, 30, 45, 30, 30, 60, 30, 45]
    },
    {
        "Id": 3,
        "Nome": "Hidden",
        "Nascosto": True,
        "MinutiTaglio": 45,
        "MinutiTaglioArr": [45, 15, 15, 15, 30, 45, 30, 30, 60, 30, 45]
    }
]

MOCK_SERVICES = {
    "Nome": [
        "Taglio normale + shampoo",
        "Colore",
        "Sopracciglia",
        "Barba corta",
        "",
        "Taglio pettine e forbice",
        "",
        "",
        "",
        "",
        "Taglio + barba"
    ],
    "Prezzo": [13.0, 0.0, 4.0, 5.0, 0.0, 15.0, 0.0, 0.0, 0.0, 0.0, 18.0],
    "Descrizione": ["", "", "", "", "", "", "", "", "", "", ""]
}

MOCK_SCHEDULE = [
    {
        "Gi": "231225",
        "Pa": "Giovanni",
        "Fe": False,
        "Pr": [
            {"Or": "2312251115", "Sl": 45},
            {"Or": "2312251200", "Sl": 30},
            {"Or": "2312251530", "Sl": 60}
        ]
    },
    {
        "Gi": "231225",
        "Pa": "Marco",
        "Fe": False,
        "Pr": [
            {"Or": "2312251000", "Sl": 45}
        ]
    },
    {
        "Gi": "241225",
        "Pa": "Giovanni",
        "Fe": True,
        "Pr": []
    }
]

MOCK_CONFIRMED_RESERVATIONS = [
    {"Or": "2312251115", "Pa": "Giovanni", "Ti": 0}
]

MOCK_PENDING_RESERVATIONS = [
    {"Or": "241225", "Pa": "Giovanni"}
]


class DummyConsole:
    """Simple console stub to capture outputs/inputs in CLI-oriented tests."""

    def __init__(self, inputs=None):
        self.inputs = list(inputs or [])
        self.print_calls = []
        self.clear_called = False

    def clear(self):
        self.clear_called = True

    def print(self, *args, **kwargs):
        self.print_calls.append((args, kwargs))

    def input(self, prompt=""):
        self.print_calls.append(((prompt,), {}))
        if self.inputs:
            return self.inputs.pop(0)
        return ""


@pytest.fixture
def ui_client(mock_client, monkeypatch):
    """BarberAppClient preloaded with mock data for UI helper tests."""
    mock_client._services = MOCK_SERVICES
    mock_client._barbers = MOCK_BARBERS
    mock_client._schedule = MOCK_SCHEDULE
    mock_client.get_pending_reservations = lambda: MOCK_PENDING_RESERVATIONS
    mock_client.get_confirmed_reservations = lambda: MOCK_CONFIRMED_RESERVATIONS

    def fake_request_json(action, *args, **kwargs):
        if action == "OrariGet":
            return MOCK_SCHEDULE
        return []

    mock_client._request_json = fake_request_json
    monkeypatch.setattr(client_module, "PREFERRED_BARBER", "Giovanni")
    monkeypatch.setattr(client_module, "PREFERRED_SERVICE_ID", 0)
    return mock_client


@pytest.fixture
def console_factory(monkeypatch):
    """Factory that swaps the module console with a dummy instance."""
    def _factory(inputs=None):
        dummy = DummyConsole(inputs)
        monkeypatch.setattr(client_module, "console", dummy)
        return dummy
    return _factory


class TestEncoding:
    """Tests for encoding/decoding methods."""
    
    def test_encode_simple_string(self, mock_client):
        """Test base64 encoding."""
        result = mock_client._encode("hello")
        assert result == base64.b64encode(b"hello").decode()
    
    def test_encode_with_special_chars(self, mock_client):
        """Test encoding with special characters."""
        payload = "user/pass/action/"
        result = mock_client._encode(payload)
        # Should be valid base64
        decoded = base64.b64decode(result)
        assert decoded.decode() == payload
    
    def test_decode_empty_string(self, mock_client):
        """Test decoding empty string returns empty."""
        assert mock_client._decode("") == ""
    
    def test_decode_with_padding(self, mock_client):
        """Test decoding handles missing padding."""
        # Base64 without proper padding
        original = "test data"
        encoded = base64.b64encode(original.encode()).decode()
        # Remove padding
        encoded_no_padding = encoded.rstrip("=")
        
        result = mock_client._decode(encoded_no_padding)
        assert result == original
    
    def test_decode_properly_padded(self, mock_client):
        """Test decoding works with proper padding."""
        original = "test data"
        encoded = base64.b64encode(original.encode()).decode()
        
        result = mock_client._decode(encoded)
        assert result == original
    
    def test_decode_restores_missing_padding(self, mock_client):
        """Test decoding adds padding when needed."""
        # "a" encoded is "YQ==", trim padding to force branch.
        assert mock_client._decode("YQ") == "a"


class TestPayloadBuilding:
    """Tests for payload construction."""
    
    def test_build_payload_basic(self, mock_client):
        """Test basic payload structure."""
        result = mock_client._build_payload("TestAction")
        expected = "test_shop_id/test_user/test_pass/TestAction/"
        assert result == expected
    
    def test_build_payload_with_args(self, mock_client):
        """Test payload with additional arguments."""
        result = mock_client._build_payload("TestAction", "arg1", 123, "arg3")
        expected = "test_shop_id/test_user/test_pass/TestAction/arg1/123/arg3/"
        assert result == expected
    
    def test_build_payload_empty_args(self, mock_client):
        """Test payload handles empty string args."""
        result = mock_client._build_payload("Action", "", "value", "")
        expected = "test_shop_id/test_user/test_pass/Action//value//"
        assert result == expected


class TestDateFormatting:
    """Tests for date/time formatting and parsing."""
    
    def test_format_datetime(self, mock_client):
        """Test datetime formatting for API (DDMMYYHHmm)."""
        dt = datetime(2025, 12, 24, 11, 15)
        result = mock_client.format_datetime(dt)
        assert result == "2412251115"
    
    def test_format_date(self, mock_client):
        """Test date formatting for API (DDMMYY)."""
        dt = datetime(2025, 12, 24)
        result = mock_client.format_date(dt)
        assert result == "241225"
    
    def test_parse_datetime(self, mock_client):
        """Test parsing datetime from API format."""
        result = mock_client.parse_datetime("2412251115")
        expected = datetime(2025, 12, 24, 11, 15)
        assert result == expected
    
    def test_parse_date(self, mock_client):
        """Test parsing date from API format."""
        result = mock_client.parse_date("241225")
        expected = datetime(2025, 12, 24)
        assert result == expected
    
    def test_format_and_parse_roundtrip(self, mock_client):
        """Test that format and parse are inverse operations."""
        dt = datetime(2025, 6, 15, 9, 30)
        formatted = mock_client.format_datetime(dt)
        parsed = mock_client.parse_datetime(formatted)
        assert parsed == dt


class TestHelperMethods:
    """Tests for helper methods that process cached data."""
    
    def test_get_service_name(self, mock_client):
        """Test getting service name by ID."""
        mock_client._services = MOCK_SERVICES
        assert mock_client.get_service_name(0) == "Taglio normale + shampoo"
        assert mock_client.get_service_name(10) == "Taglio + barba"
    
    def test_get_service_name_invalid_id(self, mock_client):
        """Test fallback for invalid service ID."""
        mock_client._services = MOCK_SERVICES
        result = mock_client.get_service_name(999)
        assert result == "Servizio #999"
    
    def test_get_service_price(self, mock_client):
        """Test getting service price by ID."""
        mock_client._services = MOCK_SERVICES
        assert mock_client.get_service_price(0) == 13.0
        assert mock_client.get_service_price(10) == 18.0
    
    def test_get_service_price_invalid_id(self, mock_client):
        """Test fallback price for invalid ID."""
        mock_client._services = MOCK_SERVICES
        result = mock_client.get_service_price(999)
        assert result == 0.0
    
    def test_get_service_duration(self, mock_client):
        """Test getting service duration for specific barber."""
        mock_client._barbers = MOCK_BARBERS
        # Giovanni has service 0 = 45 min, service 2 = 15 min
        assert mock_client.get_service_duration("Giovanni", 0) == 45
        assert mock_client.get_service_duration("Giovanni", 2) == 15
    
    def test_get_service_duration_unknown_barber(self, mock_client):
        """Test fallback duration for unknown barber."""
        mock_client._barbers = MOCK_BARBERS
        result = mock_client.get_service_duration("Unknown", 0)
        assert result == 45  # Default fallback

    def test_get_service_duration_fallback_to_default_minutes(self, mock_client):
        """Test fallback to MinutiTaglio when per-service array is too short."""
        mock_client._barbers = [
            {"Nome": "Giovanni", "MinutiTaglio": 50, "MinutiTaglioArr": [30]}
        ]
        result = mock_client.get_service_duration("Giovanni", 5)
        assert result == 50

    def test_get_service_name_handles_missing_data(self, mock_client):
        """Test graceful handling when services data is malformed."""
        mock_client._services = {"Nome": None}
        result = mock_client.get_service_name(0)
        assert result == ""


class TestAvailableSlots:
    """Tests for slot availability calculation."""
    
    def test_get_available_slots_for_barber(self, mock_client):
        """Test filtering schedule by barber."""
        mock_client._schedule = MOCK_SCHEDULE
        
        slots = mock_client.get_available_slots_for_barber("Giovanni")
        # Should get only Giovanni's non-holiday slots
        assert len(slots) == 1
        assert slots[0]["Gi"] == "231225"
    
    def test_get_available_slots_excludes_holidays(self, mock_client):
        """Test that holidays (Fe=True) are excluded."""
        mock_client._schedule = MOCK_SCHEDULE
        
        slots = mock_client.get_available_slots_for_barber("Giovanni")
        # 24/12 is marked as holiday
        dates = [s["Gi"] for s in slots]
        assert "241225" not in dates
    
    def test_calculate_available_slots(self, mock_client):
        """Test calculating time slots for a specific date."""
        mock_client._schedule = MOCK_SCHEDULE
        mock_client._barbers = MOCK_BARBERS
        
        # Service 0 = 45 min duration
        slots = mock_client.calculate_available_slots("231225", "Giovanni", 0)
        
        # Should filter to slots with duration >= 45
        times = [t for t, d in slots]
        assert "11:15" in times  # 45 min slot
        assert "15:30" in times  # 60 min slot
        # 12:00 has only 30 min, should be excluded
        assert "12:00" not in times
    
    def test_calculate_available_slots_shorter_service(self, mock_client):
        """Test that shorter services see more available slots."""
        mock_client._schedule = MOCK_SCHEDULE
        mock_client._barbers = MOCK_BARBERS
        
        # Service 2 = 15 min duration
        slots = mock_client.calculate_available_slots("231225", "Giovanni", 2)
        
        # All slots should be available (all >= 15 min)
        times = [t for t, d in slots]
        assert "11:15" in times
        assert "12:00" in times
        assert "15:30" in times
    
    def test_calculate_available_slots_no_slots(self, mock_client):
        """Test empty result for date with no slots."""
        mock_client._schedule = MOCK_SCHEDULE
        mock_client._barbers = MOCK_BARBERS
        
        # 24/12 is a holiday with no slots
        slots = mock_client.calculate_available_slots("241225", "Giovanni", 0)
        assert slots == []


class TestWorkingHours:
    """Tests for working hours logic."""
    
    def test_monday_closed(self, mock_client):
        """Monday should be closed."""
        hours = mock_client.get_working_hours(0)  # 0 = Monday
        assert hours == []
    
    def test_sunday_closed(self, mock_client):
        """Sunday should be closed."""
        hours = mock_client.get_working_hours(6)  # 6 = Sunday
        assert hours == []
    
    def test_saturday_hours(self, mock_client):
        """Saturday has continuous hours."""
        hours = mock_client.get_working_hours(5)  # 5 = Saturday
        assert len(hours) == 1
        start, end = hours[0]
        assert start == 8 * 60 + 30  # 8:30
        assert end == 18 * 60  # 18:00
    
    def test_weekday_hours(self, mock_client):
        """Weekdays (Tue-Fri) have split hours."""
        for weekday in [1, 2, 3, 4]:  # Tue-Fri
            hours = mock_client.get_working_hours(weekday)
            assert len(hours) == 2
            # Morning: 8:30-13:00
            assert hours[0] == (8 * 60 + 30, 13 * 60)
            # Afternoon: 15:00-20:00
            assert hours[1] == (15 * 60, 20 * 60)


class TestAPICalls:
    """Tests for API request methods with mocked HTTP."""
    
    @responses.activate
    def test_get_barbers(self, mock_client):
        """Test fetching barbers list."""
        # Prepare mocked response
        response_data = base64.b64encode(json.dumps(MOCK_BARBERS).encode()).decode()
        responses.add(
            responses.POST,
            mock_client.BASE_URL,
            body=response_data,
            status=200
        )
        
        result = mock_client.get_barbers()
        
        assert len(result) == 3
        assert result[0]["Nome"] == "Giovanni"
    
    @responses.activate
    def test_get_services(self, mock_client):
        """Test fetching services list."""
        response_data = base64.b64encode(json.dumps(MOCK_SERVICES).encode()).decode()
        responses.add(
            responses.POST,
            mock_client.BASE_URL,
            body=response_data,
            status=200
        )
        
        result = mock_client.get_services()
        
        assert "Nome" in result
        assert "Prezzo" in result
        assert result["Nome"][0] == "Taglio normale + shampoo"
    
    @responses.activate
    def test_get_barbers_caches_result(self, mock_client):
        """Test that barbers are cached after first call."""
        response_data = base64.b64encode(json.dumps(MOCK_BARBERS).encode()).decode()
        responses.add(
            responses.POST,
            mock_client.BASE_URL,
            body=response_data,
            status=200
        )
        
        # First call - makes HTTP request
        result1 = mock_client.get_barbers()
        # Second call - should use cache
        result2 = mock_client.get_barbers()
        
        assert result1 == result2
        # Only one HTTP request should have been made
        assert len(responses.calls) == 1
    
    @responses.activate
    def test_book_success(self, mock_client):
        """Test successful booking."""
        response_data = base64.b64encode(b"OK").decode()
        responses.add(
            responses.POST,
            mock_client.BASE_URL,
            body=response_data,
            status=200
        )
        
        result = mock_client.book("2412251115", 10, "Giovanni")
        
        assert result is True
    
    @responses.activate
    def test_book_failure(self, mock_client):
        """Test failed booking."""
        response_data = base64.b64encode(b"ERROR: Slot not available").decode()
        responses.add(
            responses.POST,
            mock_client.BASE_URL,
            body=response_data,
            status=200
        )
        
        result = mock_client.book("2412251115", 10, "Giovanni")
        
        assert result is False
    
    @responses.activate
    def test_cancel_success(self, mock_client):
        """Test successful cancellation."""
        response_data = base64.b64encode(b"OK").decode()
        responses.add(
            responses.POST,
            mock_client.BASE_URL,
            body=response_data,
            status=200
        )
        
        result = mock_client.cancel("2412251115", 10, "Giovanni", 18.0)
        
        assert result is True
    
    @responses.activate
    def test_join_queue_success(self, mock_client):
        """Test joining queue."""
        response_data = base64.b64encode(b"OK").decode()
        responses.add(
            responses.POST,
            mock_client.BASE_URL,
            body=response_data,
            status=200
        )
        
        result = mock_client.join_queue("241225", "Giovanni", 0)
        
        assert result is True
    
    @responses.activate
    def test_leave_queue_success(self, mock_client):
        """Test leaving queue."""
        response_data = base64.b64encode(b"OK").decode()
        responses.add(
            responses.POST,
            mock_client.BASE_URL,
            body=response_data,
            status=200
        )
        
        result = mock_client.leave_queue("241225")
        
        assert result is True
    
    @responses.activate
    def test_get_confirmed_reservations(self, mock_client):
        """Test fetching confirmed reservations."""
        response_data = base64.b64encode(
            json.dumps(MOCK_CONFIRMED_RESERVATIONS).encode()
        ).decode()
        responses.add(
            responses.POST,
            mock_client.BASE_URL,
            body=response_data,
            status=200
        )
        
        result = mock_client.get_confirmed_reservations()
        
        assert len(result) == 1
        assert result[0]["Pa"] == "Giovanni"
    
    @responses.activate
    def test_get_pending_reservations(self, mock_client):
        """Test fetching pending reservations."""
        response_data = base64.b64encode(
            json.dumps(MOCK_PENDING_RESERVATIONS).encode()
        ).decode()
        responses.add(
            responses.POST,
            mock_client.BASE_URL,
            body=response_data,
            status=200
        )
        
        result = mock_client.get_pending_reservations()
        
        assert len(result) == 1
        assert result[0]["Pa"] == "Giovanni"
    
    @responses.activate
    def test_request_json_empty_response(self, mock_client):
        """Test handling of empty API response."""
        response_data = base64.b64encode(b"").decode()
        responses.add(
            responses.POST,
            mock_client.BASE_URL,
            body=response_data,
            status=200
        )
        
        result = mock_client._request_json("SomeAction")
        
        assert result == []

    @responses.activate
    def test_request_json_invalid_json(self, mock_client, capsys):
        """Test handling when API returns invalid JSON payload."""
        response_data = base64.b64encode(b"not-json").decode()
        responses.add(
            responses.POST,
            mock_client.BASE_URL,
            body=response_data,
            status=200
        )

        result = mock_client._request_json("BrokenAction")

        assert result == []
        captured = capsys.readouterr()
        assert "Action: BrokenAction" in captured.out
        assert "not-json" in captured.out
    
    def test_get_last_update_invokes_request(self, mock_client):
        """Ensure get_last_update delegates to _request with expected args."""
        called = {}
        
        def fake_request(action, *args):
            called["action"] = action
            called["args"] = args
            return "123456"
        
        mock_client._request = fake_request
        
        result = mock_client.get_last_update()
        
        assert result == "123456"
        assert called == {"action": "LastUpdateGet", "args": ("",)}


class TestPublicSearch:
    """Tests for the unauthenticated search helper."""
    
    @responses.activate
    def test_search_nearby_decodes_payload(self):
        payload = base64.b64encode(json.dumps([{"Nome": "Test", "Key": "123"}]).encode()).decode()
        responses.add(
            responses.POST,
            client_module.BarberAppClient.BASE_URL,
            body=payload,
            status=200
        )
        
        result = client_module.search_nearby(lat=41.9, lon=12.5, radius=5000)
        
        assert result[0]["Nome"] == "Test"
        assert result[0]["Key"] == "123"
    
    @responses.activate
    def test_search_nearby_returns_empty_on_blank_payload(self):
        responses.add(
            responses.POST,
            client_module.BarberAppClient.BASE_URL,
            body="",
            status=200
        )
        
        result = client_module.search_nearby(lat=10.0, lon=20.0)
        assert result == []
    
    @responses.activate
    def test_search_nearby_handles_padding(self):
        payload = base64.b64encode(json.dumps([{"Nome": "Foo"}]).encode()).decode().rstrip("=")
        responses.add(
            responses.POST,
            client_module.BarberAppClient.BASE_URL,
            body=payload,
            status=200
        )
        
        result = client_module.search_nearby(lat=1.0, lon=2.0)
        assert result[0]["Nome"] == "Foo"


class TestTablesAndDashboard:
    """Tests for dashboard helper tables and rendering."""
    
    def test_get_services_table_has_rows(self, ui_client):
        table = client_module.get_services_table(ui_client)
        assert len(table.rows) > 0
    
    def test_get_barbers_table_filters_hidden(self, ui_client):
        table = client_module.get_barbers_table(ui_client)
        record_console = Console(record=True)
        record_console.print(table)
        rendered = record_console.export_text()
        assert "Hidden" not in rendered
        assert "Giovanni" in rendered
    
    def test_get_reservations_table_combines_pending_and_confirmed(self, ui_client):
        table = client_module.get_reservations_table(ui_client)
        record_console = Console(record=True)
        record_console.print(table)
        rendered = record_console.export_text()
        assert "⏳" in rendered
        assert "✅" in rendered
    
    def test_get_services_table_handles_exception(self, ui_client):
        ui_client.get_services = lambda: {"Nome": None, "Prezzo": []}
        table = client_module.get_services_table(ui_client)
        assert len(table.rows) == 0  # returns empty safe table without raising
    
    def test_get_reservations_table_handles_empty_state(self, ui_client):
        ui_client.get_pending_reservations = lambda: []
        ui_client.get_confirmed_reservations = lambda: []
        table = client_module.get_reservations_table(ui_client)
        record_console = Console(record=True)
        record_console.print(table)
        rendered = record_console.export_text()
        assert "Nessuna" in rendered
    
    def test_get_slots_table_shows_available_periods(self, ui_client):
        table = client_module.get_slots_table(ui_client, "Giovanni", 0)
        assert len(table.rows) > 0
    
    def test_get_slots_table_handles_no_days(self, ui_client):
        ui_client.get_available_slots_for_barber = lambda barber: []
        table = client_module.get_slots_table(ui_client, "Giovanni", 0)
        record_console = Console(record=True)
        record_console.print(table)
        rendered = record_console.export_text()
        assert "Nessun giorno" in rendered
    
    def test_get_slots_table_marks_occupied_days(self, ui_client):
        ui_client.get_available_slots_for_barber = lambda barber: [
            {"Gi": "231225", "Pa": barber, "Fe": False}
        ]
        ui_client.calculate_available_slots = lambda *args, **kwargs: []
        table = client_module.get_slots_table(ui_client, "Giovanni", 0)
        record_console = Console(record=True)
        record_console.print(table)
        rendered = record_console.export_text()
        assert "Occupato" in rendered
    
    def test_show_dashboard_renders_panels(self, ui_client, console_factory):
        dummy_console = console_factory()
        ui_client.get_service_name = lambda _: None  # trigger fallback
        client_module.show_dashboard(ui_client, selected_service_id=0)
        assert dummy_console.clear_called
        assert dummy_console.print_calls  # Something was rendered


class TestInteractiveFlows:
    """Tests covering interactive helper functions."""
    
    def test_select_service_valid_input(self, ui_client, console_factory):
        console_factory(inputs=["2"])
        result = client_module.select_service(ui_client, current_service_id=0)
        assert result == 2
    
    def test_select_service_invalid_id_keeps_current(self, ui_client, console_factory):
        console_factory(inputs=["99"])
        result = client_module.select_service(ui_client, current_service_id=3)
        assert result == 3
    
    def test_select_service_handles_value_error(self, ui_client, console_factory):
        console_factory(inputs=["abc"])
        result = client_module.select_service(ui_client, current_service_id=4)
        assert result == 4
    
    def test_book_appointment_success_flow(self, ui_client, console_factory):
        # Inputs: keep service, choose first day (0), first slot (0), confirm booking.
        console_factory(inputs=["n", "0", "0", "s"])

        class BookingSpy:
            def __init__(self):
                self.called = False
                self.args = None

            def __call__(self, dt_str, service_id, barber):
                self.called = True
                self.args = (dt_str, service_id, barber)
                return True

        spy = BookingSpy()
        ui_client.book = spy
        
        result = client_module.book_appointment(ui_client, current_service_id=0)
        
        assert result == 0
        assert spy.called
        dt_str, service_id, barber = spy.args
        assert service_id == 0
        assert barber == client_module.PREFERRED_BARBER
        assert dt_str.endswith("1115")  # first slot in mock data
        assert ui_client._schedule is None  # cache cleared after booking
    
    def test_book_appointment_no_available_days(self, ui_client, console_factory):
        console_factory(inputs=["s", "999"])
        ui_client.get_available_slots_for_barber = lambda barber: []
        
        result = client_module.book_appointment(ui_client, current_service_id=0)
        
        assert result == 0
    
    def test_book_appointment_invalid_day_selection(self, ui_client, console_factory):
        console_factory(inputs=["n", "5"])
        result = client_module.book_appointment(ui_client, current_service_id=0)
        assert result == 0
    
    def test_book_appointment_invalid_slot_selection(self, ui_client, console_factory):
        console_factory(inputs=["n", "0", "99"])
        result = client_module.book_appointment(ui_client, current_service_id=0)
        assert result == 0
    
    def test_book_appointment_user_declines_confirmation(self, ui_client, console_factory):
        console_factory(inputs=["n", "0", "0", "n"])
        result = client_module.book_appointment(ui_client, current_service_id=0)
        assert result == 0
    
    def test_book_appointment_handles_booking_failure(self, ui_client, console_factory):
        console_factory(inputs=["n", "0", "0", "s"])
        ui_client.book = lambda *args, **kwargs: False
        result = client_module.book_appointment(ui_client, current_service_id=0)
        assert result == 0
    
    def test_cancel_appointment_success_flow(self, ui_client, console_factory):
        console_factory(inputs=["0", "s"])
        canceled = {}
        
        def fake_cancel(dt, service_id, barber, price):
            canceled["dt"] = dt
            canceled["service_id"] = service_id
            canceled["barber"] = barber
            canceled["price"] = price
            return True
        
        ui_client.cancel = fake_cancel
        
        client_module.cancel_appointment(ui_client)
        
        assert canceled["service_id"] == 0
        assert canceled["barber"] == "Giovanni"
    
    def test_cancel_appointment_no_confirmed(self, ui_client, console_factory):
        console_factory(inputs=[])
        ui_client.get_confirmed_reservations = lambda: []
        client_module.cancel_appointment(ui_client)
    
    def test_cancel_appointment_invalid_selection(self, ui_client, console_factory):
        console_factory(inputs=["5"])
        client_module.cancel_appointment(ui_client)
    
    def test_cancel_appointment_user_declines(self, ui_client, console_factory):
        console_factory(inputs=["0", "n"])
        client_module.cancel_appointment(ui_client)
    
    def test_cancel_appointment_failure(self, ui_client, console_factory):
        console_factory(inputs=["0", "s"])
        ui_client.cancel = lambda *args, **kwargs: False
        client_module.cancel_appointment(ui_client)
    
    def test_interactive_menu_quits_immediately(self, ui_client, console_factory):
        console_factory(inputs=["q"])
        client_module.interactive_menu(ui_client)
    
    def test_interactive_menu_handles_all_commands(self, ui_client, console_factory, monkeypatch):
        dummy_console = console_factory(inputs=["s", "", "b", "", "c", "", "r", "x", "q"])
        
        show_calls = []
        monkeypatch.setattr(client_module, "show_dashboard", lambda client, sid: show_calls.append(("show", sid)))
        monkeypatch.setattr(client_module, "select_service", lambda client, sid: sid + 1)
        
        def fake_book(client, sid):
            return sid + 2
        
        monkeypatch.setattr(client_module, "book_appointment", fake_book)
        canceled = {}
        monkeypatch.setattr(client_module, "cancel_appointment", lambda client: canceled.update({"called": True}))
        
        ui_client._barbers = ["cached"]
        ui_client._services = ["cached"]
        ui_client._schedule = ["cached"]
        
        client_module.interactive_menu(ui_client)
        
        assert show_calls  # dashboard rendered multiple times
        assert canceled.get("called") is True
        assert ui_client._barbers is None
        assert ui_client._services is None
        assert ui_client._schedule is None


class TestMainEntry:
    def test_main_invokes_interactive_menu(self, monkeypatch):
        created_client = {}
        
        class FakeClient:
            pass
        
        def fake_ctor(*args, **kwargs):
            created_client["args"] = args
            created_client["kwargs"] = kwargs
            return FakeClient()
        
        invoked = {}
        
        def fake_menu(client):
            invoked["client"] = client
        
        monkeypatch.setattr(client_module, "BarberAppClient", fake_ctor)
        monkeypatch.setattr(client_module, "interactive_menu", fake_menu)
        
        client_module.main()
        
        assert "client" in invoked
