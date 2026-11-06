# Mail setup guide

Step by step: how to make the hosted site on the Oracle machine send real email, such as sign-up confirmations, password resets, email changes and test account emails, through Oracle Cloud's own mail service, **OCI Email Delivery** (roadmap R215). Until this is done, the app writes each email to its outbox instead, and you read them on the server ([Host Lifecycle walkthrough guide](Host-Lifecycle-Walkthrough-Guide.md), "Where the emails go").

**Why Email Delivery and not a mail server on the machine.** Oracle blocks outbound port 25 for tenancies made after June 2021, so a mail server on the machine couldn't reach anyone's inbox. Mail sent straight from a cloud machine's address is also often marked as spam. Email Delivery is Oracle's sending service, in the same account as the machine. The app logs in to it on port 587 with a username and password, over an encrypted connection, and it delivers the mail. Nothing needs installing on the machine, and no port needs opening.

**What it costs.** Email Delivery is part of Oracle's free tier, with a small daily allowance (about 100 emails a day on a free account; check **Limits, Quotas and Usage** in the Console for yours). That is plenty for testing and a few hosts. A paid account can ask for more.

It takes about 30 minutes. Most of it is waiting for the DNS records to be checked.

**You need:** the Oracle Cloud account that runs the machine, Cloudflare for me0.ai's DNS ([Subdomain setup guide](Subdomain-Setup-Guide.md), step 1), and an SSH connection to the machine ([deployment guide](../../deploy/README.md), step 4).

## 1. Find the machine's region

Email Delivery is set up per region, and the app must use the same region as everything else here.

1. Sign in at https://cloud.oracle.com.
2. Click the region name at the top right of the Console, then **Manage regions**. Find the machine's region in the list (open **Compute**, then **Instances**, if you're not sure which it is; the region at the top right is the one the list is for). Write down its **Region identifier**, such as `us-sanjose-1` or `us-ashburn-1`. It must be marked **Home region** or **Subscribed**.

Do every step below in this region. If the region at the top right changes, switch it back first.

## 2. Add me0.ai as an email domain

1. Open the menu (top left), then **Developer Services**, then **Email Delivery**, then **Email Domains**.
2. Pick the **Compartment** the machine is in (the root compartment if you never made one).
3. Click **Create Email Domain**, enter `me0.ai`, and click **Create**.

## 3. Add DKIM, so mail is signed as me0.ai

DKIM lets Gmail and others check that the mail really comes from me0.ai.

1. Open the email domain `me0.ai`, then **DKIM** under **Resources**, and click **Add DKIM**.
2. For **DKIM Selector**, enter `me0ai-` followed by the region's short name and the month, such as `me0ai-phx-202611`. It must be unique and must not be reused later.
3. Click **Generate DKIM Record**. Oracle shows a **CNAME Record** and a **CNAME Value**. Click **Create DKIM**.
4. In Cloudflare: open **me0.ai**, then **DNS**, then **Records**, and click **Add record**:
   - **Type** `CNAME`
   - **Name**: the CNAME Record without `.me0.ai` at the end, such as `me0ai-phx-202611._domainkey`
   - **Target**: the CNAME Value
   - **Proxy status**: click the orange cloud so it is grey, **DNS only**
   - Click **Save**.
5. Back in Oracle, the DKIM's state goes from **Creating** to **Active** once Oracle finds the record, usually within 30 minutes. You can carry on meanwhile.

## 4. Add SPF, so me0.ai allows Oracle to send for it

1. In Cloudflare's DNS records for me0.ai, look for a **TXT** record named `me0.ai` (shown as `@`) whose content starts `v=spf1`.
2. **If there is none**, click **Add record**: **Type** `TXT`, **Name** `@`, **Content**:

   ```
   v=spf1 include:rp.oracleemaildelivery.com ~all
   ```

   Use that value for a region in the Americas. For a region in Europe, use `include:eu.rp.oracleemaildelivery.com`, and in Asia-Pacific `include:ap.rp.oracleemaildelivery.com`.
3. **If there is one already**, such as one for another mail service, don't add a second: edit it and put the `include:` from step 2 before the `~all` (or `-all`) at its end. A domain may have only one SPF record.
4. Back in Oracle, the email domain's **SPF Configured** turns to **Yes** once Oracle finds it, which can take a few minutes to an hour.

## 5. Approve the sender address

Email Delivery sends only from addresses you approve, and the app's emails come from one address.

