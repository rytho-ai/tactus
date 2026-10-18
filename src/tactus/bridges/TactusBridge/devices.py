"""Native device metadata and guarded edits; standalone embedded Python 3.7.

One reader epoch owns descriptor/catalog caches. Values and write preconditions are
always read from native objects; cached descriptions never authorize a mutation.
Reads: native song/browser via LiveState; stdlib copy/hash/JSON/LRU only.
"""

import copy
import hashlib
import json
import math
import uuid
from collections import OrderedDict


def _id(obj):
    return str(obj._live_ptr)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


class DeviceAccess:
    """Inspect once, batch chosen values, and return compact fresh readback."""

    def __init__(self, state):
        self.state = state
        self._closed = False
        self._descriptors = OrderedDict()
        self._targets = OrderedDict()
        self._catalog = OrderedDict()
        self._counts = {'schema_builds': 0, 'schema_hits': 0,
                        'catalog_builds': 0, 'catalog_hits': 0}
        self._browser = getattr(state.app, 'browser', None)
        self._listening = False
        if self._browser is not None:
            try:
                self._browser.add_full_refresh_listener(self.clear_catalog)
                self._listening = True
            except (AttributeError, RuntimeError, TypeError):
                pass  # Explicit refresh remains available on older browsers.

    def _open(self):
        if self._closed or self.state._closed:
            raise RuntimeError('Live state reader is closed')

    def _target(self, track_id, device_id):
        self._open()
        if not isinstance(track_id, str) or not isinstance(device_id, str):
            raise TypeError('Supply exact inspected track_id and device_id')
        track = self.state.track(track_id)
        return track, self.state._device(track, device_id)

    @staticmethod
    def _keep(cache, key, value, limit):
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > limit:
            cache.popitem(last=False)

    def _layout(self, device):
        parameters = list(device.parameters)
        signature = []
        for parameter in parameters:
            items = tuple(parameter.value_items) if parameter.is_quantized else ()
            signature.append((_id(parameter), parameter.name, parameter.min, parameter.max,
                              parameter.is_quantized, items))
        encoded = json.dumps([self.state.instance, device.class_name, signature],
                             sort_keys=True, separators=(',', ':')).encode('utf-8')
        layout = hashlib.sha256(encoded).hexdigest()
        hit = layout in self._descriptors
        if hit:
            self._counts['schema_hits'] += 1
            self._descriptors.move_to_end(layout)
        else:
            self._counts['schema_builds'] += 1
            rows = [dict(zip(('id', 'name', 'min', 'max', 'is_quantized', 'items'), row))
                    for row in signature]
            for row in rows:
                row['items'] = list(row['items'])
            self._keep(self._descriptors, layout, rows, 32)
        # Native pointer IDs can be recycled after deletion. Keep a bounded native
        # handle solely for identity validation; never store parameter values here.
        # An old weak native handle must still refer to the same live object.
        target = _id(device)
        prior = self._targets.get(target)
        same = False
        if prior is not None:
            try:
                same = (prior['device'] == device
                        and prior['device'].class_name == device.class_name)
            except (RuntimeError, TypeError):
                pass
        if not same or prior['layout'] != layout:
            prior = {'device': device, 'layout': layout, 'schema': uuid.uuid4().hex}
        self._keep(self._targets, target, prior, 32)
        return parameters, prior['schema'], hit, self._descriptors[layout]

    @staticmethod
    def _select(parameters, names):
        if names is None:
            counts = {}
            for p in parameters:
                counts[p.name] = counts.get(p.name, 0) + 1
            names = [p.name if counts[p.name] == 1 else _id(p) for p in parameters]
        if (not isinstance(names, list) or not names
                or any(not isinstance(n, str) or not n for n in names)
                or len(set(names)) != len(names)):
            raise ValueError('parameters must select distinct names or native parameter IDs')
        selected = []
        for name in names:
            matches = [p for p in parameters if _id(p) == name]
            if not matches:
                matches = [p for p in parameters if p.name == name]
            if len(matches) != 1:
                raise ValueError('Missing/ambiguous parameter; inspect its native ID: ' + name)
            selected.append((name, matches[0]))
        if len({_id(p) for _, p in selected}) != len(selected):
            raise ValueError('Parameter aliases select the same native parameter twice')
        return selected

    def inspect(self, track_id, device_id, parameters=None, metadata=True):
        """Return selected fresh values; metadata is optional, cached and copy-isolated.

        The schema includes actual parameter identities/names/ranges/enum choices.
        Pass metadata=False after learning it; descriptions contain no stored values.
        """
        _track, device = self._target(track_id, device_id)
        native, schema, hit, descriptors = self._layout(device)
        selected = self._select(native, parameters)
        result = {'instance': self.state.instance, 'track_id': track_id,
                  'device_id': device_id, 'name': device.name, 'class': device.class_name,
                  'schema': schema, 'values': {key: p.value for key, p in selected},
                  'display': {key: p.str_for_value(p.value) for key, p in selected},
                  'enabled': {key: p.is_enabled for key, p in selected},
                  'metadata_cached': hit}
        if metadata:
            wanted = {_id(p) for _, p in selected}
            result['parameters'] = copy.deepcopy(
                [p for p in descriptors if p['id'] in wanted])
        return result

    def configure(self, edits):
        """Preflight all inspected devices/values, write once, return fresh snapshots.

        Each row is {snapshot: inspect result, values: chosen numeric values}. Every
        observed value in each snapshot remains a precondition. An exception during
        native assignment can leave partial changes; the outer execute owns Undo.
        """
        self._open()
        if not isinstance(edits, list) or not edits:
            raise ValueError('Supply a nonempty list of inspected parameter edits')
        prepared, observed, written = [], [], set()
        for edit in edits:
            if not isinstance(edit, dict) or set(edit) != {'snapshot', 'values'}:
                raise ValueError('Each edit needs snapshot and values')
            snapshot, values = edit['snapshot'], edit['values']
            if (not isinstance(snapshot, dict)
                    or snapshot.get('instance') != self.state.instance):
                raise ValueError('Device inspection expired; inspect again')
            track_id, device_id = snapshot.get('track_id'), snapshot.get('device_id')
            _track, device = self._target(track_id, device_id)
            parameters, schema, _hit, _descriptors = self._layout(device)
            if snapshot.get('schema') != schema:
                raise ValueError('Parameter layout changed; inspect again')
            expected = snapshot.get('values')
            if (not isinstance(expected, dict) or not expected or not isinstance(values, dict)
                    or not values or not values.keys() <= expected.keys()):
                raise ValueError('Update only parameters present in the inspected values')
            selected = dict(self._select(parameters, list(expected)))
            for key, value in expected.items():
                if not _number(value) or selected[key].value != value:
                    raise ValueError('Parameter value changed; inspect again: ' + key)
            for key, value in values.items():
                parameter = selected[key]
                if (not _number(value) or not parameter.min <= value <= parameter.max
                        or (parameter.is_quantized and value != int(value))):
                    raise ValueError('Invalid native parameter value: ' + key)
                if not parameter.is_enabled:
                    raise ValueError('Parameter is disabled: ' + key)
                identity = (device_id, _id(parameter))
                if identity in written:
                    raise ValueError('A batch cannot write the same parameter twice')
                written.add(identity)
                prepared.append((parameter, value))
            observed.append((track_id, device_id, list(expected)))
        for parameter, value in prepared:
            parameter.value = value
        return [self.inspect(track, device, names, metadata=False)
                for track, device, names in observed]

    def _browser_node(self, path, uri=None):
        self._open()
        if (not isinstance(path, list) or not path
                or any(not isinstance(n, str) or not n for n in path)):
            raise ValueError('Supply a browser root and exact child names')
        node = getattr(self._browser, path[0])
        for index, name in enumerate(path[1:], 1):
            matches = [c for c in node.children if c.name == name]
            if uri is not None and index == len(path) - 1:
                matches = [c for c in matches if c.uri == uri]
            if len(matches) != 1:
                raise ValueError('Missing/ambiguous browser path: ' + name)
            node = matches[0]
        return node

    def browse(self, root='audio_effects', path=None, search='', recursive=False,
               include_presets=False, refresh=False):
        """Read cached browser descriptions; resolve load targets freshly elsewhere.

        Catalogs clear on native full-refresh, explicit refresh, close or Set epoch.
        Loadable entries may include instruments/templates: this is browser metadata,
        not a claim of plugin authorization or tested sound. No musical state cached.
        """
        self._open()
        path = [root] + ([] if path is None else path)
        if not isinstance(search, str):
            raise TypeError('search must be a string')
        key = (tuple(path), bool(recursive), bool(include_presets))
        if refresh:
            self._catalog.pop(key, None)
        hit = key in self._catalog
        if hit:
            self._counts['catalog_hits'] += 1
            self._catalog.move_to_end(key)
        else:
            node = self._browser_node(path)
            entries, visited = [], [0]

            def visit(item, names, depth):
                visited[0] += 1
                if visited[0] > 5000 or depth > 32:
                    raise ValueError('Browser query is too large; choose a narrower path')
                entries.append({'name': item.name, 'uri': item.uri, 'path': names,
                                'is_loadable': item.is_loadable, 'is_device': item.is_device})
                if recursive and (include_presets or not item.is_loadable):
                    for child in item.children:
                        visit(child, names + [child.name], depth + 1)

            for child in node.children:
                visit(child, path + [child.name], 0)
            self._counts['catalog_builds'] += 1
            self._keep(self._catalog, key, entries, 8)
        query = search.casefold()
        entries = [r for r in self._catalog[key]
                   if query in ' / '.join(r['path']).casefold()]
        return {'instance': self.state.instance, 'cache_hit': hit,
                'entries': copy.deepcopy(entries)}

    def begin_append(self, path, track_id, expected_chain, uri=None):
        """Resolve a fresh exact browser item and load it once after the last device."""
        self._open()
        track = self.state.track(track_id)
        if [_id(d) for d in track.devices] != expected_chain:
            raise ValueError('Device chain changed; inspect again')
        if self._browser.hotswap_target is not None:
            raise ValueError('Exit browser hotswap before appending')
        node = self._browser_node(path, uri)
        if not node.is_loadable:
            raise ValueError('Choose a loadable browser device')
        self.state.song.view.selected_track = track
        if track.devices:
            self.state.song.view.select_device(track.devices[-1])
        self._browser.load_item(node)

    def finish_append(self, track_id, expected_chain, parameters=None, metadata=False):
        """Wait/readback step, optionally configuring the settled device in this call.

        Does not read clip vectors or Master-only unsupported mixer properties. A
        pending response never writes parameters. Loading and configuring occur in
        separate native ticks; do not span an Undo group across those ticks.
        """
        self._open()
        track = self.state.track(track_id)
        chain = [_id(d) for d in track.devices]
        if chain == expected_chain:
            return {'pending': True}
        if len(chain) != len(expected_chain) + 1 or chain[:-1] != expected_chain:
            raise ValueError('Device chain changed during load; inspect before further edits')
        device = track.devices[-1]
        result = {'id': _id(device), 'name': device.name, 'class': device.class_name}
        if parameters is not None or metadata:
            if not device.parameters:
                return {'pending': True}
            snapshot = self.inspect(track_id, _id(device),
                                    None if parameters is None else list(parameters), metadata)
            if parameters:
                updated = self.configure([{'snapshot': snapshot, 'values': parameters}])[0]
                snapshot.update(updated)
            result['snapshot'] = snapshot
        return {'pending': False, 'device': result}

    def clear_catalog(self, *unused):
        self._catalog.clear()

    def stats(self):
        return dict(self._counts, cached_schemas=len(self._descriptors),
                    cached_catalogs=len(self._catalog))

    def close(self):
        self._closed = True
        if self._listening:
            try:
                self._browser.remove_full_refresh_listener(self.clear_catalog)
            except (AttributeError, RuntimeError, TypeError):
                pass
            self._listening = False
        self._catalog.clear()
        self._descriptors.clear()
        self._targets.clear()
