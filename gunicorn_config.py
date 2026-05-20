import multiprocessing

bind = '0.0.0.0:5151'
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'sync'
timeout = 180
keepalive = 5
accesslog = '/tmp/gestion-tickets-logs/access.log'
errorlog = '/tmp/gestion-tickets-logs/error.log'
loglevel = 'info'
capture_output = True
