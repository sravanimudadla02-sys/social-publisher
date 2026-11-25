import io
import json
import os
import tempfile
import unittest

from PIL import Image

from server.app import create_app
from server.db import get_default_db_path
from server.publishers import _ensure_jpeg_for_instagram, extract_metadata, get_platform_config, to_text, validate_post


class PublishersUnitTest(unittest.TestCase):
    def test_to_text_preserves_lists_links_and_entities(self):
        html = (
            '<h2>🔥 Flash Sale!</h2><p>Save 25% &amp; enjoy:</p>'
            '<ol><li>Fast shipping</li><li>Free returns</li></ol>'
            '<ul><li>Valid today</li></ul>'
            '<p><a href="https://example.com/shop">Shop Now</a> #Sale</p>'
        )
        txt = to_text(html)
        self.assertIn('🔥 Flash Sale!', txt)
        self.assertIn('Save 25% & enjoy:', txt)
        self.assertIn('1. Fast shipping', txt)
        self.assertIn('2. Free returns', txt)
        self.assertIn('• Valid today', txt)
        self.assertIn('Shop Now (https://example.com/shop) #Sale', txt)

    def test_extract_metadata_unique_hashtags_and_links(self):
        html = '<p>Visit <a href="https://example.com/diwali">here</a> #Diwali #Festive #Diwali</p>'
        text = to_text(html)
        meta = extract_metadata(html, text)
        self.assertEqual(meta['hashtags'], ['#Diwali', '#Festive'])
        self.assertEqual(meta['links'], ['https://example.com/diwali'])

    def test_validate_post_rules(self):
        self.assertEqual(
            validate_post('instagram', text='Happy Diwali!', has_image=False),
            ['Instagram requires an image (JPG, PNG, or WebP).'],
        )
        many_tags = ' '.join(f'#tag{i}' for i in range(31))
        ig_errs = validate_post('instagram', text=many_tags, has_image=True)
        self.assertEqual(len(ig_errs), 1)
        self.assertIn('max 30 hashtags', ig_errs[0])

        gmb_errs = validate_post('gmb', text='a' * 1501, has_image=False)
        self.assertEqual(len(gmb_errs), 1)
        self.assertIn('1,500', gmb_errs[0])

    def test_get_platform_config_masks_secrets(self):
        cfg = get_platform_config({
            'PUBLISH_MODE': 'live',
            'META_PAGE_ID': '123',
            'META_PAGE_TOKEN': 'secret_tok_9876',
        })
        self.assertEqual(cfg['mode'], 'live')
        self.assertTrue(cfg['platforms']['facebook']['configured'])
        self.assertFalse(cfg['platforms']['instagram']['configured'])
        self.assertEqual(cfg['platforms']['instagram']['missingEnv'], ['META_IG_USER_ID'])
        self.assertEqual(cfg['fields']['META_PAGE_TOKEN']['preview'], '••••9876')
        self.assertNotIn('secret_tok_9876', json.dumps(cfg))

    def test_ensure_jpeg_for_instagram_converts_png(self):
        tmp_dir = tempfile.mkdtemp(prefix='ig-jpg-')
        try:
            png_path = os.path.join(tmp_dir, 'sample.png')
            Image.new('RGBA', (16, 16), (255, 0, 0, 128)).save(png_path, format='PNG')
            converted_url = _ensure_jpeg_for_instagram(
                {'image_file': 'sample.png', 'image_url': 'https://demo.example.com/uploads/sample.png', 'upload_dir': tmp_dir},
                'https://demo.example.com',
            )
            self.assertEqual(converted_url, 'https://demo.example.com/uploads/sample-ig.jpg')
            self.assertTrue(os.path.exists(os.path.join(tmp_dir, 'sample-ig.jpg')))
        finally:
            for name in os.listdir(tmp_dir):
                os.remove(os.path.join(tmp_dir, name))
            os.rmdir(tmp_dir)

    def test_vercel_env_uses_writable_temp_db_path(self):
        prev = os.environ.get('VERCEL')
        os.environ['VERCEL'] = '1'
        try:
            db_path = get_default_db_path()
            self.assertIn('social_publisher.db', db_path)
            self.assertNotIn(os.path.join('server', 'data.db'), db_path)
        finally:
            if prev is None:
                os.environ.pop('VERCEL', None)
            else:
                os.environ['VERCEL'] = prev


class FlaskApiIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix='social-pub-py-')
        self.fail_instagram = True

        def fake_publish(platform, post, env):
            if platform == 'instagram' and self.fail_instagram:
                raise RuntimeError('Instagram temporary outage')
            return {'id': f'{platform}_123', 'url': f'https://social.example/{platform}/123'}

        self.app = create_app({
            'db_path': ':memory:',
            'upload_dir': self.tmp_dir,
            'env': {'PORT': '3000', 'PUBLISH_MODE': 'sandbox'},
            'publish_fn': fake_publish,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.extensions['db'].close()
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def test_health_config_templates_and_draft_lifecycle(self):
        health = self.client.get('/api/health').get_json()
        self.assertTrue(health['ok'])
        self.assertEqual(health['database'], 'connected')
        self.assertEqual(health['driver'], 'python-sqlite3')
        self.assertEqual(health['counts']['templates'], 4)

        cfg_res = self.client.put('/api/config', json={
            'mode': 'live',
            'publicBaseUrl': 'https://demo.example.com',
            'values': {
                'IG_ACCOUNT_NAME': '@mybrand_ig',
                'IG_ACCOUNT_URL': 'https://www.instagram.com/mybrand_ig/',
                'META_PAGE_ID': 'page_999',
                'META_PAGE_TOKEN': 'super_secret_token_1234',
            },
        })
        self.assertEqual(cfg_res.status_code, 200)
        cfg = cfg_res.get_json()
        self.assertEqual(cfg['mode'], 'live')
        self.assertEqual(cfg['platforms']['instagram']['accountName'], '@mybrand_ig')
        self.assertEqual(cfg['platforms']['instagram']['accountUrl'], 'https://www.instagram.com/mybrand_ig/')
        self.assertTrue(cfg['platforms']['facebook']['configured'])
        self.assertEqual(cfg['fields']['META_PAGE_TOKEN']['preview'], '••••1234')
        self.assertNotIn('super_secret_token_1234', json.dumps(cfg))

        # Custom template create & delete
        tpl_res = self.client.post('/api/templates', json={
            'name': 'Custom Eid Offer',
            'category': 'festival',
            'html': '<p>Eid Mubarak! #Eid</p>',
        })
        self.assertEqual(tpl_res.status_code, 201)
        tpl = tpl_res.get_json()
        self.assertEqual(tpl['is_default'], 0)
        self.assertEqual(len(self.client.get('/api/templates').get_json()), 5)
        self.assertEqual(self.client.delete(f"/api/templates/{tpl['id']}").status_code, 200)

        # Save draft and promote to published
        draft_res = self.client.post('/api/drafts', json={
            'category': 'announcement',
            'html': '<p>Draft announcement #News</p>',
        })
        self.assertEqual(draft_res.status_code, 201)
        draft = draft_res.get_json()
        self.assertEqual(draft['post_status'], 'draft')
        self.assertEqual(len(self.client.get('/api/posts?postStatus=draft').get_json()), 1)

        pub_res = self.client.post('/api/publish', json={
            'draftId': draft['id'],
            'category': 'announcement',
            'html': '<p>Final announcement #News</p>',
            'platforms': ['linkedin'],
        })
        self.assertEqual(pub_res.status_code, 200)
        published = pub_res.get_json()
        self.assertEqual(published['id'], draft['id'])
        self.assertEqual(published['post_status'], 'published')
        self.assertEqual(published['results'][0]['status'], 'success')

    def test_upload_publish_partial_failure_retry_and_history(self):
        up_res = self.client.post(
            '/api/upload',
            data={'image': (io.BytesIO(b'fake-png-bytes'), 'banner.png', 'image/png')},
            content_type='multipart/form-data',
        )
        self.assertEqual(up_res.status_code, 200)
        uploaded = up_res.get_json()
        self.assertTrue(uploaded['file'])

        pub_res = self.client.post('/api/publish', json={
            'category': 'festival',
            'html': '<p>Happy Diwali! ✨ #Diwali #FestivalWishes</p>',
            'image': uploaded['file'],
            'imageOriginalName': 'banner.png',
            'ctaType': 'LEARN_MORE',
            'ctaUrl': 'https://example.com/diwali',
            'platforms': ['instagram', 'facebook', 'gmb', 'linkedin'],
        })
        self.assertEqual(pub_res.status_code, 200)
        post = pub_res.get_json()
        self.assertEqual(post['category'], 'festival')
        self.assertEqual(len(post['results']), 4)

        by_plat = {r['platform']: r for r in post['results']}
        self.assertEqual(by_plat['instagram']['status'], 'failed')
        self.assertEqual(by_plat['facebook']['status'], 'success')
        self.assertEqual(by_plat['gmb']['status'], 'success')
        self.assertEqual(by_plat['linkedin']['status'], 'success')

        self.fail_instagram = False
        retry_res = self.client.post(f"/api/posts/{post['id']}/retry", json={'platform': 'instagram'})
        self.assertEqual(retry_res.status_code, 200)
        retried = retry_res.get_json()
        ig_after = next(r for r in retried['results'] if r['platform'] == 'instagram')
        self.assertEqual(ig_after['status'], 'success')
        self.assertEqual(ig_after['attempts'], 2)

        hist = self.client.get('/api/posts?category=festival&q=Diwali').get_json()
        self.assertEqual(len(hist), 1)

        del_res = self.client.delete(f"/api/posts/{post['id']}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(len(self.client.get('/api/posts').get_json()), 0)


if __name__ == '__main__':
    unittest.main()
