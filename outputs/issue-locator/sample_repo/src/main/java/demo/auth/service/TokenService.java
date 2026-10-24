package demo.auth.service;

import java.time.Instant;
import demo.auth.exception.TokenExpiredException;
import org.springframework.stereotype.Service;

@Service
public class TokenService {
    public void validateRefreshToken(Instant expiresAt) {
        if (expiresAt == null || !expiresAt.isAfter(Instant.now())) {
            throw new TokenExpiredException("Refresh token has expired");
        }
    }
}
