# Instagram auto-posting setup

`make_reel.py --post` publishes the finished reel with the official **Instagram Graph API**
(`src/instagram.py`). The MP4 goes up from your PC with Meta's **resumable upload**
(`rupload.facebook.com`), so you don't need to host the video anywhere. Posting stays off until
`IG_USER_ID` and `IG_ACCESS_TOKEN` are filled in `.env`. While they are empty, the pipeline still makes the
reel and prints `skipping publish`.

> **About music:** a reel posted through the API can't attach a track from Instagram's music library. That
> is a Meta limit. This pipeline is built around it: the song is mixed into the MP4's audio track, so the reel
> plays the song exactly like the reference reel does. It just won't show the "♫ song name" sticker.
> Instagram may mute or limit copyrighted audio on some accounts or regions. That is outside the API's
> control.

Which login you use matters. Meta documents the resumable (local-file) upload only for **Instagram API with
Facebook Login for Business** (host `graph.facebook.com`). Use **Option A** below.

---

## 1. Make your Instagram account Professional

1. In the Instagram app, go to **Profile → ☰ → Settings and activity → Account type and tools → Switch to
   professional account**.
2. Choose **Creator** or **Business**. Both work with the API. Personal accounts do not.

## 2. Link it to a Facebook Page (needed for Option A)

1. On Facebook, create a Page (any name, e.g. your reel page) at <https://www.facebook.com/pages/create>, or
   use one you already have.
2. Link the Instagram account to it. Use **Page → Settings → Linked accounts → Instagram → Connect**, or in
   the Instagram app go to **Settings → Accounts Center → Accounts → Add accounts**, or use
   **Edit profile → Page → Connect**.
3. You need a full-control (admin) role on the Page.

## 3. Create a Meta app

1. Go to <https://developers.facebook.com/apps> and click **Create app**.
2. Use case: **Other**. App type: **Business**.
3. Add the **Instagram** product. Choose **"API setup with Facebook login"** (Option A).
4. In development mode, the app works without App Review for accounts that hold a role on the app
   (admin/developer/tester). That covers posting to your own account. **App Review is only needed if other
   people's accounts will use the app.**

## 4. Get a token with the right permissions

### Option A: Facebook Login for Business (recommended; local-file upload supported)

Permissions: **`instagram_basic`, `instagram_content_publish`, `pages_read_engagement`**. Add
`pages_show_list`, which you need to list your Pages. If your Page role was granted through Business
Manager, also add `ads_management` and `ads_read`.

1. Open the **Graph API Explorer**: <https://developers.facebook.com/tools/explorer/>
2. Pick your app. Under **User or Page**, select *Get User Access Token*.
3. Tick the permissions above and click **Generate Access Token**. Log in and select your Page **and** your
   Instagram account in the dialog.
4. That token is **short-lived (~1 h)**. Exchange it for a **long-lived (~60 day)** token:

   ```
   GET https://graph.facebook.com/v26.0/oauth/access_token
       ?grant_type=fb_exchange_token
       &client_id=<APP_ID>
       &client_secret=<APP_SECRET>
       &fb_exchange_token=<SHORT_LIVED_TOKEN>
   ```

   App ID and secret are under **App settings → Basic**. Run this in a browser or with `curl`, and keep the
   result private.

5. Find your **Instagram user id** (`IG_USER_ID`, the numeric professional-account id, which is not your
   @handle):

   ```
   GET https://graph.facebook.com/v26.0/me/accounts?fields=name,instagram_business_account&access_token=<LONG_LIVED_TOKEN>
   ```

   The `instagram_business_account.id` of your Page is the value you need (e.g. `17841400000000000`).

### Option B: Instagram API with Instagram Login (no Facebook Page needed)

Permissions: **`instagram_business_basic`, `instagram_business_content_publish`**. Host:
`graph.instagram.com`. Tokens start with `IG...`, and `src/instagram.py` detects that and switches host
automatically. You can force a host with `IG_GRAPH_HOST=graph.instagram.com`.

1. In the app's Instagram product, choose **"API setup with Instagram login"**. Add your IG account as an
   Instagram tester and accept the invite (Instagram app → Settings → Apps and websites).
2. Click **Generate token** next to your account. The dashboard returns a long-lived token (60 days) and the
   **user id**.
3. **Caveat:** Meta's docs list the resumable local-file upload as *Facebook-Login only*. If container
   creation or upload fails with Option B, switch to Option A.

## 5. Fill in `.env`

```
IG_USER_ID=17841400000000000
IG_ACCESS_TOKEN=EAAG...long-lived token...
# optional
# IG_API_VERSION=v26.0
# IG_GRAPH_HOST=graph.facebook.com
```

`.env` is in `.gitignore`. Never commit or share the token. The code sends it only in the `Authorization`
header and scrubs it from error messages.

Check it:

```
python src/instagram.py --check      # prints "credentials OK for @yourhandle"
```

## 6. Post

```
python make_reel.py --post                 # make + QA + publish one reel
python src/instagram.py output/<run_id>.mp4 --caption-file output/<run_id>.txt   # publish an existing reel
```

A reel is posted only if the automated QA (`src/qa.py`) passes.

## How the upload works (for reference)

1. `POST /{ig-user-id}/media` with `media_type=REELS`, `upload_type=resumable`, `caption`, and
   `share_to_feed=true`. This returns `{id, uri}`.
2. `POST https://rupload.facebook.com/ig-api-upload/v26.0/{container-id}` with headers
   `Authorization: OAuth <token>`, `offset: 0`, `file_size: <bytes>`, and the MP4 bytes as the body. If the
   upload is interrupted, the code resumes from `video_status.uploading_phase.bytes_transferred`.
3. Poll `GET /{container-id}?fields=status_code,status` until it shows `FINISHED`. `ERROR` or `EXPIRED`
   aborts.
4. `POST /{ig-user-id}/media_publish` with `creation_id=<container-id>`. This returns the media id, which
   is saved in `history.json`.

## Limits and maintenance

- About **100 API-published posts per rolling 24 h** per account. Check usage with
  `GET /{ig-user-id}/content_publishing_limit`.
- A container that isn't published within 24 h expires.
- Reels spec (Meta reference): MP4/MOV with the **moov atom at the front**, H.264/HEVC 4:2:0, 23-60 fps,
  max **1920 px wide**, video bitrate up to **25 Mbps**, AAC up to 48 kHz, 3 s to 15 min, up to 300 MB. Our
  1440x2560 60 fps H.264/AAC 30 s file fits these limits. `src/qa.py` checks each limit and losslessly remuxes
  the file with `+faststart` if it needs to.
- **Long-lived tokens expire after ~60 days.** Refresh before then:
  - Option A: repeat the `fb_exchange_token` call with a fresh token. You can also use a System User token
    from Business Manager, which never expires.
  - Option B: `GET https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=<token>`
- Docs: <https://developers.facebook.com/docs/instagram-platform/content-publishing> and
  <https://developers.facebook.com/docs/instagram-platform/content-publishing/resumable-uploads>
