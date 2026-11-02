# Caddy with Cloudflare's DNS module (roadmap R71a). Let's Encrypt gives the one certificate for
# every site's subdomain, *.me0.ai, only after a DNS check, which Caddy does through Cloudflare's
# API with the token in .env (docs/guides/Subdomain-Setup-Guide.md). Built by `docker compose build caddy`.
FROM caddy:2-builder AS builder
RUN xcaddy build --with github.com/caddy-dns/cloudflare

FROM caddy:2
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
