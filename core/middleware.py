from __future__ import annotations
import time
import logging
import traceback
from typing import Iterable
from django.db import connection
from django.http import HttpRequest, HttpResponse


TARGET_PREFIXES: tuple[str, ...] = (
    "/admin/rental/client",
    "/admin/rental/payment",
    "/admin/dashboard/",
)


class SqlTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("performance")

    def __call__(self, request: HttpRequest) -> HttpResponse:
        path = request.path or ""
        should_trace = path.startswith(TARGET_PREFIXES)

        if not should_trace:
            return self.get_response(request)

        prev_force = connection.force_debug_cursor
        connection.force_debug_cursor = True
        start = time.perf_counter()
        response: HttpResponse | None = None
        exc: Exception | None = None
        try:
            response = self.get_response(request)
            return response
        except Exception as e:  # log and re-raise
            exc = e
            # Логируем полный traceback для диагностики 500 даже при DEBUG=False
            tb = traceback.format_exc()
            # Печатаем всегда (stdout), чтобы гарантированно попасть в Render Logs
            print("TRACEBACK", request.path, "\n", tb)
            # И дублируем в логгер performance
            try:
                self.logger.error("TRACEBACK %s\n%s", request.path, tb)
            except Exception:
                pass
            raise
        finally:
            total_s = time.perf_counter() - start
            # Sum SQL timings (in seconds) and count queries
            try:
                queries = list(connection.queries)
            except Exception:
                queries = []
            try:
                sql_time_s = 0.0
                for q in queries:
                    try:
                        sql_time_s += float(q.get("time", 0) or 0)
                    except Exception:
                        pass
                sql_count = len(queries)
                slow = total_s >= 0.3 or sql_time_s >= 0.2
                status = getattr(response, 'status_code', 500 if exc else 200)
                line = (
                    f"PERF path={path} status={status} "
                    f"total={total_s:.3f}s sql_time={sql_time_s:.3f}s sql_count={sql_count} slow={slow}"
                )
                slow_qs = sorted(
                    (
                        (float(q.get("time", 0) or 0), q.get("sql", ""))
                        for q in queries
                        if float(q.get("time", 0) or 0) >= 0.05
                    ),
                    key=lambda x: x[0],
                    reverse=True,
                )[:3]
                for i, (secs, sql) in enumerate(slow_qs, 1):
                    sql_short = " ".join(sql.split())
                    if len(sql_short) > 300:
                        sql_short = sql_short[:300] + "…"
                    line += f"\n  #{i} {secs*1000:.1f}ms: {sql_short}"
                print(line)
                try:
                    (self.logger.warning if slow else self.logger.info)(line)
                except Exception:
                    pass
            finally:
                connection.force_debug_cursor = prev_force
