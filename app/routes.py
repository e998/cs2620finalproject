from flask import Blueprint, render_template, redirect, url_for, flash, request, session, g
from flask_login import login_user, logout_user, current_user, login_required
from .forms import LoginForm, RegistrationForm, SellForm
from .models import User, Product, Message, Offer, Order
from werkzeug.security import check_password_hash, generate_password_hash
from . import db
from .utils import save_picture
from flask_socketio import emit, join_room, leave_room
from . import socketio
from sqlalchemy import or_, and_

main = Blueprint('main', __name__)

@main.route('/')
@login_required
def home():
    # Count unread messages for current user
    unread_count = Message.query.filter_by(receiver_id=current_user.id, is_read=False, deleted_by_receiver=False).count()
    return redirect(url_for('main.history', unread_count=unread_count))

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
    unread_count = Message.query.filter_by(receiver_id=current_user.id, is_read=False, deleted_by_receiver=False).count()
    bought_orders = current_user.orders  # Orders where user is the buyer
    sold_orders = [product.order for product in current_user.listings if product.is_sold and product.order]
    return render_template('history.html', bought_orders=bought_orders, sold_orders=sold_orders, unread_count=unread_count)
    
@main.route('/my_listings')
@login_required
def my_listings():
    listings = Product.query.filter_by(seller_id=current_user.id).all()
    # Show pending offers for user's listings
    offers = Offer.query.filter_by(seller_id=current_user.id, status='Pending').all()
    pending_offer_count = len(offers)
    return render_template('my_listings.html', listings=listings, offers=offers, pending_offer_count=pending_offer_count)

@main.route('/browse')
@login_required
def browse():
    # Show all products not sold and not listed by current user
    products = Product.query.filter_by(is_sold=False).filter(Product.seller_id != current_user.id).all()
    # Pending offers for current user
    pending_offers = Offer.query.filter_by(buyer_id=current_user.id, status='Pending').all()
    pending_offer_product_ids = set(offer.product_id for offer in pending_offers)
    return render_template('browse.html', products=products, pending_offer_product_ids=pending_offer_product_ids)

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

@main.route('/buy_proposal/<int:product_id>', methods=['POST'])
@login_required
def buy_proposal(product_id):
    product = Product.query.get_or_404(product_id)
    if product.is_sold or product.seller_id == current_user.id:
        flash('You cannot buy this item.', 'danger')
        return redirect(url_for('main.browse'))
    # Check if offer already exists
    existing = Offer.query.filter_by(product_id=product_id, buyer_id=current_user.id, status='Pending').first()
    if existing:
        flash('You have already sent a buy proposal for this item.', 'info')
        return redirect(url_for('main.browse'))
    offer = Offer(product_id=product_id, buyer_id=current_user.id, seller_id=product.seller_id)
    db.session.add(offer)
    db.session.commit()
    flash('Buy proposal sent to the seller!', 'success')
    return redirect(url_for('main.browse'))

@main.route('/accept_offer/<int:offer_id>', methods=['POST'])
@login_required
def accept_offer(offer_id):
    offer = Offer.query.get_or_404(offer_id)
    if offer.seller_id != current_user.id or offer.status != 'Pending':
        flash('Invalid offer.', 'danger')
        return redirect(url_for('main.my_listings'))
    offer.status = 'Accepted'
    # Mark product as sold
    product = Product.query.get(offer.product_id)
    product.is_sold = True
    db.session.commit()
    # Create transaction history for buyer and seller
    order = Order(product_id=offer.product_id, buyer_id=offer.buyer_id, status='Completed')
    db.session.add(order)
    db.session.commit()
    flash(f'Congrats! You have successfully sold {product.title}. Please contact the buyer via chat to discuss payment and shipping options.', 'success')
    return redirect(url_for('main.my_listings'))

@main.route('/cancel_offer/<int:offer_id>', methods=['POST'])
@login_required
def cancel_offer(offer_id):
    offer = Offer.query.get_or_404(offer_id)
    if offer.seller_id != current_user.id or offer.status != 'Pending':
        flash('Invalid offer.', 'danger')
        return redirect(url_for('main.my_listings'))
    offer.status = 'Rejected'
    db.session.commit()
    flash(f'Offer for {offer.product.title} has been cancelled.', 'info')
    return redirect(url_for('main.my_listings'))

@main.route('/chats')
@login_required
def chats():
    unread_count = Message.query.filter_by(receiver_id=current_user.id, is_read=False, deleted_by_receiver=False).count()
    # Only include messages not deleted for the current user
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
    return render_template('chats.html', chats=sorted_chats, current_user=current_user, unread_count=unread_count)

@main.route('/delete_chat/<int:other_id>/<int:product_id>', methods=['POST'])
@login_required
def delete_chat(other_id, product_id):
    # Soft delete all messages for this chat for current user
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == other_id) | (Message.sender_id == other_id) & (Message.receiver_id == current_user.id)) &
        (Message.product_id == product_id)
    ).all()
    for msg in messages:
        if msg.sender_id == current_user.id:
            msg.deleted_by_sender = True
        if msg.receiver_id == current_user.id:
            msg.deleted_by_receiver = True
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
    # Mark all received messages as read
    Message.query.filter_by(receiver_id=current_user.id, sender_id=seller_id, product_id=product_id, is_read=False).update({Message.is_read: True}, synchronize_session=False)
    db.session.commit()
    unread_count = Message.query.filter_by(receiver_id=current_user.id, is_read=False, deleted_by_receiver=False).count()
    return render_template('chat.html', seller=seller, product=product, messages=messages, unread_count=unread_count)

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

def inject_offer_badge():
    if current_user.is_authenticated:
        pending_offer_count = Offer.query.filter_by(seller_id=current_user.id, status='Pending').count()
    else:
        pending_offer_count = 0
    return dict(pending_offer_count=pending_offer_count)

main.context_processor(inject_offer_badge)
