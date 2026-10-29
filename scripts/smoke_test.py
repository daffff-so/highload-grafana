#!/usr/bin/env python3
"""Functional HTTP check, not a load generator. Python 3 standard library only."""
import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def request(base, method, path, expected, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(base + path, data=data, method=method,
                  headers={'Content-Type': 'application/json'})
    try:
        response = urlopen(req, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        body = response.read()
        assert response.status == expected, (method, path, response.status, body)
        return json.loads(body) if body else None


def check(base):
    request(base, 'GET', '/health', 200)
    item = request(base, 'POST', '/items', 201, {'name': 'smoke-check'})
    path = '/items/' + str(item['id'])
    assert request(base, 'GET', path, 200)['name'] == 'smoke-check'
    assert request(base, 'PUT', path, 200, {'name': 'updated'})['name'] == 'updated'
    assert request(base, 'GET', path, 200)['name'] == 'updated'
    request(base, 'GET', '/items/9223372036854775807', 404)
    request(base, 'PUT', '/items/9223372036854775807', 404, {'name': 'missing'})
    request(base, 'POST', '/items', 400, {'name': ' '})
    print('PASS:', base, '(health, create/read/update, 404, validation)')


if __name__ == '__main__':
    for base in sys.argv[1:] or ['http://localhost:8081', 'http://localhost:8082']:
        check(base.rstrip('/'))
