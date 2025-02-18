from flask import Flask, render_template, request, redirect, url_for, session
from pymongo import MongoClient
from bson.objectid import ObjectId
import sys

app = Flask(__name__)
app.secret_key = 'your_secret_key'

client = MongoClient("mongodb+srv://musab05ahs:pyKC3HZqfrHTjD16@cluster0.l8wgb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client['ticket_reservation_system']
users_collection = db['users']
tickets_collection = db['tickets']
bookings_collection = db['bookings']
requests_collection = db['requests']

# Create admin user if not exists
if users_collection.count_documents({'username': 'admin'}) == 0:
    users_collection.insert_one({'username': 'admin', 'is_admin': True})

@app.route('/')
def home():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    user = users_collection.find_one({'username': username})
    if not user:
        # Add the user to the collection if not exists
        users_collection.insert_one({'username': username, 'is_admin': False})
        user = users_collection.find_one({'username': username})
    session['username'] = username
    session['is_admin'] = user.get('is_admin', False)
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('home'))
    if session.get('is_admin'):
        bookings = list(bookings_collection.find())
        return render_template('admin_dashboard.html', bookings=bookings)
    tickets = list(tickets_collection.find())
    bookings = list(bookings_collection.find({'username': session['username']}))
    return render_template('user_dashboard.html', tickets=tickets, bookings=bookings)

@app.route('/book', methods=['GET', 'POST'])
def book():
    print("Received POST request", file=sys.stderr)
    print("Form Data:", request.form, file=sys.stderr)
    if request.method == 'GET':
        return "This endpoint only accepts POST requests.", 400  # Handle GET request properly

    if 'username' not in session:
        return redirect(url_for('home'))
    
    # Ensure request contains necessary form data
    if not all(k in request.form for k in ['ticket_id', 'num_tickets', 'timestamp']):
        return jsonify({"error": "Missing form data"}), 400

    ticket_id = request.form['ticket_id']
    num_tickets = int(request.form['num_tickets'])
    timestamp = request.form['timestamp']
    
    # Send request for mutual exclusion
    requests_collection.insert_one({
        'username': session['username'],
        'timestamp': timestamp,
        'status': 'pending'
    })
    
    # Wait for replies
    while requests_collection.find_one({'username': session['username'], 'status': 'pending'}):
        pass
    
    ticket = tickets_collection.find_one({'_id': ObjectId(ticket_id)})
    if ticket and ticket['available'] >= num_tickets:
        booking_id = bookings_collection.insert_one({
            'username': session['username'],
            'ticket_id': ticket_id,
            'num_tickets': num_tickets
        }).inserted_id
        return redirect(url_for('payment', booking_id=booking_id))
    
    return jsonify({"error": "Not enough tickets available"}), 400


@app.route('/payment/<booking_id>', methods=['GET', 'POST'])
def payment(booking_id):
    if 'username' not in session:
        return redirect(url_for('home'))
    booking = bookings_collection.find_one({'_id': ObjectId(booking_id)})
    if request.method == 'POST':
        tickets_collection.update_one(
            {'_id': ObjectId(booking['ticket_id'])},
            {'$inc': {'available': -booking['num_tickets']}}
        )
        return redirect(url_for('dashboard'))
    return render_template('payment.html', booking=booking)

@app.route('/cancel', methods=['POST'])
def cancel():
    if 'username' not in session:
        return redirect(url_for('home'))
    booking_id = request.form['booking_id']
    booking = bookings_collection.find_one({'_id': ObjectId(booking_id)})
    if booking and booking['username'] == session['username']:
        num_tickets = int(request.form['num_tickets'])
        if num_tickets <= booking['num_tickets']:
            bookings_collection.update_one(
                {'_id': ObjectId(booking_id)},
                {'$inc': {'num_tickets': -num_tickets}}
            )
            tickets_collection.update_one(
                {'_id': ObjectId(booking['ticket_id'])},
                {'$inc': {'available': num_tickets}}
            )
            return redirect(url_for('dashboard'))
    return 'Invalid booking ID or number of tickets'

@app.route('/admin/set_tickets', methods=['POST'])
def set_tickets():
    if 'username' not in session or not session.get('is_admin'):
        return redirect(url_for('home'))
    total_tickets = int(request.form['total_tickets'])
    tickets_collection.update_one({}, {'$set': {'available': total_tickets}}, upsert=True)
    return 'Total tickets updated'

@app.route('/admin/add_user', methods=['GET', 'POST'])
def add_user():
    if 'username' not in session or not session.get('is_admin'):
        return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form['username']
        is_admin = 'is_admin' in request.form
        if users_collection.find_one({'username': username}):
            return 'User already exists'
        users_collection.insert_one({'username': username, 'is_admin': is_admin})
        return 'User added successfully'
    return render_template('add_user.html')

@app.route('/request', methods=['POST'])
def request_access():
    if 'username' not in session:
        return redirect(url_for('home'))
    timestamp = request.form['timestamp']
    requests_collection.insert_one({
        'username': session['username'], 
        'timestamp': timestamp,
        'status': 'pending'
    })
    return 'Request sent'

@app.route('/reply', methods=['POST'])
def reply_access():
    if 'username' not in session:
        return redirect(url_for('home'))
    requester = request.form['requester']
    requests_collection.update_one(
        {'username': requester, 'status': 'pending'},
        {'$set': {'status': 'granted'}}
    )
    return 'Reply sent'

if __name__ == '__main__':
    app.run(debug=True, port=5001)
