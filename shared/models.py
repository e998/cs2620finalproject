from shared.extensions import db
from flask_login import UserMixin
from datetime import datetime

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    listings = db.relationship('Product', backref='seller', lazy=True)
    orders = db.relationship('Order', backref='buyer', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    is_sold = db.Column(db.Boolean, default=False)
    image_file = db.Column(db.String(120), nullable=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Pending')
    product = db.relationship('Product', backref=db.backref('order', uselist=False))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    deleted_by_sender = db.Column(db.Boolean, default=False)
    deleted_by_receiver = db.Column(db.Boolean, default=False)
    is_read = db.Column(db.Boolean, default=False)

    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])
    product = db.relationship('Product')

class Offer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='Pending')  # Pending, Accepted, Rejected
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    product = db.relationship('Product')
    buyer = db.relationship('User', foreign_keys=[buyer_id])
    seller = db.relationship('User', foreign_keys=[seller_id])

class Clients(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client = db.Column(db.String(256))
    leader = db.Column(db.Boolean, default=False)
    time_start = db.Column(db.DateTime, default=datetime.utcnow)
    became_leader_at = db.Column(db.DateTime, nullable=True)
    last_connected = db.Column(db.DateTime, nullable=True)
    last_disconnected = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'client': self.client,
            'leader': self.leader,
            'time_start': self.time_start.isoformat() if self.time_start else None
        }
    
class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(256))
    activitytime = db.Column(db.DateTime, default=datetime.utcnow)

class Logs(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event = db.Column(db.String(512)) # Store the event description
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Log {self.id}: {self.event[:50]}... at {self.timestamp}>'