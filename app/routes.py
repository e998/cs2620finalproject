from flask import Blueprint, current_app, render_template, redirect, url_for, flash, request, session, g
from flask_login import login_user, logout_user, current_user, login_required
from .forms import LoginForm, RegistrationForm, SellForm
from shared.models import User, Product, Message, Offer, Order, Clients, Activity
from werkzeug.security import check_password_hash, generate_password_hash
from . import db
from .utils import save_picture
from flask_socketio import emit, join_room, leave_room
from . import socketio
from sqlalchemy import or_, and_
import os
import requests
from flask import jsonify
import json
import threading
import time
from datetime import datetime

STORE_FILE = 'distributed_store.json'
REPLICATION_QUEUE_FILE = 'replication_queue.json'

# --- Leader Election and State ---
from health import create_healthapp
app = create_healthapp()
with app.app_context():
    LEADER_NODE = os.environ.get('LEADER_NODE_URL')  # initial value, will be updated in memory
    currleader = Clients.query.filter_by(client=LEADER_NODE).first()
    if currleader:
        currleader.leader = True
    else:
        currleader = Clients(client=LEADER_NODE, leader=True)
        db.session.add(currleader)
    db.session.commit()

PORT = int(os.environ.get('PORT', 'PORT')) ###
PEERS = [p for p in os.environ.get('PEER_NODES', '').split(',') if p]
local_store = {}
replication_queue = []

leader_lock = threading.Lock()
last_alive_peers = set()

# --- Persistent distributed state ---
def load_store():
    global local_store
    try:
        with open(STORE_FILE, 'r') as f:
            local_store.update(json.load(f))
    except Exception:
        pass

def save_store():
    with open(STORE_FILE, 'w') as f:
        json.dump(local_store, f)

