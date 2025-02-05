# Spotify Buddy Service

A microservice that provides access to Spotify friend activity data using the unofficial Spotify Buddylist API.

## Prerequisites

- Node.js (v14 or higher)
- npm (comes with Node.js)
- A valid Spotify account with an active web session

## Installation

1. Install dependencies:
```bash
npm install
```

2. Get your SP_DC cookie from Spotify:
   - Log into [Spotify Web Player](https://open.spotify.com)
   - Open your browser's Developer Tools (F12)
   - Go to Application/Storage > Cookies > https://open.spotify.com
   - Find the `sp_dc` cookie and copy its value

3. Create a `.env` file in the buddy_service directory:
```env
SP_DC=your_sp_dc_cookie_here
PORT=3000  # Optional, defaults to 3000
```

## Usage

1. Start the service:
```bash
node index.js
```

2. The service will be available at:
   - Health check: http://localhost:3000/health
   - Friend activity: http://localhost:3000/friend-activity

## API Endpoints

### GET /health
Returns the service health status.

Response:
```json
{
  "status": "healthy"
}
```

### GET /friend-activity
Returns the current friend activity from Spotify.

Success Response:
```json
{
  "friends": [
    {
      "timestamp": "2024-02-05T22:27:51.234Z",
      "user": {
        "name": "Friend Name",
        "uri": "spotify:user:username"
      },
      "track": {
        "name": "Song Name",
        "artist": {
          "name": "Artist Name"
        }
      }
    }
  ]
}
```

Error Response:
```json
{
  "error": "Error message",
  "details": "Detailed error information"
}
```

## Error Handling

The service includes comprehensive error handling for:
- Missing or invalid SP_DC cookie
- Network connectivity issues
- API response errors
- Authentication failures

## Integration with Flask App

The buddy service is designed to work with the main Flask application. The Flask app includes an endpoint at `/api/friend-activity` that proxies requests to this service.

## Security Notes

- The SP_DC cookie is sensitive information. Never commit it to version control.
- The service is configured to only accept requests from the Flask app (localhost:5001).
- CORS is properly configured for secure communication.

## Troubleshooting

1. If you get authentication errors:
   - Verify your SP_DC cookie is correct and not expired
   - Try logging out and back into Spotify Web Player
   - Clear your browser cookies and get a fresh SP_DC

2. If the service won't start:
   - Check if port 3000 is available
   - Verify Node.js is installed correctly
   - Check the .env file exists with proper values

3. If you get CORS errors:
   - Verify the Flask app is running on port 5001
   - Check the CORS configuration in index.js 