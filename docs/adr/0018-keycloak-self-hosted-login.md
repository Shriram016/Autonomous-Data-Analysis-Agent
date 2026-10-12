# Login uses self-hosted Keycloak (OIDC); the backend only verifies tokens

Managers log in through Keycloak, an open-source identity server run as one more Docker container. It owns sign-up, password hashing, brute-force protection, token issuing (JWT), refresh/expiry, password reset and admin. Our backend only verifies each request's JWT against Keycloak's public keys (standard OIDC) and reads the manager's identity. No cloud or login-vendor dependency, works identically on a laptop and on EC2, and no security-critical login code of our own.

## Considered Options

- **Build our own** (password hashing, JWT issuing, refresh, reset, lockout in FastAPI). Deep learning, but every piece is a known source of security bugs; "rolled their own auth" reads as a red flag. Rejected.
- **AWS Cognito.** Low code lock-in via OIDC, but high data lock-in: it won't export password hashes, so leaving means every manager resets their password; ties login to the (provisional) cloud choice; cloud-only, no local Docker. Rejected.
- **Auth0 / Clerk.** Secure and easy, but accounts live with a vendor; cloud-only; paid beyond free tiers. Rejected.
- **Authentik / Zitadel.** Same pattern as Keycloak and lighter on RAM; kept as fallbacks if Keycloak's memory use is a problem on a single VM.

## Key distinction (learning note)

JWT is a token format; OAuth 2.0 / OIDC are the protocols for issuing tokens; Keycloak is a complete server implementing them. The real choice is who issues tokens and holds the accounts, not how the backend uses them: token verification is the same either way.

## Consequences

- One more service (~0.5–1 GB RAM) in Docker Compose and on the VM.
- User accounts live in our own database: exportable, no lock-in.
- Single sign-on ("Sign in with Google/Microsoft") can be added later as Keycloak config.
- The backend's token check is the integration point; the UI only handles the login redirect and sends the token.

## Questions that drove this

- Who holds the user accounts, and can we take them with us?
- Which login code is security-critical, and should we write it?
- Does the choice tie login to a cloud or vendor?
- Does it work the same locally and in deployment?
