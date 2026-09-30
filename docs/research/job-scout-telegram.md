# Job Scout: Telegram research

Research date: 2026-09-29. Sources: Telegram's Bot API docs (Bot API 10.3, dated August 24, 2026), Bot Features, Bots FAQ, Bots intro and Mini Apps docs on core.telegram.org; n8n docs fetched as `.md` on 2026-09-29; n8n source at tag `n8n@2.41.3` (`packages/nodes-base/nodes/Telegram/`, `packages/nodes-base/utils/sendAndWait/`, `packages/core/src/utils/hitl-callback-reference.ts`, `packages/cli/src/webhooks/`). No bot, credential or workflow was created.

**Labels.** **[Doc]** means a primary doc states it. **[Source]** means I read it in n8n's source at `n8n@2.41.3`. **[Observed]** means I saw it live. **[Inference]** means my own reasoning, not verified. **[Opinion]** means judgment only. **[Unverified]** means I found no primary source.

This builds on `job-scout-build.md` section 2.3 (shared Send-and-Wait implementation, Form Trigger with prefilled query params, link prefetchers). It doesn't repeat that material.

---

## 1. Summary and recommendation

- **New since the build doc: Telegram Send-and-Wait has native one-tap approval.** At 2.41.3 the Approval response type has an "Approve Within Chat" toggle. It sends callback buttons instead of link buttons, records who tapped, and edits the message afterward [Source: `Telegram/hitl/*`; Doc: Telegram message operations]. Free Text and Custom Form still open a browser page [Source].
- **The daily ping needs no Telegram Trigger.** Sending messages with URL buttons needs only the credential and a chat ID. Add a Trigger only for commands such as `/scan` or for custom callback buttons [Inference].
- **Chat ID: capture it once with `getUpdates`, before any webhook exists.** Send `/start` to the bot, then call `getUpdates` from a terminal and read `message.chat.id`. Store it in a Job Scout config Data Table row, not in the node and not in the repo [Opinion; reasons in section 3].
- **Digest shape: one header message, then one message per lead** with two URL buttons, "Open posting" and "Pass". Cap the count, for example the top 10 by score. Each message stays far below 4096 characters, and the n8n node's fixed keyboard UI works per item [Opinion; limits in sections 5 and 6].
- **Pass reason: keep the build doc's recommendation.** The "Pass" URL button opens an n8n Form Trigger with `lead_id` prefilled. It needs no Trigger, leaves no waiting executions, and a GET only renders the form, so prefetchers can't submit it [Inference]. Add a signed token to the link so a guessed URL can't record a pass [Opinion].
- **Use Send-and-Wait with "Approve Within Chat"** for one-decision prompts such as the feedback loop's "Apply to brief / Dismiss" [Opinion].
- **A Telegram Mini App that opens the board inside Telegram is a later upgrade, not MVP.** It needs an HTTPS page and server-side `initData` validation [Doc: Mini Apps].
- **Use two bots, one for testing and one for production.** n8n's docs suggest this because Telegram allows one webhook per bot [Doc: Telegram Trigger common issues].

---

## 2. Bot setup with BotFather

