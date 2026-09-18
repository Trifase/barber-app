import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from fastapi.testclient import TestClient
from web_server import app
from scheduler import scheduler

from tests.conftest import (
    MOCK_BARBERS,
    MOCK_SERVICES,
    MOCK_SCHEDULE,
    MOCK_CONFIRMED_RESERVATIONS,
    MOCK_PENDING_RESERVATIONS
)

client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_barber_client():
    """Mock get_client in web_server to return simulated data."""
    mock_instance = MagicMock()
    mock_instance.get_barbers.return_value = MOCK_BARBERS
    mock_instance.get_services.return_value = MOCK_SERVICES
    mock_instance.get_service_name.side_effect = lambda idx: (
        MOCK_SERVICES["Nome"][idx] if 0 <= idx < len(MOCK_SERVICES["Nome"]) and MOCK_SERVICES["Nome"][idx] else f"Servizio #{idx}"
    )
    mock_instance.get_service_price.side_effect = lambda idx: (
        MOCK_SERVICES["Prezzo"][idx] if 0 <= idx < len(MOCK_SERVICES["Prezzo"]) else 0.0
    )
    mock_instance.get_service_duration.return_value = 45
    mock_instance.get_confirmed_reservations.return_value = MOCK_CONFIRMED_RESERVATIONS
    mock_instance.get_pending_reservations.return_value = MOCK_PENDING_RESERVATIONS
    mock_instance.get_available_slots_for_barber.return_value = MOCK_SCHEDULE
    mock_instance.calculate_available_slots.return_value = [("11:15", 45)]
    mock_instance.parse_datetime.side_effect = lambda s: datetime.strptime(s, "%d%m%y%H%M")
    mock_instance.parse_date.side_effect = lambda s: datetime.strptime(s, "%d%m%y")
    mock_instance.book.return_value = True
    mock_instance.cancel.return_value = True

    with patch("web_server.get_client", return_value=mock_instance):
        yield mock_instance

def test_root_serves_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "BarberApp Web Client" in response.text
    assert "Auto-Booking Bot" in response.text

def test_api_status():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "username" in data
    assert "preferred_barber" in data
    assert "preferred_service_id" in data
    assert "telegram_configured" in data
    assert "scheduler_running" in data

def test_api_barbers():
    response = client.get("/api/barbers")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert any(b["nome"] == "Giovanni" for b in data)

def test_api_services():
    response = client.get("/api/services")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert any("Taglio normale" in s["name"] for s in data)

def test_api_reservations():
    response = client.get("/api/reservations")
    assert response.status_code == 200
    data = response.json()
    assert "confirmed" in data
    assert "pending" in data
    assert isinstance(data["confirmed"], list)
    assert isinstance(data["pending"], list)
    assert len(data["confirmed"]) > 0

def test_api_slots():
    response = client.get("/api/slots?barber=Giovanni&service_id=0&date_preset=all")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

def test_api_book_slot():
    res = client.post("/api/book", json={
        "datetime_str": "2312251115",
        "service_id": 0,
        "barber": "Giovanni"
    })
    assert res.status_code == 200
    assert res.json()["success"] is True

def test_api_cancel_reservation():
    res = client.request("DELETE", "/api/reservations", json={
        "datetime_str": "2312251115",
        "service_id": 0,
        "barber": "Giovanni",
        "price": 13.0
    })
    assert res.status_code == 200
    assert res.json()["success"] is True

def test_scheduler_lifecycle():
    scheduler.stop()

    res = client.get("/api/scheduler/status")
    assert res.status_code == 200
    status_data = res.json()
    assert status_data["status"] in ["idle", "stopped"]

    start_payload = {
        "barber": "Giovanni",
        "service_id": 0,
        "interval_minutes": 30,
        "min_hour": 19,
        "max_hour": 21,
        "dry_run": True
    }
    start_res = client.post("/api/scheduler/start", json=start_payload)
    assert start_res.status_code == 200
    assert start_res.json()["success"] is True

    status_res = client.get("/api/scheduler/status")
    assert status_res.json()["status"] == "running"

    stop_res = client.post("/api/scheduler/stop")
    assert stop_res.status_code == 200
    assert stop_res.json()["success"] is True

    final_status = client.get("/api/scheduler/status")
    assert final_status.json()["status"] == "stopped"
