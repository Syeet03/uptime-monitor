# Uptime Monitor

A small Python monitor that checks your websites every 10 minutes and sends you a notification via [ntfy.sh](https://ntfy.sh) as soon as something changes. It runs for free on GitHub Actions, so you don't need your own server.

## What is checked?

| Check | When is it a problem? | Notification level |
|---|---|---|
| **Outage** | HTTP status code is not 200, or there is no response (timeout, connection error) | urgent |
| **Keyword** | the configured keyword does not appear on the page (case-insensitive) | high |
| **Slow** | response time above `slow_seconds` (default 3 s) | warning |
| **SSL certificate** | certificate expires within `ssl_warn_days` (default 14 days) or is invalid | warning |

You **only get a notification when the status changes**: one message when something goes wrong and one recovery message when it's fixed. An outage that lasts an hour therefore gives you two messages, not six per hour. Each check is tracked separately, so "slow" and "outage" are independent notifications.

## Files

| File | Purpose |
|---|---|
| `config.yaml` | sites and settings |
| `monitor.py` | the monitor |
| `state.json` | last known status (updated automatically, don't edit by hand) |
| `history.json` | daily uptime history per site (updated automatically) |
| `.github/workflows/monitor.yml` | GitHub Actions workflow |
| `tests/` | tests |

## Setup

### 1. Choose an ntfy topic

1. Install the ntfy app on your phone (Android/iOS) or open <https://ntfy.sh/app>.
2. Pick a **hard-to-guess topic name**, for example `uptime-x7k2q9-yourname`. On ntfy.sh, anyone who knows the name can read and send messages, so the topic name works like a password.
3. Subscribe to that topic in the app.

### 2. Store the topic as a secret

Because this repo is public, **don't** put the topic name in the code or in `config.yaml`. Store it as a GitHub secret instead:

1. In your repo, go to **Settings → Secrets and variables → Actions → New repository secret**.
2. Name: `NTFY_TOPIC`. Value: your topic name.

### 3. Give the workflow write access

Go to **Settings → Actions → General → Workflow permissions** and choose **Read and write permissions**. The workflow already requests `contents: write` itself, but an organisation or repository setting can override this. Write access is needed to commit `state.json` and `history.json` back to the repo.

### 4. Start

Push the files to GitHub. Then go to **Actions → Uptime-monitor → Run workflow** to start a run right away. After that it runs automatically every 10 minutes.

## Uptime history

Besides `state.json`, the monitor keeps `history.json`: for each site and each day, the number of checks and how many of them were successful (HTTP 200), for the last 90 days. You can use this to show something like "99.9% uptime over the last 30 days".

- Every run updates the history; in between, the Actions cache keeps the latest version.
- `history.json` is committed at most once an hour, so the repo doesn't fill up with commits. A manually started run (**Run workflow**) always commits it.
- A check that can't be determined (for example a network error on GitHub's side) is not counted.

## Adding a site

Add a block to `config.yaml`:

```yaml
sites:
  - name: My new site
    url: https://example.com
    keyword: Welcome         # optional
    slow_seconds: 5          # optional: overrides the default for this site only
```

Optional per-site settings: `keyword`, `timeout`, `slow_seconds`, `ssl_warn_days`, `failures_before_alert`.

**Note:** choose a keyword that is actually in the page's HTML. If the text only appears after JavaScript has loaded, the monitor won't find it and you'll get a false alert.

## Fewer false alarms

Set `failures_before_alert: 2` in `config.yaml`. A site then has to fail two checks in a row (about 10 minutes) before you get a notification, so a single short hiccup goes unnoticed. The default is 1 (alert immediately).

## Testing locally

You need Python 3.10 or newer.

```bash
pip install -r requirements.txt pytest
pytest                                 # tests for the alerting logic
python monitor.py                      # real check; without NTFY_TOPIC no notifications are sent
NTFY_TOPIC=my-test-topic python monitor.py   # with notifications (Windows PowerShell: $env:NTFY_TOPIC="my-test-topic")
```

Note: `python monitor.py` also writes `state.json` and `history.json`. Without `NTFY_TOPIC`, a problem status is not saved, so the notification is still sent on the next run that does have a topic. For a clean start, reset `state.json` to `{"sites": {}}` and `history.json` to `{"sites": {}}`.

## Good to know

- **Timing isn't exact.** GitHub sometimes starts scheduled workflows 5 to 15 minutes late, especially at busy times. "Every 10 minutes" is a target, not a guarantee.
- **Scheduled workflows can be disabled after 60 days without activity.** GitHub does this in repositories where nothing happens. The hourly `history.json` commits normally keep the repo active, but if notifications stop arriving, check under **Actions** whether the workflow is still enabled and turn it back on if needed.
- **`state.json` and `history.json` are public.** They only contain the site URLs, ok/problem status, daily check counts and timestamps, so no secrets. Anyone can, however, see when your sites had problems.
- **If sending a notification fails**, the status is not saved and the next run tries again.
- **If the monitor itself can't reach ntfy or GitHub**, you won't hear anything. For critical sites, a second, independent monitor is a good addition.
