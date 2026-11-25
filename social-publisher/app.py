import os
from server.app import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', '3000'))
    print(f'Social Publisher (Python/Flask) running at http://localhost:{port}')
    app.run(host='0.0.0.0', port=port, threaded=True)
