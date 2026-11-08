# Setting up www

How to make `me0.ai` and `www.me0.ai` open the app on the Oracle machine instead of Squarespace's "under construction" page: the DNS records (at Cloudflare or Squarespace), the Oracle ports, Caddy, and how to check each step. Source of `Setting-up-www-Guide.pdf`.

**The short version**

1. Find out who answers for me0.ai's DNS: Cloudflare (expected, since the [subdomain setup](Subdomain-Setup-Guide.md)) or still Squarespace.
2. There, delete Squarespace's default records for `me0.ai` and `www`, and add two `A` records, `@` and `www`, pointing at the Oracle machine's IP, **DNS only** (grey cloud).
3. At Squarespace, make sure no Squarespace website or forwarding uses the domain.
4. Check that Oracle lets ports 80 and 443 in (it already should).
5. On the server, `git pull` and recreate Caddy, so it gets a certificate for `me0.ai`. It sends `me0.ai` to `www.me0.ai`, which the app serves as the main address.

It takes about 20 minutes of work, plus up to a few hours for old DNS answers to expire.

## Why it shows Squarespace's page today

Two things send the two addresses somewhere other than the app:

- **DNS.** When me0.ai was bought, Squarespace added its **Squarespace Defaults** records: four `A` records for `me0.ai` itself (`198.185.159.144`, `198.185.159.145`, `198.49.23.144`, `198.49.23.145`) and a `CNAME` for `www` to `ext-sq.squarespace.com`. Those are Squarespace's servers, which show the parked "under construction" page. When the DNS moved to Cloudflare, its quick scan copied them. The `*` record from the subdomain setup doesn't help: a record named `www` always wins over `*`, and `*` never covers the bare `me0.ai`.
- **Caddy.** Until this guide's change, Caddy served `app.me0.ai` and `*.me0.ai` (which includes `www.me0.ai`) but had nothing for the bare `me0.ai`, so it would get no certificate even with the right DNS. Caddy now has a block for it that sends people to `https://www.me0.ai`, keeping the path.

The app already treats `me0.ai`, `www.me0.ai` and `app.me0.ai` as the main address (where hosts sign up), and a subdomain with no site goes to `www.me0.ai` (R270). `SITE_ADDRESS` in `.env` stays `app.me0.ai`: Stripe's webhook and the sign-in links use it, and it keeps working.

> **Keep email records.** Delete only the records this guide names. Any `MX` or `TXT` record (email, domain checks) stays as it is.

## 1. Find out who answers for me0.ai

1. On your laptop, open Command Prompt (Windows) or Terminal (Mac) and run:

   ```
   nslookup -type=NS me0.ai
   ```

   It lists the nameservers. Two names ending in `.ns.cloudflare.com` mean **Cloudflare**; follow step 2A. Names with `squarespacedns`, `googledomains` or `domaincontrol` mean **Squarespace**; follow step 2B.
2. Note what the addresses answer today, to compare later:

   ```
   nslookup me0.ai
   nslookup www.me0.ai
   nslookup app.me0.ai
   ```

   `app.me0.ai` already answers with the Oracle machine's IP, such as `129.146.1.2`. The other two answer `198.185.159.x` or `198.49.23.x`, or `ext-sq.squarespace.com`: Squarespace's.
3. Make sure that IP is still the machine's. In the Oracle console: **☰**, **Compute**, **Instances**, **imageskin**, then **Public IP address** under **Instance access**. Or on the server, `curl -4 ifconfig.me` prints it. The examples below use `129.146.1.2`; use yours.

> If the IP shows **(Ephemeral)** next to it, it stays the same while the instance exists, even across restarts, but changes if the instance is ever recreated. Then every record in this guide, `app` and `*` must be changed to the new IP.

## 2A. DNS at Cloudflare (expected)

Sign in at https://dash.cloudflare.com, click **me0.ai**, then **DNS**, then **Records**.

**Delete Squarespace's records**

1. In the list, find every record whose **Name** is `me0.ai` (shown as `me0.ai` or `@`) or `www` and whose **Type** is `A`, `AAAA`, `CNAME` or `HTTPS`. These are usually the four `A` records to `198.185.159.144`, `198.185.159.145`, `198.49.23.144`, `198.49.23.145`, and the `CNAME` `www` to `ext-sq.squarespace.com`.
2. For each one: click **Edit** on its row, then **Delete**, and confirm.
3. Leave `app`, `*`, every `MX` and every `TXT` record as they are.

**Add the two records for the machine**

1. Click **Add record**: **Type** `A`, **Name** `@`, **IPv4 address** `129.146.1.2`, **Proxy status** off so the cloud is grey and reads **DNS only**, **TTL** **Auto**. Click **Save**.
2. Click **Add record** again: the same, with **Name** `www`. Click **Save**. (The `*` record would cover `www` too, but a record of its own makes it plain and survives any change to `*`.)
3. The list now has `A me0.ai 129.146.1.2`, `A www 129.146.1.2`, `A app 129.146.1.2` and `A * 129.146.1.2`, all four with a grey cloud.

