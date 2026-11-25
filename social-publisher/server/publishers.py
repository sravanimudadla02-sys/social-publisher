import html as html_lib
import os
import random
import re
import time
from urllib.parse import quote, urlparse
import requests

PLATFORM_META = {
    'instagram': {
        'key': 'instagram',
        'name': 'Instagram',
        'maxChars': 2200,
        'maxHashtags': 30,
        'requiresImage': True,
        'requiredEnv': ['META_IG_USER_ID', 'META_PAGE_TOKEN'],
    },
    'facebook': {
        'key': 'facebook',
        'name': 'Facebook',
        'maxChars': 63206,
        'requiresImage': False,
        'requiredEnv': ['META_PAGE_ID', 'META_PAGE_TOKEN'],
    },
    'gmb': {
        'key': 'gmb',
        'name': 'Google Business Profile',
        'maxChars': 1500,
        'requiresImage': False,
        'requiredEnv': [
            'GOOGLE_CLIENT_ID',
            'GOOGLE_CLIENT_SECRET',
            'GOOGLE_REFRESH_TOKEN',
            'GMB_ACCOUNT_ID',
            'GMB_LOCATION_ID',
        ],
    },
    'linkedin': {
        'key': 'linkedin',
        'name': 'LinkedIn',
        'maxChars': 3000,
        'requiresImage': False,
        'requiredEnv': ['LINKEDIN_TOKEN', 'LINKEDIN_AUTHOR_URN'],
    },
}

PLATFORMS = list(PLATFORM_META.keys())
GMB_CTA_TYPES = ['LEARN_MORE', 'BOOK', 'ORDER', 'SHOP', 'SIGN_UP']

CONFIGURABLE_ENV_KEYS = [
    'PUBLISH_MODE',
    'PUBLIC_BASE_URL',
    'META_PAGE_ID',
    'META_PAGE_TOKEN',
    'META_IG_USER_ID',
    'LINKEDIN_TOKEN',
    'LINKEDIN_AUTHOR_URN',
    'LINKEDIN_VERSION',
    'GOOGLE_CLIENT_ID',
    'GOOGLE_CLIENT_SECRET',
    'GOOGLE_REFRESH_TOKEN',
    'GMB_ACCOUNT_ID',
    'GMB_LOCATION_ID',
]

SECRET_KEYS = {
    'META_PAGE_TOKEN',
    'LINKEDIN_TOKEN',
    'GOOGLE_CLIENT_SECRET',
    'GOOGLE_REFRESH_TOKEN',
}


def to_text(html_str: str = '') -> str:
    """Converts Quill rich-text HTML into clean plain text suitable for social APIs."""
    if not html_str:
        return ''
    out = str(html_str)

    def _ol_repl(match):
        inner = match.group(1)
        items = re.findall(r'<li[^>]*>([\s\S]*?)</li>', inner, flags=re.IGNORECASE)
        return '\n' + ''.join(f'{i}. {item.strip()}\n' for i, item in enumerate(items, 1))

    def _ul_repl(match):
        inner = match.group(1)
        items = re.findall(r'<li[^>]*>([\s\S]*?)</li>', inner, flags=re.IGNORECASE)
        return '\n' + ''.join(f'• {item.strip()}\n' for item in items)

    out = re.sub(r'<ol[^>]*>([\s\S]*?)</ol>', _ol_repl, out, flags=re.IGNORECASE)
    out = re.sub(r'<ul[^>]*>([\s\S]*?)</ul>', _ul_repl, out, flags=re.IGNORECASE)
    out = re.sub(r'<li[^>]*>', '• ', out, flags=re.IGNORECASE)
    out = re.sub(r'</li>', '\n', out, flags=re.IGNORECASE)
    out = re.sub(r'<blockquote[^>]*>([\s\S]*?)</blockquote>', lambda m: f"\n> {m.group(1).strip()}\n", out, flags=re.IGNORECASE)

    def _link_repl(match):
        href = match.group(1)
        raw_label = re.sub(r'<[^>]+>', '', match.group(2))
        label = html_lib.unescape(raw_label).strip()
        if not label or label == href or href in label:
            return href
        return f'{label} ({href})'

    out = re.sub(r'<a\s+[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', _link_repl, out, flags=re.IGNORECASE)
    out = re.sub(r'<br\s*/?>', '\n', out, flags=re.IGNORECASE)
    out = re.sub(r'</(p|div|h[1-6])>', '\n', out, flags=re.IGNORECASE)
    out = re.sub(r'<[^>]+>', '', out)

    out = html_lib.unescape(out).replace('\xa0', ' ').replace('\r\n', '\n')
    out = re.sub(r'[ \t]+\n', '\n', out)
    out = re.sub(r'\n{3,}', '\n\n', out)
    return out.strip()


