#!/usr/bin/env python3
import os
import time
import django
from django.test import Client
from django.contrib.auth import get_user_model

# Configure settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

# Create benchmark user if not exists
def get_client():
    User = get_user_model()
    username = 'benchmark_user'
    password = 'benchmark_pass'
    email = 'benchmark@example.com'
    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(username=username, email=email, password=password)
    client = Client()
    logged_in = client.login(username=username, password=password)
    if not logged_in:
        raise RuntimeError('Failed to log in as benchmark_user')
    return client

if __name__ == '__main__':
    client = get_client()
    url = '/admin/dashboard/'
    runs = 5
    times = []
    print('Measuring dashboard response times:')
    for i in range(runs):
        start = time.time()
        response = client.get(url)
        elapsed = time.time() - start
        if response.status_code != 200:
            print(f'Run {i+1}: FAIL status {response.status_code}')
        else:
            print(f'Run {i+1}: {elapsed:.4f} seconds')
        times.append(elapsed)
    avg = sum(times) / len(times)
    print(f'Average: {avg:.4f} seconds')
