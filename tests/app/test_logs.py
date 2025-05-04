import pytest
import json
from unittest.mock import patch, MagicMock
import datetime as dt

# Import functions to test
from app.logs import add_log, collect_logs, clear_logs, LOG_KEY

@patch('app.logs.r') # Mock the Redis client 'r' used in app.logs
def test_add_log(mock_redis):
    """Test that add_log pushes a correctly formatted JSON string to Redis."""
    message = "Test event occurred"
    add_log(message)

    # Check if rpush was called correctly
    mock_redis.rpush.assert_called_once() # Check if called
    args, kwargs = mock_redis.rpush.call_args
    
    assert args[0] == LOG_KEY # Check the key used
    
    # Check the value pushed (should be JSON string)
    log_data = json.loads(args[1])
    assert log_data['event'] == message
    assert 'time' in log_data
    # Could add more specific time format check if needed
    try:
        dt.datetime.strptime(log_data['time'], "%H:%M:%S")
    except ValueError:
        pytest.fail("Timestamp format is incorrect")

@patch('app.logs.r')
def test_collect_logs(mock_redis):
    """Test that collect_logs retrieves and parses logs correctly."""
    # Setup mock return value for lrange
    mock_log_data = [
        json.dumps({"time": "10:00:00", "event": "Event 1"}),
        json.dumps({"time": "10:01:00", "event": "Event 2"})
    ]
    mock_redis.lrange.return_value = mock_log_data

    logs = collect_logs()

    # Check if lrange was called correctly
    mock_redis.lrange.assert_called_once_with(LOG_KEY, 0, -1)

    # Check the returned data
    assert len(logs) == 2
    assert logs[0] == {"time": "10:00:00", "event": "Event 1"}
    assert logs[1] == {"time": "10:01:00", "event": "Event 2"}

@patch('app.logs.r')
def test_collect_logs_empty(mock_redis):
    """Test collect_logs when there are no logs in Redis."""
    mock_redis.lrange.return_value = [] # Simulate empty list from Redis

    logs = collect_logs()

    mock_redis.lrange.assert_called_once_with(LOG_KEY, 0, -1)
    assert logs == []

@patch('app.logs.r')
def test_clear_logs(mock_redis):
    """Test that clear_logs calls delete on the correct Redis key."""
    clear_logs()
    mock_redis.delete.assert_called_once_with(LOG_KEY)
