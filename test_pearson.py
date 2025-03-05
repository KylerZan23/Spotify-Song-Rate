"""
Test the Pearson Correlation Coefficient implementation.

This script tests the Pearson Correlation Coefficient implementation
against known examples to ensure it's working correctly.
"""

import sys
import os
from app import calculate_pearson_correlation, get_correlation_strength

def test_perfect_positive_correlation():
    """Test perfect positive correlation."""
    x = [1, 2, 3, 4, 5]
    y = [1, 2, 3, 4, 5]
    correlation = calculate_pearson_correlation(x, y)
    print(f"Perfect positive correlation: {correlation}")
    assert abs(correlation - 1.0) < 0.0001, f"Expected 1.0, got {correlation}"
    assert get_correlation_strength(correlation) == "Very strong"

def test_perfect_negative_correlation():
    """Test perfect negative correlation."""
    x = [1, 2, 3, 4, 5]
    y = [5, 4, 3, 2, 1]
    correlation = calculate_pearson_correlation(x, y)
    print(f"Perfect negative correlation: {correlation}")
    assert abs(correlation + 1.0) < 0.0001, f"Expected -1.0, got {correlation}"
    assert get_correlation_strength(correlation) == "Very strong"

def test_no_correlation():
    """Test no correlation."""
    x = [1, 2, 3, 4, 5]
    y = [3, 3, 3, 3, 3]
    correlation = calculate_pearson_correlation(x, y)
    print(f"No correlation: {correlation}")
    assert abs(correlation) < 0.0001, f"Expected 0.0, got {correlation}"
    assert get_correlation_strength(correlation) == "Very weak or no correlation"

def test_moderate_correlation():
    """Test moderate correlation."""
    x = [1, 2, 3, 4, 5]
    y = [1, 3, 2, 4, 5]
    correlation = calculate_pearson_correlation(x, y)
    print(f"Moderate correlation: {correlation}")
    assert 0.7 < correlation < 0.95, f"Expected moderate correlation, got {correlation}"
    assert get_correlation_strength(correlation) == "Very strong"

def test_real_world_example():
    """Test with a real-world example of user ratings."""
    # User 1 ratings for 10 songs
    user1 = [5, 4, 5, 3, 2, 1, 5, 4, 3, 2]
    # User 2 ratings for the same 10 songs
    user2 = [4, 5, 5, 2, 1, 2, 4, 5, 3, 1]
    
    correlation = calculate_pearson_correlation(user1, user2)
    strength = get_correlation_strength(correlation)
    
    print(f"Real-world example correlation: {correlation}")
    print(f"Correlation strength: {strength}")

def test_edge_cases():
    """Test edge cases."""
    # Empty lists
    assert calculate_pearson_correlation([], []) == 0
    
    # Single element
    assert calculate_pearson_correlation([1], [1]) == 0
    
    # Different lengths
    assert calculate_pearson_correlation([1, 2, 3], [1, 2]) == 0
    
    # All same values in one list
    x = [3, 3, 3, 3]
    y = [1, 2, 3, 4]
    correlation = calculate_pearson_correlation(x, y)
    assert correlation == 0, f"Expected 0, got {correlation}"

if __name__ == "__main__":
    print("Testing Pearson Correlation Coefficient implementation...")
    
    test_perfect_positive_correlation()
    test_perfect_negative_correlation()
    test_no_correlation()
    test_moderate_correlation()
    test_real_world_example()
    test_edge_cases()
    
    print("All tests passed!") 