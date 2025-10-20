from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import json
import os
from datetime import datetime, timedelta
import hashlib
from calendar import monthrange

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-this-in-production'

# For PythonAnywhere - use absolute paths in the user's home directory
if 'PYTHONANYWHERE_DOMAIN' in os.environ:
    # PythonAnywhere environment
    BASE_DIR = os.path.expanduser('~/health_tracker_data')
else:
    # Local development environment
    BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'health_tracker_data')

# Ensure data directory exists
os.makedirs(BASE_DIR, exist_ok=True)

# JSON database files paths
USERS_FILE = os.path.join(BASE_DIR, 'users.json')
LOGS_FILE = os.path.join(BASE_DIR, 'logs.json')

print(f"Data directory: {BASE_DIR}")
print(f"Users file: {USERS_FILE}")
print(f"Logs file: {LOGS_FILE}")

def load_json(file):
    """Load JSON data from file, create file if it doesn't exist"""
    try:
        if os.path.exists(file):
            with open(file, 'r') as f:
                return json.load(f)
        else:
            # Create empty file if it doesn't exist
            print(f"Creating new file: {file}")
            with open(file, 'w') as f:
                json.dump({}, f)
            return {}
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading {file}: {e}")
        # Return empty dict and recreate file
        try:
            with open(file, 'w') as f:
                json.dump({}, f)
            return {}
        except Exception as e2:
            print(f"Critical error creating file {file}: {e2}")
            return {}

def save_json(file, data):
    """Save JSON data to file with error handling"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(file), exist_ok=True)
        
        # Save new data
        with open(file, 'w') as f:
            json.dump(data, f, indent=4)
        
        print(f"Data successfully saved to {file}")
        return True
    except Exception as e:
        print(f"Error saving to {file}: {e}")
        return False

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_current_time():
    return datetime.now().strftime('%H:%M')

def initialize_daily_log():
    return {
        'meals': {
            'morning': '',
            'afternoon': '', 
            'evening': '',
            'dinner_snacks': ''
        },
        'water_ml': 0,
        'sleep_hours': 0,
        'tasks': '',
        'period': {
            'start': '',
            'end': '',
            'notes': ''
        },
        'last_updated': {
            'breakfast': '',
            'lunch': '',
            'evening': '',
            'dinner': '',
            'water': '',
            'sleep': '',
            'tasks': '',
            'period': ''
        }
    }

def calculate_period_calendar(period_history, cycle_length=28, period_duration=5, months=6):
    """Calculate period dates for calendar display for multiple months"""
    if len(period_history) < 1:
        return []
    
    # Get all period start dates
    period_dates = []
    for period in period_history:
        try:
            start_date = datetime.strptime(period['start'], '%Y-%m-%d')
            period_dates.append(start_date)
        except:
            continue
    
    if len(period_dates) < 1:
        return []
    
    # Use the last period as reference
    last_period = period_dates[-1]
    
    # Generate predictions for next months
    predictions = []
    
    for i in range(months):
        next_period = last_period + timedelta(days=cycle_length * (i + 1))
        # Add period window (based on user's average period duration)
        for day in range(period_duration):
            period_date = next_period + timedelta(days=day)
            predictions.append({
                'date': period_date.strftime('%Y-%m-%d'),
                'month': period_date.month,
                'year': period_date.year,
                'cycle_number': i + 1
            })
    
    return predictions

def get_period_delay(next_period_prediction):
    """Calculate if period is delayed"""
    if not next_period_prediction or next_period_prediction == "Need more data for prediction":
        return None
    
    try:
        predicted_date = datetime.strptime(next_period_prediction, '%Y-%m-%d')
        today = datetime.now()
        
        if today > predicted_date:
            delay_days = (today - predicted_date).days
            return delay_days
    except:
        pass
    
    return None

def calculate_cycle_analysis(period_history):
    """Calculate cycle statistics and predictions"""
    if len(period_history) < 2:
        return {
            'cycle_length': 28,
            'period_duration': 5,
            'cycle_regularity': 'Insufficient data',
            'next_ovulation': 'Need more data',
            'fertile_window': 'Need more data',
            'last_period_start': period_history[0]['start'] if period_history else 'No data'
        }
    
    # Get all period start dates
    period_dates = []
    for period in period_history:
        try:
            start_date = datetime.strptime(period['start'], '%Y-%m-%d')
            period_dates.append(start_date)
        except:
            continue
    
    if len(period_dates) < 2:
        return {
            'cycle_length': 28,
            'period_duration': 5,
            'cycle_regularity': 'Insufficient data',
            'next_ovulation': 'Need more data',
            'fertile_window': 'Need more data',
            'last_period_start': period_history[0]['start'] if period_history else 'No data'
        }
    
    # Calculate average cycle length
    period_dates.sort()
    differences = []
    for i in range(1, len(period_dates)):
        diff = (period_dates[i] - period_dates[i-1]).days
        differences.append(diff)
    
    avg_cycle = sum(differences) // len(differences)
    
    # Calculate cycle regularity
    cycle_variance = max(differences) - min(differences)
    if cycle_variance <= 3:
        regularity = 'Very Regular'
    elif cycle_variance <= 7:
        regularity = 'Regular'
    elif cycle_variance <= 10:
        regularity = 'Slightly Irregular'
    else:
        regularity = 'Irregular'
    
    # Calculate ovulation and fertile window
    last_period = period_dates[-1]
    next_period = last_period + timedelta(days=avg_cycle)
    
    # Ovulation typically occurs 14 days before next period
    ovulation_date = next_period - timedelta(days=14)
    fertile_start = ovulation_date - timedelta(days=3)
    fertile_end = ovulation_date + timedelta(days=1)
    
    # Estimate period duration (default to 5 days if not enough data)
    period_duration = 5
    
    return {
        'cycle_length': avg_cycle,
        'period_duration': period_duration,
        'cycle_regularity': regularity,
        'next_ovulation': ovulation_date.strftime('%Y-%m-%d'),
        'fertile_window': f"{fertile_start.strftime('%Y-%m-%d')} to {fertile_end.strftime('%Y-%m-%d')}",
        'last_period_start': last_period.strftime('%Y-%m-%d')
    }

def initialize_data_files():
    """Initialize data files if they don't exist"""
    print(f"Initializing data files in: {BASE_DIR}")
    
    # Initialize users file
    users_data = load_json(USERS_FILE)
    print(f"Users data loaded: {len(users_data)} users")
    
    # Initialize logs file
    logs_data = load_json(LOGS_FILE)
    print(f"Logs data loaded: {len(logs_data)} user logs")