> **Grey cloud, not orange.** Caddy makes the HTTPS connection itself; with Cloudflare's proxy (orange) in between, browsers get `ERR_TOO_MANY_REDIRECTS` or Cloudflare error 525 or 526.

Then skip to step 3.

## 2B. DNS still at Squarespace

The subdomains (`anna.me0.ai`) need me0.ai's DNS at Cloudflare for their certificate, and Caddy won't start without `CLOUDFLARE_API_TOKEN`. **The best fix is to do step 1 of the [Subdomain setup guide](Subdomain-Setup-Guide.md) now** (move the DNS to Cloudflare, about 30 minutes, mostly waiting), then come back and do step 2A. In Cloudflare's import, step 1.3 of that guide, you can already leave out the Squarespace records named in 2A.

If you only want `me0.ai` and `www` working first, change them at Squarespace:

1. Sign in at https://account.squarespace.com/domains, click **me0.ai**, then **DNS** (or **DNS settings**).
2. Under **Squarespace Defaults**, click the trash icon of the group (or of each of its records) and confirm. That removes the four `A` records for `@` and the `CNAME` for `www`.
3. Under **Custom records**, click **Add record**: **Host** `@`, **Type** `A`, **Data** `129.146.1.2`, and save. Add another with **Host** `www`. Keep the `app` record and any `MX` or `TXT` records.

## 3. Make sure Squarespace doesn't use the domain

Whichever answers the DNS, check the domain's own page at Squarespace (https://account.squarespace.com/domains, then **me0.ai**):

- **No website uses it.** If it says the domain is connected to a Squarespace site, open that site's **Settings**, **Domains**, and disconnect `me0.ai` there. A connected site can add its records back.
- **No forwarding.** If **Domain forwarding** (or **Forwarding**) has a rule for `me0.ai` or `www`, delete it.
- **Nameservers and DNSSEC.** With DNS at Cloudflare, **Domain nameservers** lists Cloudflare's two, and **DNSSEC** is off (or set up again in Cloudflare). Don't change these otherwise.
- **The domain stays registered and paid at Squarespace.** Keep auto-renew on.

## 4. Check Oracle's ports

These were opened in the first setup ([the deployment guide](../../deploy/README.md), steps 3 and 5); check that nothing changed. Let's Encrypt needs port 80 to give `me0.ai` its certificate, and browsers use 443.

1. In the Oracle console, open the instance's page, then its **subnet** (under **Primary VNIC**, or the **Networking** tab), then **Security** (or **Security Lists**), then the **Default Security List**.
2. Under **Ingress Rules**, there are two rules with **Source** `0.0.0.0/0`, **IP Protocol** `TCP`, and **Destination Port Range** `80` and `443`. If one is missing, click **Add Ingress Rules** and add it. (A third, `UDP` `443`, lets browsers use HTTP/3; it is optional.)
3. On the server (connect as in the deployment guide, step 4), check the machine's own firewall:

   ```
   sudo iptables -L INPUT -n | grep -E "dpt:(80|443)"
   ```

   It prints two `ACCEPT` lines. If not, run the three `iptables` and `netfilter-persistent` lines of the deployment guide's step 5 again.

## 5. Update Caddy on the server

The Caddyfile's new block for the bare domain is in the repository (from PR #325). On the server:

```
cd ~/ImageSkinForLLM/deploy
git checkout main
git pull
```

Before PR #325 is merged, get it from its branch instead: `git fetch origin`, then `git checkout participant-only-subdomains` (or, if the branch is already on the server, `git checkout participant-only-subdomains`, then `git pull`). Go back to `main` once it is merged.

Start the app with #325's code and recreate Caddy, so it reads the new Caddyfile (a restart alone can keep the old file after `git pull`):

```
docker compose up -d --build
docker compose up -d --force-recreate caddy
```

Check the block is there and that Caddy accepts it:

```
grep -A2 '^{$MAIN_DOMAIN}' Caddyfile
docker compose exec caddy caddy validate --config /etc/caddy/Caddyfile
```

The first prints `redir https://www.{$MAIN_DOMAIN}{uri} 302`; the second ends with `Valid configuration`.

`.env` needs no change: `MAIN_DOMAIN=me0.ai` is already there from the subdomain setup.

**Wait for DNS, then check the certificate**

