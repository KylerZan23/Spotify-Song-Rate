from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
from spotipy.cache_handler import FlaskSessionCacheHandler
import os
from dotenv import load_dotenv
import re
import csv
from io import StringIO
from datetime import datetime, timedelta
import random
import pytz
import secrets
import urllib.parse
import requests
import numpy as np

# Load environment variables
load_dotenv()

app = Flask(__name__)
# Use a fixed secret key from environment variable, with a default for development
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-123')
app.config['SESSION_COOKIE_NAME'] = 'spotify-login-session'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=60)
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///songs.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure CORS with specific settings
CORS(app, resources={
    r"/*": {
        "origins": ["http://localhost:5001"],  # Only use localhost:5001
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

# Set Spotify credentials
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID', '')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET', '')
SPOTIFY_REDIRECT_URI = 'http://localhost:5001/callback'

# Verify required environment variables
if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    raise ValueError("Missing Spotify API credentials. Please check your .env file.")

db = SQLAlchemy(app)

# Initialize Spotify clients
spotify_client_creds = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

# Initialize OAuth with proper configuration
cache_handler = FlaskSessionCacheHandler(session)

class Playlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    spotify_id = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    owner_id = db.Column(db.String(100), nullable=False)
    tracks = db.relationship('Song', secondary='playlist_songs', backref='playlists')

class PlaylistSong(db.Model):
    __tablename__ = 'playlist_songs'
    playlist_id = db.Column(db.Integer, db.ForeignKey('playlist.id'), primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id'), primary_key=True)
    position = db.Column(db.Integer, nullable=False)

class Song(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    spotify_id = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    artist = db.Column(db.String(200), nullable=False)
    link = db.Column(db.String(300), nullable=False)
    artwork_url = db.Column(db.String(300))
    ratings = db.relationship('Rating', backref='song', lazy=True)
    added_date = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_by = db.Column(db.String(100))  # New field to track who added the song

    @property
    def average_rating(self):
        if not self.ratings:
            return 0
        return sum(r.rating for r in self.ratings) / len(self.ratings)

    def to_dict(self):
        return {
            'id': self.id,
            'spotify_id': self.spotify_id,
            'name': self.name,
            'artist': self.artist,
            'link': self.link,
            'artwork_url': self.artwork_url,
            'average_rating': self.average_rating,
            'ratings': [{
                'username': r.username, 
                'rating': r.rating,
                'created_at': r.created_at
            } for r in self.ratings],
            'playlists': [{'name': p.name, 'spotify_id': p.spotify_id} for p in self.playlists],
            'submitted_by': self.submitted_by
        }

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Float, nullable=False)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(pytz.UTC))

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'rating': self.rating,
            'song_id': self.song_id,
            'created_at': self.created_at
        }

def extract_spotify_id(spotify_url):
    match = re.search(r'track/([a-zA-Z0-9]+)', spotify_url)
    return match.group(1) if match else None

@app.before_request
def before_request():
    # Make session permanent but with a lifetime
    session.permanent = True
    # Ensure session is available
    if not session.get('session_id'):
        session['session_id'] = secrets.token_urlsafe(32)
    
    # Log session data for debugging
    print("Current session data:", dict(session))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/input', methods=['GET', 'POST'])
def input_mode():
    if request.method == 'POST':
        username = request.form.get('username')
        spotify_link = request.form.get('spotify_link')
        rating = int(request.form.get('rating'))  # Now expecting integer 1-5

        if not username or not spotify_link or rating < 1 or rating > 5:
            flash('Please fill all fields correctly. Rating must be between 1 and 5 stars.')
            return redirect(url_for('input_mode'))

        spotify_id = extract_spotify_id(spotify_link)
        if not spotify_id:
            flash('Invalid Spotify URL. Please make sure you copy the full track URL from Spotify.')
            return redirect(url_for('input_mode'))

        try:
            # Verify Spotify credentials are loaded
            if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
                flash('Spotify API credentials are not properly configured. Please check your .env file.')
                return redirect(url_for('input_mode'))

            track_info = spotify_client_creds.track(spotify_id)
            if not track_info:
                flash('Could not find the specified track on Spotify')
                return redirect(url_for('input_mode'))

            existing_song = Song.query.filter_by(spotify_id=spotify_id).first()

            if not existing_song:
                # Get artwork URL from album images
                artwork_url = track_info['album']['images'][0]['url'] if track_info['album']['images'] else None
                
                song = Song(
                    spotify_id=spotify_id,
                    name=track_info['name'],
                    artist=track_info['artists'][0]['name'],
                    link=spotify_link,
                    artwork_url=artwork_url,
                    submitted_by=username  # Track who added the song
                )
                db.session.add(song)
                db.session.commit()
            else:
                song = existing_song

            # Check if user has already rated this song
            existing_rating = Rating.query.filter_by(
                username=username,
                song_id=song.id
            ).first()

            if existing_rating:
                flash('You have already rated this song!')
                return redirect(url_for('input_mode'))

            new_rating = Rating(username=username, rating=rating, song_id=song.id)
            db.session.add(new_rating)
            db.session.commit()

            flash(f'Successfully added rating for {song.name} by {song.artist}')
            return redirect(url_for('input_mode'))

        except spotipy.exceptions.SpotifyException as e:
            flash(f'Spotify API Error: {str(e)}')
            return redirect(url_for('input_mode'))
        except Exception as e:
            flash(f'Error processing track: {str(e)}')
            return redirect(url_for('input_mode'))

    return render_template('input.html')

@app.route('/rate', methods=['GET', 'POST'])
def rate_mode():
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        
        if form_type == 'single_song':
            username = request.form.get('username')
            spotify_link = request.form.get('spotify_link')
            rating_value = request.form.get('rating')
            
            if not all([username, spotify_link, rating_value]):
                flash('Please fill in all fields')
                return redirect(url_for('rate_mode'))
            
            try:
                spotify_id = extract_spotify_id(spotify_link)
                if not spotify_id:
                    flash('Invalid Spotify link')
                    return redirect(url_for('rate_mode'))
                
                # Get song details from Spotify
                track = spotify_client_creds.track(spotify_id)
                
                # Check if song exists in database
                song = Song.query.filter_by(spotify_id=spotify_id).first()
                if not song:
                    # Create new song if it doesn't exist
                    song = Song(
                        spotify_id=spotify_id,
                        name=track['name'],
                        artist=track['artists'][0]['name'],
                        link=track['external_urls']['spotify'],
                        artwork_url=track['album']['images'][0]['url'] if track['album']['images'] else None,
                        submitted_by=username
                    )
                    db.session.add(song)
                    db.session.commit()
                
                # Check if user has already rated this song
                existing_rating = Rating.query.filter_by(
                    username=username,
                    song_id=song.id
                ).first()

                if existing_rating:
                    flash('You have already rated this song!')
                    return redirect(url_for('rate_mode'))
                
                # Add rating
                rating = Rating(
                    username=username,
                    rating=float(rating_value),
                    song_id=song.id,
                    created_at=datetime.now(pytz.UTC)
                )
                db.session.add(rating)
                db.session.commit()
                
                flash('Rating submitted successfully!')
                
            except Exception as e:
                flash(f'Error: {str(e)}')
                return redirect(url_for('rate_mode'))
                
        elif form_type == 'playlist_import':
            username = request.form.get('username')
            playlist_id = request.form.get('playlist_id')
            track_ids = request.form.getlist('track_ids[]')
            ratings = request.form.getlist('ratings[]')
            
            if not all([username, playlist_id]) or not track_ids or not ratings:
                flash('Please fill in all fields and rate all songs')
                return redirect(url_for('rate_mode'))
            
            try:
                # Get playlist details
                playlist_data = spotify_client_creds.playlist(playlist_id)
                
                # Create or update playlist in database
                playlist = Playlist.query.filter_by(spotify_id=playlist_id).first()
                if not playlist:
                    playlist = Playlist(
                        spotify_id=playlist_id,
                        name=playlist_data['name'],
                        description=playlist_data.get('description', ''),
                        owner_id=playlist_data['owner']['id']
                    )
                    db.session.add(playlist)
                    db.session.commit()
                
                # Process each track and its rating
                processed_count = 0
                for track_id, rating in zip(track_ids, ratings):
                    track = spotify_client_creds.track(track_id)
                    
                    # Check if song exists
                    song = Song.query.filter_by(spotify_id=track_id).first()
                    if not song:
                        song = Song(
                            spotify_id=track_id,
                            name=track['name'],
                            artist=track['artists'][0]['name'],
                            link=track['external_urls']['spotify'],
                            artwork_url=track['album']['images'][0]['url'] if track['album']['images'] else None,
                            submitted_by=username
                        )
                        db.session.add(song)
                        db.session.commit()
                    
                    # Create playlist-song relationship if it doesn't exist
                    if song not in playlist.tracks:
                        playlist_song = PlaylistSong(
                            playlist_id=playlist.id,
                            song_id=song.id,
                            position=len(playlist.tracks)
                        )
                        db.session.add(playlist_song)
                    
                    # Add rating
                    new_rating = Rating(
                        username=username,
                        rating=float(rating),
                        song_id=song.id,
                        created_at=datetime.now(pytz.UTC)
                    )
                    db.session.add(new_rating)
                    processed_count += 1
                
                db.session.commit()
                flash(f'Successfully imported and rated {processed_count} songs from playlist "{playlist.name}"!')
                
            except Exception as e:
                flash(f'Error importing playlist: {str(e)}')
                return redirect(url_for('rate_mode'))
    
    # Get filter parameters for overview functionality
    group_by_user = request.args.get('group_by_user') == 'true'
    
    # Query songs and ratings
    query = Song.query.order_by(Song.added_date.desc())
    songs = query.all()
    # Sort songs by average rating in descending order
    songs.sort(key=lambda x: x.average_rating, reverse=True)
    
    if group_by_user:
        # Group songs by user and include playlist information
        users_data = {}
        for song in songs:
            for rating in song.ratings:
                if rating.username not in users_data:
                    users_data[rating.username] = []
                if song not in users_data[rating.username]:
                    # Include playlist information with the song
                    song_data = song.to_dict()
                    users_data[rating.username].append(song_data)
        
        # Sort each user's songs by average rating
        for username in users_data:
            users_data[username].sort(key=lambda x: x['average_rating'], reverse=True)
    else:
        users_data = None
    
    return render_template('rate.html',
                         songs=songs,
                         users_data=users_data,
                         group_by_user=group_by_user)

@app.route('/api/playlists/<playlist_id>', methods=['GET'])
def get_playlist(playlist_id):
    try:
        playlist_data = spotify_client_creds.playlist(playlist_id)
        
        # Create or update playlist in database
        playlist = Playlist.query.filter_by(spotify_id=playlist_id).first()
        if not playlist:
            playlist = Playlist(
                spotify_id=playlist_id,
                name=playlist_data['name'],
                description=playlist_data.get('description', ''),
                owner_id=playlist_data['owner']['id']
            )
            db.session.add(playlist)
            
        # Add tracks to database
        for idx, item in enumerate(playlist_data['tracks']['items']):
            track = item['track']
            song = Song.query.filter_by(spotify_id=track['id']).first()
            if not song:
                song = Song(
                    spotify_id=track['id'],
                    name=track['name'],
                    artist=track['artists'][0]['name'],
                    link=track['external_urls']['spotify']
                )
                db.session.add(song)
            
            # Create playlist-song relationship if it doesn't exist
            if song not in playlist.tracks:
                playlist_song = PlaylistSong(
                    playlist_id=playlist.id,
                    song_id=song.id,
                    position=idx
                )
                db.session.add(playlist_song)
        
        db.session.commit()
        return jsonify({
            'playlist': {
                'id': playlist.id,
                'spotify_id': playlist.spotify_id,
                'name': playlist.name,
                'description': playlist.description,
                'tracks': [song.to_dict() for song in playlist.tracks]
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/ratings/export', methods=['GET'])
def export_ratings():
    username = request.args.get('username')
    
    # Query ratings
    query = Rating.query
    if username:
        query = query.filter_by(username=username)
    
    ratings = query.all()
    
    # Create CSV in memory
    si = StringIO()
    cw = csv.writer(si)
    
    # Write header
    cw.writerow(['Username', 'Song Name', 'Artist', 'Rating', 'Date Rated', 'Spotify Link'])
    
    # Write data
    for rating in ratings:
        cw.writerow([
            rating.username,
            rating.song.name,
            rating.song.artist,
            rating.rating,
            rating.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            rating.song.link
        ])
    
    output = si.getvalue()
    si.close()
    
    return send_file(
        StringIO(output),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'song_ratings{"_" + username if username else ""}.csv'
    )

@app.route('/overview')
def overview_mode():
    return redirect(url_for('rate_mode'))

@app.route('/api/playlist_preview/<playlist_id>', methods=['GET'])
def playlist_preview(playlist_id):
    try:
        playlist_data = spotify_client_creds.playlist(playlist_id)
        
        # Get all tracks from playlist (handling pagination)
        all_tracks = []
        results = playlist_data['tracks']
        all_tracks.extend(results['items'])
        while results['next']:
            results = spotify_client_creds.next(results)
            all_tracks.extend(results['items'])
        
        # Filter out local tracks and empty tracks
        valid_tracks = [
            item['track'] for item in all_tracks 
            if item['track'] and not item['track'].get('is_local', False)
        ]
        
        # Randomly shuffle the tracks
        random.shuffle(valid_tracks)
        
        preview_data = {
            'name': playlist_data['name'],
            'total_tracks': len(valid_tracks),
            'tracks': []
        }
        
        # Take the first 20 tracks after shuffling (we'll limit by user's selection later)
        for track in valid_tracks[:20]:
            preview_data['tracks'].append({
                'id': track['id'],
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'spotify_id': track['id']
            })
        
        return jsonify(preview_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/login')
def login():
    """Initialize Spotify OAuth when user clicks Personalize"""
    try:
        # Clear any existing OAuth state
        session.pop('oauth_state', None)
        
        # Generate new state
        state = secrets.token_urlsafe(16)
        session['oauth_state'] = state
        
        print("Setting new oauth_state in session:", state)
        
        # Create a new OAuth instance for this request
        auth_manager = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope='user-read-private user-read-email user-follow-read playlist-read-collaborative',
            cache_handler=cache_handler,
            show_dialog=True
        )
        
        # Get the authorization URL with our state
        auth_url = auth_manager.get_authorize_url(state=state)
        
        # Force session to be saved
        session.modified = True
        
        return redirect(auth_url)
        
    except Exception as e:
        print(f"Login error: {str(e)}")
        flash('Failed to initialize Spotify login. Please try again.')
        return redirect(url_for('index'))

@app.route('/callback')
def callback():
    """Handle the Spotify OAuth callback"""
    try:
        # Verify state parameter
        state = request.args.get('state')
        stored_state = session.get('oauth_state')
        
        print(f"Callback - Received state: {state}")
        print(f"Callback - Stored state: {stored_state}")
        print(f"Callback - Full session data: {dict(session)}")
        
        if not state or not stored_state or state != stored_state:
            print("State verification failed")
            flash('State verification failed. Please try again.')
            return redirect(url_for('index'))
        
        # Create a new OAuth instance
        auth_manager = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope='user-read-private user-read-email user-follow-read playlist-read-collaborative',
            cache_handler=cache_handler
        )
        
        # Get the access token
        code = request.args.get('code')
        if not code:
            flash('No authorization code received from Spotify.')
            return redirect(url_for('index'))
        
        # Get token info
        token_info = auth_manager.get_access_token(code, check_cache=False)
        
        if not token_info:
            flash('Failed to get access token. Please try again.')
            return redirect(url_for('index'))
        
        # Create Spotify client with token
        sp = spotipy.Spotify(auth=token_info['access_token'])
        
        # Get user profile
        user_info = sp.current_user()
        
        # Store necessary info in session
        session['token_info'] = token_info
        session['user_id'] = user_info['id']
        session['display_name'] = user_info['display_name']
        
        # Clean up the state
        session.pop('oauth_state', None)
        
        # Force session to be saved
        session.modified = True
        
        # Redirect to index with success message
        flash(f'Successfully logged in as {user_info["display_name"]}')
        return redirect(url_for('index'))
        
    except Exception as e:
        print(f"Callback error: {str(e)}")
        flash('Authentication failed. Please try again.')
        return redirect(url_for('index'))

@app.route('/friends')
def friends_mode():
    """Handle friends page access"""
    # Check if user is authenticated
    token_info = session.get('token_info')
    if not token_info:
        flash('Please log in using the Personalize button first.')
        return redirect(url_for('index'))
    
    try:
        sp = spotipy.Spotify(auth=token_info['access_token'])
        
        # Verify that the token is still valid
        try:
            sp.current_user()
        except Exception as e:
            session.clear()
            flash('Your session has expired. Please log in again.')
            return redirect(url_for('login'))
        
        # Fetch friend activity from the buddy service
        try:
            friend_activity_response = requests.get('http://localhost:3000/friend-activity')
            friend_activity_response.raise_for_status()
            friend_activity_data = friend_activity_response.json()
        except Exception as e:
            print(f"Error fetching friend activity: {str(e)}")
            friend_activity_data = {"friends": []}
        
        # Get the friend activity list
        friend_activity = friend_activity_data.get('friends', [])
        
        # For each friend from the activity feed, extract their username and get playlists
        friend_playlists = []
        seen_usernames = set()  # Track unique usernames to avoid duplicates
        
        for activity in friend_activity:
            friend = activity.get('user', {})
            friend_uri = friend.get('uri', '')
            if friend_uri:
                # Spotify user URIs are in the format "spotify:user:USERNAME"
                friend_username = friend_uri.split(':')[-1]
                
                # Skip if we've already processed this friend
                if friend_username in seen_usernames:
                    continue
                seen_usernames.add(friend_username)
                
                try:
                    playlists_response = sp.user_playlists(friend_username)
                    playlists = []
                    # Iterate over the playlists and only add public ones
                    for playlist in playlists_response.get('items', []):
                        if playlist.get('public', True):
                            playlists.append({
                                'id': playlist['id'],
                                'name': playlist['name'],
                                'image_url': playlist['images'][0]['url'] if playlist.get('images') else None,
                                'tracks_total': playlist['tracks']['total']
                            })
                    # Only include friends that have at least one public playlist
                    if playlists:
                        friend_playlists.append({
                            'id': friend_username,
                            'name': friend.get('name'),
                            'image_url': friend.get('imageUrl'),
                            'playlists': playlists
                        })
                except Exception as e:
                    print(f"Error fetching playlists for friend {friend_username}: {str(e)}")
                    continue
        
        if not friend_playlists and not friend_activity:
            flash('No friends activity or playlists found. Try following some Spotify users!')
        
        # Render the template with both friend activity and playlists
        return render_template('friends.html', 
                            friend_activity=friend_activity, 
                            friends=friend_playlists,
                            friend_playlists=True)
        
    except Exception as e:
        flash(f'Error accessing Spotify: {str(e)}')
        session.clear()  # Clear invalid session
        return redirect(url_for('index'))

@app.route('/api/friend-activity')
def friend_activity():
    """Proxy endpoint to fetch friend activity from buddy service"""
    try:
        # Check if user is authenticated
        token_info = session.get('token_info')
        if not token_info:
            flash('Please log in using the Personalize button first.')
            return jsonify({'error': 'Not authenticated'}), 401

        # Call the buddy service
        response = requests.get('http://localhost:3000/friend-activity')
        response.raise_for_status()
        data = response.json()
        return jsonify(data)
    except requests.exceptions.ConnectionError:
        return jsonify({
            'error': 'Buddy service unavailable',
            'details': 'Make sure the buddy service is running on port 3000'
        }), 503
    except Exception as e:
        print(f"Error fetching friend activity: {str(e)}")
        return jsonify({
            'error': 'Failed to fetch friend activity',
            'details': str(e)
        }), 500

@app.route('/api/match-playlists', methods=['POST'])
def match_playlists():
    """Match playlists based on similarity scores and group similar playlists together."""
    try:
        data = request.get_json()
        playlist_ids = data.get('playlist_ids', [])
        weights = data.get('weights', {'jaccard': 0.5, 'cosine': 0.5})
        similarity_threshold = data.get('threshold', 0.6)  # Minimum similarity to be considered in same group
        
        if not playlist_ids or len(playlist_ids) < 2:
            return jsonify({'error': 'At least two playlist IDs are required'}), 400
            
        # Fetch all playlists and their tracks
        playlists_data = {}
        for playlist_id in playlist_ids:
            try:
                playlist = spotify_client_creds.playlist(playlist_id)
                tracks = []
                
                # Get all tracks (handling pagination)
                results = playlist['tracks']
                tracks.extend(results['items'])
                while results['next']:
                    results = spotify_client_creds.next(results)
                    tracks.extend(results['items'])
                
                # Extract track IDs and audio features
                track_ids = []
                for item in tracks:
                    if item['track'] and not item['track'].get('is_local', False):
                        track_ids.append(item['track']['id'])
                
                # Get audio features for all tracks
                audio_features = []
                for i in range(0, len(track_ids), 100):
                    batch = track_ids[i:i+100]
                    features = spotify_client_creds.audio_features(batch)
                    audio_features.extend([f for f in features if f is not None])
                
                playlists_data[playlist_id] = {
                    'name': playlist['name'],
                    'track_ids': set(track_ids),
                    'audio_features': audio_features
                }
            except Exception as e:
                print(f"Error fetching playlist {playlist_id}: {str(e)}")
                continue
        
        # Calculate similarity matrix
        n = len(playlists_data)
        similarity_matrix = np.zeros((n, n))
        playlist_ids_list = list(playlists_data.keys())
        
        for i in range(n):
            for j in range(i+1, n):
                id1, id2 = playlist_ids_list[i], playlist_ids_list[j]
                data1, data2 = playlists_data[id1], playlists_data[id2]
                
                # Calculate Jaccard similarity for track IDs
                intersection = len(data1['track_ids'].intersection(data2['track_ids']))
                union = len(data1['track_ids'].union(data2['track_ids']))
                jaccard_sim = intersection / union if union > 0 else 0
                
                # Calculate cosine similarity for audio features
                features1 = np.array([[
                    f['danceability'], f['energy'], f['key'], f['loudness'],
                    f['speechiness'], f['acousticness'], f['instrumentalness'],
                    f['liveness'], f['valence'], f['tempo']
                ] for f in data1['audio_features']])
                
                features2 = np.array([[
                    f['danceability'], f['energy'], f['key'], f['loudness'],
                    f['speechiness'], f['acousticness'], f['instrumentalness'],
                    f['liveness'], f['valence'], f['tempo']
                ] for f in data2['audio_features']])
                
                # Normalize features
                features1_mean = np.mean(features1, axis=0)
                features2_mean = np.mean(features2, axis=0)
                
                # Calculate cosine similarity between mean feature vectors
                cosine_sim = np.dot(features1_mean, features2_mean) / (
                    np.linalg.norm(features1_mean) * np.linalg.norm(features2_mean)
                )
                
                # Calculate weighted similarity score
                total_sim = (weights['jaccard'] * jaccard_sim + 
                           weights['cosine'] * cosine_sim)
                
                similarity_matrix[i, j] = total_sim
                similarity_matrix[j, i] = total_sim
        
        # Group playlists using similarity-based clustering
        groups = []
        unassigned = set(range(n))
        
        while unassigned:
            # Start a new group with the first unassigned playlist
            current = unassigned.pop()
            current_group = [current]
            
            # Find all similar playlists
            to_check = [current]
            while to_check:
                playlist_idx = to_check.pop(0)
                for other_idx in list(unassigned):
                    if similarity_matrix[playlist_idx, other_idx] >= similarity_threshold:
                        current_group.append(other_idx)
                        to_check.append(other_idx)
                        unassigned.remove(other_idx)
            
            # Add group to results
            group_playlists = [{
                'id': playlist_ids_list[idx],
                'name': playlists_data[playlist_ids_list[idx]]['name']
            } for idx in current_group]
            
            # Calculate average similarity within group
            group_similarities = []
            for i in range(len(current_group)):
                for j in range(i+1, len(current_group)):
                    idx1, idx2 = current_group[i], current_group[j]
                    group_similarities.append(similarity_matrix[idx1, idx2])
            
            avg_similarity = np.mean(group_similarities) if group_similarities else 1.0
            
            groups.append({
                'playlists': group_playlists,
                'average_similarity': float(avg_similarity)
            })
        
        # Sort groups by size and average similarity
        groups.sort(key=lambda x: (len(x['playlists']), x['average_similarity']), reverse=True)
        
        return jsonify({
            'groups': groups
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/match', methods=['GET', 'POST'])
def match():
    if request.method == 'POST':
        username1 = request.form.get('username1')
        username2 = request.form.get('username2')
        
        # Get ratings for both users from the database
        user1_ratings = Rating.query.filter_by(username=username1).all()
        user2_ratings = Rating.query.filter_by(username=username2).all()
        
        # Create dictionaries of song_id: rating for each user
        user1_dict = {rating.song_id: rating.rating for rating in user1_ratings}
        user2_dict = {rating.song_id: rating.rating for rating in user2_ratings}
        
        # Find shared songs
        shared_song_ids = set(user1_dict.keys()) & set(user2_dict.keys())
        
        if not shared_song_ids:
            match_result = {
                'percentage': 0,
                'shared_songs': [],
                'username1': username1,
                'username2': username2,
                'correlation': 0,
                'correlation_strength': 'No correlation (no shared songs)'
            }
        else:
            # Calculate match percentage using the old method
            total_diff = 0
            shared_songs = []
            
            # Prepare data for Pearson correlation
            user1_ratings_list = []
            user2_ratings_list = []
            
            for song_id in shared_song_ids:
                rating1 = user1_dict[song_id]
                rating2 = user2_dict[song_id]
                total_diff += abs(rating1 - rating2)
                
                # Add to lists for Pearson correlation
                user1_ratings_list.append(rating1)
                user2_ratings_list.append(rating2)
                
                # Get song details
                song = Song.query.get(song_id)
                shared_songs.append({
                    'name': song.name,
                    'artist': song.artist,
                    'rating1': rating1,
                    'rating2': rating2
                })
            
            # Calculate percentage (100% - average difference * 20)
            # A difference of 5 stars = 0% match, 0 stars = 100% match
            avg_diff = total_diff / len(shared_song_ids)
            match_percentage = max(0, 100 - (avg_diff * 20))
            
            # Calculate Pearson correlation coefficient
            correlation = calculate_pearson_correlation(user1_ratings_list, user2_ratings_list)
            
            # Determine correlation strength
            correlation_strength = get_correlation_strength(correlation)
            
            match_result = {
                'percentage': round(match_percentage, 1),
                'shared_songs': shared_songs,
                'username1': username1,
                'username2': username2,
                'correlation': round(correlation, 2),
                'correlation_strength': correlation_strength
            }
        
        return render_template('match.html', match_result=match_result)
    
    return render_template('match.html')

def calculate_pearson_correlation(x, y):
    """
    Calculate the Pearson correlation coefficient between two lists of ratings.
    
    Args:
        x (list): First user's ratings
        y (list): Second user's ratings
        
    Returns:
        float: Pearson correlation coefficient between -1 and 1
    """
    if len(x) != len(y) or len(x) < 2:
        return 0
    
    # Calculate means
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    
    # Calculate numerator (covariance)
    numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    
    # Calculate denominator (product of standard deviations)
    sum_x_squared = sum((xi - mean_x) ** 2 for xi in x)
    sum_y_squared = sum((yi - mean_y) ** 2 for yi in y)
    
    denominator = (sum_x_squared ** 0.5) * (sum_y_squared ** 0.5)
    
    # Avoid division by zero
    if denominator == 0:
        return 0
    
    return numerator / denominator

def get_correlation_strength(correlation):
    """
    Convert a correlation coefficient to a descriptive string.
    
    Args:
        correlation (float): Pearson correlation coefficient
        
    Returns:
        str: Description of correlation strength
    """
    correlation = abs(correlation)
    
    if correlation >= 0.8:
        return "Very strong"
    elif correlation >= 0.6:
        return "Strong"
    elif correlation >= 0.4:
        return "Moderate"
    elif correlation >= 0.2:
        return "Weak"
    else:
        return "Very weak or no correlation"

@app.template_filter('timestamp_to_time')
def timestamp_to_time(timestamp):
    """Convert a timestamp or datetime to a date format in PST"""
    # Create PST timezone
    pst = pytz.timezone('America/Los_Angeles')
    
    # If timestamp is already a datetime object, make sure it's timezone aware
    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            # If timestamp is naive, assume it's in UTC and convert to PST
            dt = pytz.utc.localize(timestamp).astimezone(pst)
        else:
            # If timestamp is already timezone aware, just convert to PST
            dt = timestamp.astimezone(pst)
    else:
        # Convert Unix timestamp to PST
        dt = datetime.fromtimestamp(timestamp, pst)
    
    # Return in date format: MM/DD/YYYY
    return dt.strftime('%m/%d/%Y')

if __name__ == '__main__':
    with app.app_context():
        # Drop all tables and recreate them
        db.drop_all()
        db.create_all()
        print("Database initialized successfully!")
    app.run(debug=True, port=5001) 