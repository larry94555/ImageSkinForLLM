# Milestone 20 walkthrough guide

Step by step: every use case Milestone 20 (many customers on me0.ai) added, tried by hand on the hosted site, then everything the test changed cleared away again. It covers host sign-up and the free trial, email confirmation, Forgot password, changing the email, signing in from any address, the display name, sites kept apart, subscribing and the site's subdomain, several sites for one host, PDFs shared among them, participants and where each may go, the administrator acting as a host and disabling one, and cancelling, pausing, resuming, deleting and starting a site again (roadmap R214 to R262, with R46 from Milestone 12).

Plan on about two hours for all of it. Each part can be done on its own once Part 1 and Part 2 are done, and each ends with **What to look for**, the page or the log line that shows it worked. [Part 11](#part-11-clear-away-everything-the-test-changed) puts the site back as it was before you started.

## Contents

- [Before you start](#before-you-start)
- [Part 0. Save a restore point](#part-0-save-a-restore-point)
- [Part 1. Sign in as the administrator](#part-1-sign-in-as-the-administrator)
- [Part 2. A host signs up for a free trial](#part-2-a-host-signs-up-for-a-free-trial)
- [Part 3. The host's account: password, email, display name, signing in anywhere](#part-3-the-hosts-account-password-email-display-name-signing-in-anywhere)
- [Part 4. Each site kept apart](#part-4-each-site-kept-apart)
- [Part 5. Subscribing and the site's own address](#part-5-subscribing-and-the-sites-own-address)
- [Part 6. Several sites for one host, and their shared PDFs](#part-6-several-sites-for-one-host-and-their-shared-pdfs)
- [Part 7. Participants and where each may go](#part-7-participants-and-where-each-may-go)
- [Part 8. The administrator acts as a host, and disables one](#part-8-the-administrator-acts-as-a-host-and-disables-one)
- [Part 9. Cancelling, pausing and resuming](#part-9-cancelling-pausing-and-resuming)
- [Part 10. Deleting a site and starting it again](#part-10-deleting-a-site-and-starting-it-again)
- [Part 11. Clear away everything the test changed](#part-11-clear-away-everything-the-test-changed)
- [Which part covers each roadmap PR](#which-part-covers-each-roadmap-pr)
- [If something doesn't work](#if-something-doesnt-work)

## Before you start

**Why the hosted site, not the laptop.** Two things only work on the real domain: a participant's sign-in is shared by a host's sites through a cookie for `me0.ai` (R260), which `localhost` addresses don't share, and Stripe sends its payment events to a public address (R67). So this guide uses `app.me0.ai` and its subdomains. Everything is done in Stripe's **test mode**, so no card is charged.

**What has to be in place first:**

1. The server runs `main` with Milestone 20 merged (PR #312 or later). On the server: `cd ~/ImageSkinForLLM && git log --oneline -1`. If it is older, `git pull`, then in `deploy`, `docker compose up -d --build`.
2. The administrator's password is set in `deploy/admin/admin.toml` (the [Admin password guide](Admin-Password-Guide.pdf)), and, if you use `admin-laptops.toml`, your laptop is listed.
3. Subscribing is turned on in **test mode**: [the deployment guide](../../deploy/README.md), step 9, steps 1 to 7, with the `sk_test_` key, the test webhook's `whsec_` secret and the test price's `price_` ID in `deploy/.env`. The webhook must have the three events `checkout.session.completed`, `customer.subscription.updated` and `customer.subscription.deleted`. Without this, Parts 5, 6 (Add a site), 9 and 10 can't be done; Parts 2 to 4, 7 and 8 still can, using the command in Part 6 for a second site.
4. Every subdomain works over HTTPS: `https://nosuchsite.me0.ai` shows the app's **Site not found** page with a padlock ([Subdomain setup guide](Subdomain-Setup-Guide.md)).

**The test people.** Use one Gmail address with `+` names, so every email reaches your one inbox but each is a different account to the app. In this guide `you@gmail.com` stands for your address; type yours.

| Who | Email | Display name | Role |
|---|---|---|---|
| Ann | `you+ann@gmail.com` | Dr. Ann | Host with two sites |
| Bob | `you+bob@gmail.com` | Bob's Tutoring | Host with one trial site |
| Pat | `you+pat@gmail.com` | | Participant of Ann's |
| Quinn | `you+quinn@gmail.com` | | Participant of Ann's |

Each email address gets one free trial only (R66). Part 11's restore puts that record back as it was before the test, so the same names work again after a restore. If you run the guide twice without restoring, use new names, such as `you+ann2@gmail.com`.

**The subdomains used:** `m20-ann` and `m20-ann2` for Ann's sites, `m20-bob` for Bob's once paid. Any free names work.

**Browsers.** You need three separate sign-ins at once: the administrator, a host and a participant. Use one normal window, one private (incognito) window, and a second browser (such as Edge beside Chrome). Each private window starts with no cookies, which is also how you test as a brand-new visitor.

**Where the emails go.** If the server has a mail service set (`smtp_host` in `deploy/config.toml`), emails arrive in your Gmail. If not, the server writes each one to its outbox, and you read the newest one on the server with:

```
cd ~/ImageSkinForLLM/deploy
docker compose exec app python -c "import email,email.policy,pathlib;f=max(pathlib.Path('/data/outbox').glob('*.eml'));m=email.message_from_bytes(f.read_bytes(),policy=email.policy.default);print(f.name);print('To:',m['To']);print('Subject:',m['Subject']);print(m.get_content())"
```

It prints the newest email whole, with its link on one line ready to copy. Use this command, not `cat`: the saved file can break a long link over two lines.

**Watching the log.** In a second SSH window, keep the log running while you test, and the **What to look for** lines show up as you go:

```
cd ~/ImageSkinForLLM/deploy
docker compose logs -f --since 1m app
```

Ctrl+C stops watching; the site keeps running. To look for one line afterwards: `docker compose logs --since 30m app | grep "Site created"`.

**The sites' inside names.** `docker compose exec app imageskin site list` lists every site by the name the server keeps it under, its host, and where it is (a trial's 12-character code, or its subdomain). It prints `.localhost` after a subdomain; on the hosted site read that as `.me0.ai`. Parts 10 and 11 need these names.

## Part 0. Save a restore point

Do this before anything else, so [Part 11](#part-11-clear-away-everything-the-test-changed) can put every site, host, participant, PDF and setting back exactly as they are now. It copies the app's data, leaving out the large shared downloads (the models and the default people), which the test doesn't change.

On the server:

```
cd ~/ImageSkinForLLM/deploy
docker compose stop app
docker run --rm -v imageskin_imageskin-data:/data -v "$HOME":/backup ubuntu tar czf /backup/before-m20-test.tgz -C /data --exclude=./models --exclude=./default-people --exclude=./huggingface .
docker compose start app
ls -lh ~/before-m20-test.tgz
```

The site is down for the minute or so this takes. The file is in your home folder on the server, outside the git folder, so it is never committed.

**What to look for:** `ls` prints the file with its size, usually tens of MB at most.

## Part 1. Sign in as the administrator

Browser 1 (your normal window) is the administrator's for the whole guide.

1. Open `https://app.me0.ai/#/settings`.
2. Under **Administrator**, type the administrator's password and click **Sign in as administrator**.
3. Click **Open the admin view**. The tabs are **Resources**, **Admin settings** and **Admin guidelines**.
4. Open **Admin settings**. Under **Deleting paused sites**, note **Days before deleting (1 to 365)**, 30 to begin with. Leave it for now; Part 10 changes it.
5. Under **Hosts**, **Host properties** lists every host. You'll come back here in Part 8.

**What to look for:** "Signed in as administrator" on the Settings page.

## Part 2. A host signs up for a free trial

Covers R62 (sign-up makes a trial site at a path), R62b (confirming the email), R66 (one trial per email), R259 (display name at sign-up) and R61a (a site at a trial path).

Browser 2 (a private window) is Ann's.

1. Open `https://app.me0.ai` and click **Host sign up** in the top bar.
2. Fill in `you+ann@gmail.com`, a password twice, and **Display name** `Dr. Ann`. Click **Sign up**.
3. The browser goes to Ann's new site at a trial path, such as `https://app.me0.ai/t/k7q2x9mf3a8w/`, on its setup. Copy this address somewhere; it is Ann's trial address. Every page says **Confirm your email**, with **Send it again**, and there is no Settings link yet.
4. Click **Send it again** once. Click it again at once: it is refused for a minute.
5. Open the newest email (Gmail, or the outbox command in [Before you start](#before-you-start)). Open its link. Ann's site opens on its setup, confirmed: the banner is gone and **Settings** is in the top bar.
6. Open the first email's link (the one before **Send it again**). It says the link didn't work, as a new one replaced it.
7. Set up the site's person as for any site: pick a ready-made person with **Start now** for speed, or your own photo and voice. Then ask the chat a question.
8. **One trial per email:** in a third private window, open `https://app.me0.ai`, click **Host sign up**, and sign up again with `you+ann@gmail.com`. It is refused: **This email address has already had a free trial. Sign up with another address.**
9. **Sign-up only at the main address:** on Ann's trial address, open `#/host/sign-up` (add it after the trial address) and try to sign up with a new email. It is refused, as the site already has its host.
10. Now Bob: in browser 3 (the second browser), open `https://app.me0.ai`, click **Host sign up**, and sign up `you+bob@gmail.com` with display name `Bob's Tutoring`. Confirm from his email and set up his person, as for Ann. Copy his trial address too.

**What to look for:** `Site created` with the trial code, `Confirmation email sent`, `Host email confirmed`, `Trial refused: email already used`.

## Part 3. The host's account: password, email, display name, signing in anywhere

Covers R62a (Forgot password), R62c (changing the email), R259 (changing the display name) and R255 (signing in at any address).

In Ann's browser (browser 2):

1. **Display name.** Click Ann's name in the top bar to open **Your account**. Change **Display name** to `Dr. Ann Smith` and click **Save display name**. It says participants and visitors now see her by it.
2. In a new private window, open Ann's trial address as a visitor. The top bar says **Hosted by Dr. Ann Smith**. Ann's email is nowhere on the page.
3. **Forgot password.** Click **Sign out**. Click **Host sign in**, then **Forgot your password?**, enter `you+ann@gmail.com` and send. It says the same whether or not the account exists. Enter a made-up email such as `you+nobody@gmail.com`: the same answer, and no email.
4. Open the reset email's link, set a new password twice, and sign in with it.
5. Open the same reset link again: it is refused, as it works once.
6. **Signing in from any address.** Sign out. Open `https://app.me0.ai`, click **Host sign in**, and sign in as Ann. The browser goes to Ann's trial site, signed in there. Sign out, open Bob's trial address, click **Host sign in**, and sign in as Ann there: she lands on her own site, never Bob's.
7. A wrong password at any address is refused with **The email address or password is wrong.**, saying nothing about where her site is.
8. **Change email.** On **Your account**, under **Change email**, enter `you+ann.new@gmail.com` and Ann's password. A link goes to the new address; the account still uses the old one until it is opened.
9. Open the link. Ann is still signed in, now as `you+ann.new@gmail.com`, and the old address gets a notice that the email was changed.
10. Change it back the same way, to `you+ann@gmail.com`, so the rest of the guide's names hold.

**What to look for:** `Host display name set`, `Password reset link sent`, `Host password reset` with `by: link`, `Host password not reset`, `Host sent to their own site`, `Host signed in` with `from: "another address"`, `Email change link sent`, `Host email changed`.

## Part 4. Each site kept apart

Covers R61 (one store per site, matched by address), R44 (a site's settings for its host only, the administrator on the main address only), R65 (each site's own history and progress), R65a (each visitor's own conversation), R65b (every file in the Resources page) and R71 (no password in front of the sites).

1. **No password at the proxy.** Open Ann's trial address in a new private window. No browser password box appears; the chat opens for a visitor.
2. **Site not found.** Open `https://nosuchsite.me0.ai`. It shows **Site not found**, with a padlock.
3. **Settings only for its own host.** As Bob (browser 3), open Ann's trial address followed by `#/settings`. Bob gets what a visitor gets, not Ann's settings. Opening `#/content` there shows no Manage Content for him either.
4. **A setting changes one site only.** As Ann, open **Settings** and turn on **Teach me** (or any other setting). As Bob, on his site's **Settings**, it is still off.
5. **The administrator is not on a customer's site.** In the administrator's browser (browser 1), open Ann's trial address followed by `#/settings`. There is no administrator sign-in there and no admin view: the administrator is only at `app.me0.ai`. The ChatGPT plan isn't offered under the LLM choice on Ann's site either.
6. **Each visitor's own conversation.** Open Ann's trial address in two different private windows (or one private window and the second browser signed out). Ask a different question in each. Each window shows only its own question and answer. Reload each: each still shows its own. **Clear conversation** in one clears only that one.
7. **Teach me progress per site.** With Teach me on for Ann's site, start a lesson there as a visitor. Open Bob's trial address in the same window: no lesson under way there.
8. **Resources.** As Ann, click **Resources** in the top bar. It shows **Images and voice recordings**, **PDFs**, **Guidelines**, **Conversations and history**, **Preferences**, **Other** and **Total**. The visitors' questions from step 6 count under Conversations and history. Bob's Resources page shows only his.

**What to look for:** `Site matched` with each site, `Site not found` with the address, `Admin route refused on a customer's site`, `ChatGPT plan refused on a customer's site`, `Visitor conversation started`, `Host disk space counted`.

## Part 5. Subscribing and the site's own address

Covers R67 (subscribing through Stripe), R63 (picking the subdomain at the first payment) and R64 (changing it). Needs Stripe's test mode from [Before you start](#before-you-start).

As Ann (browser 2):

1. Open **Settings**. The **Subscription** panel says the price, 5 GB for $1.99 a month, with **Subscribe**, and the **Free trial** panel has **Cancel free trial**.
2. Click **Subscribe**. Stripe's own page opens, with Ann's email filled in. Pay with the test card `4242 4242 4242 4242`, any future date, any three digits and any postcode.
3. Stripe sends the browser back to **Settings**, which says **Subscribed** and asks **Pick your site's address**. **Cancel free trial** is gone.
4. **The name is checked as you type.** Type `app`: it is kept for the service. Type `m20 ann`: letters, digits and hyphens only. Type the subdomain of an existing site (such as your own `larry-freeman`): taken. Type `m20-ann`: it says `m20-ann is free.`
5. Click **Use this address**. The browser goes to `https://m20-ann.me0.ai`, still signed in, with the same person, PDFs, settings and conversation as on the trial path.
6. Open Ann's old trial address. It goes on to `https://m20-ann.me0.ai` by itself.
7. **Changing the address.** In **Settings**, the **Site address** panel says `m20-ann`. Under **Change your site's address**, type `m20-ann-x`, click **Change address**, and the browser goes to `https://m20-ann-x.me0.ai`, signed in. `https://m20-ann.me0.ai` now says **Site not found**, and the old trial address goes to the new name.
8. Change it back to `m20-ann` the same way. The name was freed at once, so it is accepted.
9. In Stripe's test Dashboard, **Customers** has Ann's email with a subscription, and on the webhook's page each event shows **200 OK**.

**What to look for:** `Stripe event` with each event's type, `Site subscribed`, `Subdomain picked`, `Trial path moved`, `Subdomain changed` with the old and new names.

## Part 6. Several sites for one host, and their shared PDFs

Covers R256 and R257 (several sites for one host), R258 and R258a (a host's PDFs kept once and used on any of their sites).

1. **Add a site.** As Ann, open **Your account**. **Your sites** lists `m20-ann.me0.ai` as "this site". Under **Add a site**, type `m20-ann2` (checked as you type, as in Part 5), and click **Add and subscribe**. Stripe's page opens for Ann's Stripe customer, with her card from Part 5 offered. Pay.
2. Stripe sends the browser back to the account page. **Your sites** now lists both. A **site switcher** is in the top bar of every host page.
3. Click **Open** beside `m20-ann2.me0.ai` (or use the switcher). It opens signed in: one sign-in works on both. Set up its person with **Start now**, a different person from `m20-ann`'s, so you can tell them apart.
4. Bob still can't open either of Ann's sites as a host, and Ann can't sign in on Bob's site as its host.

   *Without Stripe:* give Ann a second site from the server instead, then sign in again: `docker compose exec app imageskin site add m20-ann2 --host you+ann@gmail.com`.

5. **A PDF on two sites.** On `m20-ann`, open **Manage Content** and upload a small PDF. Wait until it is read and its wiki built.
6. In the PDF's row, **Used on** has a checkbox for each of Ann's sites; `m20-ann`'s is ticked. Tick `m20-ann2.me0.ai`.
7. Switch to `m20-ann2`. The PDF is in its Manage Content and wiki at once, not read again. Ask the chat about it there, and on `m20-ann`: both answer from it.
8. Edit a wiki page on one site. Open it on the other: the edit is there too.
9. Bob's site shows nothing of the PDF.
10. On either site, open **Resources**: the PDF is counted once, under **PDFs**, however many sites use it.
11. **Remove from one site.** On `m20-ann2`, click **Remove** on the PDF. It asks **Remove from this site** or **Delete everywhere**. Choose **Remove from this site**. It is gone from `m20-ann2` and still on `m20-ann`. (You can give it back by ticking `m20-ann2` again; **Delete everywhere** removes it from both.)

**What to look for:** `Site added, to be paid for`, `Site subscribed`, `Host site opened`, `Host's PDFs opened`, `PDF's sites changed` with the sites before and after, `PDF taken off the site`.

## Part 7. Participants and where each may go

Covers R46 (participant sign-up and sign-in, from Milestone 12), R260 (a participant belongs to the host and one sign-in works on the host's sites), R261 (the host's policy for which sites each participant may open and where they land) and R262 (the page for a site a participant may not use). Needs Ann's two sites from Part 6.

Browser 3 is the participants' for this part: first sign Bob out there.

1. **Sign up.** Open `https://m20-ann.me0.ai`. Click **Sign up** in the top bar (the participants' link, not **Host sign up**). Sign up `you+pat@gmail.com` with a password. The top bar shows Pat's email and **Sign out**; there is no Settings, Manage Content or setup.
2. Ask a question. Close the browser completely, open it again and go to `https://m20-ann.me0.ai`: Pat is still signed in, and the conversation is still there.
3. **One sign-in for the host's sites.** Open `https://m20-ann2.me0.ai`: Pat is already signed in there too.
4. **Another host's site doesn't know Pat.** Open Bob's trial address: Pat isn't signed in. Click **Sign in** and use Pat's email and password: refused, as the account is Ann's.
5. Sign up Quinn the same way on `m20-ann2` (sign Pat out first, or use another private window).
6. **The policy.** As Ann (browser 2), open **Your account** and find **Where participants may go**. The rule for **Every participant** has both sites ticked under **May open:**, sending them to the first site they may open.
7. Add a rule for Pat alone: pick `you+pat@gmail.com`, tick only `m20-ann2.me0.ai` under **May open:**, choose `m20-ann2.me0.ai` as where Pat is sent, and save.
8. **Landing site.** In browser 3, sign Pat out, open `https://m20-ann.me0.ai`, and sign in as Pat. The browser goes to `https://m20-ann2.me0.ai`, signed in.
9. **A site Pat may not use.** Still as Pat, open `https://m20-ann.me0.ai`. The page shows only "This subdomain is not yet active -- check with the host on its status.", with Pat's email and **Sign out**, and no **Hosted by**, links or anything of Ann's site.
10. Quinn, under the rule for every participant, still opens both sites.
11. **Change the policy.** As Ann, tick `m20-ann.me0.ai` again in Pat's rule and save. Pat opens `m20-ann` again (a change applies at once to which sites Pat may open, and at Pat's next sign-in to where Pat lands).
12. Try saving a rule that allows no site at all: it is refused with its reason.

**What to look for:** `Participant signed up`, `Participant signed in`, `Participant sign-in refused`, `Participant sent to their site`, `Participant not allowed here` with the site and the path.

## Part 8. The administrator acts as a host, and disables one

Covers R44a and R44b (acting as a host) and R44c and R44d (disabling a host).

In the administrator's browser (browser 1), at `https://app.me0.ai`:

1. **Act as a host.** In the admin view, open **Admin settings**, then **Host properties**. Under **Search hosts by email**, type `ann` and pick `you+ann@gmail.com`. Her panel lists both of her sites.
2. Click **Act as this host**. It asks first, naming Ann. Click **Yes, act as this host**.
3. The browser goes to Ann's site with a bar on every page: "Acting as you+ann@gmail.com, as the administrator", with **Stop acting**. Everything else is as Ann sees it.
4. Change something, such as a setting in **Settings**. Use the switcher to go to `m20-ann2`: still acting as Ann there.
5. Open **Your account**, then **Change email**: the box asks for the **Administrator password**, not Ann's. (Don't send it; this only shows it.) **Add a site** isn't offered, as it is paid with Ann's card.
6. Click **Stop acting**. The browser is back in the admin view at `app.me0.ai`, still signed in as the administrator.
7. In Ann's own browser (browser 2), reload: the change from step 4 is there, with no acting bar.
8. **Disable a host.** In **Host properties**, pick Bob and click **Disable**. It asks "Disable you+bob@gmail.com?". Confirm. The host list now says "Disabled: read-only for them" under his email.
9. In Bob's browser (sign Pat out and Bob in again in browser 3), every host page shows "Your site is read-only. Changes are turned off by the administrator." Every button and field that would change something is turned off; reading every page still works, and visitors still chat on his site.
10. As the administrator, act as Bob (step 2): the bar says acting, and the controls work. Change a setting, then **Stop acting**. Bob's own page shows the change, still read-only for him.
11. Back in **Host properties**, click **Enable** for Bob. His controls work again at once.

**What to look for:** `Admin acting as host started` and `Admin acting as host stopped` with the host's email, `acting_as` in each request's line while acting, `Host disabled`, `Host change refused` with `why: "disabled"`, `Host enabled`.

## Part 9. Cancelling, pausing and resuming

Covers R66 (cancelling a free trial), R69 (cancelling a subscription, and the site paused when it ends) and R69b (resuming in one click).

**A free trial cancelled.** As Bob:

1. Open **Settings**. Under **Free trial**, click **Cancel free trial**. It asks first and says how many days the content is kept. Confirm.
2. In a private window, open Bob's trial address: visitors see **This site is paused**, with **Host sign in**.
3. Bob, signed in, still uses every page, with a bar saying the site is paused and a **Resume subscription** link to Settings. Bob never paid, so in Settings he has **Subscribe**, not a one-click resume. Leave Bob paused: Part 10 deletes his site.

**A subscription cancelled, then kept.** As Ann, on `m20-ann`:

4. Open **Settings**. In **Subscription**, click **Cancel subscription**, then **Yes, cancel it**. It says "Cancelled: your site keeps working until <date>, then pauses", with **Keep my subscription**. The site still works for visitors.
5. Click **Keep my subscription**. The cancellation is undone.

**The subscription ending, then resumed.** Stripe would end it at the end of the month; the Dashboard ends it now:

6. Cancel again as in step 4.
7. In Stripe's test Dashboard, open **Subscriptions**, open the one for Ann's email whose site is `m20-ann` (the older of her two), click **Cancel subscription**, choose **Immediately**, and confirm.
8. Reload `https://m20-ann.me0.ai` in a private window: **This site is paused**. Ann sees the paused bar on every page.
9. As Ann, open **Settings** and click **Resume subscription**. The confirmation says "Your subscription, 5 GB for $1.99 a month, starts again now and is charged to the card Stripe keeps for you." Click **Yes, resume it**.
10. The site is back at once, with everything on it, and no card was typed. Stripe's Dashboard shows a new subscription for Ann.

*Optional, the fallback when Stripe has no card:* in the Dashboard, remove the card from Ann's customer, end her subscription again as in step 7, and click **Resume subscription**: Stripe's page opens for a card instead.

*Not walked here:* a failed renewal (R69's notice while Stripe retries, then the pause when it gives up) needs Stripe to try a renewal, which only happens at the end of a real month or on a Stripe test clock; the unit tests cover it.

**What to look for:** `Trial cancelled`, `Paused site refused a visitor`, `Subscription cancelled` with when it ends, `Subscription kept`, `Subscription changed`, `Site paused` with why `subscription ended`, `Subscription resumed`.

## Part 10. Deleting a site and starting it again

Covers R69a (deleting a site, its content kept for the admin settings' days), R69c (starting a deleted site again) and R256's removal of one of a host's several sites.

A paused site's content is deleted only after **Days before deleting**, at least 1 day. To see it now, you set the days to 1 and mark the site as paused two days ago, so the server's hourly sweep deletes it at its next start.

**Ann deletes her second site.**

1. As Ann, on `m20-ann2`, open **Settings**, then **Delete site**. Type Ann's password and click **Delete site**. The confirmation says the subscription is cancelled, the service lasts until the end of the month, then the 30 days to renew. Click **Yes, delete it**. The panel says until when the service lasts.
2. In Stripe's test Dashboard, cancel the `m20-ann2` subscription **Immediately**, as in Part 9, step 7. The site pauses, and its **Delete site** panel says "Your site has been paused. You will have 30 days to start it again before it gets deleted.", counting down.

**Bob's trial.** Bob's site is already paused from Part 9 (Cancel free trial), which is all deletion needs. Had he not cancelled, **Delete site** in his Settings, with his password, would pause it at once, as a trial has nothing paid for.

3. As Bob, open **Settings**: the **Delete site** panel says how many days are left before his site is deleted.

**Make the deletion happen now.**

4. As the administrator, in **Admin settings**, set **Days before deleting** to `1` and save.
5. On the server, find the two sites' inside names: `docker compose exec app imageskin site list`. Ann's second site is listed as `m20-ann2` (or a random code, if the name had been used before), and Bob's by his 12-character trial code.
6. Mark each as paused two days ago, putting its name in place of `NAME`:

   ```
   docker compose exec app python -c "import json,sys,time;p='/data/sites.json';d=json.load(open(p));d['sites'][sys.argv[1]]['paused_at']=time.time()-2*86400;json.dump(d,open(p,'w'),indent=2)" NAME
   ```

7. `docker compose restart app`. Within a minute of starting, the server deletes both.
8. `https://m20-ann2.me0.ai` says **Site not found**, and Bob's trial address does too.
9. Ann signs in as before. **Your sites** lists only `m20-ann`, and the PDF from Part 6 is still there on it. Its Resources page is as before.
10. **Starting again.** Bob signs in at `https://app.me0.ai`. With the right password it says "Your site was paused for 30 days, so its content was deleted. You can start a new, empty site at the same address if it is still free." with **Start my site again**. (The message gives the admin settings' days, so after step 4 it may say 1 day.)
11. Click **Start my site again**. Bob lands on a new, empty site, paused until paid for. His trial was never paid, so Settings has **Subscribe**: pay with the test card, pick `m20-bob` as in Part 5, and the site opens. A host whose deleted site was paid for gets **Resume subscription** with their card instead, as in Part 9.
12. Set **Days before deleting** back to `30`.

**What to look for:** `Site deletion asked`, `Site paused` with why `deleted by its host`, `Paused sites deleted`, `Site deleted` with why and how long it took, `Host site removed`, `Host's site deleted`, `Deleted site's PDFs taken off`, `Site started again`.

## Part 11. Clear away everything the test changed

When you are done, or whenever you want to start over, clear the test away in two places: Stripe, then the app's data. Do Stripe first, so its cancellations reach the test sites and not sites restored in their place.

**1. Stripe (test mode only).** In the Dashboard, with **Test mode** (or the sandbox) on:

- Open **Subscriptions** and cancel each test subscription still active, **Immediately**.
- Optionally, remove the test customers in **Customers**, or clear the whole sandbox: in **Developers**, **Overview**, Stripe offers to delete all test data (wording differs between Dashboard versions). Live mode is never touched by either.

**2. The app's data: back to the restore point.** This puts back every site, host, participant, PDF, setting, conversation and email in the outbox as they were at Part 0, and forgets every test account and trial. On the server:

```
cd ~/ImageSkinForLLM/deploy
docker compose stop app
docker run --rm -v imageskin_imageskin-data:/data -v "$HOME":/backup ubuntu bash -c 'cd /data && find . -mindepth 1 -maxdepth 1 ! -name models ! -name default-people ! -name huggingface -exec rm -rf {} + && tar xzf /backup/before-m20-test.tgz -C /data'
docker compose start app
docker compose exec app imageskin site list
```

`site list` shows the sites you had before the test, and none of the `m20-` ones. Sign in to your own site as before. Keep `~/before-m20-test.tgz` to restore again after the next run, or delete it with `rm ~/before-m20-test.tgz`.

**What the restore doesn't touch:** the administrator's password and laptops (`deploy/admin`), the Stripe keys (`deploy/.env`), `deploy/config.toml`, and emails already delivered to Gmail. Admin settings, such as **Days before deleting**, go back to what they were at Part 0.

**Clearing one thing without a restore.** If you'd rather keep the rest:

- A test site: delete it as in Part 10 (with the days at 1 and its `paused_at` moved back). The host's account stays, as it does for real customers.
- A setting, the PDFs or the person on one site: as the administrator, **Act as this host** (Part 8), then change it back, remove the PDF, or use **Delete my data** on that site's Settings.
- A host's sign-ins: `imageskin host-password-reset` gives a new password, as the last resort.
- There is no command or page that deletes a host account or a participant account: only the restore removes those.

## Which part covers each roadmap PR

| PR | What it does | Part |
|---|---|---|
| R214 | Review of host and participant functionality | (a review; nothing to try) |
| R61b, R61c, R61d | One set of app state per site; engines shared; the clone and Prepare taking turns across sites | 4 (sites kept apart); the turns show as "Waiting for another site's preparation to finish" when two sites Prepare at once |
| R61 | One store per site, matched by address | 4 |
| R61e, R61f | Each existing host's files and PDFs moved to their own site | Done once at the first start after it was deployed; your own site shows it |
| R61a | Sites at a trial path | 2 |
| R62, R62b | Sign-up with a trial site, confirming the email | 2 |
| R62a | Forgot password | 3 |
| R62c | Changing the email | 3 |
| R44 | A site's settings for its host only | 4 |
| R44a, R44b | Acting as a host | 8 |
| R44c, R44d | Disabling a host | 8 |
| R65, R65a | Each site's history and progress; each visitor's conversation | 4 |
| R65b | Every site file in the Resources page | 4, 6 |
| R66 | Free trial, one per email, and cancelling it | 2, 9 |
| R67 | Subscribing through Stripe | 5 |
| R255 | Signing in from any address | 3 |
| R63, R64 | Picking and changing the subdomain | 5 |
| R69 | Cancel, a failed payment, a paused site | 9 |
| R69a | Deleting a site | 10 |
| R69b | Resuming a cancelled subscription | 9 |
| R69c | Starting a deleted site again | 10 |
| R256, R257 | Several sites for one host | 6, 10 |
| R258, R258a | A host's PDFs kept once, on several sites | 6 |
| R259 | The host's display name | 2, 3 |
| R46 | Participant sign-up and sign-in (Milestone 12) | 7 |
| R260 | Participants belong to the host | 7 |
| R261 | Where each participant may go | 7 |
| R262 | The page for a site a participant may not use | 7 |
| R71a, R71 | Every subdomain over HTTPS, with no password in front | Before you start, 4 |

## If something doesn't work

- **Subscribe says subscribing isn't set up:** one of the three Stripe settings is missing. `docker compose logs app | grep "Stripe setting is missing"` names it; see [the deployment guide](../../deploy/README.md), step 9.
- **After paying, Settings doesn't say Subscribed:** Stripe's event didn't reach the app. On the webhook's page in Stripe, a failed event says why; `Stripe event refused` in the log means the `whsec_` secret in `.env` isn't the test webhook's. The webhook must be at `https://app.me0.ai/api/payments/stripe/events`.
- **No confirmation or reset email:** with no mail service set, look in the outbox (Before you start). With one set, `Email failed` in the log says why.
- **A subdomain doesn't open:** see the [Subdomain setup checklist](Subdomain-Setup-Checklist.md).
- **A participant isn't signed in on the host's other site:** both sites must be subdomains of `me0.ai` (`m20-ann` and `m20-ann2`); a trial path's participant sign-in is for `app.me0.ai` only.
- **Part 10's sites aren't deleted after the restart:** the days must be saved as 1 before the restart, and the name in step 6 must be the inside name from `site list`. A site deleted by Ann but not yet ended in Stripe isn't paused, so it isn't deleted; end it in the Dashboard first.
- **Signed out as the administrator in the middle:** the admin sign-in ends after the admin settings' minutes without activity, and acting as a host ends with it. Sign in again and act again.
