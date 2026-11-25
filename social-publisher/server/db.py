import os
import sqlite3
import tempfile
import threading
from contextlib import contextmanager


def get_default_db_path() -> str:
    if os.environ.get('VERCEL'):
        return os.path.join(tempfile.gettempdir(), 'social_publisher.db')
    return os.path.join(os.path.dirname(__file__), 'data.db')


DEFAULT_DB_PATH = get_default_db_path()

DEFAULT_TEMPLATES = [
    {
        'name': 'Flash Sale Offer',
        'category': 'promotional',
        'cta_type': 'SHOP',
        'cta_url': 'https://example.com/sale',
        'html': (
            '<h2>🔥 Weekend Flash Sale — Flat 25% Off!</h2>'
            '<p>Upgrade your favorites before midnight Sunday. Enjoy <strong>25% off sitewide</strong> '
            'plus free shipping on orders above $49.</p>'
            '<p>👉 <a href="https://example.com/sale">Shop the collection now</a></p>'
            '<p>#FlashSale #LimitedTimeOffer #WeekendDeals #ShopNow #SpecialOffer</p>'
        ),
    },
    {
        'name': 'Festival Wishes',
        'category': 'festival',
        'cta_type': 'LEARN_MORE',
        'cta_url': 'https://example.com/festive',
        'html': (
            '<h2>🪔 Warmest Festival Wishes to You &amp; Your Family!</h2>'
            '<p>May this season bring light, peace, joy, and prosperity into your home. '
            'Thank you for being part of our journey! ✨🙏</p>'
            '<p>Visit us in-store or online for festive specials: '
            '<a href="https://example.com/festive">Explore festive hours</a></p>'
            '<p>#FestivalWishes #HappyFestivities #Celebration #JoyAndLight #Community</p>'
        ),
    },
    {
        'name': 'New Year Greetings',
        'category': 'festival',
        'cta_type': None,
        'cta_url': None,
        'html': (
            '<h2>🎉 Happy New Year! Here is to New Beginnings ✨</h2>'
            '<p>Wishing our customers, partners, and friends a year filled with growth, '
            'good health, and memorable milestones. 🌟</p>'
            '<p>#HappyNewYear #NewBeginnings #Gratitude #CheersTo2027</p>'
        ),
    },
    {
        'name': 'Product Announcement',
        'category': 'announcement',
        'cta_type': 'LEARN_MORE',
        'cta_url': 'https://example.com/announcement',
        'html': (
            '<h2>📣 Big Announcement: Something New Has Arrived!</h2>'
            '<p>We are thrilled to introduce our latest release, built from your feedback:</p>'
            '<ul><li>Faster everyday experience</li><li>Smarter customization options</li>'
            '<li>Available starting today</li></ul>'
            '<p>Read the full update: <a href="https://example.com/announcement">See what is new</a></p>'
            '<p>#Announcement #NewLaunch #ProductUpdate #Innovation</p>'
        ),
    },
]


class Database:
    """Thread-safe SQLite wrapper supporting both file-backed and :memory: databases."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or get_default_db_path()
        self._is_memory = db_path == ':memory:'
        self._lock = threading.Lock()
        self._mem_conn = None
        if self._is_memory:
            self._mem_conn = sqlite3.connect(':memory:', check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row
            self._mem_conn.execute('PRAGMA foreign_keys = ON')
        self.init_schema()

    @contextmanager
    def connect(self):
        if self._is_memory:
            with self._lock:
                try:
                    yield self._mem_conn
                    self._mem_conn.commit()
                except Exception:
                    self._mem_conn.rollback()
                    raise
        else:
            conn = sqlite3.connect(self.db_path, timeout=15.0)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA foreign_keys = ON')
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _ensure_column(self, conn, table: str, column: str, definition: str):
        cols = {row['name'] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}
        if column not in cols:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')

    def init_schema(self):
        with self.connect() as conn:
            if not self._is_memory:
                conn.execute('PRAGMA journal_mode = WAL')

            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS posts (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  category TEXT NOT NULL DEFAULT 'general',
                  post_status TEXT NOT NULL DEFAULT 'published',
                  html TEXT NOT NULL,
                  text TEXT NOT NULL,
                  hashtags TEXT NOT NULL DEFAULT '[]',
                  links TEXT NOT NULL DEFAULT '[]',
                  cta_type TEXT,
                  cta_url TEXT,
                  image TEXT,
                  image_original_name TEXT,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS results (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                  platform TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  external_id TEXT,
                  url TEXT,
                  error TEXT,
                  attempts INTEGER NOT NULL DEFAULT 1,
                  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS settings (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL,
                  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS templates (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  category TEXT NOT NULL DEFAULT 'general',
                  html TEXT NOT NULL,
                  cta_type TEXT,
                  cta_url TEXT,
                  is_default INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            self._ensure_column(conn, 'posts', 'category', "TEXT NOT NULL DEFAULT 'general'")
            self._ensure_column(conn, 'posts', 'post_status', "TEXT NOT NULL DEFAULT 'published'")
            self._ensure_column(conn, 'posts', 'hashtags', "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, 'posts', 'links', "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, 'posts', 'cta_type', 'TEXT')
            self._ensure_column(conn, 'posts', 'cta_url', 'TEXT')
            self._ensure_column(conn, 'posts', 'image', 'TEXT')
            self._ensure_column(conn, 'posts', 'image_original_name', 'TEXT')
            self._ensure_column(conn, 'results', 'attempts', 'INTEGER NOT NULL DEFAULT 1')

            count = conn.execute('SELECT COUNT(*) AS c FROM templates').fetchone()['c']
            if count == 0:
                for tpl in DEFAULT_TEMPLATES:
                    conn.execute(
                        'INSERT INTO templates (name, category, html, cta_type, cta_url, is_default) VALUES (?, ?, ?, ?, ?, 1)',
                        (tpl['name'], tpl['category'], tpl['html'], tpl['cta_type'], tpl['cta_url']),
                    )

    def close(self):
        if self._mem_conn is not None:
            self._mem_conn.close()
            self._mem_conn = None
