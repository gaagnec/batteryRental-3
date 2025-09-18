#!/usr/bin/env python3
import os
import time
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django
from django.test import RequestFactory
from django.db import connection
from django.http import HttpRequest

django.setup()

from rental.views import dashboard


def run_once():
    rf = RequestFactory()
    req: HttpRequest = rf.get('/admin/dashboard/')
    # Imitate staff user requirement bypass: view itself doesn't use request.user
    connection.force_debug_cursor = True
    t0 = time.perf_counter()
    try:
        resp = dashboard(req)
        # Force render to catch template errors
        if hasattr(resp, 'render'):
            resp = resp.render()
        dt = time.perf_counter() - t0
        # Aggregate SQL timings
        try:
            queries = list(connection.queries)
        except Exception:
            queries = []
        sql_time_s = 0.0
        for q in queries:
            try:
                sql_time_s += float(q.get('time', 0) or 0)
            except Exception:
                pass
        print(f"OK status={getattr(resp, 'status_code', '?')} total={dt:.3f}s sql_time={sql_time_s:.3f}s sql_count={len(queries)}")
        # Top 5 slow queries
        slow_qs = sorted(
            (
                (float(q.get('time', 0) or 0), q.get('sql', ''))
                for q in queries
                if float(q.get('time', 0) or 0) >= 0.01
            ),
            key=lambda x: x[0],
            reverse=True,
        )[:5]
        for i, (secs, sql) in enumerate(slow_qs, 1):
            sql_short = ' '.join(sql.split())
            if len(sql_short) > 300:
                sql_short = sql_short[:300] + '…'
            print(f"  #{i} {secs*1000:.1f}ms: {sql_short}")
    except Exception:
        dt = time.perf_counter() - t0
        tb = traceback.format_exc()
        try:
            queries = list(connection.queries)
        except Exception:
            queries = []
        sql_time_s = 0.0
        for q in queries:
            try:
                sql_time_s += float(q.get('time', 0) or 0)
            except Exception:
                pass
        print(f"ERROR total={dt:.3f}s sql_time={sql_time_s:.3f}s sql_count={len(queries)}")
        print(tb)


if __name__ == '__main__':
    run_once()
