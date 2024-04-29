from flask import Flask, redirect, request, url_for, render_template, session, abort, jsonify
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import requests
import os
from flask_sqlalchemy import SQLAlchemy
from models import db, User, Activity  # Import db and User from models.py
from datetime import datetime
from flask_migrate import Migrate
from sqlalchemy import create_engine
from dotenv import load_dotenv


# Load environment variables from .env file
load_dotenv()

# Access environment variables
client_id = os.getenv("STRAVA_CLIENT_ID")
client_secret = os.getenv("STRAVA_CLIENT_SECRET")

app = Flask(__name__)
app.secret_key = os.getenv("SHOE_INSIGHTS_SECRET_KEY")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
migrate = Migrate(app, db)

db.init_app(app)

# Route to initiate OAuth2 authorization flow
@app.route('/authorize')
def authorize():
    # Construct the URL for Strava's authorization page
    strava_auth_url = 'https://www.strava.com/oauth/authorize'
    redirect_uri = 'http://127.0.0.1:5000/authorization/callback'  # Replace with your redirect URI
    scope = 'profile:read_all,activity:read_all'  # Replace with the desired scope
    auth_url = f'{strava_auth_url}?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope={scope}'
    print("I CREATED AN AUTH URL!")
    # Redirect the user to Strava's authorization page
    return redirect(auth_url)

@app.route('/authorization/callback')
def authorization_callback():
    error = request.args.get('error')
    if error == 'access_denied':
        return render_template('authorization_denied.html')
    else:
        # Extract the authorization code from the callback URL
        code = request.args.get('code')

        # Make a POST request to exchange the authorization code for an access token
        token_url = 'https://www.strava.com/oauth/token'
        data = {
            'client_id': 124834,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code'
        }
        response = requests.post(token_url, data=data)

        # Log the status code of the response
        print("Response status code:", response.status_code)

        # Handle the response from Strava
        if response.status_code == 200:
            # Extract user information from the response
            response_json = response.json()
            athlete_id = response_json.get('athlete').get('id')
            access_token = response_json.get('access_token')
            refresh_token = response_json.get('refresh_token')
            expires_at = response_json.get('expires_at')
            scope = response_json.get('scope')
            print("I GOT THE RESPONSE!")

            # Check if the user already exists in the database
            existing_user = User.query.filter_by(athlete_id=athlete_id).first()

            if existing_user:
                # Update the existing user's information
                existing_user.access_token = access_token
                existing_user.refresh_token = refresh_token
                existing_user.expires_at = expires_at
                existing_user.scope = scope
                db.session.commit()# Call get_and_update_athlete_summary with existing_user
                get_and_update_athlete_summary(existing_user)
                print("I CALLED A get_and_update_athlete_summary(existing_user) FUNCTION!")

                new_user_id = existing_user.id
            else:
                # Store user information in the database
                user = User(
                    athlete_id=athlete_id,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_at=expires_at,
                    scope=scope
                )
                db.session.add(user)
                db.session.commit()
                print("I STORED THE NEW USER INFO IN THE DATABASE!")
                new_user_id = user.id
                
                # Get and update athlete summary
                get_and_update_athlete_summary(user)
                print("I CALLED A get_and_update_athlete_summary(user) FUNCTION!")

            return redirect(url_for('authorization_success', user_id=new_user_id))
        else:
            return "Error: Unable to retrieve access token."

def deauthorize_user(access_token):
    deauth_url = 'https://www.strava.com/oauth/deauthorize'
    params = {'access_token': access_token}
    response = requests.post(deauth_url, params=params)

    if response.status_code == 200:
        return True  # Deauthorization successful
    else:
        return False  # Deauthorization failed
            
@app.route('/')
def main_page():
    return render_template('main_page.html')  # Replace 'main_page.html' with the name of your HTML template

# Function to refresh the access token if it has expired
def refresh_access_token(user):
    current_time = datetime.now().timestamp()
    if user.expires_at <= current_time:
        # Access token has expired, refresh it
        token_url = 'https://www.strava.com/oauth/token'
        data = {
            'client_id': 'YOUR_CLIENT_ID',
            'client_secret': 'YOUR_CLIENT_SECRET',
            'refresh_token': user.refresh_token,
            'grant_type': 'refresh_token'
        }
        response = requests.post(token_url, data=data)

        # Handle the response from Strava
        if response.status_code == 200:
            response_json = response.json()
            new_access_token = response_json.get('access_token')
            new_refresh_token = response_json.get('refresh_token')  # Optional: Refresh token may or may not change
            new_expires_at = response_json.get('expires_at')

            # Update user's access token in the database
            user.access_token = new_access_token
            user.refresh_token = new_refresh_token
            user.expires_at = new_expires_at
            db.session.commit()

            return new_access_token
        else:
            # Failed to refresh access token
            return None
    else:
        # Access token is still valid
        return user.access_token

