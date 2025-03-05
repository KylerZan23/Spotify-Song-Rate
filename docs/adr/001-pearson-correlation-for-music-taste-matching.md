# ADR 001: Implementing Pearson Correlation Coefficient for Music Taste Matching

## Status

Accepted

## Context

The application allows users to rate songs and compare their music tastes with other users. Previously, we used a simple difference-based approach to calculate a match percentage between users:

1. Find songs that both users have rated
2. Calculate the absolute difference between ratings for each shared song
3. Calculate the average difference
4. Convert to a percentage: `100% - (average_difference * 20)`

While this approach is intuitive, it has limitations:
- It doesn't account for different rating scales between users (some users might consistently rate higher than others)
- It treats all differences equally, regardless of the overall pattern
- It's not a statistically robust measure of similarity

## Decision

We will implement the Pearson Correlation Coefficient as an additional measure of similarity between users' music tastes. The Pearson Correlation:

1. Measures the linear correlation between two sets of ratings
2. Returns a value between -1 and 1:
   - 1: Perfect positive correlation (identical taste)
   - 0: No correlation (unrelated taste)
   - -1: Perfect negative correlation (opposite taste)
3. Normalizes for different rating scales and focuses on patterns rather than absolute values

The implementation will:
- Calculate both the original percentage match and the Pearson Correlation
- Display both metrics to users with appropriate explanations
- Categorize the correlation strength (e.g., "Very strong", "Strong", "Moderate", etc.)

## Consequences

### Positive

- Provides a more statistically sound measure of similarity
- Accounts for different rating tendencies between users
- Gives users more insight into how their music tastes align
- Enhances the application's analytical capabilities
- Allows for future features like recommendation systems based on correlation

### Negative

- Adds complexity to the codebase
- May be less intuitive for users to understand compared to the percentage match
- Requires additional UI space to explain the correlation
- Edge cases (e.g., when users have rated only a few shared songs) may produce unreliable results

### Mitigations

- We will keep the original percentage match alongside the correlation
- We will provide clear explanations of what the correlation means
- We will handle edge cases appropriately (e.g., return 0 correlation when there are insufficient shared ratings)
- We will add comprehensive tests to ensure the implementation is correct

## Implementation Notes

The Pearson Correlation is calculated using the formula:

```
r = Σ[(x_i - x̄)(y_i - ȳ)] / √[Σ(x_i - x̄)² * Σ(y_i - ȳ)²]
```

Where:
- x_i and y_i are individual ratings from each user
- x̄ and ȳ are the mean ratings for each user
- Σ represents summation

The implementation includes:
1. A `calculate_pearson_correlation` function that takes two lists of ratings
2. A `get_correlation_strength` function that converts the numerical correlation to a descriptive string
3. Updates to the match route to calculate and display the correlation
4. UI changes to display and explain the correlation
5. Comprehensive tests to verify the implementation 