def extract_metadata(html_str: str = '', text: str = '') -> dict:
    hashtags = []
    seen_tags = set()
    for match in re.finditer(r'(?:^|[\s(])(#[a-zA-Z0-9_\u00C0-\u024F\u0900-\u097F]+)', text or ''):
        tag = match.group(1).strip()
        if len(tag) > 1 and tag not in seen_tags:
            seen_tags.add(tag)
            hashtags.append(tag)

    links = []
    seen_links = set()
    for match in re.finditer(r'href="(https?://[^"]+)"', str(html_str or ''), flags=re.IGNORECASE):
        url = match.group(1)
        if url not in seen_links:
            seen_links.add(url)
            links.append(url)
    for match in re.finditer(r'https?://[^\s)<>"]+', text or '', flags=re.IGNORECASE):
        url = match.group(0).rstrip('.,;!?')
        if url not in seen_links:
            seen_links.add(url)
            links.append(url)

    return {'hashtags': hashtags, 'links': links}


def is_valid_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
    except Exception:
        return False


def is_public_url(url: str) -> bool:
    if not is_valid_http_url(url):
        return False
    host = (urlparse(url).hostname or '').lower()
    return host not in ('localhost', '127.0.0.1', '0.0.0.0', '::1')


def validate_post(platform: str, text: str = '', has_image: bool = False, cta_url: str = '') -> list[str]:
    meta = PLATFORM_META.get(platform)
    if not meta:
        return [f'Unsupported platform: {platform}']

    clean_text = (text or '').strip()
    errs = []
    if not clean_text and not has_image:
        errs.append('Post content cannot be empty.')
    if len(clean_text) > meta['maxChars']:
        errs.append(f"Text is {len(clean_text):,} chars; {meta['name']} allows max {meta['maxChars']:,}.")
    if meta['requiresImage'] and not has_image:
        errs.append('Instagram requires an image (JPG, PNG, or WebP).')
    if meta.get('maxHashtags'):
        tags = extract_metadata('', clean_text)['hashtags']
        if len(tags) > meta['maxHashtags']:
            errs.append(f"{meta['name']} allows max {meta['maxHashtags']} hashtags (found {len(tags)}).")
    if platform == 'gmb' and cta_url and not is_valid_http_url(cta_url):
        errs.append('Google Business Profile CTA link must be a valid http(s) URL.')
    return errs


def mask_value(key: str, val: str) -> str:
    if not val:
        return ''
    if key not in SECRET_KEYS:
        return val
    if len(val) <= 4:
        return '••••'
    return '••••' + val[-4:]


def get_platform_config(env: dict) -> dict:
    mode = 'live' if env.get('PUBLISH_MODE') == 'live' else 'sandbox'
    public_base_url = env.get('PUBLIC_BASE_URL') or f"http://localhost:{env.get('PORT', '3000')}"

    platforms = {}
    for key, meta in PLATFORM_META.items():
        missing_env = [k for k in meta['requiredEnv'] if not env.get(k)]
        platforms[key] = {
            'key': meta['key'],
            'name': meta['name'],
            'maxChars': meta['maxChars'],
            'maxHashtags': meta.get('maxHashtags'),
            'requiresImage': meta['requiresImage'],
            'configured': len(missing_env) == 0,
            'missingEnv': missing_env,
        }

    fields = {}
    for key in CONFIGURABLE_ENV_KEYS:
        val = env.get(key) or ''
        fields[key] = {
            'isSet': bool(val),
            'isSecret': key in SECRET_KEYS,
            'preview': mask_value(key, val),
        }

    return {
        'mode': mode,
        'publicBaseUrl': public_base_url,
        'platforms': platforms,
        'fields': fields,
    }


def _require_env(env: dict, *keys: str):
    missing = [k for k in keys if not env.get(k)]
    if missing:
        raise RuntimeError(f"Missing credentials: {', '.join(missing)}")


