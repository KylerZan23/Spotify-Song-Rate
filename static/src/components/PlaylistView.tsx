import React, { useState, useEffect } from 'react';
import axios from 'axios';

interface Track {
  id: number;
  spotify_id: string;
  name: string;
  artist: string;
  link: string;
  average_rating: number;
  ratings_count: number;
}

interface Playlist {
  id: number;
  spotify_id: string;
  name: string;
  description: string;
  tracks: Track[];
}

interface PlaylistViewProps {
  playlistId: string;
}

const PlaylistView: React.FC<PlaylistViewProps> = ({ playlistId }) => {
  const [playlist, setPlaylist] = useState<Playlist | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [username, setUsername] = useState('');
  const [ratings, setRatings] = useState<Record<number, number>>({});

  useEffect(() => {
    const fetchPlaylist = async () => {
      try {
        const response = await axios.get(`/api/playlists/${playlistId}`);
        setPlaylist(response.data.playlist);
        setError(null);
      } catch (err) {
        setError('Failed to load playlist');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchPlaylist();
  }, [playlistId]);

  const handleRatingChange = (trackId: number, rating: number) => {
    setRatings(prev => ({
      ...prev,
      [trackId]: rating
    }));
  };

  const submitRatings = async () => {
    if (!username) {
      setError('Please enter a username');
      return;
    }

    try {
      const ratingPromises = Object.entries(ratings).map(([trackId, rating]) =>
        axios.post('/api/ratings', {
          username,
          song_id: parseInt(trackId),
          rating
        })
      );

      await Promise.all(ratingPromises);
      setError('Ratings submitted successfully!');
      setRatings({});
    } catch (err) {
      setError('Failed to submit ratings');
      console.error(err);
    }
  };

  const exportRatings = async () => {
    try {
      window.location.href = `/api/ratings/export${username ? `?username=${username}` : ''}`;
    } catch (err) {
      setError('Failed to export ratings');
      console.error(err);
    }
  };

  if (loading) return <div>Loading playlist...</div>;
  if (error) return <div className="error">{error}</div>;
  if (!playlist) return <div>No playlist found</div>;

  return (
    <div className="playlist-view">
      <h2>{playlist.name}</h2>
      <p>{playlist.description}</p>

      <div className="username-input">
        <input
          type="text"
          placeholder="Enter your username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
      </div>

      <div className="tracks-list">
        {playlist.tracks.map(track => (
          <div key={track.id} className="track-item">
            <div className="track-info">
              <h3>{track.name}</h3>
              <p>by {track.artist}</p>
              <p>Average Rating: {track.average_rating.toFixed(1)} ({track.ratings_count} ratings)</p>
              <a href={track.link} target="_blank" rel="noopener noreferrer">
                Listen on Spotify
              </a>
            </div>
            <div className="rating-input">
              <select
                value={ratings[track.id] || ''}
                onChange={(e) => handleRatingChange(track.id, parseFloat(e.target.value))}
              >
                <option value="">Rate this song</option>
                {[0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5].map(rating => (
                  <option key={rating} value={rating}>{rating}</option>
                ))}
              </select>
            </div>
          </div>
        ))}
      </div>

      <div className="actions">
        <button onClick={submitRatings} disabled={!username || Object.keys(ratings).length === 0}>
          Submit Ratings
        </button>
        <button onClick={exportRatings}>
          Export Ratings as CSV
        </button>
      </div>
    </div>
  );
};

export default PlaylistView; 