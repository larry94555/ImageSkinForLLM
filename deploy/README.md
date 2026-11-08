# Hosting the app on Oracle Cloud's free tier

This puts the whole app on a hosted HTTPS site (roadmap R32), on a machine Oracle gives away for free: 4 ARM cores, 24 GB of memory and up to 200 GB of disk, with no time limit. The microphone works there, since browsers allow it only over HTTPS. Since R71 the site asks for no password of its own: visitors use each site as it is, and the hosts and the administrator sign in to the app itself (host accounts, R62, and the administrator's password, R149).

Four pieces run on the machine, with Docker:

- **the app**, from the `Dockerfile` at the top of the repository, with every voice and video extra installed;
- **the LLM**, llama.cpp's `llama-server` with Gemma 3 4B, the same model as on the laptop, which only the app can reach;
- **Caddy**, a web server in front of it, which gets the HTTPS certificate from Let's Encrypt (and renews it) by itself;
- **data volumes**: `/data` inside the app, which keeps the uploads, the prepared face, the settings and any API keys, and the downloaded models, and another keeps the LLM's model, through restarts and new versions.

The secrets stay on the server: the tokens are in `deploy/.env` there, which is never committed, and API keys typed on the Settings page are saved in the data volume, readable only by the app.

It takes about an hour, most of it waiting for the first build.

## 1. Make an Oracle Cloud account

1. Go to https://signup.cloud.oracle.com and sign up. Oracle asks for a credit card to check who you are; an Always Free account isn't charged.
2. Pick your **home region** carefully, near you: it can't be changed later, and the free machines are made there. If one region often says it is out of capacity (step 2), a less busy one nearby is better.
3. Sign in to the console at https://cloud.oracle.com.

## 2. Make the machine

1. Open the menu (☰) and choose **Compute**, then **Instances**, then **Create instance**. Name it `imageskin`.
2. Under **Image and shape**:
   - **Change image**: pick **Canonical Ubuntu**, version **24.04** (not "Minimal").
   - **Change shape**: pick **Ampere**, then **VM.Standard.A1.Flex**, with **4** OCPUs and **24** GB of memory. It is marked "Always Free-eligible".
3. Under **Networking**, keep **Create new virtual cloud network** and **Create new public subnet**, and make sure **Assign a public IPv4 address** is on.
4. Under **Add SSH keys**, choose **Generate a key pair for me** and click **Save private key**. Keep the file: it is the only way into the machine.
5. Under **Boot volume**, turn on **Specify a custom boot volume size** and enter **100** GB (the image and models need about 20 GB, and the rest is room for uploads).
6. Click **Create**. After a minute or two the instance is **Running**; note its **Public IP address** on its page, such as `129.146.1.2`.

If it says **Out of capacity for shape VM.Standard.A1.Flex**, pick another availability domain under **Placement** if your region has more than one, or try again later. Upgrading the account to **Pay As You Go** (under Billing) usually gets a machine at once and keeps the Always Free resources free, but anything beyond them is then charged, so set a budget alert if you do. Oracle may stop an Always Free machine that stays idle for a week on a free account; start it again from its page.

## 3. Open the web ports

The machine only lets SSH in at first. Open HTTP (for the certificate) and HTTPS:

1. On the instance's page, open its **subnet** (under **Primary VNIC**, or the **Networking** tab), then its **Security** tab or **Security Lists**, and open the **Default Security List**.
2. **Add Ingress Rules**: Source CIDR `0.0.0.0/0`, IP Protocol **TCP**, Destination Port Range `80`. Add another the same with `443`.

The machine's own firewall is opened in step 5.

## 4. Connect from your laptop

Move the private key you saved into your `.ssh` folder as `oracle.key`, make it readable only by you (SSH refuses a key others can read), and connect. Replace `129.146.1.2` with your machine's public IP, and the download path if yours differs. The first time, type `yes` to trust the machine.

macOS / Linux:

```
mkdir -p ~/.ssh
mv ~/Downloads/ssh-key-*.key ~/.ssh/oracle.key
chmod 600 ~/.ssh/oracle.key
ssh -i ~/.ssh/oracle.key ubuntu@129.146.1.2
```

Windows 11, Command Prompt:

```
mkdir "%USERPROFILE%\.ssh"
move "%USERPROFILE%\Downloads\ssh-key-*.key" "%USERPROFILE%\.ssh\oracle.key"
icacls "%USERPROFILE%\.ssh\oracle.key" /inheritance:r /grant:r "%USERNAME%:R"
ssh -i "%USERPROFILE%\.ssh\oracle.key" ubuntu@129.146.1.2
```

Windows 11, PowerShell:

```
New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh"
Move-Item "$env:USERPROFILE\Downloads\ssh-key-*.key" "$env:USERPROFILE\.ssh\oracle.key"
icacls "$env:USERPROFILE\.ssh\oracle.key" /inheritance:r /grant:r "${env:USERNAME}:R"
ssh -i "$env:USERPROFILE\.ssh\oracle.key" ubuntu@129.146.1.2
```

The prompt changes to `ubuntu@imageskin:~$`. Every command from here on is typed there, the same whichever laptop you use.

## 5. Install Docker and open the firewall

Oracle's Ubuntu image blocks every port but SSH in its own firewall, so open 80 and 443 there too, then install Docker:

```
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit
```

Connect again with the same `ssh` command as in step 4, so Docker can be used without `sudo`, and check it with `docker run --rm hello-world`.

## 6. Get the app and set the address

### 6a. Get the app

```
git clone https://github.com/larry94555/ImageSkinForLLM.git
cd ImageSkinForLLM/deploy
cp .env.example .env
chmod 600 .env
```

### 6b. Point a name at the machine

The site needs a name that leads to the machine's public IP address. The IP is on the instance's page in the Oracle console (**Public IP address**, under **Instance access**), or, on the server, `curl -4 ifconfig.me` prints it. The examples below use `129.146.1.2`; use yours.

- **With your domain (me0.ai):** at the company you bought `me0.ai` from (its **DNS** settings), add a record with **Type** `A`, **Name** (or Host) `app`, and **Value** (or Points to) your machine's IP, such as `129.146.1.2`. The site is then `app.me0.ai`. The record can take a few minutes to work: on your laptop, `nslookup app.me0.ai` prints the machine's IP once it does. Don't start the site (step 7) before then, or Let's Encrypt can't give it a certificate.
- **With no domain:** use the IP with dashes and `.sslip.io`, such as `129-146-1-2.sslip.io`. [sslip.io](https://sslip.io) points that name at that IP for free, so there is nothing to set up.

### 6c. Fill in `.env`

Open it with `nano .env`. Change only the lines that don't start with `#`, one per setting; leave the `#` lines (notes) as they are. For the site `app.me0.ai`, the file's settings read like this:

```
# Copy to .env (cp .env.example .env) and fill in. .env stays on the server only.

# The site's address: ...
SITE_ADDRESS=app.me0.ai

# The domain every site's subdomain is under ...
MAIN_DOMAIN=me0.ai

# A Cloudflare API token that can edit me0.ai's DNS ...
CLOUDFLARE_API_TOKEN=Xy9AbCdEfGhIjKlMnOpQrStUvWxYz0123456789

# A Hugging Face read token ...
HF_TOKEN=
```

- `SITE_ADDRESS`: the name from 6b, with no `https://` and no `/` at the end.
- `MAIN_DOMAIN` and `CLOUDFLARE_API_TOKEN`: for every site's own subdomain, such as `anna.me0.ai` (roadmap R71a). The [Subdomain setup guide](../docs/guides/Subdomain-Setup-Guide.md) says how to get the token and point `*.me0.ai` at the machine, and the [Subdomain setup checklist](../docs/guides/Subdomain-Setup-Checklist.md) lists every change to confirm.
- `HF_TOKEN`: filled in at 6d.

A `.env` made before R71 also has `LOGIN_NAME` and `LOGIN_PASSWORD_HASH`, the old site password's. Nothing reads them now; delete those two lines.

Save with Ctrl+O and Enter, and close with Ctrl+X. `cat .env` shows it to check.

### 6d. A Hugging Face token, for a fast voice

The person's own voice is spoken with Pocket TTS, which keeps up with the video: each clip is made faster than it plays, so a reply has no long pauses. Without it, the app uses Chatterbox, which took 11 to 32 seconds a clip on this machine, so a reply could pause for half a minute between sentences (roadmap R160). Pocket's weights that clone a voice are free, but Hugging Face asks you to accept their terms once:

1. Make a free account at https://huggingface.co/join, or sign in.
2. Open https://huggingface.co/kyutai/pocket-tts and accept the terms on that page.
3. Open https://huggingface.co/settings/tokens, click **Create new token**, pick **Read**, give it any name and click **Create token**. Copy it: it starts with `hf_`.
4. In `.env` (`nano .env`), paste it after `HF_TOKEN=` on that line, such as `HF_TOKEN=hf_AbCd...`, then save and close as above.

The token stays in `.env` on the server, which is never committed. With `HF_TOKEN` left empty, the site still works, with Chatterbox.

Every Hugging Face model the app uses, and setting all of this up from scratch, is in [Set up Hugging Face models](../docs/guides/Set-up-Hugging-Face-Models.pdf).

## 7. Start it

```
docker compose up -d --build
```

The first build downloads and installs about 3 GB (PyTorch, the voice and video models' code) and takes 15 to 30 minutes; later ones reuse it. Then check it:

```
docker compose ps
docker compose logs app | grep "Starting server"
docker compose logs caddy | grep -i "certificate obtained"
```

`docker compose ps` shows `app` as **healthy** and `caddy` as **Up**, the app's log has `Starting server` with `"host": "0.0.0.0"`, and Caddy's has `certificate obtained successfully` for your address.

Open `https://<SITE_ADDRESS>` (such as https://129-146-1-2.sslip.io) in your browser. The app opens as it does on your laptop, with a padlock in the address bar and no password asked: anyone with the address can use the sites as a visitor. Settings, the host pages and the admin view each need their own sign-in, so set the administrator's password before sharing the address ([Admin-Password-Guide.pdf](../docs/guides/Admin-Password-Guide.pdf)).

## 8. The LLM

The chat answers with the same open model as on the laptop: llama.cpp's `llama-server` with Gemma 3 4B, in its own container (`llama` in `compose.yaml`), started by step 7 like the rest. The first time it starts, it downloads the model (about 2.5 GB) into its own volume; until then the chat says the LLM can't be reached. Watch it with:

```
docker compose logs -f llama
```

It is ready when the log says `server is listening on http://0.0.0.0:8080` (Ctrl+C stops watching). It writes on 2 of the 4 cores (`--threads 2`) and leaves the other 2 to the voice and the video, as on the laptop; it reads a prompt on all 4 (`--threads-batch 4`) and reuses what it has read (`--swa-full`, R97). It runs Gemma 3 4B in the Q4_0 quantization, which llama.cpp speeds up on ARM cores such as this machine's (R97). To try another model, change the `-hf` name under `llama` in `compose.yaml` and run `docker compose up -d`.

To use a cloud LLM instead, go to the Settings page (host view), under **LLM** pick **Claude**, **OpenAI**, **Grok** or **OpenRouter**, and paste your API key. It is saved on the server only, in the data volume. **Local (llama.cpp)** on the same page goes back to llama-server.

**ChatGPT plan** works too, the way OpenAI's [Self-hosted VMs](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms) guide says: sign in on your laptop, where OpenAI can send the browser back to the app on `127.0.0.1`, then move that sign-in to the server, which keeps its own host ID and renews the tokens itself. **Continue with ChatGPT** on the hosted site's own Settings page can't finish, as OpenAI only sends the browser back to `127.0.0.1`.

1. On your laptop, with the app installed as in the main README, run `imageskin serve`, open http://127.0.0.1:8000/#/settings, click **Continue with ChatGPT** and sign in with the account the hosted site should use. Then stop it with Ctrl+C.
2. Still on your laptop, move the sign-in into a file and copy it to the server. Your laptop is signed out of ChatGPT afterwards, since only one copy of a sign-in can keep renewing; sign in there again later to use the plan on the laptop too. Replace `129.146.1.2` as in step 4.

   macOS / Linux:

   ```
   imageskin chatgpt-export chatgpt-sign-in.json
   scp -i ~/.ssh/oracle.key chatgpt-sign-in.json ubuntu@129.146.1.2:
   rm chatgpt-sign-in.json
   ```

   Windows 11, Command Prompt:

   ```
   imageskin chatgpt-export chatgpt-sign-in.json
   scp -i "%USERPROFILE%\.ssh\oracle.key" chatgpt-sign-in.json ubuntu@129.146.1.2:
   del chatgpt-sign-in.json
   ```

   Windows 11, PowerShell:

   ```
   imageskin chatgpt-export chatgpt-sign-in.json
   scp -i "$env:USERPROFILE\.ssh\oracle.key" chatgpt-sign-in.json ubuntu@129.146.1.2:
   Remove-Item chatgpt-sign-in.json
   ```

3. On the server, in `~/ImageSkinForLLM/deploy`, import it and delete the copy:

   ```
   docker compose exec -T app imageskin chatgpt-import - < ~/chatgpt-sign-in.json
   rm ~/chatgpt-sign-in.json
   ```

   It prints `Signed in with ChatGPT as` your account's email. On the hosted site's Settings page, pick **ChatGPT plan** under **LLM**.

The file holds the sign-in's tokens, so it only goes over SSH and is deleted on both sides. To move to another account, do the same again with that account.

Then set up the person (photos, recordings, Prepare) as on your laptop. Prepare is slower on the free machine's cores than on a fast laptop.

## 9. Turn on subscribing (Stripe)

A site's host subscribes from **Settings** for 5 GB at $1.99 a month (roadmap R67). They pay on Stripe's own page, so card details never reach the server. Until these steps are done, **Subscribe** says subscribing isn't set up yet. Do them first in Stripe's test mode (a sandbox), where a test card pays nothing, then again with the live keys.

**Before you start:** the server's `.env` must already have `MAIN_DOMAIN` and `CLOUDFLARE_API_TOKEN`, from the [Subdomain setup guide](../docs/guides/Subdomain-Setup-Guide.md) (roadmap R71a). Caddy needs both since R71a, so without them every `docker compose up` stops with `set MAIN_DOMAIN in .env` or `set CLOUDFLARE_API_TOKEN in .env`. On the server, `grep -E "^(MAIN_DOMAIN|CLOUDFLARE_API_TOKEN)=." deploy/.env` prints both lines once they are set; if it doesn't, do that guide first.

1. **Make a Stripe account.** Sign up at [dashboard.stripe.com/register](https://dashboard.stripe.com/register) and confirm your email. To take real money later, finish **Activate payments** (your business details and the bank account payouts go to). Test mode works without it.
2. **Make the product and its price.** In the Dashboard, open **Product catalog** and click **Add product**. Name it, such as `ImageSkin 5 GB`, pick **Recurring**, enter **1.99 USD**, and set **Billing period** to **Monthly**. Save it, open the product, and copy its price's ID, which starts `price_`.
3. **Copy the secret key.** Open **Developers**, then **API keys**, click **Reveal** on the **Secret key**, and copy it. It starts `sk_test_` in test mode and `sk_live_` in live mode. Treat it as a password.
4. **Add the webhook.** Open **Developers**, then **Webhooks**, and add an endpoint (in newer dashboards, **Add destination**, then **Webhook endpoint**):
   - **Endpoint URL**: `https://<SITE_ADDRESS>/api/payments/stripe/events`, such as `https://app.me0.ai/api/payments/stripe/events`. It must be the main address, not a site's subdomain.
   - **Events**: `checkout.session.completed`, `customer.subscription.updated` and `customer.subscription.deleted`.

   Save it, then click **Reveal** under **Signing secret** on its page and copy it. It starts `whsec_`.
5. **Put them on the server.** Connect with SSH (step 4), then:

   ```
   cd ImageSkinForLLM/deploy
   git pull
   nano .env
   ```

   Paste the key, the signing secret and the price's ID after the `=` on their lines (take them from `.env.example` if `.env` doesn't have them yet), then save and close as in 6c:

   ```
   IMAGESKIN_STRIPE_SECRET_KEY=sk_test_...
   IMAGESKIN_STRIPE_WEBHOOK_SECRET=whsec_...
   IMAGESKIN_STRIPE_PRICE_ID=price_1Q...
   ```

   All three stay in `.env`, so `config.toml`, which `git pull` updates, is never edited here. If you put `stripe_price_id` in `config.toml` before, move its value to `IMAGESKIN_STRIPE_PRICE_ID` and run `git checkout config.toml` to put the file back as it was: the app no longer starts with it there, and says so.
6. **Restart with them.** A changed `.env` needs the app made again, not only restarted, and Caddy reads the new Caddyfile, which since R71 asks for no password, so Stripe's events reach the app:

   ```
   docker compose up -d --build
   docker compose restart caddy
   ```

   If `docker compose logs app | grep "Stripe setting is missing"` prints a line, one of the three is empty or misspelled.
7. **Try it.** Sign in to a trial site, open **Settings**, and click **Subscribe**. In test mode, pay with the card `4242 4242 4242 4242`, any future date and any three digits. Back on Settings it says the site is subscribed. On the webhook's page in Stripe, the events show **200 OK**, and `docker compose logs app | grep "Site subscribed"` shows the site.
8. **Go live.** Switch the Dashboard out of test mode and repeat steps 2 to 6 with the live price, key and webhook, which are separate from the test ones.

## If it doesn't work

- **The browser says `ERR_SSL_PROTOCOL_ERROR` or "can't provide a secure connection":** Caddy has no certificate yet. `docker compose logs caddy --tail 40` says why. `NXDOMAIN` or a timeout on your address means the A record (step 6b) isn't working yet, or ports 80 and 443 aren't open (steps 3 and 5). A lookup on `127.0.0.53` that is refused, or `network is unreachable`, means the Caddy container has no network, which happens when it was first started while port 80 was taken (next point): `docker inspect imageskin-caddy-1 --format '{{json .NetworkSettings.Networks}}'` prints `{}`. Make it again with `docker compose up -d --force-recreate caddy`. Caddy tries again every minute by itself; once the log says `certificate obtained successfully`, reload the page.
- **The page can't read how far Prepare has got, and the machine stops answering:** it ran out of memory. `compose.yaml` caps each container (14 GB for the app, 6 GB for the LLM) so this restarts the container instead of freezing the machine; if the machine is frozen already, use **Reboot** with **Force reboot** on the instance's page in the Oracle console, then `docker compose stop app llama` as soon as you can connect. While Prepare runs, `docker stats` in a second SSH window shows each container's memory against its cap.
- **`docker compose up` says port 80 or 443 is already in use (`address already in use`):** something else on the machine is using it, such as an earlier web server or container. `sudo ss -ltnp 'sport = :80'` names the program, and `docker ps` lists running containers. Stop it: `docker rm -f <name>` for a container, or, for a web server installed on the machine itself, `sudo systemctl disable --now caddy` (or `nginx`, or `apache2`), then run `docker compose up -d --force-recreate` so the containers are made again with their network.

## Looking after it

| To | Run, in `~/ImageSkinForLLM/deploy` |
|---|---|
| Update to the latest version | `git pull`, then `docker compose up -d --build` |
| Speak with Pocket TTS on a site set up before it (R160) | step 6d, then `git pull`, `docker compose up -d --build`, and **Prepare** again on the Setup page; the log then says `cloned with Pocket TTS` (`docker compose logs app \| grep "Prepare speaks"`) |
| Set or change the administrator password | edit `admin/admin.toml` here; no restart (see [Admin-Password-Guide.pdf](../docs/guides/Admin-Password-Guide.pdf)) |
| Let only your own laptops sign in as the administrator | list each laptop's ID, from its Settings page, in `admin/admin-laptops.toml` here; no restart (see "Only the laptops you list" in [Admin-Password-Guide.pdf](../docs/guides/Admin-Password-Guide.pdf)) |
| Find out why an admin sign-in failed ("Admin login failed with error code A-…") | `docker compose logs app --since 24h \| grep A-…` with the page's code; the reasons are in the [FAQ](../docs/FAQ.md#admin-login-failed-with-an-error-code-how-do-i-find-out-why) |
| Make `me0.ai` and `www.me0.ai` open the app instead of Squarespace's page | [Setting up www guide](../docs/guides/Setting-up-www-Guide.md) |
| Serve each site at its own subdomain, such as `anna.me0.ai` | [Subdomain setup guide](../docs/guides/Subdomain-Setup-Guide.md), then the [Subdomain setup checklist](../docs/guides/Subdomain-Setup-Checklist.md) |
| Change the app's settings (`config.toml` here) | edit it, then `docker compose restart app` |
| Turn on subscribing, or change Stripe's keys | step 9 above; a changed `.env` needs `docker compose up -d` |
| See the app's log | `docker compose logs -f app` (Ctrl+C stops watching) |
| Stop the site | `docker compose down` (the data is kept) |
| Host the default people for Start now | copy the packs to `default-people` here, as [tools/default_people/README.md](../tools/default_people/README.md#uploading-the-packs-to-the-hosted-site-r32a) says |
| Back up the data | `docker run --rm -v imageskin_imageskin-data:/data -v "$PWD":/backup ubuntu tar czf /backup/imageskin-data.tgz -C /data .` |

Ctrl+C on a `docker compose logs -f` only stops showing the log: the site keeps running in the background, since `up -d` started it that way. Only `docker compose down` or `stop` takes it down.

`docker compose down -v` would delete the data volume, with every upload, setting and key: don't use it unless you mean to start over.

The containers start again by themselves after the machine restarts.