def load_replication_queue():
    try:
        with open(REPLICATION_QUEUE_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []

def save_replication_queue(queue):
    with open(REPLICATION_QUEUE_FILE, 'w') as f:
        json.dump(queue, f)

replication_queue = load_replication_queue()

# --- Heartbeat and Leader Election ---
def get_my_url():
    ip = os.environ.get('MY_IP') 
    port = os.environ.get('PORT', 8080)
    return f"http://{ip}:{port}"

def is_leader():
    with leader_lock:
        leader = get_my_url()
        set_leader(leader)
    return LEADER_NODE == get_my_url()

def set_leader(new_leader_url):
    global LEADER_NODE
    LEADER_NODE = new_leader_url
    from health import create_healthapp
    app = create_healthapp()
    with app.app_context():
        all_clients = Clients.query.all()
        for client in all_clients:
            if client.client == new_leader_url:
                if not client.leader:
                    client.became_leader_at = datetime.utcnow()
                client.leader = True
            else:
                if client.leader:
                    client.became_leader_at = None
                client.leader = False
        db.session.commit()

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

            activity = Activity(label="Login")
            db.session.add(activity)
            db.session.commit()
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

        activity = Activity(label="Registration")
        db.session.add(activity)
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
    if not is_leader():
        if request.method == 'POST':
            # Forward POST to leader
            data = request.form.to_dict()
            files = request.files
            # For file uploads, you may need to handle this differently or use a proxy
            return forward_to_leader('/sell', method='POST', json_data=data)
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

        activity = Activity(label="Item Listing")
        db.session.add(activity)
        db.session.commit()
        flash('Your item has been listed for sale!', 'success')
        return redirect(url_for('main.my_listings'))
    return render_template('sell.html', form=form)

@main.route('/edit_listing/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_listing(product_id):
    if not is_leader():
        if request.method == 'POST':
            data = request.form.to_dict()
            return forward_to_leader(f'/edit_listing/{product_id}', method='POST', json_data=data)
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

        activity = Activity(label="Listing Updated")
        db.session.add(activity)
        db.session.commit()
        flash('Listing updated.', 'success')
        return redirect(url_for('main.my_listings'))
    return render_template('sell.html', form=form, edit=True)

@main.route('/delete_listing/<int:product_id>', methods=['POST'])
@login_required
def delete_listing(product_id):
    if not is_leader():
        return forward_to_leader(f'/delete_listing/{product_id}', method='POST')
    product = Product.query.get_or_404(product_id)
    if product.seller_id != current_user.id:
        flash('You are not authorized to delete this listing.', 'danger')
        return redirect(url_for('main.my_listings'))
    db.session.delete(product)
    db.session.commit()

    activity = Activity(label="Listing Deleted")
    db.session.add(activity)
    db.session.commit()
    flash('Listing deleted.', 'info')
    return redirect(url_for('main.my_listings'))

@main.route('/buy_proposal/<int:product_id>', methods=['POST'])
@login_required
def buy_proposal(product_id):
    print(f"Authenticated: {current_user.is_authenticated}") ###
    if not is_leader():
        return forward_to_leader(f'/buy_proposal/{product_id}', method='POST')
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

    activity = Activity(label="Buy Proposal Sent")
    db.session.add(activity)
    db.session.commit()
    flash('Buy proposal sent to the seller!', 'success')
    return redirect(url_for('main.browse'))

@main.route('/accept_offer/<int:offer_id>', methods=['POST'])
@login_required
def accept_offer(offer_id):
    if not is_leader():
        return forward_to_leader(f'/accept_offer/{offer_id}', method='POST')
    offer = Offer.query.get_or_404(offer_id)
    if offer.seller_id != current_user.id or offer.status != 'Pending':
        flash('Invalid offer.', 'danger')
        return redirect(url_for('main.my_listings'))
    offer.status = 'Accepted'
    # Mark product as sold
    product = Product.query.get(offer.product_id)
    product.is_sold = True
    db.session.commit()
    # Cancel all other pending offers for this product
    other_offers = Offer.query.filter(
        Offer.product_id == offer.product_id,
        Offer.id != offer.id,
        Offer.status == 'Pending'
    ).all()
    for o in other_offers:
        o.status = 'Canceled'
    db.session.commit()
    # Create transaction history for buyer and seller
    order = Order(product_id=offer.product_id, buyer_id=offer.buyer_id, status='Completed')
    db.session.add(order)
    db.session.commit()

    activity = Activity(label="Sale")
    db.session.add(activity)
    db.session.commit()
    flash(f'Congrats! You have successfully sold {product.title}. All other pending offers have been canceled. Please contact the buyer via chat to discuss payment and shipping options.', 'success')
    return redirect(url_for('main.my_listings'))

@main.route('/cancel_offer/<int:offer_id>', methods=['POST'])
@login_required
def cancel_offer(offer_id):
    if not is_leader():
        return forward_to_leader(f'/cancel_offer/{offer_id}', method='POST')
    offer = Offer.query.get_or_404(offer_id)
    if offer.seller_id != current_user.id or offer.status != 'Pending':
        flash('Invalid offer.', 'danger')
        return redirect(url_for('main.my_listings'))
    offer.status = 'Rejected'
    db.session.commit()
    flash(f'Offer for {offer.product.title} has been cancelled.', 'info')
    return redirect(url_for('main.my_listings'))

@main.route('/delete_chat/<int:other_id>/<int:product_id>', methods=['POST'])
@login_required
def delete_chat(other_id, product_id):
    if not is_leader():
        return forward_to_leader(f'/delete_chat/{other_id}/{product_id}', method='POST')
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

@socketio.on('chat_message')
def handle_chat_message(data):
    if not is_leader():
        # Forward chat message to leader
        try:
            requests.post(f'{LEADER_NODE}/socketio/chat_message', json=data, timeout=2)
        except Exception as e:
            print(f'Could not forward chat message to leader: {e}')
        return
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

@main.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.login'))

@main.route('/set_key', methods=['POST'])
def set_key():
    key = request.json['key']
    value = request.json['value']
    if not is_leader():
        # Forward to leader
        try:
            resp = requests.post(f'{LEADER_NODE}/set_key', json={'key': key, 'value': value}, timeout=2)
            return (resp.text, resp.status_code, resp.headers.items())
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'Could not forward to leader: {e}'}), 503
    local_store[key] = value
    save_store()
    for peer in PEERS:
        try:
            requests.post(f'{peer}/replicate', json={'key': key, 'value': value}, timeout=1)
        except Exception as e:
            print(f'Could not replicate to {peer}: {e}')
            replication_queue.append({'peer': peer, 'key': key, 'value': value})
            save_replication_queue(replication_queue)
    return jsonify({'status': 'ok', 'key': key, 'value': value})

@main.route('/replicate', methods=['POST'])
def replicate():
    key = request.json['key']
    value = request.json['value']
    local_store[key] = value
    save_store()
    return jsonify({'status': 'replicated', 'key': key, 'value': value})

@main.route('/get_key/<key>', methods=['GET'])
def get_key(key):
    value = local_store.get(key)
    return jsonify({'key': key, 'value': value})

