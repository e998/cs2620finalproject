import os
from werkzeug.utils import secure_filename
from flask import current_app

def save_picture(form_picture):
    filename = secure_filename(form_picture.filename)
    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, filename)
    form_picture.save(file_path)
    return filename