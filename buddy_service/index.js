require('dotenv').config();

const express = require('express');
const buddyList = require('spotify-buddylist');
const app = express();
const port = process.env.PORT || 3000;

// Enable CORS for your Flask app
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', 'http://localhost:5001');
  res.header('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type');
  res.header('Access-Control-Allow-Credentials', 'true');
  next();
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'healthy' });
});

// Endpoint to fetch friend activity
app.get('/friend-activity', async (req, res) => {
  try {
    // Get SP_DC cookie from environment variable
    const spDcCookie = process.env.SP_DC;
    if (!spDcCookie) {
      console.error('Missing SP_DC cookie. Please set the SP_DC environment variable.');
      return res.status(500).json({ 
        error: 'Configuration error: Missing SP_DC cookie',
        details: 'Please set the SP_DC environment variable with your Spotify cookie.'
      });
    }

    console.log('Obtaining web access token...');
    console.log('SP_DC cookie length:', spDcCookie.length);
    const tokenResponse = await buddyList.getWebAccessToken(spDcCookie);
    console.log('Access token obtained:', tokenResponse.accessToken ? 'Yes' : 'No');
    const accessToken = tokenResponse.accessToken;
    
    console.log('Fetching friend activity...');
    const friendActivity = await buddyList.getFriendActivity(accessToken);
    
    console.log('Friend activity response:', JSON.stringify(friendActivity, null, 2));
    console.log(`Successfully retrieved friend activity for ${friendActivity.friends?.length || 0} friends`);
    return res.json(friendActivity);
  } catch (error) {
    console.error('Error details:', {
      message: error.message,
      type: error.type,
      stack: error.stack
    });
    
    // Determine the appropriate error response
    let statusCode = 500;
    let errorMessage = 'Failed to fetch friend activity';
    
    if (error.message?.includes('cookie')) {
      statusCode = 401;
      errorMessage = 'Invalid or expired SP_DC cookie';
    } else if (error.message?.includes('token')) {
      statusCode = 401;
      errorMessage = 'Failed to obtain access token';
    } else if (error.type === 'invalid-json') {
      statusCode = 502;
      errorMessage = 'Invalid response from Spotify API';
    }
    
    return res.status(statusCode).json({
      error: errorMessage,
      details: error.message,
      type: error.type
    });
  }
});

// Start the server
app.listen(port, () => {
  console.log(`Buddy service is listening on port ${port}`);
  console.log('Available endpoints:');
  console.log('  - GET /health');
  console.log('  - GET /friend-activity');
}); 