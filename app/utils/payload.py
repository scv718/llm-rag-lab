import json


def payload_from_row(row):

    pj = row["payload_json"]

    if not pj:
        return None

    try:
        return json.loads(pj)
    except Exception:
        return None


def last_assistant_payload(turns):

    for r in reversed(turns):

        if r["role"] == "assistant":

            payload = payload_from_row(r)

            if payload:
                return payload

    return None
