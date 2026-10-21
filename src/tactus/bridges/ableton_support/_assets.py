"""Declare known generated-device binaries/JS; transient command/status files stay live."""

from ... import tool


def declare_device(config):
    if config.get('amxd_path'):
        device = tool(config['amxd_path'])
        for script in device.parent.glob('*.js'):
            tool(str(script))
