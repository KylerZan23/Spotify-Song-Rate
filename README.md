# Spotify Song Rate

A web application for rating and sharing Spotify songs with friends.

## Features

- Rate songs from Spotify
- View song ratings from other users
- Import songs from playlists
- Export ratings to CSV
- View friend activity (NEW!)
- Group ratings by user
- Sort by average rating
- Match music taste with other users using Pearson Correlation (NEW!)
- OAuth2 authentication with Spotify

## Architecture

The application consists of two main components:

1. **Flask Application (Main Service)**
   - Handles user authentication
   - Manages song ratings
   - Provides the web interface
   - Runs on port 5001

2. **Node.js Buddy Service**
   - Provides friend activity data
   - Uses unofficial Spotify API
   - Runs on port 3000

## Prerequisites

- Python 3.9+
- Node.js 14+
- npm (comes with Node.js)
- Spotify Developer Account
- Spotify Premium Account (for some features)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/KylerZan23/spotify-song-rate.git
cd spotify-song-rate
```

2. Set up the Flask application:
```bash
# Create and activate virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy example environment file and fill in your details
cp .env.example .env
```

3. Set up the Buddy Service:
```bash
cd buddy_service
npm install

# Copy example environment file and fill in your details
cp .env.example .env
```

## Configuration

### Flask Application (.env)
```env
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
FLASK_SECRET_KEY=your_secret_key
```

### Buddy Service (buddy_service/.env)
```env
SP_DC=your_spotify_cookie
PORT=3000
```

## Running the Application

1. Start the Flask application:
```bash
python app.py
```

2. Start the Buddy Service:
```bash
cd buddy_service
node index.js
```

3. Access the application at http://localhost:5001

## Usage

1. Log in with your Spotify account
2. Rate songs individually or import from playlists
3. View your friends' activity
4. Compare your music taste with other users
5. Export your ratings

## Music Taste Matching

The application uses two methods to compare music tastes between users:

1. **Simple Difference Method**
   - Calculates the average difference between ratings for shared songs
   - Converts to a percentage (100% - average difference * 20)
   - Easy to understand but less statistically robust

2. **Pearson Correlation Coefficient**
   - Measures the linear correlation between two users' ratings
   - Range from -1 to 1:
     - 1: Perfect positive correlation (identical taste)
     - 0: No correlation (unrelated taste)
     - -1: Perfect negative correlation (opposite taste)
   - Provides a more statistically sound measure of similarity
   - Accounts for different rating scales between users

The Pearson Correlation is particularly useful because it:
- Normalizes different rating tendencies (some users might rate everything high)
- Focuses on patterns rather than absolute values
- Is a widely accepted statistical measure for comparing preferences

## Development

- The Flask application uses SQLite for data storage
- Frontend uses vanilla JavaScript and Bootstrap
- Friend activity is fetched from a separate microservice

## Security Notes

- Never commit .env files
- Keep your SP_DC cookie private
- Use HTTPS in production
- Regularly rotate secret keys

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Spotify Web API
- Flask-SQLAlchemy
- spotify-buddylist package 