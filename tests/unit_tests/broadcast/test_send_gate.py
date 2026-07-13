from langbot.pkg.broadcast.send_gate import resolve_broadcast_send_gate


def test_send_gate_enables_real_send_for_every_connector_without_configuration() -> None:
    gate = resolve_broadcast_send_gate(broadcast_config={}, env={})

    assert gate.send_enabled is True
    assert gate.error_code is None
    assert gate.is_connector_allowed("wxwork-local") is True
    assert gate.is_connector_allowed("wechat-local") is True
    assert gate.is_connector_allowed("custom-test-connector") is True
    assert gate.is_scope_send_enabled("custom-test-connector") is True
    assert gate.to_runtime_environment() == {
        "LANGBOT_BROADCAST_SEND_ENABLED": "1",
        "LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS": "*",
    }
