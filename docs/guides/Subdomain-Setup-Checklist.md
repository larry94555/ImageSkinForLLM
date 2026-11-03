# Subdomain setup checklist

Every change needed so each customer's site opens at its own subdomain, such as `anna.me0.ai` (roadmap R71a). Tick each line once its check shows what the last column says. The step numbers are those of the [Subdomain setup guide](Subdomain-Setup-Guide.md), which says how to make each change; its **If it doesn't work** section helps when a line can't be ticked. Source of `Subdomain-Setup-Checklist.pdf`.

Run the `docker compose` and `grep` checks on the server, in `~/ImageSkinForLLM/deploy`; the `nslookup` checks on your laptop.

| ✓ | What | How to check | Right when |
|---|---|---|---|
| ☐ | me0.ai's nameservers are Cloudflare's (step 1) | `nslookup -type=NS me0.ai` on your laptop; Cloudflare's **Overview** for me0.ai | two `*.ns.cloudflare.com` names; Cloudflare says **Active** |
| ☐ | DNSSEC is off at Squarespace, or set up again in Cloudflare | Squarespace: **Domains**, **me0.ai**, **DNS** | off, or Cloudflare's **DNS**, **Settings** shows DNSSEC **Active** |
| ☐ | Every record from Squarespace is in Cloudflare (step 1.3) | Cloudflare: **DNS**, **Records** | the same `app`, email (MX, TXT) and website records |
| ☐ | `app.me0.ai` points at the machine, DNS only | `nslookup app.me0.ai`; its **Proxy status** in Cloudflare | the machine's IP; a grey cloud |
| ☐ | `*.me0.ai` points at the machine, DNS only (step 2) | `nslookup anything.me0.ai`; the `*` record's **Proxy status** | the machine's IP; a grey cloud |
| ☐ | The token can read the zone and edit its DNS (step 3) | Cloudflare: **My Profile**, **API Tokens**, the token's **Edit** | **Zone · DNS · Edit** and **Zone · Zone · Read**, for **me0.ai**; status **Active** |
| ☐ | `.env` has the domain and the token (step 4) | `grep -E "MAIN_DOMAIN\|CLOUDFLARE" .env` | `MAIN_DOMAIN=me0.ai` and the whole token, with no spaces or quotes |
| ☐ | `config.toml` has the same domain (step 4) | `grep main_domain config.toml` | `main_domain = "me0.ai"` |
| ☐ | Ports 80 and 443 are open in Oracle and on the machine | Oracle: the subnet's **Default Security List**; on the machine, `sudo iptables -L INPUT -n \| grep -E "dpt:(80\|443)"` | ingress rules for TCP 80 and 443 from `0.0.0.0/0`; two `ACCEPT` lines |
| ☐ | Caddy has Cloudflare's module (step 5) | `docker compose exec caddy caddy list-modules \| grep cloudflare` | `dns.providers.cloudflare` |
| ☐ | Caddy's settings are valid (step 5) | `docker compose exec caddy caddy validate --config /etc/caddy/Caddyfile` | `Valid configuration` |
| ☐ | The wildcard certificate was obtained (step 6) | `docker compose logs caddy \| grep -i "obtained"` | `certificate obtained successfully` for `*.me0.ai` |
| ☐ | A subdomain reaches the app (step 6) | open `https://nosuchsite.me0.ai` | a padlock and **Site not found**, with no password asked |
| ☐ | A site opens at its subdomain (step 6) | `imageskin site list`, then open one's address | that site, with the padlock |
