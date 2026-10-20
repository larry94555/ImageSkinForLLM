# Hosting the app on Oracle Cloud's free tier

This puts the whole app on a hosted HTTPS site (roadmap R32), on a machine Oracle gives away for free: 4 ARM cores, 24 GB of memory and up to 200 GB of disk, with no time limit. The microphone works there, since browsers allow it only over HTTPS. The site asks for one name and password before anything is shown, so only you can use it.

Three pieces run on the machine, with Docker:

- **the app**, from the `Dockerfile` at the top of the repository, with every voice and video extra installed;
- **Caddy**, a web server in front of it, which gets the HTTPS certificate from Let's Encrypt (and renews it) by itself and asks for the password;
- **a data volume**, `/data` inside the app, which keeps the uploads, the prepared face, the settings and any API keys, and the downloaded models, through restarts and new versions.

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

## 6. Get the app and set the password

```
git clone https://github.com/larry94555/ImageSkinForLLM.git
cd ImageSkinForLLM/deploy
cp .env.example .env
chmod 600 .env
docker run --rm -it caddy:2 caddy hash-password
```

The last command asks for the password twice and prints its hash, starting `$2a$14$`. Open `.env` with `nano .env` and set:

- `SITE_ADDRESS`: the site's address. With no domain of your own, use the machine's IP with dashes and `.sslip.io`, such as `129-146-1-2.sslip.io` ([sslip.io](https://sslip.io) points it at that IP, for free). With a domain, add an **A** record for a name such as `app.me0.ai` pointing at the IP at your domain's DNS provider, and use that name.
- `LOGIN_NAME`: the name the browser will ask for.
- `LOGIN_PASSWORD_HASH`: the hash, pasted between the single quotes.

Save with Ctrl+O and Enter, and close with Ctrl+X.

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

## 8. Pick the LLM

There is no local LLM on the server. On the Settings page (host view), under **LLM**, pick **Claude**, **OpenAI**, **Grok** or **OpenRouter** and paste your API key. It is saved on the server only, in the data volume.

**ChatGPT plan** works too, but OpenAI sends the browser back to the app's own address on `127.0.0.1`, so sign in through an SSH tunnel from your laptop once. Stop any `imageskin serve` on your laptop first (it uses port 8000 too), then connect with `-L 8000:127.0.0.1:8000` added to the `ssh` command from step 4, such as:

```
ssh -i ~/.ssh/oracle.key -L 8000:127.0.0.1:8000 ubuntu@129.146.1.2
```

(on Windows, the same with the key path from step 4). While it is connected, open http://127.0.0.1:8000/#/settings on your laptop, click **Continue with ChatGPT** and sign in. The tokens are saved on the server, so the hosted site answers through the plan after the tunnel is closed. The tunnel reaches the app without the password, but only for someone who already has the machine's SSH key.

Then set up the person (photos, recordings, Prepare) as on your laptop. Prepare is slower on the free machine's cores than on a fast laptop.

## Looking after it

| To | Run, in `~/ImageSkinForLLM/deploy` |
|---|---|
| Update to the latest version | `git pull`, then `docker compose up -d --build` |
| Change the password | a new hash in `.env`, then `docker compose up -d` |
| Change the app's settings (`config.toml` here) | edit it, then `docker compose restart app` |
| See the app's log | `docker compose logs -f app` (Ctrl+C stops watching) |
| Stop the site | `docker compose down` (the data is kept) |
| Back up the data | `docker run --rm -v imageskin_imageskin-data:/data -v "$PWD":/backup ubuntu tar czf /backup/imageskin-data.tgz -C /data .` |

`docker compose down -v` would delete the data volume, with every upload, setting and key: don't use it unless you mean to start over.

The containers start again by themselves after the machine restarts.