1. In **Email Delivery**, open **Approved Senders** (in the same region and compartment) and click **Create Approved Sender**.
2. Enter `noreply@me0.ai` and click **Create Approved Sender**.

The address doesn't need a mailbox: the app only sends from it.

## 6. Make a mail user and its SMTP username and password

The app logs in to Email Delivery with SMTP credentials that belong to an Oracle user. Make a user just for this, with permission only to send email. Your own sign-in user often doesn't work for this (Oracle answers `535 Authentication credentials invalid` even with the right password, as in Larry's first try), and a separate user keeps your own sign-in out of the server.

1. **A group.** Open the menu, then **Identity & Security**, then **Domains**, then **Default** (the domain itself, not a user). Open the **User management** tab (or **Groups** on the left in older consoles), and in the **Groups** section click **Create group**. Name it `EmailSenders` and create it.
2. **The user.** In the same tab's **Users** section, click **Create user**:
   - **First name** `me0`, **Last name** `Mail`
   - **Username / Email**: an address no other user has. A Gmail plus address works, such as `you+me0mail@gmail.com`: it still reaches your inbox. If there's a box to use the email as the username, you can uncheck it and enter `me0-mail`.
   - Add the user to the `EmailSenders` group, there or afterwards from the group's **Users** tab (**Assign users to group**). It doesn't need to be activated.
3. **The permission.** Open **Identity & Security**, then **Policies**, and pick the **root** compartment (named after your tenancy) on the left. Click **Create Policy**:
   - **Name** `EmailSendersPolicy` (no spaces), **Description** `Lets the mail user send email through Email Delivery`
   - Click **Show Manual Editor**, ignore the use cases and templates, and paste:

     ```
     Allow group 'Default'/'EmailSenders' to use email-family in tenancy
     ```

   - Click **Create**.
4. **The credentials.** Back in **Domains**, **Default**, **User management**, click the new user's name. Open **SMTP credentials** (a tab, or under **Resources**), click **Generate credentials**, enter `me0.ai app`, and generate.
5. Oracle shows a **Username**, a long string that starts `ocid1.user`, and a **Password**. Click the copy button next to the username and paste it into Notepad, then **⋯ → Copy** next to the password and paste it on the next line. The copy buttons copy the **whole** username, which on newer accounts goes on past an `@`, such as `ocid1.user.oc1..aaaa...@ocid1.tenancy.oc1..aaaa....xy.com`. **Copy both now**: the password is shown only once. If you lose it, delete these credentials and make new ones. Treat the password like the administrator's.
6. Wait about 5 minutes: new credentials, groups and policies take a few minutes to work.

## 7. Find the SMTP server's name

1. In **Email Delivery**, open **Configuration**.
2. Under **SMTP Sending Information**, copy the **Public Endpoint**. It is `smtp.email.` followed by the region identifier from step 1 and `.oci.oraclecloud.com`, such as `smtp.email.us-ashburn-1.oci.oraclecloud.com` for `us-ashburn-1`. If the region in it isn't the one from step 1, the Console is on another region: switch it at the top right and open **Configuration** again. Port **587** is the one to use (the app encrypts the connection with STARTTLS before logging in).

## 8. Put them on the server

Everything goes in `deploy/.env`, so `config.toml`, which `git pull` updates, is never edited.

1. Connect to the machine with SSH, then:

   ```
   cd ImageSkinForLLM/deploy
   git pull
   nano .env
   ```

