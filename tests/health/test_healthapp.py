import pytest
from collections import defaultdict
from health.healthapp import get_api_metrics

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

def test_cluster_status_endpoint(client):
    """
    GIVEN a Flask application configured for testing
    WHEN the '/health/cluster_status' page is requested (GET)
    THEN check that the response is valid JSON with status code 200
    AND check that the JSON data is a dictionary with 'alive' and 'leader' keys containing empty lists initially
    """
    response = client.get('/health/cluster_status')
    assert response.status_code == 200
    assert response.is_json
    json_data = response.get_json()
    assert isinstance(json_data, dict) # Expect a dictionary
    assert 'alive' in json_data
    assert 'leader' in json_data
    assert json_data['alive'] == [] # Check value for 'alive'
    assert json_data['leader'] == [] # Check value for 'leader'
