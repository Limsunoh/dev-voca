from django.test import SimpleTestCase

from config.sentry import scrub


class ScrubTest(SimpleTestCase):
    def test_keeps_user_agent_and_masked_url_only(self):
        event = {
            "request": {
                "url": "https://api.example/api/accounts/email/Ab3xToken9/?code=secret#frag",
                "method": "POST",
                "query_string": "code=secret",
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Linux; Android 15)",
                    "X-Next-Relay": "relay-secret",
                    "X-Next-Client-Ip": "203.0.113.7",
                    "Cookie": "devvoca_token=abc",
                },
                "cookies": {"devvoca_token": "abc"},
                "data": {"password": "pw"},
                "env": {"REMOTE_ADDR": "203.0.113.7"},
            },
            "user": {"ip_address": "203.0.113.7"},
        }

        out = scrub(event, {})

        self.assertEqual(
            out["request"],
            {
                "url": "https://api.example/api/accounts/email/:id/",
                "method": "POST",
                "headers": {"User-Agent": "Mozilla/5.0 (Linux; Android 15)"},
            },
        )
        self.assertNotIn("user", out)

    def test_drops_sql_params_from_query_breadcrumbs(self):
        event = {
            "breadcrumbs": {
                "values": [
                    {
                        "category": "query",
                        "message": "SELECT ... WHERE key = %s",
                        "data": {"db.params": ["login-token"]},
                    },
                    {"category": "httplib", "data": {"url": "https://oauth2.googleapis.com/token"}},
                ]
            }
        }

        values = scrub(event, {})["breadcrumbs"]["values"]

        self.assertEqual(values[0], {"category": "query", "message": "SELECT ... WHERE key = %s"})
        self.assertEqual(values[1]["data"], {"url": "https://oauth2.googleapis.com/token"})

    def test_event_without_request_passes(self):
        event = {"message": "cleanup failed"}
        self.assertEqual(scrub(event, {}), {"message": "cleanup failed"})
