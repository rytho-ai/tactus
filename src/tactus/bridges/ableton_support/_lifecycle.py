"""Run one cleanup attempt while preserving a primary performance/control error."""

from contextlib import contextmanager


@contextmanager
def cleanup(action, description):
    failure = None
    try:
        yield
    except BaseException as exc:
        failure = exc
        raise
    finally:
        try:
            action()
        except Exception as exc:
            if failure is None:
                raise
            failure.add_note(f'{description}: {exc}')
