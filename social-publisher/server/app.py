from concurrent.futures import ThreadPoolExecutor
import json
import os
import random
import string
import tempfile
import time
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

from .db import Database, get_default_db_path
from .publishers import (
    CONFIGURABLE_ENV_KEYS,
    GMB_CTA_TYPES,
    PLATFORMS,
    extract_metadata,
    get_platform_config,
    publish as default_publish,
    to_text,
    validate_post,
)

VALID_CATEGORIES = {'promotional', 'festival', 'announcement', 'general'}
ALLOWED_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}
ALLOWED_MIMES = {'image/jpeg', 'image/jpg', 'image/png', 'image/webp'}


def _safe_json_loads(raw, fallback):
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _serialize_post(conn, post_id: int):
    row = conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    if row is None:
        return None
    results = [
        dict(r)
        for r in conn.execute('SELECT * FROM results WHERE post_id = ? ORDER BY id ASC', (post_id,)).fetchall()
    ]
    data = dict(row)
    data['hashtags'] = _safe_json_loads(data.get('hashtags'), [])
    data['links'] = _safe_json_loads(data.get('links'), [])
    data['results'] = results
    return data


def _effective_env(db: Database, base_env: dict) -> dict:
    merged = dict(base_env)
    with db.connect() as conn:
        for row in conn.execute('SELECT key, value FROM settings').fetchall():
            if row['key'] in CONFIGURABLE_ENV_KEYS:
                merged[row['key']] = row['value']
    return merged


