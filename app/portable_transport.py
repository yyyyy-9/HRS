"""RFC 6455 control frames only, for local window liveness, not document data.

The browser answers protocol pings without JavaScript timers. WebSockets do not
consume the browser's small pool of ordinary HTTP document/asset connections.
No extensions, fragments or application data are accepted on this endpoint.
"""
import base64
import hashlib


def accept_key(key):
    if not isinstance(key, str):
        raise ValueError('WebSocket key missing')
    try:
        if len(base64.b64decode(key, validate=True)) != 16:
            raise ValueError('WebSocket key invalid')
    except (ValueError, UnicodeError) as exc:
        raise ValueError('WebSocket key invalid') from exc
    return base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode('ascii')).digest()).decode('ascii')


def read_exact(stream, count):
    data = stream.read(count)
    if len(data) != count:
        raise ConnectionError('Window socket closed')
    return data


def read_control(stream):
    first, second = read_exact(stream, 2)
    opcode = first & 15
    size = second & 127
    if first & 240 != 128 or opcode not in (8, 9, 10) or not second & 128 or size > 125:
        raise ValueError('Only masked, unfragmented control frames are accepted')
    if opcode == 8 and size == 1:
        raise ValueError('Invalid close frame')
    mask = read_exact(stream, 4)
    payload = read_exact(stream, size)
    return opcode, bytes(value ^ mask[index % 4] for index, value in enumerate(payload))


def write_control(stream, opcode, payload=b''):
    if opcode not in (8, 9, 10) or len(payload) > 125:
        raise ValueError('Invalid server control frame')
    stream.write(bytes((128 | opcode, len(payload)))+payload)
    stream.flush()
