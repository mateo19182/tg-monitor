#!/usr/bin/env python3
"""Serve the static archive and GET /api/search on the same origin."""
import argparse
import json
import logging
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from search import DB, HERE, WATCHLIST, InvalidSearch, SearchRequest, SearchTimeout, SearchUnavailable, ensure_index, search_messages
import storyapi

log = logging.getLogger(__name__)


class ArchiveHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, db_path: Path, watchlist_path: Path, **kwargs):
        self.db_path, self.watchlist_path = db_path, watchlist_path
        super().__init__(*args, **kwargs)

    def send_json(self, status: int, payload: dict, *, head: bool = False) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        if url.path == "/api/search":
            try:
                if len(self.path) > 4096:
                    raise InvalidSearch("invalid_request")
                params = parse_qs(url.query, keep_blank_values=True, max_num_fields=20)
                if any(len(v) != 1 for v in params.values()):
                    raise InvalidSearch("invalid_request")
                request = SearchRequest.from_params({k: v[0] for k, v in params.items()})
                result = search_messages(request, db_path=self.db_path, watchlist_path=self.watchlist_path)
            except InvalidSearch as e:
                self.send_json(400, {"error": str(e)})
            except ValueError:
                self.send_json(400, {"error": "invalid_request"})
            except SearchTimeout:
                self.send_json(503, {"error": "search_timeout"})
            except SearchUnavailable:
                log.exception("Search unavailable")
                self.send_json(503, {"error": "search_unavailable"})
            else:
                self.send_json(200, result)
        elif url.path in ("/api/stories", "/api/story", "/api/threads"):
            try:
                params = {k: v[0] for k, v in parse_qs(url.query, keep_blank_values=True, max_num_fields=6).items()}
                if url.path == "/api/threads":
                    result = storyapi.threads(min(max(int(params.get("min", "3")), 2), 52))
                elif url.path == "/api/story":
                    result = storyapi.story(int(params.get("id", "")))
                    if result is None:
                        self.send_json(404, {"error": "not_found"}); return
                elif params.get("week"):
                    result = storyapi.stories(params["week"], params.get("region") or None, params.get("theme") or None)
                else:
                    result = storyapi.weeks()
            except ValueError:
                self.send_json(400, {"error": "invalid_request"})
            except Exception:
                log.exception("Stories unavailable")
                self.send_json(503, {"error": "search_unavailable"})
            else:
                self.send_json(200, result)
        elif url.path.startswith("/api/"):
            self.send_json(404, {"error": "not_found"})
        else:
            super().do_GET()

    def do_HEAD(self) -> None:
        if urlsplit(self.path).path.startswith("/api/"):
            self.send_json(405, {"error": "method_not_allowed"}, head=True)
        else:
            super().do_HEAD()

    def list_directory(self, path):
        self.send_error(403)
        return None


def make_server(port: int, *, bind: str = "127.0.0.1", directory: Path = HERE / "site",
                db_path: Path = DB, watchlist_path: Path = WATCHLIST) -> ThreadingHTTPServer:
    handler = partial(ArchiveHandler, directory=str(directory), db_path=db_path, watchlist_path=watchlist_path)
    return ThreadingHTTPServer((bind, port), handler)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--directory", type=Path, default=HERE / "site")
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--watchlist", type=Path, default=WATCHLIST)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    ensure_index(args.db)
    with make_server(args.port, bind=args.bind, directory=args.directory,
                     db_path=args.db, watchlist_path=args.watchlist) as server:
        print(f"Archive: http://{args.bind}:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