def create_app(options: dict | None = None) -> Flask:
    load_dotenv()
    opts = options or {}

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    public_dir = os.path.join(base_dir, 'public')
    default_upload_dir = (
        os.path.join(tempfile.gettempdir(), 'social_publisher_uploads')
        if os.environ.get('VERCEL')
        else os.path.join(os.path.dirname(__file__), 'uploads')
    )
    upload_dir = opts.get('upload_dir') or default_upload_dir
    db_path = opts.get('db_path') or get_default_db_path()
    base_env = dict(opts.get('env') if opts.get('env') is not None else os.environ)
    if os.environ.get('VERCEL') and not base_env.get('PUBLIC_BASE_URL'):
        vercel_host = os.environ.get('VERCEL_PROJECT_PRODUCTION_URL') or os.environ.get('VERCEL_URL')
        if vercel_host:
            base_env['PUBLIC_BASE_URL'] = f'https://{vercel_host}'
    publish_fn = opts.get('publish_fn') or default_publish

    os.makedirs(upload_dir, exist_ok=True)
    db = opts.get('db') or Database(db_path)

    app = Flask(__name__, static_folder=public_dir, static_url_path='')
    app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
    app.extensions['db'] = db

    def get_public_base(env: dict) -> str:
        return (env.get('PUBLIC_BASE_URL') or f"http://localhost:{env.get('PORT', '3000')}").rstrip('/')

    def run_one(post: dict, result: dict, env: dict, simulate_failures=None):
        errs = validate_post(
            result['platform'],
            text=post['text'],
            has_image=bool(post.get('image')),
            cta_url=post.get('cta_url') or '',
        )
        if errs:
            with db.connect() as conn:
                conn.execute(
                    'UPDATE results SET status = ?, external_id = NULL, url = NULL, error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    ('failed', ' '.join(errs), result['id']),
                )
            return

        try:
            image_file = post.get('image')
            res = publish_fn(
                result['platform'],
                {
                    'text': post['text'],
                    'html': post['html'],
                    'category': post['category'],
                    'cta_type': post.get('cta_type'),
                    'cta_url': post.get('cta_url'),
                    'image_file': image_file,
                    'image_url': f"{get_public_base(env)}/uploads/{image_file}" if image_file else None,
                    'upload_dir': upload_dir,
                    'simulate_failures': simulate_failures or [],
                },
                env,
            )
            with db.connect() as conn:
                conn.execute(
                    'UPDATE results SET status = ?, external_id = ?, url = ?, error = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    ('success', res.get('id'), res.get('url'), result['id']),
                )
        except Exception as exc:
            with db.connect() as conn:
                conn.execute(
                    'UPDATE results SET status = ?, external_id = NULL, url = NULL, error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    ('failed', str(exc) or 'Unknown publishing error', result['id']),
                )

    @app.errorhandler(413)
    def handle_file_too_large(_err):
        return jsonify({'error': 'Image exceeds the 8 MB upload limit.'}), 400

    @app.get('/')
    def index():
        return send_from_directory(public_dir, 'index.html')

    @app.get('/uploads/<path:filename>')
    def uploaded_file(filename):
        return send_from_directory(upload_dir, filename)

    @app.get('/api/health')
    def health():
        env = _effective_env(db, base_env)
        with db.connect() as conn:
            posts_count = conn.execute('SELECT COUNT(*) AS c FROM posts').fetchone()['c']
            results_count = conn.execute('SELECT COUNT(*) AS c FROM results').fetchone()['c']
            templates_count = conn.execute('SELECT COUNT(*) AS c FROM templates').fetchone()['c']
            settings_count = conn.execute('SELECT COUNT(*) AS c FROM settings').fetchone()['c']
        return jsonify({
            'ok': True,
            'database': 'connected',
            'driver': 'python-sqlite3',
            'mode': 'live' if env.get('PUBLISH_MODE') == 'live' else 'sandbox',
            'counts': {
                'posts': posts_count,
                'results': results_count,
                'templates': templates_count,
                'settings': settings_count,
            },
        })

    @app.get('/api/config')
    def get_config():
        env = _effective_env(db, base_env)
        return jsonify(get_platform_config(env))

    @app.put('/api/config')
    def update_config():
        body = request.get_json(silent=True) or {}
        with db.connect() as conn:
            if body.get('mode') in ('sandbox', 'live'):
                conn.execute(
                    """
                    INSERT INTO settings (key, value, updated_at) VALUES ('PUBLISH_MODE', ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                    """,
                    (body['mode'],),
                )

            if isinstance(body.get('publicBaseUrl'), str):
                trimmed = body['publicBaseUrl'].strip()
                if trimmed:
                    conn.execute(
                        """
                        INSERT INTO settings (key, value, updated_at) VALUES ('PUBLIC_BASE_URL', ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                        """,
                        (trimmed,),
                    )
                else:
                    conn.execute("DELETE FROM settings WHERE key = 'PUBLIC_BASE_URL'")

            values = body.get('values')
            if isinstance(values, dict):
                for key in CONFIGURABLE_ENV_KEYS:
                    if key in ('PUBLISH_MODE', 'PUBLIC_BASE_URL') or key not in values:
                        continue
                    val = str(values[key] or '').strip()
                    if val:
                        conn.execute(
                            """
                            INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
                            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                            """,
                            (key, val),
                        )
                    elif body.get('clearEmpty'):
                        conn.execute('DELETE FROM settings WHERE key = ?', (key,))

        env = _effective_env(db, base_env)
        return jsonify(get_platform_config(env))

    @app.get('/api/templates')
    def list_templates():
        with db.connect() as conn:
            rows = [dict(r) for r in conn.execute('SELECT * FROM templates ORDER BY is_default DESC, id ASC').fetchall()]
        return jsonify(rows)

    @app.post('/api/templates')
    def create_template():
        body = request.get_json(silent=True) or {}
        name = str(body.get('name') or '').strip()
        html = body.get('html') or ''
        if not name:
            return jsonify({'error': 'Template name is required.'}), 400
        if not to_text(html):
            return jsonify({'error': 'Template content cannot be empty.'}), 400

        category = body.get('category') if body.get('category') in VALID_CATEGORIES else 'general'
        cta_type = body.get('ctaType') if body.get('ctaType') in GMB_CTA_TYPES else None
        cta_url = str(body.get('ctaUrl')).strip() if body.get('ctaUrl') else None

        with db.connect() as conn:
            cur = conn.execute(
                'INSERT INTO templates (name, category, html, cta_type, cta_url, is_default) VALUES (?, ?, ?, ?, ?, 0)',
                (name, category, html, cta_type, cta_url),
            )
            tpl = dict(conn.execute('SELECT * FROM templates WHERE id = ?', (cur.lastrowid,)).fetchone())
        return jsonify(tpl), 201

    @app.delete('/api/templates/<int:tpl_id>')
    def delete_template(tpl_id: int):
        with db.connect() as conn:
            tpl = conn.execute('SELECT * FROM templates WHERE id = ?', (tpl_id,)).fetchone()
            if tpl is None:
                return jsonify({'error': 'Template not found.'}), 404
            if tpl['is_default']:
                return jsonify({'error': 'Built-in templates cannot be deleted.'}), 400
            conn.execute('DELETE FROM templates WHERE id = ?', (tpl_id,))
        return jsonify({'deleted': True, 'id': tpl_id})

    @app.post('/api/upload')
    def upload_image():
        file = request.files.get('image')
        if not file or not file.filename:
            return jsonify({'error': 'Please select an image file to upload.'}), 400

        orig_name = secure_filename(file.filename) or 'image.jpg'
        ext = os.path.splitext(orig_name)[1].lower()
        if ext not in ALLOWED_EXTS or (file.mimetype and file.mimetype.lower() not in ALLOWED_MIMES):
            return jsonify({'error': 'Only JPG, PNG, or WebP images up to 8 MB are allowed.'}), 400

        rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        saved_name = f'{int(time.time() * 1000)}-{rand}{ext}'
        save_path = os.path.join(upload_dir, saved_name)
        file.save(save_path)
        size = os.path.getsize(save_path)

        return jsonify({
            'file': saved_name,
            'originalName': file.filename,
            'size': size,
            'mimetype': file.mimetype,
            'url': f'/uploads/{saved_name}',
        })

    @app.post('/api/drafts')
    def save_draft():
        body = request.get_json(silent=True) or {}
        draft_id = body.get('id')
        html = body.get('html') or ''
        image = os.path.basename(body['image']) if body.get('image') else None
        text = to_text(html)
        if not text and not image:
            return jsonify({'error': 'Write post content or attach an image before saving a draft.'}), 400

        category = body.get('category') if body.get('category') in VALID_CATEGORIES else 'general'
        cta_type = body.get('ctaType') if body.get('ctaType') in GMB_CTA_TYPES else None
        cta_url = str(body.get('ctaUrl')).strip() if body.get('ctaUrl') else None
        image_orig = body.get('imageOriginalName')
        meta = extract_metadata(html, text)

        with db.connect() as conn:
            if draft_id:
                existing = conn.execute(
                    "SELECT id FROM posts WHERE id = ? AND post_status = 'draft'",
                    (int(draft_id),),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE posts
                        SET category = ?, html = ?, text = ?, hashtags = ?, links = ?,
                            cta_type = ?, cta_url = ?, image = ?, image_original_name = ?
                        WHERE id = ?
                        """,
                        (
                            category,
                            html,
                            text,
                            json.dumps(meta['hashtags']),
                            json.dumps(meta['links']),
                            cta_type,
                            cta_url,
                            image,
                            image_orig,
                            int(draft_id),
                        ),
                    )
                    return jsonify(_serialize_post(conn, int(draft_id)))

            cur = conn.execute(
                """
                INSERT INTO posts (category, post_status, html, text, hashtags, links, cta_type, cta_url, image, image_original_name)
                VALUES (?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    category,
                    html,
                    text,
                    json.dumps(meta['hashtags']),
                    json.dumps(meta['links']),
                    cta_type,
                    cta_url,
                    image,
                    image_orig,
                ),
            )
            return jsonify(_serialize_post(conn, cur.lastrowid)), 201

    @app.post('/api/publish')
    def publish_post():
        body = request.get_json(silent=True) or {}
        raw_platforms = body.get('platforms') or []
        selected_platforms = []
        for p in raw_platforms:
            if p in PLATFORMS and p not in selected_platforms:
                selected_platforms.append(p)

        if not selected_platforms:
            return jsonify({'error': 'Select at least one platform to publish.'}), 400

        html = body.get('html') or ''
        image = os.path.basename(body['image']) if body.get('image') else None
        text = to_text(html)
        if not text and not image:
            return jsonify({'error': 'Write post content or attach an image before publishing.'}), 400

        if image and not os.path.exists(os.path.join(upload_dir, image)):
            return jsonify({'error': 'Uploaded image could not be found. Please re-upload.'}), 400

        category = body.get('category') if body.get('category') in VALID_CATEGORIES else 'general'
        cta_type = body.get('ctaType') if body.get('ctaType') in GMB_CTA_TYPES else None
        cta_url = str(body.get('ctaUrl')).strip() if body.get('ctaUrl') else None
        image_orig = body.get('imageOriginalName')
        draft_id = body.get('draftId')
        simulate_failures = body.get('simulateFailures') or []
        meta = extract_metadata(html, text)

        with db.connect() as conn:
            post_id = None
            if draft_id:
                existing = conn.execute(
                    "SELECT id FROM posts WHERE id = ? AND post_status = 'draft'",
                    (int(draft_id),),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE posts
                        SET category = ?, post_status = 'published', html = ?, text = ?, hashtags = ?, links = ?,
                            cta_type = ?, cta_url = ?, image = ?, image_original_name = ?, created_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (
                            category,
                            html,
                            text,
                            json.dumps(meta['hashtags']),
                            json.dumps(meta['links']),
                            cta_type,
                            cta_url,
                            image,
                            image_orig,
                            int(draft_id),
                        ),
                    )
                    post_id = int(draft_id)

            if post_id is None:
                cur = conn.execute(
                    """
                    INSERT INTO posts (category, post_status, html, text, hashtags, links, cta_type, cta_url, image, image_original_name)
                    VALUES (?, 'published', ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        category,
                        html,
                        text,
                        json.dumps(meta['hashtags']),
                        json.dumps(meta['links']),
                        cta_type,
                        cta_url,
                        image,
                        image_orig,
                    ),
                )
                post_id = cur.lastrowid

            for platform in selected_platforms:
                conn.execute(
                    "INSERT INTO results (post_id, platform, status) VALUES (?, ?, 'pending')",
                    (post_id, platform),
                )

            post = dict(conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone())
            pending_results = [
                dict(r) for r in conn.execute('SELECT * FROM results WHERE post_id = ?', (post_id,)).fetchall()
            ]

        env = _effective_env(db, base_env)
        with ThreadPoolExecutor(max_workers=len(pending_results)) as pool:
            futures = [pool.submit(run_one, post, res_row, env, simulate_failures) for res_row in pending_results]
            for f in futures:
                f.result()

        with db.connect() as conn:
            return jsonify(_serialize_post(conn, post_id))

    @app.post('/api/posts/<int:post_id>/retry')
    def retry_post(post_id: int):
        body = request.get_json(silent=True) or {}
        target_platform = body.get('platform') or request.args.get('platform')

        with db.connect() as conn:
            post_row = conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
            if post_row is None:
                return jsonify({'error': 'Post not found.'}), 404
            post = dict(post_row)

            failed_rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM results WHERE post_id = ? AND status = 'failed'",
                    (post_id,),
                ).fetchall()
            ]
            if target_platform:
                failed_rows = [r for r in failed_rows if r['platform'] == target_platform]

            if not failed_rows:
                return jsonify({'error': 'No failed platform deliveries to retry.'}), 400

            for r in failed_rows:
                conn.execute(
                    "UPDATE results SET status = 'pending', attempts = attempts + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (r['id'],),
                )

        env = _effective_env(db, base_env)
        with ThreadPoolExecutor(max_workers=len(failed_rows)) as pool:
            futures = [pool.submit(run_one, post, r, env) for r in failed_rows]
            for f in futures:
                f.result()

        with db.connect() as conn:
            return jsonify(_serialize_post(conn, post_id))

    @app.get('/api/posts')
    def list_posts():
        q = (request.args.get('q') or '').strip().lower()
        category = request.args.get('category') or ''
        platform = request.args.get('platform') or ''
        status = request.args.get('status') or ''
        post_status = request.args.get('postStatus') or 'published'

        with db.connect() as conn:
            if post_status == 'all':
                rows = conn.execute('SELECT id FROM posts ORDER BY id DESC LIMIT 200').fetchall()
            else:
                target = 'draft' if post_status == 'draft' else 'published'
                rows = conn.execute(
                    'SELECT id FROM posts WHERE post_status = ? ORDER BY id DESC LIMIT 200',
                    (target,),
                ).fetchall()
            posts = [_serialize_post(conn, r['id']) for r in rows]

        posts = [p for p in posts if p is not None]
        if category in VALID_CATEGORIES:
            posts = [p for p in posts if p['category'] == category]
        if platform in PLATFORMS:
            posts = [p for p in posts if any(r['platform'] == platform for r in p['results'])]
        if status in ('success', 'failed', 'pending'):
            posts = [p for p in posts if any(r['status'] == status for r in p['results'])]
        if q:
            posts = [
                p for p in posts
                if q in p['text'].lower() or any(q in h.lower() for h in p['hashtags'])
            ]

        return jsonify(posts)

    @app.delete('/api/posts/<int:post_id>')
    def delete_post(post_id: int):
        with db.connect() as conn:
            existing = conn.execute('SELECT id FROM posts WHERE id = ?', (post_id,)).fetchone()
            if existing is None:
                return jsonify({'error': 'Post not found.'}), 404
            conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
        return jsonify({'deleted': True, 'id': post_id})

    return app