def _call_api(method: str, url: str, **kwargs):
    resp = requests.request(method, url, timeout=30, **kwargs)
    try:
        data = resp.json()
    except ValueError:
        data = {'raw': resp.text}

    if not resp.ok:
        err = data.get('error')
        if isinstance(err, dict):
            msg = err.get('message')
        else:
            msg = None
        msg = msg or data.get('error_description') or data.get('message') or (data.get('raw') or '')[:220] or f'HTTP {resp.status_code}'
        raise RuntimeError(msg)
    return data, resp.headers


def _get_mime(filename: str) -> str:
    ext = os.path.splitext(filename or '')[1].lower()
    if ext == '.png':
        return 'image/png'
    if ext == '.webp':
        return 'image/webp'
    return 'image/jpeg'


def _publish_facebook(post: dict, env: dict) -> dict:
    _require_env(env, 'META_PAGE_ID', 'META_PAGE_TOKEN')
    base = f"https://graph.facebook.com/v21.0/{env['META_PAGE_ID']}"
    text = post.get('text', '')
    image_file = post.get('image_file')
    image_url = post.get('image_url')

    if image_file:
        if image_url and is_public_url(image_url):
            data, _ = _call_api('POST', f'{base}/photos', data={
                'url': image_url,
                'caption': text,
                'access_token': env['META_PAGE_TOKEN'],
            })
        else:
            file_path = os.path.join(post['upload_dir'], image_file)
            with open(file_path, 'rb') as f:
                data, _ = _call_api(
                    'POST',
                    f'{base}/photos',
                    data={'caption': text, 'access_token': env['META_PAGE_TOKEN']},
                    files={'source': (image_file, f, _get_mime(image_file))},
                )
        post_id = data.get('post_id') or data.get('id')
        return {'id': post_id, 'url': f'https://www.facebook.com/{post_id}'}

    data, _ = _call_api('POST', f'{base}/feed', data={
        'message': text,
        'access_token': env['META_PAGE_TOKEN'],
    })
    post_id = data.get('post_id') or data.get('id')
    return {'id': post_id, 'url': f'https://www.facebook.com/{post_id}'}


def _publish_instagram(post: dict, env: dict) -> dict:
    _require_env(env, 'META_IG_USER_ID', 'META_PAGE_TOKEN')
    image_url = post.get('image_url')
    if not image_url or not is_public_url(image_url):
        raise RuntimeError(
            'Instagram Graph API requires a publicly reachable PUBLIC_BASE_URL (e.g. ngrok or production domain) to fetch the image.'
        )

    token = env['META_PAGE_TOKEN']
    base = f"https://graph.facebook.com/v21.0/{env['META_IG_USER_ID']}"
    container, _ = _call_api('POST', f'{base}/media', data={
        'image_url': image_url,
        'caption': post.get('text', ''),
        'access_token': token,
    })
    creation_id = container['id']

    for _ in range(6):
        status_data, _ = _call_api(
            'GET',
            f'https://graph.facebook.com/v21.0/{creation_id}',
            params={'fields': 'status_code,status', 'access_token': token},
        )
        code = status_data.get('status_code')
        if not code or code in ('FINISHED', 'PUBLISHED'):
            break
        if code in ('ERROR', 'EXPIRED'):
            raise RuntimeError(f"Instagram media container failed ({code}): {status_data.get('status', 'invalid media')}")
        time.sleep(1.5)

    published, _ = _call_api('POST', f'{base}/media_publish', data={
        'creation_id': creation_id,
        'access_token': token,
    })
    media_id = published['id']

    permalink = 'https://www.instagram.com/'
    try:
        info, _ = _call_api(
            'GET',
            f'https://graph.facebook.com/v21.0/{media_id}',
            params={'fields': 'permalink', 'access_token': token},
        )
        if info.get('permalink'):
            permalink = info['permalink']
    except Exception:
        pass

    return {'id': media_id, 'url': permalink}


