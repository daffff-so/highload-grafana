#!/usr/bin/env python3
"""Create/update a Grafana dashboard from the running service's /handlers."""
import argparse
import base64
import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError

DS = {'type': 'prometheus', 'uid': 'prometheus-main'}
METRIC = 'http_server_requests_seconds'
UID = 'items-golden-signals'


def api(url, payload=None, auth=None):
    headers = {'Accept': 'application/json'}
    if auth:
        headers['Authorization'] = 'Basic ' + base64.b64encode(auth.encode()).decode()
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers['Content-Type'] = 'application/json'
    with urlopen(Request(url, data=data, headers=headers), timeout=30) as response:
        return json.load(response)


def variable(name, label, query):
    return {
        'name': name, 'label': label, 'type': 'query', 'datasource': DS,
        'query': {'query': query, 'refId': name}, 'definition': query,
        'refresh': 2, 'sort': 1, 'multi': True, 'includeAll': True,
        'allValue': '.*', 'options': [],
        'current': {'text': 'All', 'value': '$__all'},
    }


def panel(panel_id, title, x, y, unit, expressions):
    return {
        'id': panel_id, 'title': title, 'type': 'timeseries', 'datasource': DS,
        'gridPos': {'x': x, 'y': y, 'w': 8, 'h': 8},
        'fieldConfig': {'defaults': {'unit': unit, 'min': 0}, 'overrides': []},
        'options': {'legend': {'displayMode': 'list', 'placement': 'bottom'},
                    'tooltip': {'mode': 'multi', 'sort': 'none'}},
        'targets': [
            {'refId': chr(65 + i), 'expr': expr, 'legendFormat': legend,
             'datasource': DS, 'editorMode': 'code', 'range': True}
            for i, (expr, legend) in enumerate(expressions)
        ],
    }


def build_dashboard(handlers):
    if not isinstance(handlers, list) or not handlers:
        raise ValueError('/handlers must return a nonempty list')
    routes = set()
    for handler in handlers:
        method, path = handler['method'], handler['path']
        if not isinstance(method, str) or not isinstance(path, str):
            raise ValueError('Handler method and path must be strings')
        routes.add((method, path))
    panels = []
    common = 'job="items-service",datacenter=~"${datacenter:regex}",pod_id=~"${pod_id:regex}"'
    for row, (method, path) in enumerate(sorted(routes)):
        labels = common + ',method=' + json.dumps(method) + ',uri=' + json.dumps(path)
        buckets = METRIC + '_bucket{' + labels + '}'
        count = METRIC + '_count{' + labels + '}'
        errors = METRIC + '_count{' + labels + ',status=~"4..|5.."}'
        title = method + ' ' + path
        latency = [
            ('histogram_quantile(' + str(q) + ', sum by (le) (rate('
             + buckets + '[$__rate_interval])))', legend)
            for q, legend in [(0.50, 'p50'), (0.95, 'p95'), (0.99, 'p99')]
        ]
        panels.extend([
            panel(row * 3 + 1, title + ' | Latency', 0, row * 8, 's', latency),
            panel(row * 3 + 2, title + ' | RPS', 8, row * 8, 'reqps',
                  [('sum(rate(' + count + '[$__rate_interval]))', 'RPS')]),
            panel(row * 3 + 3, title + ' | Errors/s by status', 16, row * 8, 'reqps',
                  [('sum by (status) (rate(' + errors + '[$__rate_interval]))', '{{status}}')]),
        ])
    return {
        'id': None, 'uid': UID, 'title': 'Items | Golden Signals',
        'schemaVersion': 41, 'version': 0, 'editable': False,
        'timezone': 'browser', 'refresh': '5s',
        'time': {'from': 'now-15m', 'to': 'now'}, 'tags': ['highload', 'generated'],
        'templating': {'list': [
            variable('datacenter', 'Datacenter',
                     'label_values(http_server_requests_seconds_count{job="items-service"}, datacenter)'),
            variable('pod_id', 'Pod',
                     'label_values(http_server_requests_seconds_count{job="items-service",datacenter=~"${datacenter:regex}"}, pod_id)'),
        ]},
        'panels': panels,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-url', default=os.getenv('APP_URL', 'http://app-1:8080'))
    parser.add_argument('--grafana-url', default=os.getenv('GRAFANA_URL', 'http://grafana:3000'))
    args = parser.parse_args()
    username = os.environ['GRAFANA_ADMIN_USER']
    password = os.environ['GRAFANA_ADMIN_PASSWORD']
    dashboard = build_dashboard(api(args.app_url.rstrip('/') + '/handlers'))
    auth = username + ':' + password
    grafana = args.grafana_url.rstrip('/')
    result = api(grafana + '/api/dashboards/db',
                 {'dashboard': dashboard, 'overwrite': True, 'message': 'Generated from /handlers'}, auth)
    saved = api(grafana + '/api/dashboards/uid/' + UID, auth=auth)['dashboard']
    if saved.get('editable') is not False or len(saved['panels']) != len(dashboard['panels']):
        raise RuntimeError('Dashboard verification failed')
    print('Dashboard saved:', result.get('url', UID))
    print('Panels:', len(saved['panels']))


if __name__ == '__main__':
    try:
        main()
    except HTTPError as error:
        print('HTTP error:', error.code, error.reason, file=sys.stderr)
        sys.exit(1)
