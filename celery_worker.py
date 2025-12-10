from gevent import monkey
monkey.patch_all()

from wsgi import app

celery_app = app.extensions["celery"]