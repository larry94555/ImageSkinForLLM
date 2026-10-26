# Hosting the app on Oracle Cloud's free tier

This puts the whole app on a hosted HTTPS site (roadmap R32), on a machine Oracle gives away for free: 4 ARM cores, 24 GB of memory and up to 200 GB of disk, with no time limit. The microphone works there, since browsers allow it only over HTTPS. The site asks for one name and password before anything is shown, so only you can use it.

Four pieces run on the machine, with Docker:

- **the app**, from the `Dockerfile` at the top of the repository, with every voice and video extra installed;
- **the LLM**, llama.cpp's `llama-server` with Gemma 3 4B, the same model as on the laptop, which only the app can reach;
- **Caddy**, a web server in front of it, which gets the HTTPS certificate from Let's Encrypt (and renews it) by itself and asks for the password;
- **data volumes**: `/data` inside the app, which keeps the uploads, the prepared face, the settings and any API keys, and the downloaded models, and another keeps the LLM's model, through restarts and new versions.

The secrets stay on the server: the password's hash is in `deploy/.env` there, which is never committed, and API keys typed on the Settings page are saved in the data volume, readable only by the app.

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

## 6. Get the app and set the address and password

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

### 6c. Make the password's hash

```
docker run --rm -it caddy:2 caddy hash-password
```

Type the password you want, press Enter, type it again and press Enter. It prints one long line starting `$2a$14$`: the password in a form that can't be turned back into it. Copy that whole line (select it with the mouse; in most terminals selecting copies it, or use Ctrl+Shift+C).

### 6d. Fill in `.env`

Open it with `nano .env`. Change only the three lines that don't start with `#`, one per setting; leave the `#` lines (notes) as they are. For the site `app.me0.ai`, the name `larry` and the hash from 6c, the whole file reads like this:

```
# Copy to .env (cp .env.example .env) and fill in. .env stays on the server only.

# The site's address: ...
SITE_ADDRESS=app.me0.ai

# The name and password the browser asks for. ...
LOGIN_NAME=larry
LOGIN_PASSWORD_HASH='$2a$14$Xb3k9mQ1vL7pR2sT8uW0yOeZ4aB6cD5fG1hJ2kL3mN4oP5qR6sT7u'
```

- `SITE_ADDRESS`: the name from 6b, with no `https://` and no `/` at the end.
- `LOGIN_NAME`: the name the browser will ask for; any word you like.
- `LOGIN_PASSWORD_HASH`: your own hash from 6c (the one above is only an example), between the single quotes, which keep its `$` signs as they are. The browser asks for the password you typed in 6c, not the hash.

Save with Ctrl+O and Enter, and close with Ctrl+X. `cat .env` shows it to check.

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

Open `https://<SITE_ADDRESS>` (such as https://129-146-1-2.sslip.io) in your browser. It asks for the name and password; then the app opens as it does on your laptop, with a padlock in the address bar. A wrong password asks again and shows nothing of the app.

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

## If it doesn't work

- **The browser says `ERR_SSL_PROTOCOL_ERROR` or "can't provide a secure connection":** Caddy has no certificate yet. `docker compose logs caddy --tail 40` says why. `NXDOMAIN` or a timeout on your address means the A record (step 6b) isn't working yet, or ports 80 and 443 aren't open (steps 3 and 5). A lookup on `127.0.0.53` that is refused, or `network is unreachable`, means the Caddy container has no network, which happens when it was first started while port 80 was taken (next point): `docker inspect imageskin-caddy-1 --format '{{json .NetworkSettings.Networks}}'` prints `{}`. Make it again with `docker compose up -d --force-recreate caddy`. Caddy tries again every minute by itself; once the log says `certificate obtained successfully`, reload the page.
- **The page can't read how far Prepare has got, and the machine stops answering:** it ran out of memory. `compose.yaml` caps each container (14 GB for the app, 6 GB for the LLM) so this restarts the container instead of freezing the machine; if the machine is frozen already, use **Reboot** with **Force reboot** on the instance's page in the Oracle console, then `docker compose stop app llama` as soon as you can connect. While Prepare runs, `docker stats` in a second SSH window shows each container's memory against its cap.
- **`docker compose up` says port 80 or 443 is already in use (`address already in use`):** something else on the machine is using it, such as an earlier web server or container. `sudo ss -ltnp 'sport = :80'` names the program, and `docker ps` lists running containers. Stop it: `docker rm -f <name>` for a container, or, for a web server installed on the machine itself, `sudo systemctl disable --now caddy` (or `nginx`, or `apache2`), then run `docker compose up -d --force-recreate` so the containers are made again with their network.

## Looking after it

| To | Run, in `~/ImageSkinForLLM/deploy` |
|---|---|
| Update to the latest version | `git pull`, then `docker compose up -d --build` |
| Change the password | a new hash in `.env`, then `docker compose up -d` |
| Set or change the administrator password (the admin view's, not the site's) | edit `admin/admin.toml` here; no restart (see [Admin-Password-Guide.pdf](../docs/guides/Admin-Password-Guide.pdf)) |
| Change the app's settings (`config.toml` here) | edit it, then `docker compose restart app` |
| See the app's log | `docker compose logs -f app` (Ctrl+C stops watching) |
| Stop the site | `docker compose down` (the data is kept) |
| Host the default people for Start now | copy the packs to `default-people` here, as [tools/default_people/README.md](../tools/default_people/README.md#uploading-the-packs-to-the-hosted-site-r32a) says |
| Back up the data | `docker run --rm -v imageskin_imageskin-data:/data -v "$PWD":/backup ubuntu tar czf /backup/imageskin-data.tgz -C /data .` |

Ctrl+C on a `docker compose logs -f` only stops showing the log: the site keeps running in the background, since `up -d` started it that way. Only `docker compose down` or `stop` takes it down.

`docker compose down -v` would delete the data volume, with every upload, setting and key: don't use it unless you mean to start over.

The containers start again by themselves after the machine restarts.
