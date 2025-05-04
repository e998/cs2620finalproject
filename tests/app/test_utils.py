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

    # Patch secure_filename to check it's called and returns the expected name
    # Patch os.makedirs to prevent actual directory creation
    with patch('app.utils.secure_filename', return_value=expected_secure_filename) as mock_secure, \
         patch('app.utils.os.makedirs') as mock_makedirs:

        # --- Act ---
        returned_filename = save_picture(mock_form_picture)

        # --- Assert ---
        # 1. Check secure_filename was called with the original filename
        mock_secure.assert_called_once_with(original_filename)

        # 2. Check the returned filename is the result from secure_filename
        assert returned_filename == expected_secure_filename

        # 3. Check os.makedirs was called (we don't need to check the exact path)
        mock_makedirs.assert_called_once()

        # 4. Check that the 'save' method was called with a path ending in the secure filename
        #    We use ANY because the beginning of the path depends on current_app.root_path
        mock_form_picture.save.assert_called_once_with(ANY)
        # Get the path argument that save was called with
        call_args, _ = mock_form_picture.save.call_args
        saved_path = call_args[0]
        # Assert the path ends with the correct structure
        assert saved_path.endswith(os.path.join('static', 'uploads', expected_secure_filename))