# Initialize data files when module loads
initialize_data_files()

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        is_parent = 'parent_login' in request.form
        
        users = load_json(USERS_FILE)
        print(f"Login attempt - Email: {email}, Is Parent: {is_parent}, Total users: {len(users)}")
        
        for user_id, user_data in users.items():
            if is_parent:
                if (user_data.get('parent_email') == email and 
                    user_data.get('parent_password') == hash_password(password)):
                    session['parent_user_id'] = user_id
                    session['is_parent'] = True
                    print(f"Parent login successful for user: {user_id}")
                    return redirect(url_for('parent_dashboard'))
            else:
                if (user_data.get('email') == email and 
                    user_data.get('password') == hash_password(password)):
                    session['user_id'] = user_id
                    session['is_parent'] = False
                    print(f"User login successful for user: {user_id}")
                    return redirect(url_for('dashboard'))
        
        print("Login failed - invalid credentials")
        return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        users = load_json(USERS_FILE)
        print(f"Registration attempt - Email: {request.form['email']}")
        
        # Check if email already exists
        for user_id, user_data in users.items():
            if user_data.get('email') == request.form['email']:
                print("Registration failed - email already exists")
                return render_template('register.html', error='Email already registered')
            if user_data.get('parent_email') == request.form['parent_email']:
                print("Registration failed - parent email already exists")
                return render_template('register.html', error='Parent email already registered')
        
        user_data = {
            'name': request.form['name'],
            'email': request.form['email'],
            'password': hash_password(request.form['password']),
            'gender': request.form['gender'],
            'age': int(request.form['age']),
            'parent_name': request.form['parent_name'],
            'parent_email': request.form['parent_email'],
            'parent_password': hash_password(request.form['parent_password']),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        user_id = f"user_{len(users) + 1}"
        users[user_id] = user_data
        
        # Save user data
        if save_json(USERS_FILE, users):
            print(f"User saved successfully: {user_id}")
            # Create initial log entry
            logs = load_json(LOGS_FILE)
            logs[user_id] = {
                datetime.now().strftime('%Y-%m-%d'): initialize_daily_log()
            }
            if save_json(LOGS_FILE, logs):
                print(f"Initial logs created for user: {user_id}")
                return redirect(url_for('login'))
            else:
                print("Error creating user logs")
                return render_template('register.html', error='Error creating user logs')
        else:
            print("Error saving user data")
            return render_template('register.html', error='Error saving user data')
    
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session or session.get('is_parent'):
        return redirect(url_for('login'))
    
    users = load_json(USERS_FILE)
    logs = load_json(LOGS_FILE)
    
    user_id = session['user_id']
    today = datetime.now().strftime('%Y-%m-%d')
    
    print(f"Dashboard accessed - User: {user_id}, Today: {today}")
    
    if user_id not in logs:
        logs[user_id] = {}
        print(f"Created new logs entry for user: {user_id}")
    
    if today not in logs[user_id]:
        logs[user_id][today] = initialize_daily_log()
        print(f"Created new daily log for: {today}")
    
    if not save_json(LOGS_FILE, logs):
        print("Warning: Failed to save logs updates")
    
    # Calculate water percentage
    water_percentage = min((logs[user_id][today]['water_ml'] / 4000) * 100, 100)
    
    # Get period history for predictions
    period_history = []
    period_calendar = []
    period_delay = None
    cycle_analysis = {}
    
    if users[user_id].get('gender') == 'female':
        for date, log_data in logs[user_id].items():
            if log_data['period']['start']:
                period_history.append({
                    'date': date,
                    'start': log_data['period']['start']
                })
        
        cycle_analysis = calculate_cycle_analysis(period_history)
        next_period_prediction = predict_next_period(period_history, cycle_analysis['cycle_length'])
        period_calendar = calculate_period_calendar(
            period_history, 
            cycle_analysis['cycle_length'], 
            cycle_analysis['period_duration']
        )
        period_delay = get_period_delay(next_period_prediction)
    else:
        next_period_prediction = None
        period_calendar = []
        period_delay = None
        cycle_analysis = {}
    
    return render_template('dashboard.html', 
                         user=users[user_id],
                         today_log=logs[user_id][today],
                         water_percentage=water_percentage,
                         next_period_prediction=next_period_prediction,
                         period_calendar=period_calendar,
                         period_delay=period_delay,
                         cycle_length=cycle_analysis.get('cycle_length', 28),
                         period_duration=cycle_analysis.get('period_duration', 5),
                         cycle_regularity=cycle_analysis.get('cycle_regularity', 'Insufficient data'),
                         next_ovulation=cycle_analysis.get('next_ovulation', 'Need more data'),
                         fertile_window=cycle_analysis.get('fertile_window', 'Need more data'),
                         last_period_start=cycle_analysis.get('last_period_start', 'No data'))

@app.route('/parent_dashboard')
def parent_dashboard():
    if 'parent_user_id' not in session or not session.get('is_parent'):
        return redirect(url_for('login'))
    
    users = load_json(USERS_FILE)
    logs = load_json(LOGS_FILE)
    
    user_id = session['parent_user_id']
    today = datetime.now().strftime('%Y-%m-%d')
    
    print(f"Parent dashboard accessed - User: {user_id}, Today: {today}")
    
    if user_id not in logs or today not in logs[user_id]:
        today_log = initialize_daily_log()
    else:
        today_log = logs[user_id][today]
    
    water_percentage = min((today_log['water_ml'] / 4000) * 100, 100)
    
    # Get period history for predictions
    period_history = []
    period_calendar = []
    period_delay = None
    cycle_analysis = {}
    
    if users[user_id].get('gender') == 'female':
        if user_id in logs:
            for date, log_data in logs[user_id].items():
                if log_data['period']['start']:
                    period_history.append({
                        'date': date,
                        'start': log_data['period']['start']
                    })
        
        cycle_analysis = calculate_cycle_analysis(period_history)
        next_period_prediction = predict_next_period(period_history, cycle_analysis['cycle_length'])
        period_calendar = calculate_period_calendar(
            period_history, 
            cycle_analysis['cycle_length'], 
            cycle_analysis['period_duration']
        )
        period_delay = get_period_delay(next_period_prediction)
    else:
        next_period_prediction = None
        period_calendar = []
        period_delay = None
        cycle_analysis = {}
    
    return render_template('parent_dashboard.html',
                         user=users[user_id],
                         today_log=today_log,
                         water_percentage=water_percentage,
                         next_period_prediction=next_period_prediction,
                         period_calendar=period_calendar,
                         period_delay=period_delay,
                         cycle_length=cycle_analysis.get('cycle_length', 28),
                         period_duration=cycle_analysis.get('period_duration', 5),
                         cycle_regularity=cycle_analysis.get('cycle_regularity', 'Insufficient data'),
                         next_ovulation=cycle_analysis.get('next_ovulation', 'Need more data'),
                         fertile_window=cycle_analysis.get('fertile_window', 'Need more data'),
                         last_period_start=cycle_analysis.get('last_period_start', 'No data'))

@app.route('/update_log', methods=['POST'])
def update_log():
    if 'user_id' not in session or session.get('is_parent'):
        return jsonify({'success': False, 'error': 'Unauthorized'})
    
    user_id = session['user_id']
    today = datetime.now().strftime('%Y-%m-%d')
    data = request.get_json()
    
    print(f"Updating log for user: {user_id}, date: {today}")
    
    logs = load_json(LOGS_FILE)
    
    if user_id not in logs:
        logs[user_id] = {}
    
    if today not in logs[user_id]:
        logs[user_id][today] = initialize_daily_log()
    
    # Update specific fields
    if 'meals' in data:
        for meal_type, meal_content in data['meals'].items():
            logs[user_id][today]['meals'][meal_type] = meal_content
    
    if 'water_ml' in data:
        logs[user_id][today]['water_ml'] = data['water_ml']
    
    if 'sleep_hours' in data:
        logs[user_id][today]['sleep_hours'] = data['sleep_hours']
    
    if 'tasks' in data:
        logs[user_id][today]['tasks'] = data['tasks']
    
    if 'period' in data:
        logs[user_id][today]['period'].update(data['period'])
    
    # Update timestamps
    current_time = get_current_time()
    if 'update_type' in data:
        update_type = data['update_type']
        # Map meal types to timestamp fields
        timestamp_mapping = {
            'morning': 'breakfast',
            'afternoon': 'lunch', 
            'evening': 'evening',
            'dinner_snacks': 'dinner'
        }
        
        if update_type in timestamp_mapping:
            timestamp_field = timestamp_mapping[update_type]
            logs[user_id][today]['last_updated'][timestamp_field] = current_time
        elif update_type in logs[user_id][today]['last_updated']:
            logs[user_id][today]['last_updated'][update_type] = current_time
    
    # Save the updated logs
    if save_json(LOGS_FILE, logs):
        print(f"Log update successful for user: {user_id}")
        return jsonify({'success': True, 'timestamp': current_time})
    else:
        print(f"Log update failed for user: {user_id}")
        return jsonify({'success': False, 'error': 'Failed to save data'})

def predict_next_period(period_history, cycle_length=28):
    if len(period_history) < 1:
        return "Need more data for prediction"
    
    # Use the last period as reference
    last_period = datetime.strptime(period_history[-1]['start'], '%Y-%m-%d')
    
    # Calculate next period based on cycle length
    next_predicted = last_period + timedelta(days=cycle_length)
    
    return next_predicted.strftime('%Y-%m-%d')

@app.route('/debug/files')
def debug_files():
    """Debug endpoint to check file status"""
    if 'user_id' not in session and 'parent_user_id' not in session:
        return redirect(url_for('login'))
    
    debug_info = {
        'base_dir': BASE_DIR,
        'users_file': USERS_FILE,
        'logs_file': LOGS_FILE,
        'users_file_exists': os.path.exists(USERS_FILE),
        'logs_file_exists': os.path.exists(LOGS_FILE),
        'data_dir_exists': os.path.exists(BASE_DIR),
    }
    
    if os.path.exists(USERS_FILE):
        users = load_json(USERS_FILE)
        debug_info['users_count'] = len(users)
        debug_info['users'] = list(users.keys())
    
    if os.path.exists(LOGS_FILE):
        logs = load_json(LOGS_FILE)
        debug_info['logs_count'] = len(logs)
        debug_info['logs_users'] = list(logs.keys())
    
    return jsonify(debug_info)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    print("Health Tracker Application Started!")
    print(f"Data directory: {BASE_DIR}")
    print(f"Users file: {USERS_FILE}")
    print(f"Logs file: {LOGS_FILE}")
    app.run(debug=True)