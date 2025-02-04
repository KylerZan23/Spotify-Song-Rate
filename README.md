# Spotify Song Rate

A Flask web application that allows users to share and rate Spotify songs. The application features two modes:
1. Input Mode: Share and rate your favorite Spotify songs
2. Rate Mode: Discover and rate songs shared by other users

## Setup Instructions

1. Clone this repository
2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

3. Install the required packages:
```bash
pip install -r requirements.txt
```
Example

4. Set up your Spotify API credentials:
   - Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   - Create a new application
   - Copy your Client ID and Client Secret
   - Create a `.env` file based on `.env.example` and add your credentials:
```
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
```

5. Run the application:
```bash
python app.py
```

6. Open your browser and navigate to `http://localhost:5000`

## Features

- Share Spotify songs with others
- Rate songs on a scale of 0-5 (with 0.5 increments)
- View average ratings for songs
- Modern, responsive UI with Spotify-inspired design
- SQLite database for storing songs and ratings

## Usage

### Input Mode
1. Enter your username
2. Paste a Spotify song link
3. Rate the song (0-5)
4. Submit to add the song to the database

### Rate Mode
1. View a random song from the database
2. Listen to the song on Spotify
3. Enter your username
4. Submit your rating

## Technologies Used

- Flask
- SQLAlchemy
- Spotipy (Spotify Web API)
- Bootstrap 5
- SQLite 