Caddy asks Let's Encrypt for `me0.ai`'s certificate once `me0.ai` leads to the machine. Old answers can be remembered for up to a few hours (Squarespace's records were set to 4 hours). On your laptop:

```
nslookup me0.ai 1.1.1.1
nslookup www.me0.ai 1.1.1.1
```

Both answer the machine's IP, and nothing else, once it works. (`1.1.1.1` asks Cloudflare's resolver, which sees changes first; without it, your laptop's own may take longer.) Then, on the server:

```
docker compose logs caddy --since 30m | grep -iE "obtain|error" | grep -i '"me0.ai"'
```

It has `certificate obtained successfully` with `"identifier":"me0.ai"`. If it has errors from before the DNS changed, Caddy tries again by itself; `docker compose restart caddy` makes it try now.

## 6. Check it works

On your laptop (Windows 10 and 11 and Mac all have `curl`):

```
curl -sI https://me0.ai/
curl -sI https://www.me0.ai/
curl -sI http://www.me0.ai/
curl -sI https://nobody.me0.ai/
```

| Address | Right when it shows |
|---|---|
| `https://me0.ai/` | `HTTP/2 302`, `location: https://www.me0.ai/`, `server: Caddy` |
| `https://www.me0.ai/` | `HTTP/2 200`, `server: Caddy`, no `squarespace` anywhere |
| `http://www.me0.ai/` | `308` to `https://www.me0.ai/` |
| `https://nobody.me0.ai/` | `302` to `https://www.me0.ai/` (R270) |

Then in the browser, open `me0.ai` and `www.me0.ai`: both show the app on `www.me0.ai`, with the padlock, and its Sign in page signs up hosts. `app.me0.ai` works as before.

> Still seeing Squarespace's page in the browser while `curl` is right? The laptop remembers the old answer. On Windows, run `ipconfig /flushdns`; on a Mac, `sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`. Then try a private window, or wait an hour.

## If it doesn't work

- **`nslookup me0.ai` still answers `198.185.159.x` or `198.49.23.x`:** a Squarespace record is left where the DNS is answered (step 1 says which), or the old answer hasn't expired: wait an hour and ask `1.1.1.1` again. If it answers both those and the machine's IP, the Squarespace ones weren't all deleted.
- **`nslookup www.me0.ai` answers `ext-sq.squarespace.com`:** the `CNAME` for `www` is still there (step 2A or 2B). A Squarespace site connected to the domain can put it back (step 3).
- **The records came back after a while:** a Squarespace site is still connected to `me0.ai` (step 3).
- **The browser says `ERR_TOO_MANY_REDIRECTS`, or Cloudflare shows error 525 or 526:** a record's cloud is orange; make it grey, **DNS only** (step 2A).
- **`NET::ERR_CERT_COMMON_NAME_INVALID` on `me0.ai`:** Caddy has no certificate for it yet. Its log (step 5) says why; usually the DNS doesn't lead to the machine yet, or the Caddyfile on the server doesn't have the new block (`git pull`, then `docker compose up -d --force-recreate caddy`).
- **Caddy's log has `Timeout during connect` or `connection refused` for `me0.ai`:** port 80 is closed in Oracle's security list or the machine's firewall (step 4).
- **Caddy's log has `too many certificates` or `rateLimited`:** Let's Encrypt was asked too often while the DNS was wrong. Wait the hour it says; Caddy tries again by itself.
- **`https://www.me0.ai` says Site not found:** the app's code is from before R270, or `main_domain` in `config.toml` isn't `me0.ai`. Update as in step 5, and check with `grep main_domain config.toml`.
- **`caddy validate` fails on the new block:** the Caddyfile was edited by hand on the server. `git diff Caddyfile` shows how; `git checkout Caddyfile` puts the repository's back.
- **Email to me0.ai stopped:** an `MX` or `TXT` record was deleted by mistake. Add it back from Squarespace's list (**DNS settings**) or your email provider's instructions.

## Checklist

| ✓ | What | How to check | Right when |
|---|---|---|---|
| ☐ | No Squarespace record for `me0.ai` or `www` (step 2) | Cloudflare: **DNS**, **Records** | no `198.185.159.x`, `198.49.23.x` or `ext-sq.squarespace.com` |
| ☐ | `me0.ai` and `www` point at the machine, DNS only | `nslookup me0.ai 1.1.1.1`, `nslookup www.me0.ai 1.1.1.1` | only the machine's IP; grey clouds |
| ☐ | No Squarespace site or forwarding uses the domain (step 3) | Squarespace: **Domains**, **me0.ai** | no connected site, no forwarding rule |
| ☐ | Ports 80 and 443 open (step 4) | the **Default Security List**; `sudo iptables -L INPUT -n \| grep -E "dpt:(80\|443)"` | two TCP ingress rules from `0.0.0.0/0`; two `ACCEPT` lines |
| ☐ | Caddy has the bare domain's block (step 5) | `docker compose exec caddy caddy validate --config /etc/caddy/Caddyfile` | `Valid configuration` |
| ☐ | `me0.ai`'s certificate was obtained (step 5) | `docker compose logs caddy \| grep -i obtained` | `certificate obtained successfully` for `me0.ai` |
| ☐ | The addresses answer (step 6) | `curl -sI` on each | `me0.ai` 302 to www; `www.me0.ai` 200 from Caddy |
