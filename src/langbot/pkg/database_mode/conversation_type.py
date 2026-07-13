from __future__ import annotations

CANONICAL_DIRECT_CONVERSATION_TYPE = 'direct'
CANONICAL_GROUP_CONVERSATION_TYPE = 'group'

_DIRECT_CONVERSATION_TYPE_ALIASES = frozenset({
    'direct',
    'person',
    'private',
    'friend',
    'dm',
    '单聊',
    '私聊',
    '好友',
    '个人',
})

_GROUP_CONVERSATION_TYPE_ALIASES = frozenset({
    'group',
    'room',
    'chatroom',
    'group_chat',
    '群聊',
    '群',
    '群组',
})


def normalize_conversation_type(
    conversation_type: object,
    *,
    default: str | None = None,
) -> str:
    raw_value = str(conversation_type or '').strip()
    if not raw_value:
        if default is None:
            raise ValueError('Unsupported conversation type: <empty>')
        raw_value = default

    normalized_value = raw_value.lower()
    if normalized_value in _DIRECT_CONVERSATION_TYPE_ALIASES:
        return CANONICAL_DIRECT_CONVERSATION_TYPE
    if normalized_value in _GROUP_CONVERSATION_TYPE_ALIASES:
        return CANONICAL_GROUP_CONVERSATION_TYPE

    raise ValueError(f'Unsupported conversation type: {raw_value}')


def is_private_conversation_type(conversation_type: object) -> bool:
    return normalize_conversation_type(conversation_type) == CANONICAL_DIRECT_CONVERSATION_TYPE