- **Create:** send `/newbot` to @BotFather and give a name and a username [Doc: features#creating-a-new-bot].
  - The username is 5–32 characters: Latin letters, digits and underscores only, and not case sensitive. It must end in `bot` and can't be changed later [Doc].
  - The name can be changed with `/setname` [Doc].
- **Token format:** `<bot_id>:<secret>`, for example `123456789:AA...` (Telegram's docs show a full sample) [Doc]. Requests go to `https://api.telegram.org/bot<token>/METHOD_NAME` [Doc: Bot API "Making requests"].
  - "Keep your token secure ... it can be used by anyone to control your bot" [Doc].
  - The numeric prefix is the bot ID. n8n treats it as non-secret: it derives its approval webhook secret from it [Source: `hitl/tokens.ts`].
- **Rotate:** "If your existing token is compromised or you lost it for some reason, use the /token command to generate a new one" [Doc]. The features page no longer lists `/revoke`, and doesn't state that the old token stops working [Unverified]. After rotating, update the n8n credential.
- **Description and about text** [Doc]:
  - `/setdescription`: up to 512 characters, shown under "What can this bot do?" before the user starts the bot.
  - `/setabouttext`: up to 120 characters, shown on the profile.
  - `/setuserpic`: sets the profile picture.
- **Commands:** `/setcommands` sets the list users see when they type `/` and in the menu button [Doc]. Updates don't carry command scope and may contain commands that don't exist, so the backend must check them [Doc]. Commands only matter if Job Scout adds a Trigger.
- **Privacy mode** applies to groups only. Bots always receive "All messages from private chats" [Doc: features#privacy-mode; FAQ]. For a one-person private chat it doesn't matter. Leave it on (the default) [Opinion].
- **`/setjoingroups`:** can turn off adding the bot to groups [Doc]. Turning it off fits a private, one-user bot [Opinion].
- **The bot can't message Rahat first.** "Bots can't start conversations with users. A user must either add them to a group or send them a message first" [Doc: bots intro]. Users see a Start button the first time they open the bot chat [Doc].

---

## 3. Capturing the chat ID

**Options**
1. **`getUpdates` after `/start`.** Open `t.me/<bot_username>`, tap Start, then run `curl -s https://api.telegram.org/bot<TOKEN>/getUpdates` and read `result[].message.chat.id`.
   - Telegram keeps updates for at most 24 hours [Doc].
   - This fails while a webhook is set: "This method will not work if an outgoing webhook is set up" [Doc: getUpdates]. `deleteWebhook` switches back [Doc].
   - **[Opinion]** Use a terminal, not a browser address bar. The token ends up in browser history.
2. **A Telegram Trigger that logs `message.chat.id`.** This is n8n's documented way [Doc: Telegram common issues "Get the Chat ID"].
   - On activation, Trigger v1.3+ sets `drop_pending_updates: true` [Source]. Send `/start` after the trigger is listening, not before.
   - Activating the Trigger claims the bot's single webhook (section 4).
3. **Third-party ID bots.** The n8n node's Chat ID hint says "ask @get_id_bot", and n8n's docs mention @RawDataBot for groups [Source; Doc]. **[Opinion]** Skip these. They mean sharing account data with a bot that isn't Telegram's or n8n's, and option 1 is just as quick.

**Chat ID types**
- `Chat.type` is one of `private`, `group`, `supergroup` or `channel` [Doc].
- IDs can exceed 32 bits (up to 52 significant bits) [Doc]. Store the ID as a string, or as a 64-bit number [Inference].
- **[Inference]** A private chat's ID equals the user's ID and is positive. I found no Bot API sentence that states this.
- Group IDs are entered in n8n with a leading `-` [Doc: n8n common issues]. The `-100…` prefix for supergroups and channels is [Unverified] in the docs I read.
- `@channelusername` works only for public channels [Doc].

**Where to store it**
- **The Telegram credential can't hold it.** Its only fields are Access Token and Base URL [Source: `TelegramApi.credentials.ts`].
- **n8n custom Variables aren't an option.** They require Cloud Pro/Enterprise or self-hosted Business/Enterprise [Doc: define-custom-variables].
- **Recommendation:** a row in the Job Scout config Data Table, with a key like `telegram_chat_id`. Nodes read it with a Data Table node. **[Inference]** This keeps it out of exported workflow JSON and the template, which matches the status doc's plan to hold rules and config in Data Tables.

---

## 4. n8n credential and Telegram Trigger

**Credential** [Source: `TelegramApi.credentials.ts`; Doc: credentials/telegram]
- Access Token (a password field, required) and Base URL (default `https://api.telegram.org`, for a self-hosted Bot API server).
- The credential test calls `getMe`.

**Trigger webhook model**
- On activation, the Trigger calls `setWebhook` with its URL, `allowed_updates` and `secret_token` = `<workflowId>_<nodeId>`. Deactivating calls `deleteWebhook` [Source].
- Versions after 1 reject requests whose `X-Telegram-Bot-Api-Secret-Token` header doesn't match (403) [Source].
- The default Trigger version is 1.5 [Source].
- The node shows: "you can use just one Telegram trigger for each bot at a time" [Source].
- **One webhook per bot.** "Every time you switch from using the testing URL to the production URL (and vice versa), Telegram overwrites the registered webhook URL" [Doc: Trigger common issues]. The fixes are to unpublish while testing, or to use a separate test bot [Doc].
- **[Inference]** Ending a test run calls `deleteWebhook`, which clears whatever URL is set. Re-publish the production workflow after testing on the same bot.
- **Telegram's requirements** [Doc: setWebhook, FAQ]:
  - An HTTPS URL on port 443, 80, 88 or 8443.
  - No redirects. The certificate CN must match the domain, and wildcard certificates "may not be supported".
  - Self-signed certificates must be uploaded as an InputFile via `certificate`. n8n's Trigger doesn't send `certificate` [Source]. So Coolify needs a real certificate, for example Let's Encrypt via its proxy [Inference].
  - Failed deliveries (non-2xx) are retried "a reasonable amount of attempts" [Doc].
- **Behind a proxy,** set the public HTTPS webhook URL env var, or Telegram rejects it with "An HTTPS URL must be provided for webhook" [Doc: Trigger common issues]. That page still says `WEBHOOK_URL`, but the build doc (2.3) notes `N8N_WEBHOOK_URL` replaces it as of 2.35.0.
- **Doc vs source:** the Trigger doc lists about 25 event types (business, reactions, chat member …). The 2.41.3 node offers `*` plus 9 types: message, edited_message, channel_post, edited_channel_post, callback_query, inline_query, poll, pre_checkout_query, shipping_query [Source]. Trust the editor.

**Trigger and "Approve Within Chat" share the webhook** [Source: `hitl/setup.ts`, `TelegramTrigger.node.ts`]
- With no Trigger, Send-and-Wait registers `https://<host>/webhook-waiting-telegram` with `allowed_updates: ['callback_query']`.
- With an active production Trigger (v1.5), the Trigger subscribes to `callback_query` and forwards taps whose data starts with `nhitl1|` to that endpoint.
- If the webhook points anywhere else, the node throws "already claimed by another system".
- **[Inference]** The same-instance check matches only `/webhook/` paths. So while a Trigger is being tested on its `/webhook-test/` URL, an in-chat approval on the same bot fails. This is another reason to use a test bot.
- Once either one sets a webhook, `getUpdates` stops working [Doc]. Capture the chat ID first.

**Does Job Scout need a Trigger?**
- **No, for MVP [Inference].** The digest, URL buttons, Form links and Send-and-Wait (including in-chat approval) all work without one.
- Add one only for:
  - commands such as `/scan`, `/digest` or `/pause`
  - custom `callback_data` buttons outside Send-and-Wait
  - free-text replies such as "reply with a reason" via ForceReply
- If added, set "Restrict to User IDs" to Rahat's ID [Source; Doc].

---

## 5. Message formatting limits

**Telegram limits** [Doc: Bot API]
- `sendMessage` text: 1–4096 characters after entity parsing.
- Media captions: 0–1024 characters.
- `answerCallbackQuery` text: 0–200 characters.
- **Rich messages (Bot API 10.1, June 2026):** up to 32768 UTF-8 characters, 500 blocks, 16 nesting levels, 50 media and 20 table columns. They support `reply_markup`.
- **Parse modes:** `HTML`, `MarkdownV2`, and legacy `Markdown` ("retained for backward compatibility").
- **MarkdownV2 escaping** [Doc]:
  - Outside entities, escape `` _ * [ ] ( ) ~ ` > # + - = | { } . ! `` with `\`.
  - Inside `pre` and `code`, escape `` ` `` and `\`.
  - Inside a link's `(...)`, escape `)` and `\`.
  - Any character with code 1–126 may be escaped.
- **Legacy Markdown:** escape `` _ * ` [ `` outside entities, and entities can't nest [Doc].
- **HTML tags allowed** [Doc]:
  - `b`/`strong`, `i`/`em`, `u`/`ins`, `s`/`strike`/`del`
  - `span class="tg-spoiler"` and `tg-spoiler`
  - `a href`, `tg-emoji`, `tg-time`
  - `code`, `pre` (with `code class="language-…"`), `blockquote` (optionally `expandable`)
  - Escape `<`, `>` and `&`. The only named entities are `&lt; &gt; &amp; &quot;`.
- **[Opinion]** Use HTML for the digest. Job titles and company names rarely contain `<>&`, while MarkdownV2 needs escaping of `.`, `-` and `(`, which appear constantly.
- **Link previews:** `link_preview_options` (`is_disabled`, `url`, `prefer_small_media`, `show_above_text` …). Without `url`, "the first URL found in the message text" is used [Doc]. Bot API 7.0 "replaced the parameter disable_web_page_preview with link_preview_options" [Doc: changelog].
- **Inline links:** "Telegram clients will display an alert to the user before opening an inline link ('Open this link?' ...)" [Doc].
- **Inline keyboards** [Doc: InlineKeyboardButton]:
  - Each button has exactly one action: `url` (HTTP or `tg://`), `callback_data` (1–64 bytes), `web_app` (private chats only), `login_url` (HTTPS, needs `/setdomain`), `switch_inline_query*`, `copy_text` (1–256 characters), `callback_game`, `pay` or `disabled`.
  - An optional `style` of `danger`, `success` or `primary` colors the button.
  - The maximum number of buttons per message isn't stated in the Bot API docs [Unverified].
- **Callback queries:** clients show a progress bar until the bot calls `answerCallbackQuery` [Doc].
- **Rate limits** [Doc: FAQ]:
  - Avoid more than 1 message per second in one chat. Short bursts are allowed, then 429 errors follow.
  - 20 messages per minute in a group.
  - About 30 messages per second for bulk sends.

**What the n8n Telegram node (v1.2) exposes** [Source; Doc: message operations]
- **Operations** include Send Message, Edit Message Text, Send and Wait for Response, and Answer Query.
  - **New:** Send Rich Message and Send Rich Message Draft, with HTML or Markdown content and reply markup [Source]. The n8n docs page doesn't list them yet [Doc].
- **Parse Mode** (Markdown Legacy, MarkdownV2, HTML): the field shows HTML as its default, and the docs say HTML is the default [Doc]. **But if the field isn't added, Send Message sends `parse_mode: 'Markdown'` (legacy)** [Source: `GenericFunctions.addAdditionalFields`]. Always add Parse Mode explicitly [Opinion].
- **Append n8n Attribution** defaults to on for node version 1.1+ [Source; Doc].
  - It adds "This message was sent automatically with n8n" plus a link.
  - It's appended only for Markdown and HTML parse modes, not MarkdownV2 [Source].
  - Send Rich Message doesn't append it [Source].
- **Disable WebPage Preview:** the docs say it sets `link_preview_options.is_disabled` [Doc]. The source sends the legacy `disable_web_page_preview` field instead, and on v1.2 defaults it to `true` [Source].
  - **[Unverified]** Whether Telegram still honors the removed field. Current docs don't list it.
  - For full control, send `link_preview_options` through an HTTP Request node [Inference].
- **Reply Markup:** None, Inline Keyboard, Reply Keyboard, Reply Keyboard Remove, Force Reply [Source].
  - Inline button fields: `callback_data`, `url`, `web_app`, `switch_inline_query`, `switch_inline_query_current_chat`, `pay`. There's no `login_url`, `copy_text` or `style` [Source].
  - The keyboard is a fixed collection of rows and buttons. Button values accept expressions, but the number of buttons is fixed in the UI [Source]. **[Inference]** A variable number of buttons per message means an HTTP Request node with a JSON `reply_markup` built in a Code node.
- **Rate limiting:** the node has no built-in throttle. n8n's docs suggest Loop Over Items plus a wait [Doc].

---

## 6. Digest design

- **Fitting N leads in one 4096-character message [Inference]:**
  - At about 250–350 characters per lead (title, company, score, pay, location, link), one message holds about 10–15 leads. Beyond that, split into several messages or cap the list.
  - Rich messages raise the ceiling to 32768 characters and allow tables [Doc]. They are new (June 2026). Rendering on older Telegram clients is [Unverified].
- **Option A: one digest message.** List the leads with inline HTML links to the posting and a Pass form link each.
  - Pros: one notification. Short and quiet.
  - Cons: tapping a text link shows "Open this link?" [Doc]. Per-lead buttons need a dynamic keyboard (HTTP Request node). A keyboard with many buttons on one message is awkward on a phone [Opinion].
- **Option B: a header message plus one message per lead** with URL buttons `[Open posting] [Pass]` (recommended).
  - Pros: fits the n8n node as is, one item per message, with button URLs from expressions. Each lead is self-contained, and the Pass button can later be edited to "Passed ✓" [Inference].
  - Cons: N notifications. Mitigate with Disable Notification on the per-lead messages [Doc] and a cap.
  - Send at ≤1 message per second [Doc: FAQ], using Loop Over Items plus a 1 s Wait [Doc].
- **URL buttons vs callback buttons for Pass:**
  - A URL button to an n8n Form Trigger needs no Trigger, no webhook ownership and no long-lived execution. Each tap is a new short execution [Inference, building on build doc 2.3].
  - A `callback_data` button (for example `pass|<lead_id>`, which must fit 64 bytes) needs a Telegram Trigger subscribed to `callback_query`. It must call `answerCallbackQuery` [Doc], and it can't collect a free-text reason without a second step, such as ForceReply and reading the reply [Inference].
  - The upside of callback buttons: the tap stays in the chat and Telegram vouches for who tapped.
  - **[Opinion]** The Form link wins for "pass with a reason". Callback buttons suit reasonless one-tap actions such as "Snooze".

---

## 7. Send and Wait on Telegram: what is actually sent

**Link mode (the default, and the only mode for Free Text and Custom Form)** [Source: `GenericFunctions.createSendAndWaitMessageBody`, `utils/sendAndWait/utils.ts`]
- One `sendMessage` call with:
  - `parse_mode: 'Markdown'` (legacy, fixed)
  - `disable_web_page_preview: true`
  - the attribution appended unless turned off
  - `reply_markup.inline_keyboard` holding **one row of URL buttons**
- **The button URLs are signed n8n resume URLs,** `https://<host>/webhook-waiting/<executionId>/<nodeId>` with `approved=true|false` and an HMAC `signature` query parameter. A bad signature renders "Invalid Form Link — This form link is invalid or has expired" (401) [Source: `cli/webhooks/waiting-webhooks.ts`].
- **Buttons per response type:**

  | Response type | Buttons | Labels |
  |---|---|---|
  | Approval | one button, or Decline + Approve | default `✅ Approve` / `❌ Decline` |
  | Free Text | one button | default `Respond` |
  | Custom Form | one button | default `Respond` |

  The Free Text and Custom Form buttons open an n8n-hosted form (the form-trigger template) [Source].
- **Only the first input item is used.** The node reads parameters at index 0, sends one message and puts the whole execution to wait [Source]. **[Inference]** One Send-and-Wait per lead therefore needs one execution per lead, for example a sub-workflow call per lead. That is the "N waiting executions" cost the build doc warns about.
- **The Message field is sent as legacy Markdown.** **[Inference]** An unmatched `_` or `*` in a job title or URL can make Telegram reject the message ("can't parse entities"). Escape `` _ * ` [ `` [Doc].
- **After submit:** a page reading "Got it, thanks / This page can be closed now" [Source: `ACTION_RECORDED_PAGE`, form `formSubmittedHeader`].
- **Tapping again after the execution finished:** a "No action required" page [Source].
  - If the execution is still running: 409 "is running already".
  - If it ended with an error: 409 [Source].
- **Limit Wait Time:** if the option is added, its default is 45 minutes. It can be an interval in minutes, hours or days, or a date. Without it, the wait is indefinite [Source: `descriptions.ts`, `configureWaitTillDate.util.ts`]. The output shape after a timeout is [Unverified]. Check it in the editor.
- **Prefetch protection:** for Approval, GETs from bot user agents (`isbot`) or Microsoft preview services get an empty 200 and don't resume [Source]. Free Text and Custom Form GETs only render the form. Submission is a POST [Source].
- **Telegram link previews:** previews come from "the first URL found in the message text" [Doc]. n8n puts the URLs in buttons and turns previews off. **[Unverified]** that Telegram never fetches button URLs. No doc says either way. **[Inference]** The risk is low given the protections above.
- **Phone behavior [Unverified]:** Telegram's docs don't say whether a URL button opens in Telegram's in-app browser or the system browser. The docs mention an in-app browser only for games, and say the Mini App `openLink` method opens "an external browser" [Doc]. Test on Rahat's phone.

**"Approve Within Chat" (Approval only)** [Source: `Telegram/hitl/*`, `core/.../hitl-callback-reference.ts`; Doc: message operations]
- **Requirements:** public HTTPS on port 443, 80, 88 or 8443. Otherwise the node logs a warning and falls back to link buttons [Source; Doc].
- **What Telegram receives:** buttons with `callback_data` = `nhitl1|<executionId>|a|d|<32-hex HMAC>` (checked to be ≤64 bytes) [Source].
- **Handling a tap:**
  - The tap posts to `/webhook-waiting-telegram`, which checks the webhook secret header and the HMAC.
  - It checks the optional approver ID list. Unauthorized users get an alert popup.
  - It calls `answerCallbackQuery`.
- **After a decision:** the default "Show Outcome and Remove Buttons" edits the message to add "✅ Approved by <name>" or "🚫 Declined by <name>" [Source].
- **Output:** `approved`, `responder {id, username, name}`, `chatId`, `messageId`, `respondedAt` [Source].
- **Late or repeated taps** get a 409 without `answerCallbackQuery` [Source]. **[Inference]** The phone shows a spinner until it times out, and Telegram may retry the non-2xx delivery [Doc: setWebhook]. With the default setting, buttons are removed after the first decision, so repeats are unlikely.

---

## 8. Pass-reason flow on a phone: three options

| | Send-and-Wait Custom Form per lead | URL button → Form Trigger `?lead_id=` | Mini App opening the board |
|---|---|---|---|
| Trigger needed | No | No | No for inline `web_app` buttons; BotFather menu button optional |
| Executions | One waiting execution per lead [Source] | One short execution per submission [Inference] | Depends on the board API |
| Link auth | HMAC-signed resume URL [Source] | None by default. Basic Auth or n8n User Auth optional [Doc: Form Trigger]; add a signed token [Opinion] | Telegram-signed `initData`, validated server side [Doc] |
| Prefill | Form built from node fields | Query params, production only; Hidden Field for `lead_id` [Doc] | Full app state |
| Opens | Browser page [Source]; which browser is [Unverified] | Browser page; which browser is [Unverified] | Inside Telegram [Doc] |
| Build cost | Low, but a scan run fans out into N waits | Low | Highest: HTML, JS, auth, API |

**Mini Apps** [Doc: core.telegram.org/bots/webapps]
- **What they are:** JavaScript web apps that "can be launched right inside Telegram". A page loads `https://telegram.org/js/telegram-web-app.js` in `<head>`.
- **Launch points:** a `web_app` inline button (private chats only), a keyboard button, the bot's menu button (`/setmenubutton` in BotFather), a Main Mini App, or a direct link `t.me/<bot>/<app>?startapp=<param>`.
- **URL:** `WebAppInfo.url` must be HTTPS [Doc: Bot API].
- **`initData`:** a query string with user info and `auth_date`. `initDataUnsafe` "should not be trusted". The server validates `hash` against `HMAC_SHA256(data_check_string, HMAC_SHA256(<bot_token>, "WebAppData"))`, and should check `auth_date` for staleness. An Ed25519 `signature` field allows third-party validation without the token.
- **Can n8n serve one? [Inference]** Yes, in principle:
  - A Webhook node plus Respond to Webhook can return the board HTML over the instance's HTTPS host (open research item 2 in `status.md`).
  - A second webhook can take `initData` and validate it in a Code node with `crypto`. On self-hosted n8n that needs `NODE_FUNCTION_ALLOW_BUILTIN=crypto` [Doc: task runners env vars; Code node].
  - The Telegram node can already send a `web_app` inline button [Source].
- **[Opinion]** Start with the Form Trigger link. It is the smallest working piece and needs no board. The Mini App fits later, once the board exists, as "Open board" in the header message or the menu button. It shows well in a demo, but it adds token-derived HMAC validation and CSP and framing checks inside Telegram, which are [Unverified].

---

## Setup checklist (for later, not now)

1. Create the production bot with `/newbot`. Set `/setdescription`, `/setabouttext` and `/setuserpic`. Consider `/setjoingroups` off.
2. Create a second bot for testing.
3. From Rahat's phone, open each bot and tap Start.
4. Before any webhook exists, run `getUpdates` in a terminal and record `message.chat.id`. Put it in the config Data Table row, never in the repo.
5. In n8n, add a Telegram credential per bot (token only, default Base URL). Confirm the credential test (`getMe`) passes.
6. Confirm Coolify serves n8n on 443 with a real certificate, and that the webhook URL env var is set to the public HTTPS URL.
7. Build the digest sender: HTML parse mode set explicitly, attribution decided, Disable Notification on per-lead messages, a 1 s pacing wait.
8. Only if commands are wanted: add a Telegram Trigger restricted to Rahat's user ID, and `/setcommands`.

---

## Open questions for Rahat

1. **Digest shape:** one message per lead (recommended), or one combined digest? What's the cap per day, and what send time and timezone?
2. **Notifications:** should per-lead messages be silent, with only the header ringing?
3. **Commands:** do you want `/scan` or other commands from the phone? That's the only reason to add a Telegram Trigger now.
4. **Pass link protection:** is an unguessable signed link enough, or do you want a Basic Auth prompt on the phone?
5. **Attribution:** keep "sent automatically with n8n" on messages? It could suit the n8n application, or it could be noise.
6. **Bot identity:** the bot's display name and username. The username can't be changed later.
7. **Mini App:** is opening the board inside Telegram in scope for the demo, or later?

---

## Sources

**Telegram**
- Bot API (10.3): https://core.telegram.org/bots/api
  - getUpdates: https://core.telegram.org/bots/api#getupdates
  - setWebhook: https://core.telegram.org/bots/api#setwebhook
  - sendMessage: https://core.telegram.org/bots/api#sendmessage
  - Formatting options: https://core.telegram.org/bots/api#formatting-options
  - LinkPreviewOptions: https://core.telegram.org/bots/api#linkpreviewoptions
  - InlineKeyboardButton: https://core.telegram.org/bots/api#inlinekeyboardbutton
  - CallbackQuery / answerCallbackQuery: https://core.telegram.org/bots/api#callbackquery
  - Rich message limits: https://core.telegram.org/bots/api#rich-message-formatting-options
- Bot API changelog: https://core.telegram.org/bots/api-changelog
- Bot Features (BotFather, privacy mode, commands, deep linking): https://core.telegram.org/bots/features
- Bots FAQ (webhooks, limits): https://core.telegram.org/bots/faq
- Bots intro: https://core.telegram.org/bots
- Mini Apps: https://core.telegram.org/bots/webapps

**n8n docs**
- Telegram node: https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.telegram.md
- Message operations: https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.telegram/message-operations.md
- Telegram node common issues: https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.telegram/common-issues.md
- Telegram credentials: https://docs.n8n.io/integrations/builtin/credentials/telegram.md
- Telegram Trigger: https://docs.n8n.io/integrations/builtin/trigger-nodes/n8n-nodes-base.telegramtrigger.md
- Telegram Trigger common issues: https://docs.n8n.io/integrations/builtin/trigger-nodes/n8n-nodes-base.telegramtrigger/common-issues.md
- Form Trigger: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.formtrigger.md
- Custom variables: https://docs.n8n.io/build/code-in-n8n/define-custom-variables.md
- Code node: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.code.md
- Task runner env vars: https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/task-runners.md

**n8n source at `n8n@2.41.3`** (under https://github.com/n8n-io/n8n/blob/n8n@2.41.3/)
- `packages/nodes-base/credentials/TelegramApi.credentials.ts`
- `packages/nodes-base/nodes/Telegram/Telegram.node.ts`
- `packages/nodes-base/nodes/Telegram/GenericFunctions.ts`
- `packages/nodes-base/nodes/Telegram/TelegramTrigger.node.ts`
- `packages/nodes-base/nodes/Telegram/hitl/{descriptions,setup,tokens,webhook}.ts`
- `packages/nodes-base/utils/sendAndWait/{utils,descriptions,configureWaitTillDate.util,email-templates}.ts`
- `packages/core/src/utils/hitl-callback-reference.ts`
- `packages/cli/src/webhooks/{waiting-webhooks,hitl-interaction-webhooks,telegram-interaction-webhooks}.ts`
- `packages/cli/templates/{send-and-wait-no-action-required,form-invalid-token}.handlebars`
- `packages/@n8n/config/src/configs/endpoints.config.ts`
