# Social Publisher — Multi-Platform Publishing Module (Python + Flask + SQLite)

A responsive web module with a rich text editor for creating promotional messages, festival wishes, and announcements, previewing them per network, and publishing simultaneously to **Instagram**, **Facebook**, **Google Business Profile (GMB)**, and **LinkedIn** with individual delivery status tracking and persistent SQLite history.

## Features

1. **Rich Text Editor & Composer**:
   - Formatting toolbar (headings, bold, italic, underline, strikethrough, ordered/bulleted lists, blockquotes, links, clear formatting) powered by Quill.
   - Database-backed quick-start templates (**Promotional**, **Festival Wishes**, **Announcement**, **General**) plus custom **Save as Template** and **Save Draft**.
   - Categorized emoji picker, hashtag packs + custom hashtag adder, link inserter, and optional Google Business Profile Call-to-Action (`LEARN_MORE`, `SHOP`, `ORDER`, `BOOK`, `SIGN_UP`).
   - Drag-and-drop image upload (`JPG`, `PNG`, `WebP` up to `8 MB`) with preview.
2. **Multi-Platform Selection & Live Previews**:
   - Select any combination of **Instagram**, **Facebook**, **Google Business Profile**, and **LinkedIn**.
   - Per-platform character meters, hashtag/image validation, and realistic platform preview cards before publishing.
3. **Simultaneous Publishing & Individual Status**:
   - `POST /api/publish` dispatches across all selected platforms concurrently via `ThreadPoolExecutor` and reports individual **Success** / **Failed** status, external post IDs, links, and error messages.
   - Failed deliveries can be retried individually or together.
4. **SQLite Database & Settings**:
   - Uses Python's built-in `sqlite3` (`server/data.db`) with `posts`, `results`, `templates`, and `settings` tables.
   - Searchable and filterable publishing history + saved drafts, and an in-app **Official API Configuration** modal backed by SQLite `settings`.

## Quick Start

Requires **Python 3.10+** (tested on Python 3.13.5).

```bash
pip install -r requirements.txt
cp .env.example .env      # Windows: copy .env.example .env
python app.py             # Open http://localhost:3000
```

By default, `PUBLISH_MODE=sandbox` simulates publishing so you can test all flows immediately (including partial failures and retries).

## Official API Integration (`PUBLISH_MODE=live`)

Set `PUBLISH_MODE=live` either in `.env` or directly in the UI's **Sandbox / Live Mode** configuration modal, and provide credentials for the platforms you want to publish to:

- **Facebook Page (`META_PAGE_ID`, `META_PAGE_TOKEN`)**: Meta Graph API `v21.0` (`/feed` and `/photos`, supporting both public URLs and direct multipart upload).
- **Instagram Business (`META_IG_USER_ID`, `META_PAGE_TOKEN`)**: Meta Graph API `v21.0` two-step media container (`/media`, status polling, `/media_publish`) — requires a publicly accessible `PUBLIC_BASE_URL` and an attached image.
- **LinkedIn (`LINKEDIN_TOKEN`, `LINKEDIN_AUTHOR_URN`, `LINKEDIN_VERSION`)**: `/rest/images?action=initializeUpload` and `/rest/posts`.
- **Google Business Profile (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `GMB_ACCOUNT_ID`, `GMB_LOCATION_ID`)**: OAuth2 refresh token exchange and `localPosts` creation (with optional `callToAction` and photo media).

## Running Tests

```bash
python -m pytest -v
```

## Project Structure

- `app.py` — Flask application entrypoint (`python app.py`)
- `server/app.py` — Flask routes (`/api/health`, `/api/config`, `/api/templates`, `/api/drafts`, `/api/upload`, `/api/publish`, `/api/posts/<id>/retry`, `/api/posts`, `DELETE /api/posts/<id>`)
- `server/publishers.py` — HTML-to-text converter, metadata extraction, validation, official API adapters, and sandbox adapter
- `server/db.py` — SQLite schema, migrations & seeded templates (`posts`, `results`, `settings`, `templates`)
- `public/index.html`, `public/styles.css`, `public/app.js` — Responsive frontend UI
- `tests/test_app.py` — Automated Python unit & Flask API integration tests
