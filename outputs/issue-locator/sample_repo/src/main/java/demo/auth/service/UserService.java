package demo.auth.service;

import demo.auth.exception.BadCredentialsException;
import demo.auth.model.LoginRequest;
import demo.auth.model.LoginResponse;
import org.springframework.stereotype.Service;

@Service
public class UserService {
    private final TokenService tokenService;

    public UserService(TokenService tokenService) {
        this.tokenService = tokenService;
    }

    public LoginResponse authenticate(LoginRequest request) {
        if (request.username() == null || request.username().isBlank()) {
            throw new BadCredentialsException("Username is required");
        }
        tokenService.validateRefreshToken(request.refreshTokenExpiresAt());
        return new LoginResponse(request.username(), "authenticated");
    }
}
