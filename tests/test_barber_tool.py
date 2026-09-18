import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, date, timedelta
import argparse

import barber_tool
from barber_tool import parse_date, parse_time, get_date_range, get_matching_slots

def test_parse_date():
    assert parse_date("2026-06-24") == date(2026, 6, 24)
    assert parse_date("240626") == date(2026, 6, 24)
    assert parse_date("24/06/26") == date(2026, 6, 24)
    assert parse_date("24/06/2026") == date(2026, 6, 24)
    
    with pytest.raises(argparse.ArgumentTypeError):
        parse_date("invalid-date")

def test_parse_time():
    from datetime import time
    assert parse_time("19:00") == time(19, 0)
    assert parse_time("0830") == time(8, 30)
    
    with pytest.raises(argparse.ArgumentTypeError):
        parse_time("invalid-time")

@patch('barber_tool.datetime')
def test_get_date_range(mock_datetime):
    # Mock current date as Wednesday 2026-06-24
    fixed_now = datetime(2026, 6, 24, 22, 30, 0)
    mock_datetime.now.return_value = fixed_now
    mock_datetime.strptime = datetime.strptime
    
    # Test --today
    args = argparse.Namespace(today=True, tomorrow=False, this_week=False, next_week=False, start_date=None, end_date=None)
    start, end = get_date_range(args)
    assert start == date(2026, 6, 24)
    assert end == date(2026, 6, 24)
    
    # Test --tomorrow
    args = argparse.Namespace(today=False, tomorrow=True, this_week=False, next_week=False, start_date=None, end_date=None)
    start, end = get_date_range(args)
    assert start == date(2026, 6, 25)
    assert end == date(2026, 6, 25)
    
    # Test --this-week (Wednesday 2026-06-24 to Sunday 2026-06-28)
    args = argparse.Namespace(today=False, tomorrow=False, this_week=True, next_week=False, start_date=None, end_date=None)
    start, end = get_date_range(args)
    assert start == date(2026, 6, 24)
    assert end == date(2026, 6, 28)
    
    # Test --next-week (Monday 2026-06-29 to Sunday 2026-07-05)
    args = argparse.Namespace(today=False, tomorrow=False, this_week=False, next_week=True, start_date=None, end_date=None)
    start, end = get_date_range(args)
    assert start == date(2026, 6, 29)
    assert end == date(2026, 7, 5)

@patch('barber_tool.datetime')
def test_get_matching_slots(mock_datetime):
    fixed_now = datetime(2026, 6, 24, 22, 30, 0)
    mock_datetime.now.return_value = fixed_now
    mock_datetime.strptime = datetime.strptime
    
    client = MagicMock()
    # Mock available slots returned by client
    # Giovanni has available days
    client.get_available_slots_for_barber.return_value = [
        {
            "Gi": "240626", # Today
            "Pa": "Giovanni",
            "Fe": False
        },
        {
            "Gi": "250626", # Tomorrow
            "Pa": "Giovanni",
            "Fe": False
        }
    ]
    
    # client.parse_date returns datetime
    client.parse_date.side_effect = lambda s: datetime.strptime(s, "%d%m%y")
    client.get_service_name.return_value = "Taglio Capelli"
    
    # Mock calculate_available_slots
    # Day 1: 19:15, 19:30
    # Day 2: 10:00, 15:00
    def mock_calc_slots(date_str, barber, service_id):
        if date_str == "240626":
            return [("19:15", 30), ("19:30", 15)]
        elif date_str == "250626":
            return [("10:00", 45), ("15:00", 45)]
        return []
    client.calculate_available_slots.side_effect = mock_calc_slots
    
    # Query today slots after 19:20
    args = argparse.Namespace(
        barber="Giovanni", service=10,
        today=True, tomorrow=False, this_week=False, next_week=False,
        start_date=None, end_date=None,
        after_time=datetime.strptime("19:20", "%H:%M").time(),
        before_time=None
    )
    
    slots = get_matching_slots(client, args)
    
    assert len(slots) == 1
    assert slots[0]["date"] == "2026-06-24"
    assert slots[0]["time"] == "19:30"
    assert slots[0]["datetime_str"] == "2406261930"

@patch('barber_tool.BarberAppClient')
def test_book_first_available(mock_client_class):
    client_mock = MagicMock()
    mock_client_class.return_value = client_mock
    
    client_mock.get_available_slots_for_barber.return_value = [
        {
            "Gi": "240626",
            "Pa": "Giovanni",
            "Fe": False
        }
    ]
    client_mock.parse_date.side_effect = lambda s: datetime.strptime(s, "%d%m%y")
    client_mock.calculate_available_slots.return_value = [("19:15", 30)]
    client_mock.book.return_value = True
    
    args = argparse.Namespace(
        command="book",
        datetime=None,
        first_available=True,
        barber="Giovanni",
        service=10,
        today=True, tomorrow=False, this_week=False, next_week=False,
        start_date=None, end_date=None,
        after_time=None, before_time=None,
        dry_run=False,
        json=False
    )
    
    with patch('barber_tool.datetime') as mock_datetime:
        mock_datetime.now.return_value = datetime(2026, 6, 24, 18, 0, 0)
        mock_datetime.strptime = datetime.strptime
        barber_tool.handle_book(client_mock, args)
        
    client_mock.book.assert_called_once_with("2406261915", 10, "Giovanni")
