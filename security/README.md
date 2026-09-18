# Security App

The `security` app uses Django's existing `auth_user` table for site users and owns the security records around it.

- Web sessions expire after 12 hours.
- First web login sends the user through Google Authenticator TOTP setup.
- The setup QR code is available at `/security/2fa/setup/qr/` during setup.
- The native app activates at `/security/api/app/activate/` using username, password, and the current six-digit TOTP code.
- Each installation receives a bearer token stored only as a hash in `AppInstallation`.
- App deactivation invalidates the token and records `deactivated_at`.

The `iolo` test account must complete the first-login setup before app activation.
