from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, current_user, login_required
from .forms import LoginForm, RegistrationForm, SellForm
from .models import User, Product, Message
from werkzeug.security import check_password_hash, generate_password_hash
from . import db
from .utils import save_picture
from flask_socketio import emit, join_room, leave_room
from . import socketio

main = Blueprint('main', __name__)

@main.route('/')
@login_required
def home():
    return redirect(url_for('main.history'))

@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('main.home'))
        else:
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('main.register'))
    return render_template('login.html', form=form)

@main.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        existing_user = User.query.filter((User.email == form.email.data) | (User.username == form.username.data)).first()
        if existing_user:
            flash('Email or username already exists.', 'danger')
            return render_template('register.html', form=form)
        hashed_pw = generate_password_hash(form.password.data)
        user = User(username=form.username.data, email=form.email.data, password=hashed_pw)
        db.session.add(user)
        db.session.commit()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('main.login'))
    return render_template('register.html', form=form)

@main.route('/history')
@login_required
def history():
    bought_orders = current_user.orders  # Orders where user is the buyer
    sold_orders = []
    for product in current_user.listings:
        if product.is_sold and product.order:
            sold_orders.append(product.order)
    return render_template('history.html', bought_orders=bought_orders, sold_orders=sold_orders)

@main.route('/my_listings')
@login_required
def my_listings():
    listings = current_user.listings
    return render_template('my_listings.html', listings=listings)

@main.route('/browse')
@login_required
def browse():
    # Show all products not sold and not listed by current user
    products = Product.query.filter_by(is_sold=False).filter(Product.seller_id != current_user.id).all()
    return render_template('browse.html', products=products)

@main.route('/sell', methods=['GET', 'POST'])
@login_required
def sell():
    form = SellForm()
    if form.validate_on_submit():
        picture_file = None
        if form.picture.data:
            picture_file = save_picture(form.picture.data)
        product = Product(
            title=form.title.data,
            description=form.description.data,
            price=form.price.data,
            image_file=picture_file,
            seller_id=current_user.id
        )
        db.session.add(product)
        db.session.commit()
        flash('Your item has been listed for sale!', 'success')
        return redirect(url_for('main.my_listings'))
    return render_template('sell.html', form=form)

@main.route('/edit_listing/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_listing(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller_id != current_user.id:
        flash('You are not authorized to edit this listing.', 'danger')
        return redirect(url_for('main.my_listings'))
    form = SellForm(obj=product)
    if form.validate_on_submit():
        product.title = form.title.data
        product.description = form.description.data
        product.price = form.price.data
        if form.picture.data:
            product.image_file = save_picture(form.picture.data)
        db.session.commit()
        flash('Listing updated.', 'success')
        return redirect(url_for('main.my_listings'))
    return render_template('sell.html', form=form, edit=True)

@main.route('/delete_listing/<int:product_id>', methods=['POST'])
@login_required
def delete_listing(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller_id != current_user.id:
        flash('You are not authorized to delete this listing.', 'danger')
        return redirect(url_for('main.my_listings'))
    db.session.delete(product)
    db.session.commit()
    flash('Listing deleted.', 'info')
    return redirect(url_for('main.my_listings'))

@main.route('/chats')
@login_required
def chats():
    # Get all distinct open chats for the current user (as sender or receiver, not deleted)
    sent = Message.query.filter_by(sender_id=current_user.id, deleted_by_sender=False).all()
    received = Message.query.filter_by(receiver_id=current_user.id, deleted_by_receiver=False).all()
    chat_partners = {}
    for m in sent + received:
        # Chat is uniquely identified by (other_user_id, product_id)
        other_id = m.receiver_id if m.sender_id == current_user.id else m.sender_id
        key = (other_id, m.product_id)
        if key not in chat_partners or m.timestamp > chat_partners[key].timestamp:
            chat_partners[key] = m
    # Sort chats by most recent message
    sorted_chats = sorted(chat_partners.values(), key=lambda x: x.timestamp, reverse=True)
    return render_template('chats.html', chats=sorted_chats, current_user=current_user)

@main.route('/delete_chat/<int:other_id>/<int:product_id>', methods=['POST'])
@login_required
def delete_chat(other_id, product_id):
    # Soft delete all messages for this chat for current user
    Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == other_id) | (Message.sender_id == other_id) & (Message.receiver_id == current_user.id)) & (Message.product_id == product_id)
    ).update({
        Message.deleted_by_sender: True if Message.sender_id == current_user.id else Message.deleted_by_sender,
        Message.deleted_by_receiver: True if Message.receiver_id == current_user.id else Message.deleted_by_receiver
    }, synchronize_session=False)
    db.session.commit()
    flash('Chat deleted.', 'info')
    return redirect(url_for('main.chats'))

@main.route('/contact/<int:seller_id>/<int:product_id>')
@login_required
def contact(seller_id, product_id):
    seller = User.query.get_or_404(seller_id)
    product = Product.query.get_or_404(product_id)
    # Load message history for this chat
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == seller_id) | (Message.sender_id == seller_id) & (Message.receiver_id == current_user.id)) & (Message.product_id == product_id)
    ).order_by(Message.timestamp.asc()).all()
    return render_template('chat.html', seller=seller, product=product, messages=messages)

@main.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.login'))

@socketio.on('join')
def handle_join(data):
    join_room(data['room'])

@socketio.on('chat_message')
def handle_chat_message(data):
    # Save message to DB
    sender_id = current_user.id
    receiver_id = int(data.get('receiver_id'))
    product_id = int(data.get('product_id'))
    msg = Message(sender_id=sender_id, receiver_id=receiver_id, product_id=product_id, message=data['message'])
    db.session.add(msg)
    db.session.commit()
    emit('chat_message', {
        'username': current_user.username,
        'message': data['message'],
        'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M')
    }, room=data['room'])