def _publish_linkedin(post: dict, env: dict) -> dict:
    _require_env(env, 'LINKEDIN_TOKEN', 'LINKEDIN_AUTHOR_URN')
    headers = {
        'Authorization': f"Bearer {env['LINKEDIN_TOKEN']}",
        'Linkedin-Version': env.get('LINKEDIN_VERSION') or '202511',
        'X-Restli-Protocol-Version': '2.0.0',
        'Content-Type': 'application/json',
    }

    media_urn = None
    image_file = post.get('image_file')
    if image_file:
        init_data, _ = _call_api(
            'POST',
            'https://api.linkedin.com/rest/images?action=initializeUpload',
            headers=headers,
            json={'initializeUploadRequest': {'owner': env['LINKEDIN_AUTHOR_URN']}},
        )
        upload_url = init_data['value']['uploadUrl']
        media_urn = init_data['value']['image']
        file_path = os.path.join(post['upload_dir'], image_file)
        with open(file_path, 'rb') as f:
            _call_api(
                'PUT',
                upload_url,
                headers={'Authorization': headers['Authorization'], 'Content-Type': _get_mime(image_file)},
                data=f.read(),
            )

    payload = {
        'author': env['LINKEDIN_AUTHOR_URN'],
        'commentary': post.get('text', ''),
        'visibility': 'PUBLIC',
        'distribution': {
            'feedDistribution': 'MAIN_FEED',
            'targetEntities': [],
            'thirdPartyDistributionChannels': [],
        },
        'lifecycleState': 'PUBLISHED',
        'isReshareDisabledByAuthor': False,
    }
    if media_urn:
        payload['content'] = {'media': {'id': media_urn}}

    _, resp_headers = _call_api('POST', 'https://api.linkedin.com/rest/posts', headers=headers, json=payload)
    post_id = resp_headers.get('x-restli-id') or f'urn:li:share:{int(time.time() * 1000)}'
    return {'id': post_id, 'url': f'https://www.linkedin.com/feed/update/{quote(post_id, safe="")}'}


def _publish_gmb(post: dict, env: dict) -> dict:
    _require_env(env, 'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REFRESH_TOKEN', 'GMB_ACCOUNT_ID', 'GMB_LOCATION_ID')
    image_url = post.get('image_url')
    if image_url and not is_public_url(image_url):
        raise RuntimeError(
            'Google Business Profile API requires a publicly reachable PUBLIC_BASE_URL to fetch attached images.'
        )

    tok_data, _ = _call_api('POST', 'https://oauth2.googleapis.com/token', data={
        'client_id': env['GOOGLE_CLIENT_ID'],
        'client_secret': env['GOOGLE_CLIENT_SECRET'],
        'refresh_token': env['GOOGLE_REFRESH_TOKEN'],
        'grant_type': 'refresh_token',
    })

    body = {
        'languageCode': 'en',
        'summary': post.get('text', ''),
        'topicType': 'STANDARD',
    }
    cta_url = post.get('cta_url')
    cta_type = post.get('cta_type')
    if cta_url and is_valid_http_url(cta_url):
        body['callToAction'] = {
            'actionType': cta_type if cta_type in GMB_CTA_TYPES else 'LEARN_MORE',
            'url': cta_url,
        }
    if image_url:
        body['media'] = [{'mediaFormat': 'PHOTO', 'sourceUrl': image_url}]

    endpoint = (
        f"https://mybusiness.googleapis.com/v4/accounts/{env['GMB_ACCOUNT_ID']}"
        f"/locations/{env['GMB_LOCATION_ID']}/localPosts"
    )
    data, _ = _call_api(
        'POST',
        endpoint,
        headers={'Authorization': f"Bearer {tok_data['access_token']}", 'Content-Type': 'application/json'},
        json=body,
    )
    return {'id': data.get('name'), 'url': data.get('searchUrl') or 'https://business.google.com'}


LIVE_ADAPTERS = {
    'facebook': _publish_facebook,
    'instagram': _publish_instagram,
    'linkedin': _publish_linkedin,
    'gmb': _publish_gmb,
}


def _sandbox_publish(platform: str, post: dict) -> dict:
    time.sleep(0.25 + random.random() * 0.35)
    fail_list = post.get('simulate_failures') or []
    if platform in fail_list or re.search(r'\bFAIL\b', post.get('text') or ''):
        raise RuntimeError(
            f"Simulated {PLATFORM_META[platform]['name']} API error (code 190: authorization token invalid or expired)"
        )
    ext_id = f"{platform}_sim_{int(time.time() * 1000)}_{random.randint(100, 999)}"
    return {'id': ext_id, 'url': f'https://example.com/{platform}/posts/{ext_id}'}


def publish(platform: str, post: dict, env: dict) -> dict:
    if env.get('PUBLISH_MODE') == 'live':
        return LIVE_ADAPTERS[platform](post, env)
    return _sandbox_publish(platform, post)