2. Add these lines (take them from `.env.example` if `.env` doesn't have them yet), with your values after the `=`:

   ```
   IMAGESKIN_SMTP_HOST=smtp.email.YOUR-REGION.oci.oraclecloud.com
   IMAGESKIN_SMTP_PORT=587
   IMAGESKIN_SMTP_USER=ocid1.user.oc1..the.username.from.step.6
   IMAGESKIN_SMTP_PASSWORD='the.password.from.step.6'
   IMAGESKIN_MAIL_FROM=me0.ai <noreply@me0.ai>
   ```

   `IMAGESKIN_SMTP_HOST` is the **Public Endpoint** you copied in step 7, with your region in it; don't keep the example's `YOUR-REGION`. **Put the password in single quotes**, as above. Oracle's passwords often have characters such as `>`, `$`, `#` or `;`, and without quotes Docker reads a `$` as the start of a variable and a ` #` as the start of a comment, so the app would get a different password. In single quotes every character is kept as it is. A `>` or `<` at the start is fine either way, even if the editor colours the line oddly. If the password itself has a `'` in it, make new credentials (step 6) rather than quote it.

   `IMAGESKIN_MAIL_FROM` must use the approved sender from step 5. The part before `<` is the name people see, so it can be anything. Save and close (Ctrl+O, Enter, Ctrl+X).

3. A changed `.env` needs the app made again, not only restarted:

   ```
   docker compose up -d --build
   ```

4. Check it started with them: `docker compose logs app | grep "Mail service set in the environment"` prints a line. If the app doesn't start, `docker compose logs app | tail` says which setting is wrong.

## 9. Send a test email

1. On the machine, in `ImageSkinForLLM/deploy`, send one to your own address:

   ```
   docker compose exec app imageskin --config /etc/imageskin/config.toml email-test you@gmail.com
   ```

2. It prints `Sent a test email to you@gmail.com through smtp.email....`, and the email **ImageSkinForLLM test email** arrives within a minute or two. If it lands in spam, mark it **Not spam**, and check that DKIM is **Active** and SPF is **Yes** (steps 3 and 4).
3. If it prints `The test email could not be sent: the log says why.`, run `docker compose logs app | grep "Email failed"` (or `docker compose logs --tail 30 app`) and see the table below.
4. Then try it in the app: on `https://app.me0.ai`, click **Host sign in**, then **Forgot your password?**, and enter a host's email. The reset email arrives in that inbox, not the outbox.

## If it doesn't work

| What you see | Why, and what to do |
|---|---|
| `535 Authentication credentials invalid` | The username or password the app got isn't the one Oracle made. Run the check below this table. The usual causes: the username cut short at its `@` (step 6, it must be whole), a space at the end of either, the password not in single quotes and with a `$` or ` #` in it (step 8), credentials generated less than a few minutes ago, or a password copied wrong, as it is shown only once. If the check looks right, make new credentials (step 6), put both in `.env` again, and run `docker compose up -d`. |
| `Envelope From address <noreply@me0.ai> not authorized`, `Sender is not authorized` or `not an approved sender` | The login worked, but Oracle won't send as this address. Either the approved sender is in another region than the endpoint (its OCID names its region, such as `us-sanjose-1`, and the endpoint must name the same one: steps 1, 5 and 7), or the mail user isn't allowed to send: it must be in `EmailSenders`, and `EmailSendersPolicy` must be in the root compartment (step 6). Group and policy changes take a few minutes. `IMAGESKIN_MAIL_FROM` must be the approved sender, but the error shows the address the app used, so compare them there. |
| A timeout, or `Connection refused` | `IMAGESKIN_SMTP_HOST` is misspelled, or the port isn't 587. Step 7. |
| `STARTTLS extension not supported` | The port is 25. Use 587. |
| It is sent, but lands in spam or never arrives | DKIM isn't **Active** or SPF isn't **Yes** yet (steps 3 and 4). Wait for both, then send again. |
| Some emails arrive, then they stop for the day | The daily limit is reached. **Limits, Quotas and Usage** in the Console shows it; it resets the next day. |
| Emails still go to the outbox | `IMAGESKIN_SMTP_HOST` is empty, or the app wasn't made again after `.env` changed. Step 8. |

**Test the login alone.** This logs in with a username and password you paste, leaving `.env` out of it. `Login OK` means Oracle's side is right and `.env` passes the app something else; a 535 means the credentials or the user are the problem (step 6).

```
docker compose exec -it app python -c "import smtplib,getpass,os; s=smtplib.SMTP(os.environ['IMAGESKIN_SMTP_HOST'],587,timeout=20); s.starttls(); s.login(input('Username: ').strip(), getpass.getpass('Password: ')); print('Login OK')"
```

**Check what the app got.** This prints each one's length and its first and last characters, never the whole password, so you can compare them with what Oracle showed you:

```
docker compose exec app python -c "import os
for n in ('IMAGESKIN_SMTP_USER', 'IMAGESKIN_SMTP_PASSWORD'):
    v = os.environ.get(n, ''); print(n, len(v), repr(v[:1]), repr(v[-1:]))"
```

For the username the length is often over 100. For the password, the first and last characters must match Oracle's, with no `'` and no space: a `'` there means the quotes were kept, and a length of 0 means `.env` has no password or the app wasn't made again after it changed.

## Turning it off

To go back to the outbox, empty `IMAGESKIN_SMTP_HOST=` in `deploy/.env` and run `docker compose up -d --build`. Nothing in Oracle needs to change.
