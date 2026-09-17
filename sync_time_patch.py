import datetime
import urllib.request
import json
import logging

def fix_google_auth_time():
    offset = 0
    try:
        req = urllib.request.urlopen('https://timeapi.io/api/Time/current/zone?timeZone=UTC', timeout=5)
        data = json.loads(req.read())
        real_time = datetime.datetime.fromisoformat(data['dateTime'].replace('Z', ''))
        local_time = datetime.datetime.utcnow()
        offset = (real_time - local_time).total_seconds()
        logging.info(f"Time offset calculated: {offset} seconds")
    except Exception as e:
        logging.warning(f"Failed to fetch real time, offset is 0. Error: {e}")
        offset = 0

    if abs(offset) > 60:
        try:
            import google.auth._helpers
            original_google_utcnow = google.auth._helpers.utcnow
            google.auth._helpers.utcnow = lambda: original_google_utcnow() + datetime.timedelta(seconds=offset)
            print("Patched google.auth._helpers.utcnow")
        except ImportError:
            pass

        try:
            import oauth2client.client
            original_oauth2_utcnow = oauth2client.client._UTCNOW
            oauth2client.client._UTCNOW = lambda: original_oauth2_utcnow() + datetime.timedelta(seconds=offset)
            print("Patched oauth2client.client._UTCNOW")
        except ImportError:
            pass

fix_google_auth_time()
