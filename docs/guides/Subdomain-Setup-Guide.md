# Subdomain setup guide

Step by step: how to set up me0.ai's DNS, the certificate and the server so each customer's site opens at its own subdomain (roadmap R71a). Once it's done, tick off every line of the [Subdomain setup checklist](Subdomain-Setup-Checklist.md) to confirm everything is in place. Source of `Subdomain-Setup-Guide.pdf`.

Each customer's site is at a subdomain of me0.ai, such as `anna.me0.ai`, beside the main address, `app.me0.ai` (roadmap R61). Trial sites need nothing more: they are at a path of the main address, such as `app.me0.ai/t/k7q2x9mf3a8w` (R61a), with its certificate. For subdomains, three things have to be in place:

1. **DNS:** a wildcard record, `*.me0.ai`, that sends every subdomain to the Oracle machine, as `app.me0.ai` already goes there.
2. **One certificate for every subdomain, `*.me0.ai`:** Let's Encrypt gives a wildcard certificate only after a DNS check, where Caddy adds a short-lived record to me0.ai's DNS through the DNS provider's API. Squarespace, where me0.ai is registered, has no such API, so its DNS moves to Cloudflare's free plan. **The domain stays registered and paid for at Squarespace**; only the nameservers change.
3. **Caddy** serves `*.me0.ai` as it serves `app.me0.ai`, with the certificate from step 2. It is built with Cloudflare's DNS module (`deploy/caddy/Dockerfile`) and finds the API token in `.env`.

**Oracle needs no change.** Ports 80 and 443 are already open from the first setup ([the deployment guide](../../deploy/README.md), steps 3 and 5), and the certificate check goes through DNS, not through the machine.

It takes about 30 minutes, most of it waiting for the nameservers to change. The sites keep working throughout: Cloudflare copies me0.ai's records before anything moves.

Until R71, every subdomain asks for the same name and password as the main address.

## 1. Move me0.ai's DNS to Cloudflare

1. Make a free account at https://dash.cloudflare.com/sign-up, or sign in.
2. Click **Add a domain** (or **Add a site**). Enter `me0.ai`, keep **Quick scan for DNS records**, and click **Continue**. Pick the **Free** plan.
3. Cloudflare lists the records it found at Squarespace. Compare them with Squarespace's own list (Squarespace: **Domains**, then **me0.ai**, then **DNS**, then **DNS settings**) and add any that are missing, so nothing stops working when the nameservers change:
   - the `app` record, **Type** `A`, pointing at the machine's IP, such as `129.146.1.2`;
   - any **MX** and **TXT** records, if me0.ai receives email;
   - any records for a Squarespace website on me0.ai or `www`.
4. For the `app` record, click the orange cloud under **Proxy status** so it turns grey and reads **DNS only**. Caddy makes the HTTPS connection itself; Cloudflare's proxy in between would break it.
5. Click **Continue**. Cloudflare shows **two nameservers**, such as `ada.ns.cloudflare.com` and `rex.ns.cloudflare.com`. Keep the page open.
6. At Squarespace: **Domains**, then **me0.ai**, then **DNS**, then **Domain nameservers**. If **DNSSEC** is on there, turn it off first (Cloudflare says so if it is). Choose **Use custom nameservers**, delete the Squarespace ones, enter Cloudflare's two, and save.
7. Back in Cloudflare, click **Check nameservers**. It can take from a few minutes to a few hours; Cloudflare emails when me0.ai is **Active**. Meanwhile the old records at Squarespace keep answering, so the site stays up.

## 2. Point every subdomain at the machine

In Cloudflare, open **me0.ai**, then **DNS**, then **Records**, and click **Add record**:

- **Type:** `A`
- **Name:** `*`
- **IPv4 address:** the machine's IP, the same as the `app` record's (on the server, `curl -4 ifconfig.me` prints it)
- **Proxy status:** **DNS only** (grey cloud)
- **TTL:** Auto

Click **Save**. On your laptop, `nslookup anything.me0.ai` prints the machine's IP once it works. Any word works in place of `anything`.

## 3. Make the API token for Caddy

