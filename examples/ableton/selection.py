"""Compatibility recipe for the shared native selected-note API; Python 3.7."""

state, args = globals()['state'], globals()['args']

if args['mode'] == 'inspect':
    result = state.selection.inspect()
else:
    result = state.selection.update(args['token'], args['notes'])
