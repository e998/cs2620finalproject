import pytest
from collections import defaultdict
from health.healthapp import get_api_metrics
from shared.models import Clients, Order, Activity 
from shared.extensions import db
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

def test_health_check_endpoint(client):
    """
    GIVEN a Flask application configured for testing
    WHEN the '/health/' page is requested (GET)
    THEN check that the response is valid and status code is 200
    """
    response = client.get('/health/') # Assuming the health blueprint is mounted at '/health/'
    assert response.status_code == 200

def test_get_api_metrics_calculation(app):
    """
    GIVEN sample data created locally
    WHEN the get_api_metrics function is called directly with this data within an app context
    THEN check that the calculated averages and counts in the JSON response are correct
    """
    # Setup: Create local test data
    test_data = defaultdict(lambda: {'count': 0, 'total_time': 0.0})
    test_data['endpoint1']['count'] = 2
    test_data['endpoint1']['total_time'] = 0.5
    test_data['endpoint2']['count'] = 1
    test_data['endpoint2']['total_time'] = 0.3

    # Execute: Call the function directly, passing our test data within an app context
    with app.app_context(): # Create app context
        response = get_api_metrics(metrics_source=test_data)
        calculated_metrics = response.get_json() # Extract JSON data from the response

    # Assert
    assert 'endpoint1' in calculated_metrics
    assert calculated_metrics['endpoint1']['count'] == 2
    # Use round() because the function now rounds
    assert calculated_metrics['endpoint1']['average_time'] == pytest.approx(0.25)

    assert 'endpoint2' in calculated_metrics
    assert calculated_metrics['endpoint2']['count'] == 1
    assert calculated_metrics['endpoint2']['average_time'] == pytest.approx(0.3)

    # Cleanup not needed for local test_data

def test_cluster_status_endpoint(client, app):
    """
    GIVEN a Flask application configured for testing
    WHEN the '/health/cluster_status' page is requested (GET)
    THEN check that the response is valid JSON with status code 200
    AND check that the JSON data is a dictionary with 'alive' and 'leader' keys containing empty lists initially
    """
    # Ensure the Clients table is empty before the request
    with app.app_context():
        Clients.query.delete()
        db.session.commit()

    response = client.get('/health/cluster_status')
    assert response.status_code == 200
    assert response.is_json
    json_data = response.get_json()
    assert isinstance(json_data, dict) # Expect a dictionary
    assert 'alive' in json_data
    assert 'leader' in json_data
    assert json_data['alive'] == [] # Check value for 'alive'
    assert json_data['leader'] == [] # Check value for 'leader'

@patch('health.healthapp.db.session.query') # Correct patch target
def test_sales_data_endpoint(mock_query, client):
    class MockRow:
        def __init__(self, time, count):
            self.time = time
            self.count = count

    mock_data = [
        MockRow(datetime(2024, 5, 4, 10, 5, 0), 3), # Bucket 1: 10:05, Count 3
        MockRow(datetime(2024, 5, 4, 10, 10, 0), 2)  # Bucket 2: 10:10, Count 2
    ]

    # Configure the mock query chain to return the mock_data at the end
    mock_query.return_value.filter.return_value.group_by.return_value.order_by.return_value.all.return_value = mock_data

    # No need to add dummy Order data anymore as we mock the query result

    response = client.get('/health/sales_data')
    assert response.status_code == 200
    data = response.get_json()

    # Check that db.session.query was called
    mock_query.assert_called_once()
    # Optionally check that filter/group_by/order_by/all were called
    mock_query.return_value.filter.assert_called()
    mock_query.return_value.filter.return_value.group_by.assert_called()
    mock_query.return_value.filter.return_value.group_by.return_value.order_by.assert_called()
    mock_query.return_value.filter.return_value.group_by.return_value.order_by.return_value.all.assert_called_once()

    # Check the structure of the JSON response
    assert 'labels' in data
    assert 'counts' in data
    assert isinstance(data['labels'], list)
    assert isinstance(data['counts'], list)

    assert len(data['labels']) == 2
    assert len(data['counts']) == 2
    assert data['labels'][0].endswith(':05') # Check if the label matches the mocked time bucket
    assert data['counts'][0] == 3
    assert data['labels'][1].endswith(':10')
    assert data['counts'][1] == 2

    # No need to clean up Order data anymore

def test_activity_log_endpoint(client):
    # Clean up any old data first
    Activity.query.delete()
    db.session.commit()

    # Add dummy data
    act1 = Activity(label='User logged in', activitytime=datetime.utcnow() - timedelta(minutes=5))
    act2 = Activity(label='Order placed', activitytime=datetime.utcnow() - timedelta(minutes=2))
    act3 = Activity(label='System started', activitytime=datetime.utcnow() - timedelta(hours=1))
    # Add more than 10 to test the limit
    for i in range(10):
         db.session.add(Activity(label=f'Old event {i}', activitytime=datetime.utcnow() - timedelta(days=1)))

    db.session.add_all([act1, act2, act3])
    db.session.commit()

    response = client.get('/health/activity_log')
    assert response.status_code == 200
    data = response.get_json()

    assert isinstance(data, list)
    assert len(data) == 13  # Should match the number of inserted activities
    assert data[0]['activity'] == 'Order placed'  # Most recent
    assert data[1]['activity'] == 'User logged in'
    assert data[2]['activity'] == 'System started'

    # Clean up dummy data
    Activity.query.delete()
    db.session.commit()