1. In Cloudflare, click the person icon at the top right, then **My Profile**, then **API Tokens**, then **Create Token**.
2. Next to **Edit zone DNS**, click **Use template**.
3. Under **Permissions**, keep **Zone · DNS · Edit**, and click **+ Add more** to add **Zone · Zone · Read**.
4. Under **Zone Resources**, choose **Include** · **Specific zone** · **me0.ai**.
5. Click **Continue to summary**, then **Create Token**. Copy the token: Cloudflare shows it only once. If it's lost, make another the same way and delete the old one.

The token can change me0.ai's DNS and nothing else. It stays in `.env` on the server, which is never committed.

## 4. Give the server the domain and the token

Connect to the machine as in [the deployment guide](../../deploy/README.md), step 4, then:

```
cd ~/ImageSkinForLLM/deploy
git pull
nano .env
```

Add these two lines, or fill them in if `.env` was made from a newer `.env.example`, with your own token:

```
MAIN_DOMAIN=me0.ai
CLOUDFLARE_API_TOKEN=Xy9AbCdEfGhIjKlMnOpQrStUvWxYz0123456789
```

Save with Ctrl+O and Enter, and close with Ctrl+X. Check that `config.toml` here has the same domain:

```
grep main_domain config.toml
```

It prints `main_domain = "me0.ai"`. If you changed it, it must match `MAIN_DOMAIN`.

## 5. Rebuild Caddy and start it

```
docker compose build caddy
docker compose up -d
```

The build adds Cloudflare's module to Caddy and takes 2 to 5 minutes the first time. Then check that Caddy has the module and accepts its settings:

```
docker compose exec caddy caddy list-modules | grep cloudflare
docker compose exec caddy caddy validate --config /etc/caddy/Caddyfile
```

The first prints `dns.providers.cloudflare`; the second ends with `Valid configuration`.

## 6. Check the certificate and a site

```
docker compose logs caddy --since 10m | grep -iE "obtain|error"
```

Within a minute or two it has `certificate obtained successfully` with `"identifier":"*.me0.ai"`. Then:

1. Open `https://nosuchsite.me0.ai`. It has the padlock, asks for the name and password, and then says **Site not found**: the subdomain reached the app, which knows no site by that name.
2. List the sites, and open one at its subdomain:

   ```
   docker compose exec app imageskin site list
   ```

   For a line such as `anna: anna@example.com at anna.localhost`, open `https://anna.me0.ai` (the list names each site's address on a laptop, `.localhost`; hosted, it is the same name with `.me0.ai`). It opens that site, with the padlock. A line `at /t/<code>` is a trial site, at `https://app.me0.ai/t/<code>/`.

## Then

Go through the [Subdomain setup checklist](Subdomain-Setup-Checklist.md): every line should be ticked.

## If it doesn't work

- **`docker compose up` says `set MAIN_DOMAIN in .env` or `set CLOUDFLARE_API_TOKEN in .env`:** that line is missing from `.env` (step 4).
- **Caddy's log has `Invalid request headers`, `Authentication error` or `403` from Cloudflare:** the token is wrong, was copied only in part, or lacks a permission. Make a new one (step 3), put it in `.env`, and run `docker compose up -d caddy`.
- **Caddy's log has `timed out waiting for record to fully propagate` or `NXDOMAIN` for `_acme-challenge.me0.ai`:** Cloudflare isn't answering for me0.ai yet. Wait until Cloudflare says **Active** (step 1.7); Caddy tries again by itself.
- **The browser says the certificate is for another name (`NET::ERR_CERT_COMMON_NAME_INVALID`) on a subdomain, while `app.me0.ai` works:** the `*.me0.ai` certificate wasn't obtained yet; Caddy's log says why (the two points above).
- **`nslookup anything.me0.ai` finds nothing:** the `*` record is missing (step 2), or the nameservers haven't changed yet (step 1).
- **The browser says `ERR_TOO_MANY_REDIRECTS`, or Cloudflare shows error 525 or 526:** the record's cloud is orange. Make it grey, **DNS only** (steps 1.4 and 2).
- **A real site's subdomain says Site not found:** the name isn't in `imageskin site list`, or `main_domain` in `config.toml` isn't `me0.ai` (`docker compose restart app` after changing it).
- **Email to me0.ai stopped arriving after the move:** an MX or TXT record from Squarespace is missing in Cloudflare (step 1.3).
- **`docker compose build caddy` fails while downloading:** run it again; the module comes from GitHub, which is sometimes slow.
