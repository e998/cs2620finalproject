import pytest
import os
from unittest.mock import patch, MagicMock, ANY
from werkzeug.utils import secure_filename

# Function to test
from app.utils import save_picture

# Assuming 'client' fixture provides app context
def test_save_picture(client):
    """Test the save_picture utility function."""
    original_filename = "../unsafe/Path/image test.jpg"
    expected_secure_filename = "image_test.jpg"

    # Create a mock object simulating a FileStorage object
    mock_form_picture = MagicMock()
    mock_form_picture.filename = original_filename
    mock_form_picture.save = MagicMock()
    with patch('app.utils.secure_filename', return_value=expected_secure_filename) as mock_secure, \
         patch('app.utils.os.makedirs') as mock_makedirs:

        returned_filename = save_picture(mock_form_picture)

        mock_secure.assert_called_once_with(original_filename)
        assert returned_filename == expected_secure_filename
        mock_makedirs.assert_called_once()
        mock_makedirs.assert_called_once()
        mock_form_picture.save.assert_called_once_with(ANY)
        call_args, _ = mock_form_picture.save.call_args
        saved_path = call_args[0]
        assert saved_path.endswith(os.path.join('static', 'uploads', expected_secure_filename))