# Functions to format seconds to mm:ss format
def convert_to_mm_ss(seconds):
    minutes, remainder = divmod(seconds, 60)
    return '{:02d}:{:02d}'.format(int(minutes), int(remainder))

def format_seconds(x, pos):
    minutes = int(x // 60)
    seconds = int(x % 60)
    return f"{minutes:02d}:{seconds:02d}"

#@app.route('/trigger_runstats/<int:athlete_id>', methods=['POST'])
#def trigger_runstats(athlete_id):
    # Directly trigger the stats_page route
    return jsonify({'status': 'success'})

@app.route('/stats_page/<int:athlete_id>', methods=['GET', 'POST'])
def stats_page(athlete_id):
    try:
        shoe_stats_data, scatter_plot_filename, box_plot_filename, pace_distance_scatter_plot_filename = runstats(athlete_id)

        # Render the HTML template with the data and filenames
        return render_template('stats_page.html', data=shoe_stats_data,
                               scatter_plot_filename=scatter_plot_filename,
                               box_plot_filename=box_plot_filename,
                               pace_distance_scatter_plot_filename=pace_distance_scatter_plot_filename)
    except Exception as e:
        return str(e), 500

@app.route('/runstats/<int:athlete_id>')
def runstats(athlete_id):
    print("I ENTERED THE INDEX ROUTE!")
    #print("Athlete ID:", athlete_id)  # Log the athlete_id

    # Query all activities using SQLAlchemy's ORM
    activities = Activity.query.filter_by(athlete_id=athlete_id).all()

    # Convert the queried activities into a list of dictionaries
    activity_data = []
    for activity in activities:
        activity_data.append({
            'athlete_id': activity.athlete_id,
            'activity_id': activity.activity_id,
            'activity_date': activity.activity_date,
            'activity_type': activity.activity_type,
            'elapsed_time': activity.elapsed_time,
            'moving_time': activity.moving_time,
            'distance': activity.distance,
            'average_speed': activity.average_speed,
            'gear_id': activity.gear_id,
            'pace': activity.pace
        })
    print("I COPIED ALL ACTIVITIES INTO THE ACTIVITY_DATA ARRAY!")

    # Convert the list of dictionaries into a DataFrame
    activities_df = pd.DataFrame(activity_data)
    print("I CONVERTED ACTIVITY_DATA INTO THE ACTIVITIES_DF!")

    # Filter records where Activity Type is 'Run'
    df = activities_df[activities_df['activity_type'] == 'Run']
    print("I FILTERED THE ACTIVITIES_DF TO ONLY INCLUDE RUNS!")

    # Convert 'distance' column to numeric
    df.loc[:, 'distance'] = pd.to_numeric(df['distance'], errors='coerce')
    print("I CONVERTED THE DISTANCE COLUMN TO NUMERIC!")

    # Convert speed from meters per second into pace format with seconds per kilometer
    df.loc[:, 'pace'] = 1 / df['average_speed'] * 1000
    print("I FILLED THE PACE COLUMN BASED ON AVERAFE SPEED!")

    # Convert seconds per kilometer to integer format
    df.loc[:, 'pace'] = df['pace'].astype(int)
    print("I CONVERTED THE PACE COLUMN TO INTEGER FORMAT!")

    # Fetch the shoe data from the User table and create a dictionary mapping gear IDs to shoe names
    shoe_mapping = {}

    # Fetch the current user data
    current_user = User.query.filter_by(athlete_id=athlete_id).first()

    # Fetch the shoe data from the User table and create a dictionary mapping gear IDs to shoe names
    current_user = User.query.filter_by(athlete_id=athlete_id).first()
    if current_user:
        shoes_data = json.loads(current_user.shoes)
        shoe_mapping = {shoe['id']: shoe['name'] for shoe in shoes_data}
    else:
        shoe_mapping = {}

    # Replace gear IDs with shoe names in the DataFrame
    if shoe_mapping:
        df['gear_id'] = df['gear_id'].map(shoe_mapping)
        print("I MAPPED GEAR IDS TO SHOE NAMES!")
    else:
        print("Shoe mapping not found!")
        df['gear_id'] = "Unknown"  # Assign a placeholder value for gear IDs if mapping is not found
    
    # Group by 'gear_id' and calculate the number of runs, average pace, and average distance for each shoe
    shoe_stats = df.groupby('gear_id').agg({'activity_id': 'count', 'pace': 'mean', 'distance': 'mean'}).reset_index()
    shoe_stats.columns = ['Gear', 'Number of Runs', 'Average Pace', 'Average Distance']
    print("I GROUPED BY GEAR_ID AND CALCULATED THE NUMBER OF RUNS, AVERAGE PACE, AND AVERAGE DISTANCE FOR EACH SHOE!")  

    # Convert average pace from seconds to mm:ss format
    shoe_stats['Average Pace'] = shoe_stats['Average Pace'].apply(convert_to_mm_ss)
    print("I CONVERTED AVERAGE PACE FROM SECONDS TO MM:SS FORMAT!") 

    # Round the average distance to two digits after the comma
    shoe_stats['Average Distance'] = (shoe_stats['Average Distance'] / 1000).round(2)
    print("I ROUNDED THE AVERAGE DISTANCE TO TWO DECIMALS AFTER THE COMMA!")

    # Sort the shoe statistics by the number of runs in descending order
    shoe_stats = shoe_stats.sort_values(by='Number of Runs', ascending=False)
    print("I SORTED THE SHOE STATISTICS BY THE NUMBER OF RUNS IN DESCENDING ORDER!")

    # Prepare data for rendering in HTML template
    shoe_stats_data = shoe_stats.to_dict(orient='records')
    print("I PREPARED THE TABLE DATA FOR RENDERING IN THE HTML TEMPLATE!")

    # Scatter Plot: Shoe Performance
    plt.figure(figsize=(8, 6))
    plt.scatter(shoe_stats['Gear'], shoe_stats['Average Pace'])
    plt.xlabel('Shoe')
    plt.ylabel('Average Pace (min/km)')
    print("I CREATED THE SCATTER PLOT!")

    # Set custom tick formatter for Y-axis
    plt.gca().yaxis.set_major_formatter(ticker.FuncFormatter(format_seconds))

    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    scatter_plot_filename = 'static/scatter_plot.png'
    plt.savefig(scatter_plot_filename, format='png')
    plt.close()  # Clear the current figure
    print("I SAVED THE SCATTER PLOT!")

    # Box Plot: Shoe Performance with outliers excluded
    plt.figure(figsize=(8, 6))
    box_plot = df.boxplot(column='pace', by='gear_id', showfliers=False, figsize=(8, 6))
    box_plot.set_title('')  # Remove the title "Boxplot grouped by Gear"
    plt.xlabel('')  # Remove X-axis label
    plt.ylabel('Pace (min/km)')
    plt.xticks(rotation=45, ha='right')
    print("I CREATED THE BOX PLOT!")

    # Set custom tick formatter for Y-axis
    box_plot.yaxis.set_major_formatter(ticker.FuncFormatter(format_seconds))

    plt.tight_layout()
    box_plot_filename = 'static/box_plot_no_outliers.png'
    plt.savefig(box_plot_filename, format='png')
    plt.close()  # Clear the current figure
    print("I SAVED THE BOX PLOT!")

    # Scatter Plot: Pace vs Distance
    plt.figure(figsize=(8, 6))
    print("I CREATED THE SCATTER PLOT-2!")

    # Define a list of colors for each shoe
    colors = ['b', 'g', 'r', 'c', 'm', 'y', 'k']

    # Loop through each unique shoe and plot its data with a different color
    for i, (shoe, group) in enumerate(df.groupby('gear_id')):
        plt.scatter(group['distance'], group['pace'], label=shoe, color=colors[i % len(colors)])

    plt.xlabel('Distance (m)')
    plt.ylabel('Pace (min/km)')
    plt.title('Scatter Plot: Pace vs Distance')

    # Set custom tick formatter for Y-axis
    plt.gca().yaxis.set_major_formatter(ticker.FuncFormatter(format_seconds))

    plt.legend()  # Show legend with shoe names
    plt.tight_layout()

    pace_distance_scatter_plot_filename = 'static/pace_distance_scatter_plot.png'
    plt.savefig(pace_distance_scatter_plot_filename, format='png')
    plt.close()  # Clear the current figure
    print("I SAVED THE SCATTER PLOT-2!")

    # Render the HTML template with the data
    return shoe_stats_data, scatter_plot_filename, box_plot_filename, pace_distance_scatter_plot_filename

@app.route('/logout')
def logout():
    if 'access_token' in session:
        access_token = session['access_token']
        # Deauthorize the user
        if deauthorize_user(access_token):
            # Clear the user's session
            session.pop('access_token', None)
            # Redirect to the main page or login page
            return redirect(url_for('main_page'))
        else:
            # Handle deauthorization failure
            return "Failed to deauthorize user", 500
    else:
        # User not logged in
        return redirect(url_for('main_page'))

# Function to make API call to get athlete summary and update user info
def get_and_update_athlete_summary(user):
    access_token = user.access_token
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get('https://www.strava.com/api/v3/athlete', headers=headers)
    
    if response.status_code == 200:
        athlete_summary = response.json()
        update_user_info(user, athlete_summary)
    else:
        print("Error fetching athlete summary:", response.text)

def update_user_info(user, athlete_summary):
    # Check if the name has changed
    if user.name != athlete_summary.get('firstname'):
        user.name = athlete_summary.get('firstname')
        print("User's name updated:", user.name)

    # Extract list of shoes and their IDs and names
    shoes = athlete_summary.get('shoes', [])

    # Process shoe data
    shoe_data = [{'id': shoe['id'], 'name': shoe['name']} for shoe in shoes]

    # Check if shoe data has changed
    if user.shoes != json.dumps(shoe_data):
        user.shoes = json.dumps(shoe_data)
        print("User's shoe data updated:", user.shoes)

    # Commit changes to the database
    db.session.commit()

@app.route('/users')
def list_users():
    users = User.query.all()
    user_data = []
    for user in users:
        user_data.append({
            'id': user.id,
            'name': user.name,
            'athlete_id': user.athlete_id,
            'access_token': user.access_token,
            'refresh_token': user.refresh_token,
            'expires_at': user.expires_at,
            'scope': user.scope,
            'shoes': user.shoes
        })
    return jsonify(user_data)

@app.route('/authorization/success/<int:user_id>')
def authorization_success(user_id):
    
    # Fetch user from the database by user ID
    user = User.query.get(user_id)
    if user is None:
        abort(404, "User not found")

    # Extract real user name and athlete ID
    user_name = user.name
    athlete_id = user.athlete_id
    user_id = user.id

    # Render the success template with user name and athlete ID
    return render_template('authorization_success.html', user_name=user_name, athlete_id=athlete_id, user_id=user_id)

@app.route('/fetch_activities/<int:user_id>')
def fetch_activities(user_id):
   # Fetch user from the database by user ID
    user = User.query.get(user_id)
    if user is None:
        abort(404, "User not found")
    
    # Trigger fetching and storing of activities
    fetch_and_store_activities(user)

    # Return a response
    return jsonify({"message": "Activities fetched and stored successfully!"})

def fetch_and_store_activities(user):
    access_token = user.access_token
    headers = {'Authorization': f'Bearer {access_token}'}
    before = int(datetime.now().timestamp())  # Set 'before' parameter to current time
    after = 0  # Set 'after' parameter to 0 to get all activities
    page = 1
    per_page = 200  # Set per_page to 200 for custom page size

    while True:
        params = {'before': before, 'after': after, 'page': page, 'per_page': per_page}
        response = requests.get('https://www.strava.com/api/v3/athlete/activities', headers=headers, params=params)
        
        if response.status_code == 200:
            activities = response.json()
            if not activities:  # If no activities returned, break the loop
                break
            
            # Process and store activities in the database
            store_activities_in_database(user, activities)
            
            # Increment page number for next request
            page += 1
        else:
            print("Error fetching activities:", response.text)
            break

def store_activities_in_database(user, activities):
    for activity in activities:
        # Extract relevant data from the activity JSON
        activity_id = activity.get('id')
        existing_activity = Activity.query.filter_by(athlete_id=user.athlete_id, activity_id=activity_id).first()

        if existing_activity:
            # Update existing activity
            existing_activity.activity_date = datetime.strptime(activity.get('start_date'), '%Y-%m-%dT%H:%M:%SZ')
            existing_activity.activity_type = activity.get('type')
            existing_activity.elapsed_time = activity.get('elapsed_time')
            existing_activity.moving_time = activity.get('moving_time')
            existing_activity.distance = activity.get('distance')
            existing_activity.average_speed = activity.get('average_speed')
            existing_activity.gear_id = activity.get('gear_id')
            # Assuming pace is not provided in the activity JSON
            existing_activity.pace = None  
        else:
            # Create a new activity object and store it in the database
            new_activity = Activity(
                athlete_id=user.athlete_id,
                activity_id=activity_id,
                activity_date=datetime.strptime(activity.get('start_date'), '%Y-%m-%dT%H:%M:%SZ'),
                activity_type=activity.get('type'),
                elapsed_time=activity.get('elapsed_time'),
                moving_time=activity.get('moving_time'),
                distance=activity.get('distance'),
                average_speed=activity.get('average_speed'),
                gear_id=activity.get('gear_id'),
                pace=None  
            )
            db.session.add(new_activity)

    db.session.commit()

@app.route('/activities')
def list_activities():
    activities = Activity.query.all()
    activity_data = []
    for activity in activities:
        activity_data.append({
            'id': activity.id,
            'athlete_id': activity.athlete_id,
            'activity_id': activity.activity_id,
            'activity_date': activity.activity_date,
            'activity_type': activity.activity_type,
            'elapsed_time': activity.elapsed_time,
            'moving_time': activity.moving_time,
            'distance': activity.distance,
            'average_speed': activity.average_speed
        })
    return jsonify(activity_data)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

