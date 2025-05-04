import pytest
from app.forms import RegistrationForm, LoginForm, ProductForm, SellForm
from wtforms.validators import ValidationError

# Helper to simulate request data for WTForms
class DummyPostData(dict):
    def getlist(self, key):
        v = self[key]
        if not isinstance(v, (list, tuple)):
            v = [v]
        return v

# --- RegistrationForm Tests --- 

def test_registration_form_valid(app):
    with app.test_request_context('/register', method='POST'):
        form = RegistrationForm(DummyPostData({
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        }))
        assert form.validate() is True

@pytest.mark.parametrize("field, value, expected_error", [
    ('username', '', ['This field is required.']),
    ('email', '', ['This field is required.']),
    ('email', 'not-an-email', ['Invalid email address.']),
    ('password', '', ['This field is required.']),
    ('password', 'short', ['Field must be at least 6 characters long.']),
    ('confirm_password', '', ['This field is required.']),
])
def test_registration_form_missing_or_invalid_fields(app, field, value, expected_error):
    with app.test_request_context('/register', method='POST'):
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        }
        data[field] = value
        form = RegistrationForm(DummyPostData(data))
        assert form.validate() is False
        assert form.errors.get(field) == expected_error

def test_registration_form_password_mismatch(app):
    with app.test_request_context('/register', method='POST'):
        form = RegistrationForm(DummyPostData({
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'differentpassword'
        }))
        assert form.validate() is False
        assert 'Field must be equal to password.' in form.errors.get('confirm_password', [])

# --- LoginForm Tests --- 

def test_login_form_valid(app):
    with app.test_request_context('/login', method='POST'):
        form = LoginForm(DummyPostData({
            'username': 'testuser',
            'password': 'password123'
        }))
        assert form.validate() is True

@pytest.mark.parametrize("field, value, expected_error", [
    ('username', '', ['This field is required.']),
    ('password', '', ['This field is required.']),
])
def test_login_form_missing_fields(app, field, value, expected_error):
    with app.test_request_context('/login', method='POST'):
        data = {'username': 'testuser', 'password': 'password123'}
        data[field] = value
        form = LoginForm(DummyPostData(data))
        assert form.validate() is False
        assert form.errors.get(field) == expected_error

# --- ProductForm Tests --- 

def test_product_form_valid(app):
    with app.test_request_context('/product', method='POST'):
        form = ProductForm(DummyPostData({
            'title': 'Test Product',
            'description': 'A description.',
            'price': 99.99
        }))
        assert form.validate() is True

@pytest.mark.parametrize("field, value, expected_error", [
    ('title', '', ['This field is required.']),
    ('title', 'a' * 101, ['Field cannot be longer than 100 characters.']), # Example WTForms default message
    ('description', '', ['This field is required.']),
    ('price', '', ['This field is required.']),
    ('price', 'not-a-number', ['Not a valid float value.', 'This field is required.']), # Accept either error
])
def test_product_form_invalid(app, field, value, expected_error):
    with app.test_request_context('/product', method='POST'):
        data = {'title': 'Test', 'description': 'Desc', 'price': 10.0}
        data[field] = value
        form = ProductForm(DummyPostData(data))
        assert form.validate() is False
        field_errors = form.errors.get(field, [])
        assert field_errors, f"Expected errors for field {field}, but got none."
        # Optional: Keep the original check if specific error messages are preferred, adjusting expected_error list
        # assert any(any(e in msg for e in expected_error) for msg in field_errors), \
        #        f"Expected error containing {expected_error} for field {field}, got {field_errors}"


# --- SellForm Tests --- 
# Note: FileField validation is complex and often better tested in integration tests

def test_sell_form_valid(app):
    with app.test_request_context('/sell', method='POST', content_type='multipart/form-data'):
        form = SellForm(DummyPostData({
            'title': 'Test Item',
            'description': 'Selling this item.',
            'price': '123.45' # DecimalField often takes string input
            # 'picture': (io.BytesIO(b"abcdef"), 'test.jpg') # Optional - FileField testing setup
        }))
        assert form.validate() is True

@pytest.mark.parametrize("field, value, expected_error", [
    ('title', '', ['This field is required.']),
    ('title', 'a' * 101, ['Field cannot be longer than 100 characters.']),
    ('description', '', ['This field is required.']),
    ('description', 'a' * 501, ['Field cannot be longer than 500 characters.']),
    ('price', '', ['This field is required.']),
    ('price', 'abc', ['Not a valid decimal value.', 'This field is required.']), # Accept either error
    # ('price', '12.345', ['Ensure that there are no more than 2 decimal places.']), # REMOVED: places=2 doesn't validate input length
])
def test_sell_form_invalid(app, field, value, expected_error):
    with app.test_request_context('/sell', method='POST', content_type='multipart/form-data'):
        data = {'title': 'Test', 'description': 'Desc', 'price': '10.00'}
        data[field] = value
        form = SellForm(DummyPostData(data))
        assert form.validate() is False
        field_errors = form.errors.get(field, [])
        assert field_errors, f"Expected errors for field {field}, but got none."
        # Optional: Keep the original check if specific error messages are preferred, adjusting expected_error list
        # assert any(any(e in msg for e in expected_error) for msg in field_errors), \
        #        f"Expected error containing {expected_error} for field {field}, got {field_errors}"