@main.route('/heartbeat', methods=['GET'])
def heartbeat():
    return jsonify({'status': 'alive', 'port': PORT})

@main.route('/cluster_status')
def cluster_status():
    # Get all clients and their info
    clients = Clients.query.all()
    return jsonify({
        'leader': LEADER_NODE,
        'clients': [
            {
                'client': c.client,
                'leader': c.leader,
                'last_connected': c.last_connected.isoformat() if c.last_connected else 'N/A',
                'last_disconnected': c.last_disconnected.isoformat() if c.last_disconnected else 'N/A'
            }
            for c in clients
        ]
    })

# Background thread for leader election and heartbeat
def leader_election():
    global LEADER_NODE, last_alive_peers
    from health import create_healthapp
    app = create_healthapp()

    while True:
        time.sleep(3)

        with app.app_context():
            # Gather all candidates (self + peers) with no duplicates
            candidates = []
            for peer in [get_my_url()] + PEERS:
                if peer not in candidates:
                    candidates.append(peer)
            alive = []
            for peer in candidates:
                try:
                    r = requests.get(f"{peer}/heartbeat", timeout=1)
                    if r.status_code == 200:
                        alive.append(peer)
                except Exception:
                    continue

            # Ensure all alive peers are present in the Clients table and update last_connected
            now = datetime.utcnow()
            for peer in alive:
                client = Clients.query.filter_by(client=peer).first()
                if not client:
                    client = Clients(client=peer)
                    db.session.add(client)
                    if not client.last_connected:
                        client.last_connected = now  # Set on first discovery
                        client.last_disconnected = None # Clear disconnect on first discovery
                else:
                    # If client exists, check if it needs its status updated
                    # Update last_connected ONLY if previously disconnected OR if it was somehow null
                    if (client.last_disconnected and (not client.last_connected or client.last_disconnected > client.last_connected)) or not client.last_connected:
                        client.last_connected = now
                        client.last_disconnected = None # Clear disconnect since it's alive again
                
            # Mark clients not in alive list as disconnected
            # Only mark as disconnected if it wasn't already disconnected
            all_clients = Clients.query.all()
            for client in all_clients:
                if client.client not in alive and not client.last_disconnected:
                    client.last_disconnected = now
            db.session.commit()

            # Debug: print alive list every cycle
            print(f"[Leader Election] Alive nodes: {alive}")

            if alive:
                # Always select the lowest (sorted) peer as leader
                new_leader = sorted(alive)[0]
                set_leader(new_leader)
                if get_my_url() == new_leader:
                    print(f"[Leader Election] I am the leader: {get_my_url()}")
                else:
                    print(f"[Leader Election] Current leader: {new_leader}")
            else:
                # No alive peers, default to self as leader
                set_leader(get_my_url())
                print(f"[Leader Election] No peers alive, self is leader.")

threading.Thread(target=leader_election, daemon=True).start()

# Background thread to retry failed replications

def retry_replications():
    while True:
        time.sleep(5)
        queue_copy = replication_queue[:]
        for item in queue_copy:
            peer, key, value = item['peer'], item['key'], item['value']
            try:
                requests.post(f'{peer}/replicate', json={'key': key, 'value': value}, timeout=1)
                replication_queue.remove(item)
                save_replication_queue(replication_queue)
            except Exception:
                continue
threading.Thread(target=retry_replications, daemon=True).start()

# Load state at startup
load_store()

# --- Utility for forwarding writes to leader ---
def forward_to_leader(path, method='POST', json_data=None):
    url = f"{LEADER_NODE}{path}"
    try:
        if method == 'POST':
            resp = requests.post(url, json=json_data, timeout=3)
        elif method == 'PUT':
            resp = requests.put(url, json=json_data, timeout=3)
        elif method == 'DELETE':
            resp = requests.delete(url, json=json_data, timeout=3)
        else:
            raise Exception('Unsupported method')
        return (resp.text, resp.status_code, resp.headers.items())
    except Exception as e:
        return (json.dumps({'status': 'error', 'message': f'Could not forward to leader: {e}'}), 503, [('Content-Type','application/json')])

@socketio.on('join')
def handle_join(data):
    join_room(data['room'])

def inject_offer_badge():
    if current_user.is_authenticated:
        pending_offer_count = Offer.query.filter_by(seller_id=current_user.id, status='Pending').count()
    else:
        pending_offer_count = 0
    return dict(pending_offer_count=pending_offer_count)

main.context_processor(inject_offer_badge)