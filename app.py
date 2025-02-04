from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
import os
from dotenv import load_dotenv
import re
import csv
from io import StringIO
from datetime import datetime

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///songs.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Set Spotify credentials as environment variables
os.environ['SPOTIPY_CLIENT_ID'] = os.getenv('SPOTIFY_CLIENT_ID', '')
os.environ['SPOTIPY_CLIENT_SECRET'] = os.getenv('SPOTIFY_CLIENT_SECRET', '')
os.environ['SPOTIPY_REDIRECT_URI'] = os.getenv('SPOTIPY_REDIRECT_URI', 'http://localhost:5000/callback')

db = SQLAlchemy(app)

# Initialize Spotify clients
spotify_client_creds = spotipy.Spotify(auth_manager=SpotifyClientCredentials())
spotify_oauth = spotipy.Spotify(auth_manager=SpotifyOAuth(scope='playlist-read-private'))

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
    ratings = db.relationship('Rating', backref='song', lazy=True)
    added_date = db.Column(db.DateTime, default=datetime.utcnow)

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
            'average_rating': self.average_rating(),
            'ratings_count': len(self.ratings)
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/input', methods=['GET', 'POST'])
def input_mode():
    if request.method == 'POST':
        username = request.form.get('username')
        spotify_link = request.form.get('spotify_link')
        rating = float(request.form.get('rating'))

        if not username or not spotify_link or rating < 0 or rating > 5:
            flash('Please fill all fields correctly')
            return redirect(url_for('input_mode'))

        spotify_id = extract_spotify_id(spotify_link)
        if not spotify_id:
            flash('Invalid Spotify URL. Please make sure you copy the full track URL from Spotify.')
            return redirect(url_for('input_mode'))

        try:
            # Verify Spotify credentials are loaded
            if not os.getenv('SPOTIFY_CLIENT_ID') or not os.getenv('SPOTIFY_CLIENT_SECRET'):
                flash('Spotify API credentials are not properly configured. Please check your .env file.')
                return redirect(url_for('input_mode'))

            track_info = spotify_client_creds.track(spotify_id)
            if not track_info:
                flash('Could not find the specified track on Spotify')
                return redirect(url_for('input_mode'))

            existing_song = Song.query.filter_by(spotify_id=spotify_id).first()

            if not existing_song:
                song = Song(
                    spotify_id=spotify_id,
                    name=track_info['name'],
                    artist=track_info['artists'][0]['name'],
                    link=spotify_link
                )
                db.session.add(song)
                db.session.commit()
            else:
                song = existing_song

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
        username = request.form.get('username')
        rating = float(request.form.get('rating'))
        song_id = int(request.form.get('song_id'))

        if not username or rating < 0 or rating > 5:
            flash('Please fill all fields correctly')
            return redirect(url_for('rate_mode'))

        new_rating = Rating(username=username, rating=rating, song_id=song_id)
        db.session.add(new_rating)
        db.session.commit()
        flash('Rating added successfully!')
        return redirect(url_for('rate_mode'))

    # Get a random song that hasn't been rated by the current user
    song = Song.query.order_by(db.func.random()).first()
    return render_template('rate.html', song=song)

@app.route('/api/playlists/<playlist_id>', methods=['GET'])
def get_playlist(playlist_id):
    try:
        playlist_data = spotify_oauth.playlist(playlist_id)
        
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
    
    # Base query for ratings
    query = db.session.query(Rating, Song).join(Song)
    
    # Filter by username if provided
    if username:
        query = query.filter(Rating.username == username)
    
    # Order by most recent first
    query = query.order_by(Rating.created_at.desc())
    
    # Get all ratings with their associated songs
    ratings = query.all()
    
    # Group ratings by song
    songs_data = {}
    for rating, song in ratings:
        if song.id not in songs_data:
            # Get song artwork using Spotify API
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
        songs_data[song.id]['ratings'].append({
            'username': rating.username,
            'rating': rating.rating,
            'date': rating.created_at.strftime('%Y-%m-%d %H:%M')
        })

    return render_template('overview.html', songs=songs_data.values(), filter_username=username)

if __name__ == '__main__':
    with app.app_context():
        # Drop all tables and recreate them
        db.drop_all()
        db.create_all()
        print("Database initialized successfully!")
    app.run(debug=True) 