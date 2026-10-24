package demo.auth.model;

import java.time.Instant;

public record LoginRequest(String username, Instant refreshTokenExpiresAt) {
}
