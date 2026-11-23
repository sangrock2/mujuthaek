"""Send fixed operational summaries without logging the Slack credential or response."""

import json
import re
import urllib.request

WEBHOOK = re.compile(r'https://hooks\.slack\.com/services/[A-Za-z0-9]+/[A-Za-z0-9]+/[A-Za-z0-9]+')


class SlackError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def send(webhook, title, messages):
    if not WEBHOOK.fullmatch(webhook):
        raise SlackError('Invalid Slack webhook configuration.')
    text = '\n'.join([title, *('• ' + line for line in messages)])
    request = urllib.request.Request(
        webhook, data=json.dumps({'text': text, 'mrkdwn': False}).encode(),
        headers={'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
            if response.status != 200 or response.read(32).strip() != b'ok':
                raise SlackError('Slack did not confirm delivery.')
    except (OSError, ValueError):
        raise SlackError('Slack delivery failed.') from None
