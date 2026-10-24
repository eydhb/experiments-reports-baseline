# Login analysis fixture

This is a deliberately small, synthetic Java/Spring-style repository for static
issue-localization demonstrations. It is not a real GitHub project and is not a
complete, runnable application. No dependency download or Java execution is needed.

The example question is: `登录接口返回 500`.

## Intended behavior and planted defect

`POST /api/login` calls `UserService.authenticate()`, which asks `TokenService`
to validate a supplied refresh token. An expired token throws
`TokenExpiredException`. `GlobalExceptionHandler` handles bad credentials as 401,
but has no specific mapping for `TokenExpiredException`. Its generic exception
handler therefore maps this exception to 500.

A potential fix is a dedicated `TokenExpiredException` handler that returns 401,
followed by an integration test submitting an expired token and checking the
response status. The fixture intentionally leaves that handler absent.

This is a hypothesis supported by source code, not an observed production
incident. Confirm a real incident using its stack trace, token timestamps and
actual framework configuration.

`HealthController` is unrelated to authentication and is included as a distractor.
