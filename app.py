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
from datetime import datetime
import random
import pytz
import secrets
import urllib.parse

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)  # Generate a secure secret key
app.config['SESSION_COOKIE_NAME'] = 'spotify-login-session'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///songs.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure CORS with specific settings
CORS(app, resources={
    r"/*": {
        "origins": ["http://localhost:5000"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

# Set Spotify credentials
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID', '')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET', '')
SPOTIFY_REDIRECT_URI = 'http://localhost:5000/callback'

db = SQLAlchemy(app)

# Initialize Spotify clients
spotify_client_creds = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

# Initialize OAuth with proper configuration
cache_handler = FlaskSessionCacheHandler(session)
auth_manager = SpotifyOAuth(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET,
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope='user-read-private user-read-email user-follow-read playlist-read-collaborative',
    cache_handler=cache_handler,
    show_dialog=True
)

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

    def average_rating(self):
        if not self.ratings:
            return 0
        avg = sum(r.rating for r in self.ratings) / len(self.ratings)
        return round(avg)  # Round to nearest whole number

    def to_dict(self):
        return {
            'id': self.id,
            'spotify_id': self.spotify_id,
            'name': self.name,
            'artist': self.artist,
            'link': self.link,
            'artwork_url': self.artwork_url,
            'average_rating': self.average_rating(),
            'ratings_count': len(self.ratings),
            'added_date': self.added_date.isoformat() if self.added_date else None
        }

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Float, nullable=False)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'rating': self.rating,
            'song_id': self.song_id,
            'created_at': self.created_at.isoformat()
        }

def extract_spotify_id(spotify_url):
    match = re.search(r'track/([a-zA-Z0-9]+)', spotify_url)
    return match.group(1) if match else None

@app.before_request
def before_request():
    # Ensure session is available
    if not session.get('session_id'):
        session['session_id'] = secrets.token_urlsafe(32)

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
                    artwork_url=artwork_url
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
    # Get any existing imported songs from session
    imported_songs = []
    if 'imported_songs' in session:
        imported_songs = [Song.query.get(song_id) for song_id in session['imported_songs']]
        username = session.get('rating_username', '')
    
    if request.method == 'POST':
        if 'playlist_id' in request.form:
            # Handle playlist import
            playlist_id = request.form.get('playlist_id')
            username = request.form.get('username')  # Get username for all ratings
            num_songs = int(request.form.get('num_songs', 5))  # Default to 5 songs
            
            if not username:
                flash('Please provide a username')
                return redirect(url_for('rate_mode'))
            
            try:
                # Get all playlist tracks
                playlist_data = spotify_client_creds.playlist(playlist_id)
                all_tracks = playlist_data['tracks']['items']
                
                # Randomly select tracks
                selected_tracks = random.sample(all_tracks, min(num_songs, len(all_tracks)))
                
                imported_songs = []
                for item in selected_tracks:
                    track = item['track']
                    # Skip local tracks or None tracks
                    if not track or track.get('is_local', False):
                        continue
                        
                    # Check if song already exists
                    existing_song = Song.query.filter_by(spotify_id=track['id']).first()
                    if not existing_song:
                        # Get additional track details including artwork
                        track_info = spotify_client_creds.track(track['id'])
                        song = Song(
                            spotify_id=track['id'],
                            name=track['name'],
                            artist=track['artists'][0]['name'],
                            link=track['external_urls']['spotify'],
                            artwork_url=track_info['album']['images'][0]['url'] if track_info['album']['images'] else None
                        )
                        db.session.add(song)
                        db.session.commit()
                        imported_songs.append(song)
                    else:
                        imported_songs.append(existing_song)
                
                if not imported_songs:
                    flash('No valid songs found in the playlist to import.')
                    return redirect(url_for('rate_mode'))
                
                # Store imported songs and username in session
                session['imported_songs'] = [song.id for song in imported_songs]
                session['rating_username'] = username
                    
                flash(f'Successfully imported {len(imported_songs)} random songs from playlist!')
                return render_template('rate.html', imported_songs=imported_songs, username=username)
                
            except Exception as e:
                flash(f'Error importing playlist: {str(e)}')
                return redirect(url_for('rate_mode'))
        
        elif 'clear_imported' in request.form:
            # Clear imported songs from session
            session.pop('imported_songs', None)
            session.pop('rating_username', None)
            return redirect(url_for('rate_mode'))
        
        else:
            # Handle regular song rating
            username = request.form.get('username')
            rating = int(request.form.get('rating'))  # Now expecting integer 1-5
            song_id = int(request.form.get('song_id'))

            if not username or rating < 1 or rating > 5:
                flash('Please fill all fields correctly. Rating must be between 1 and 5 stars.')
                return redirect(url_for('rate_mode'))

            # Check if user has already rated this song
            existing_rating = Rating.query.filter_by(
                username=username,
                song_id=song_id
            ).first()

            if existing_rating:
                flash('You have already rated this song!')
                return redirect(url_for('rate_mode'))

            new_rating = Rating(username=username, rating=rating, song_id=song_id)
            db.session.add(new_rating)
            db.session.commit()
            
            # Remove rated song from imported songs if it exists
            if 'imported_songs' in session:
                session['imported_songs'] = [s for s in session['imported_songs'] if s != song_id]
                if not session['imported_songs']:  # If no more songs to rate
                    session.pop('imported_songs', None)
                    session.pop('rating_username', None)
            
            flash('Rating added successfully!')
            return redirect(url_for('rate_mode'))

    # Get a random song that hasn't been rated yet if no imported songs
    song = None if imported_songs else Song.query.order_by(db.func.random()).first()
    return render_template('rate.html', song=song, imported_songs=imported_songs, username=session.get('rating_username', ''))

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

@app.route('/overview', methods=['GET'])
def overview_mode():
    # Get username from query parameter if provided
    username = request.args.get('username', '')
    
    # Check if group_by_user is in the request, otherwise use session value or default to false
    if 'group_by_user' in request.args:
        group_by_user = request.args.get('group_by_user') == 'true'
        # Store the preference in session
        session['group_by_user'] = group_by_user
    else:
        # Use stored preference or default to false
        group_by_user = session.get('group_by_user', False)
    
    # Base query for ratings
    query = db.session.query(Rating, Song).join(Song)
    
    # Filter by username if provided
    if username:
        query = query.filter(Rating.username == username)
    
    # Order by most recent first
    query = query.order_by(Rating.created_at.desc())
    
    # Get all ratings with their associated songs
    ratings = query.all()
    
    # Set up timezone conversion
    utc = pytz.UTC
    pst = pytz.timezone('America/Los_Angeles')
    
    if group_by_user:
        # Group by users
        users_data = {}
        for rating, song in ratings:
            if rating.username not in users_data:
                users_data[rating.username] = []
            
            # Check if song already exists in user's list
            song_exists = False
            for existing_song in users_data[rating.username]:
                if existing_song['id'] == song.id:
                    song_exists = True
                    break
            
            if not song_exists:
                try:
                    track_info = spotify_client_creds.track(song.spotify_id)
                    artwork_url = track_info['album']['images'][0]['url'] if track_info['album']['images'] else None
                except:
                    artwork_url = None
                    
                song_data = {
                    'id': song.id,
                    'name': song.name,
                    'artist': song.artist,
                    'link': song.link,
                    'spotify_id': song.spotify_id,
                    'artwork_url': artwork_url,
                    'ratings': [],
                    'average_rating': song.average_rating()
                }
                users_data[rating.username].append(song_data)
            
            # Convert UTC time to PST
            utc_time = utc.localize(rating.created_at)
            pst_time = utc_time.astimezone(pst)
            
            # Add rating to the song's ratings list
            for user_song in users_data[rating.username]:
                if user_song['id'] == song.id:
                    user_song['ratings'].append({
                        'username': rating.username,
                        'rating': rating.rating,
                        'date': pst_time.strftime('%m/%d/%Y %I:%M %p PST')
                    })
        
        # Sort each user's songs by average rating
        for username in users_data:
            users_data[username] = sorted(
                users_data[username],
                key=lambda x: (x['average_rating'], len(x['ratings'])),
                reverse=True
            )
        
        return render_template('overview.html', users_data=users_data, group_by_user=True, filter_username=username)
    else:
        # Original song-based grouping
        songs_data = {}
        for rating, song in ratings:
            if song.id not in songs_data:
                try:
                    track_info = spotify_client_creds.track(song.spotify_id)
                    artwork_url = track_info['album']['images'][0]['url'] if track_info['album']['images'] else None
                except:
                    artwork_url = None
                    
                songs_data[song.id] = {
                    'id': song.id,
                    'name': song.name,
                    'artist': song.artist,
                    'link': song.link,
                    'spotify_id': song.spotify_id,
                    'artwork_url': artwork_url,
                    'ratings': [],
                    'average_rating': song.average_rating()
                }
            
            # Convert UTC time to PST
            utc_time = utc.localize(rating.created_at)
            pst_time = utc_time.astimezone(pst)
            
            songs_data[song.id]['ratings'].append({
                'username': rating.username,
                'rating': rating.rating,
                'date': pst_time.strftime('%m/%d/%Y %I:%M %p PST')
            })

        # Convert to list and sort by average rating
        sorted_songs = sorted(
            songs_data.values(),
            key=lambda x: (x['average_rating'], len(x['ratings'])),
            reverse=True
        )

        return render_template('overview.html', songs=sorted_songs, group_by_user=group_by_user, filter_username=username)

@app.route('/api/playlist_preview/<playlist_id>', methods=['GET'])
def playlist_preview(playlist_id):
    try:
        playlist_data = spotify_client_creds.playlist(playlist_id)
        preview_data = {
            'name': playlist_data['name'],
            'total_tracks': playlist_data['tracks']['total'],
            'tracks': []
        }
        
        # Get first 10 tracks for preview
        for item in playlist_data['tracks']['items'][:10]:
            track = item['track']
            preview_data['tracks'].append({
                'name': track['name'],
                'artist': track['artists'][0]['name']
            })
        
        return jsonify(preview_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/login')
def login():
    """Initialize Spotify OAuth when user clicks Personalize"""
    try:
        # Create a new OAuth instance for this request
        auth_manager = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope='user-read-private user-read-email user-follow-read playlist-read-collaborative',
            show_dialog=True,
            cache_handler=cache_handler
        )
        
        # Get the authorization URL
        auth_url = auth_manager.get_authorize_url()
        return redirect(auth_url)
        
    except Exception as e:
        print(f"Login error: {str(e)}")
        flash('Failed to initialize Spotify login. Please try again.')
        return redirect(url_for('index'))

@app.route('/callback')
def callback():
    """Handle the Spotify OAuth callback"""
    try:
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
        token_info = auth_manager.get_access_token(code)
        
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
        # Create Spotify client with stored token
        sp = spotipy.Spotify(auth=token_info['access_token'])
        
        try:
            # Verify the token still works
            sp.current_user()
        except:
            # Token might be expired, clear session and redirect to login
            session.clear()
            flash('Your session has expired. Please log in again.')
            return redirect(url_for('login'))
        
        # Get user's followed artists and users
        followed = sp.current_user_followed_artists()
        friends_data = []
        
        if followed and 'artists' in followed and 'items' in followed['artists']:
            for item in followed['artists']['items']:
                try:
                    if item['type'] == 'user':
                        friend_info = {
                            'id': item['id'],
                            'name': item['display_name'],
                            'image_url': item['images'][0]['url'] if item.get('images') else None,
                            'playlists': []
                        }
                        
                        playlists = sp.user_playlists(item['id'])
                        for playlist in playlists['items']:
                            if playlist.get('public', True):
                                friend_info['playlists'].append({
                                    'id': playlist['id'],
                                    'name': playlist['name'],
                                    'image_url': playlist['images'][0]['url'] if playlist.get('images') else None,
                                    'tracks_total': playlist['tracks']['total']
                                })
                        
                        if friend_info['playlists']:
                            friends_data.append(friend_info)
                except Exception as e:
                    print(f"Error processing user {item['id']}: {str(e)}")
                    continue
        
        if not friends_data:
            flash('No friends with public playlists found. Try following some Spotify users!')
        
        return render_template('friends.html', friends=friends_data)
        
    except Exception as e:
        flash(f'Error accessing Spotify: {str(e)}')
        session.clear()  # Clear invalid session
        return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        # Drop all tables and recreate them
        db.drop_all()
        db.create_all()
        print("Database initialized successfully!")
    app.run(debug=True) 