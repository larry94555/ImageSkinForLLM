# Mail setup guide

Step by step: how to make the hosted site on the Oracle machine send real email, such as sign-up confirmations, password resets, email changes and test account emails, through Oracle Cloud's own mail service, **OCI Email Delivery** (roadmap R215). Until this is done, the app writes each email to its outbox instead, and you read them on the server ([Host Lifecycle walkthrough guide](Host-Lifecycle-Walkthrough-Guide.md), "Where the emails go").

**Why Email Delivery and not a mail server on the machine.** Oracle blocks outbound port 25 for tenancies made after June 2021, so a mail server on the machine couldn't reach anyone's inbox. Mail sent straight from a cloud machine's address is also often marked as spam. Email Delivery is Oracle's sending service, in the same account as the machine. The app logs in to it on port 587 with a username and password, over an encrypted connection, and it delivers the mail. Nothing needs installing on the machine, and no port needs opening.

**What it costs.** Email Delivery is part of Oracle's free tier, with a small daily allowance (about 100 emails a day on a free account; check **Limits, Quotas and Usage** in the Console for yours). That is plenty for testing and a few hosts. A paid account can ask for more.

It takes about 30 minutes. Most of it is waiting for the DNS records to be checked.

**You need:** the Oracle Cloud account that runs the machine, Cloudflare for me0.ai's DNS ([Subdomain setup guide](Subdomain-Setup-Guide.md), step 1), and an SSH connection to the machine ([deployment guide](../../deploy/README.md), step 4).

## 1. Find the machine's region

Email Delivery is set up per region, and the app must use the same region as everything else here.

1. Sign in at https://cloud.oracle.com.
2. The region is at the top right of the Console, such as **US West (Phoenix)**. Click it to see its identifier, such as `us-phoenix-1`. Write it down.

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

## 6. Make the SMTP username and password

The app logs in to Email Delivery with SMTP credentials that belong to an Oracle user. Your own user works. A separate user with only this permission is safer, but more steps; your own user is fine to start.

1. Click your profile picture (top right), then **My profile** (or **User settings**).
2. Under **Resources** (or the **Saved passwords** tab), open **SMTP Credentials** and click **Generate credentials**.
3. **Description**: `me0.ai app`. Click **Generate credentials**.
4. Oracle shows a **Username**, a long string that starts `ocid1.user`, and a **Password**. **Copy both now**: the password is shown only once. If you lose it, delete these credentials and make new ones. Treat the password like the administrator's.

## 7. Find the SMTP server's name

1. In **Email Delivery**, open **Configuration**.
2. Under **SMTP Sending Information**, copy the **Public Endpoint**, such as `smtp.email.us-phoenix-1.oci.oraclecloud.com`. Port **587** is the one to use (the app encrypts the connection with STARTTLS before logging in).

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
   IMAGESKIN_SMTP_HOST=smtp.email.us-phoenix-1.oci.oraclecloud.com
   IMAGESKIN_SMTP_PORT=587
   IMAGESKIN_SMTP_USER=ocid1.user.oc1..the.username.from.step.6
   IMAGESKIN_SMTP_PASSWORD=the.password.from.step.6
   IMAGESKIN_MAIL_FROM=me0.ai <noreply@me0.ai>
   ```

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
| `535 Authentication credentials invalid` | The username or password is wrong, or has a space at the end. Copy them again from step 6; if the password is lost, make new credentials. |
| `Sender is not authorized` or `not an approved sender` | `IMAGESKIN_MAIL_FROM` isn't the approved sender, or it was approved in another region than the endpoint's. Steps 1 and 5. |
| A timeout, or `Connection refused` | `IMAGESKIN_SMTP_HOST` is misspelled, or the port isn't 587. Step 7. |
| `STARTTLS extension not supported` | The port is 25. Use 587. |
| It is sent, but lands in spam or never arrives | DKIM isn't **Active** or SPF isn't **Yes** yet (steps 3 and 4). Wait for both, then send again. |
| Some emails arrive, then they stop for the day | The daily limit is reached. **Limits, Quotas and Usage** in the Console shows it; it resets the next day. |
| Emails still go to the outbox | `IMAGESKIN_SMTP_HOST` is empty, or the app wasn't made again after `.env` changed. Step 8. |

## Turning it off

To go back to the outbox, empty `IMAGESKIN_SMTP_HOST=` in `deploy/.env` and run `docker compose up -d --build`. Nothing in Oracle needs to change.
