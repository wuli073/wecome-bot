import asyncio
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


def _create_session_db(path):
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE conversation_table (
                id TEXT PRIMARY KEY,
                name TEXT,
                roomname_remark TEXT,
                last_message_time INTEGER,
                last_message_id INTEGER,
                con_numeric_id INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE conversation_user_table (
                conversation_id TEXT,
                user_id INTEGER,
                nick_name TEXT
            )
            """
        )
        rows = [
            ("R:room-1", "重复名", "", 300, 3, 11),
            ("R:room-2", "重复名", "", 280, 2, 12),
            ("R:project", "项目群", "", 260, 4, 13),
            ("S:100_200", "", "", 250, 12, 14),
            ("O:app-1", "应用通知", "", 400, 30, 15),
        ]
        conn.executemany(
            """
            INSERT INTO conversation_table (
                id, name, roomname_remark, last_message_time, last_message_id, con_numeric_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.executemany(
            "INSERT INTO conversation_user_table(conversation_id, user_id, nick_name) VALUES (?, ?, ?)",
            [
                ("R:project", 200, "老杨"),
                ("R:project", 300, ""),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _create_user_db(path):
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE user_table (
                id INTEGER PRIMARY KEY,
                name TEXT,
                real_name TEXT,
                account TEXT,
                external_corp_name TEXT,
                external_job TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE external_user_relation_v3 (
                user_id INTEGER,
                remarks TEXT,
                real_remarks TEXT,
                corp_remark TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO user_table(id, name, real_name, account, external_corp_name, external_job)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (100, "我", "", "self", "", ""),
                (200, "杨炳恒", "", "yangbh", "", ""),
                (300, "张三", "张三实名", "zhangsan", "外部联系企业", "销售"),
                (400, "备注联系人", "", "remark_user", "", ""),
            ],
        )
        conn.executemany(
            """
            INSERT INTO external_user_relation_v3(user_id, remarks, real_remarks, corp_remark)
            VALUES (?, ?, ?, ?)
            """,
            [
                (300, "外部联系人备注", "", "企业备注"),
                (400, "重点客户", "真实备注", ""),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _create_message_db(path):
    conn = sqlite3.connect(path)
    try:
        for table in ("message_table", "message_small_table"):
            conn.execute(
                f"""
                CREATE TABLE "{table}" (
                    message_id INTEGER,
                    server_id INTEGER,
                    sequence INTEGER,
                    sender_id INTEGER,
                    conversation_id TEXT,
                    content_type INTEGER,
                    send_time INTEGER,
                    flag INTEGER,
                    content BLOB,
                    extra_content BLOB,
                    local_extra_content BLOB
                )
                """
            )
        conn.execute(
            """
            CREATE TABLE "kf_message_tableV1" (
                message_id INTEGER,
                server_id INTEGER,
                sequence INTEGER,
                sender_id INTEGER,
                receive_id INTEGER,
                kf_id INTEGER,
                conversation_id TEXT,
                content_type INTEGER,
                send_time INTEGER,
                flag INTEGER,
                content BLOB,
                extra_content BLOB,
                local_extra_content BLOB
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO message_table(
                message_id, server_id, sequence, sender_id, conversation_id,
                content_type, send_time, flag, content, extra_content, local_extra_content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 0, 1, 200, "S:100_200", 2, 100, 0, "第一条".encode("utf-8"), b"", b""),
                (2, 0, 2, 100, "S:100_200", 2, 200, 0, "第二条".encode("utf-8"), b"", b""),
                (3, 0, 3, 200, "S:100_200", 2, 300, 0, "第三条".encode("utf-8"), b"", b""),
                (10, 0, 10, 200, "R:room-1", 2, 280, 0, "命中 关键字".encode("utf-8"), b"", b""),
                (11, 0, 11, 300, "R:project", 2, 260, 0, "项目消息".encode("utf-8"), b"", b""),
                (30, 0, 30, 0, "O:app-1", 38, 400, 0, "应用最新消息".encode("utf-8"), b"", b""),
            ],
        )
        conn.executemany(
            """
            INSERT INTO message_small_table(
                message_id, server_id, sequence, sender_id, conversation_id,
                content_type, send_time, flag, content, extra_content, local_extra_content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (20, 0, 20, 400, "R:room-2", 2, 240, 0, "另一个命中 关键字".encode("utf-8"), b"", b""),
            ],
        )
        conn.commit()
    finally:
        conn.close()


class WxworkQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.fixture_dir = self.temp_dir.name
        _create_session_db(os.path.join(self.fixture_dir, "session.db"))
        _create_user_db(os.path.join(self.fixture_dir, "user.db"))
        _create_message_db(os.path.join(self.fixture_dir, "message.db"))

    def _config(self):
        return {
            "base": self.fixture_dir,
            "decrypted_dir": self.fixture_dir,
            "output_dir": os.path.join(self.fixture_dir, "out"),
            "self_id": 100,
        }

    def test_get_recent_sessions_returns_sorted_sessions(self):
        import wxwork_query

        with patch.object(wxwork_query, "_load_config", return_value=self._config()):
            result = wxwork_query.get_recent_sessions(limit=3)

        self.assertEqual(result["sessions"][0]["conversation_id"], "O:app-1")
        self.assertEqual(result["sessions"][1]["conversation_id"], "S:100_200")
        self.assertEqual(result["sessions"][1]["session_name"], "杨炳恒")
        self.assertEqual(len(result["sessions"]), 3)

    def test_get_chat_history_returns_candidates_for_ambiguous_name(self):
        import wxwork_query

        with patch.object(wxwork_query, "_load_config", return_value=self._config()):
            result = wxwork_query.get_chat_history("重复名")

        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual([item["conversation_id"] for item in result["candidates"]], ["R:room-1", "R:room-2"])

    def test_get_chat_history_supports_conversation_id_and_old_to_new_page_order(self):
        import wxwork_query

        with patch.object(wxwork_query, "_load_config", return_value=self._config()):
            result = wxwork_query.get_chat_history("S:100_200", limit=2, offset=0)

        self.assertEqual(result["status"], "ok")
        self.assertEqual([item["content"] for item in result["messages"]], ["第二条", "第三条"])
        self.assertEqual(result["conversation"]["session_name"], "杨炳恒")

    def test_search_messages_requires_keyword_and_supports_global_search(self):
        import wxwork_query

        with patch.object(wxwork_query, "_load_config", return_value=self._config()):
            with self.assertRaisesRegex(ValueError, "keyword"):
                wxwork_query.search_messages(" ")
            result = wxwork_query.search_messages("关键字", limit=5)

        self.assertEqual(result["status"], "ok")
        self.assertEqual([item["conversation_id"] for item in result["messages"]], ["R:room-2", "R:room-1"])

    def test_get_contacts_matches_multiple_fields(self):
        import wxwork_query

        with patch.object(wxwork_query, "_load_config", return_value=self._config()):
            result = wxwork_query.get_contacts(query="重点", limit=10)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["contacts"]), 1)
        self.assertEqual(result["contacts"][0]["contact_id"], 400)
        self.assertEqual(result["contacts"][0]["display_name"], "真实备注")

    def test_get_new_messages_reports_latest_query_only(self):
        import wxwork_query

        with patch.object(wxwork_query, "_load_config", return_value=self._config()):
            result = wxwork_query.get_new_messages(limit=2)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["query_mode"], "latest_messages_query")
        self.assertEqual([item["conversation_id"] for item in result["messages"]], ["S:100_200", "O:app-1"])

    def test_get_messages_for_monitor_filters_self_sent_and_exposes_source_rowid(self):
        import wxwork_query

        with patch.object(wxwork_query, "_load_config", return_value=self._config()):
            messages = wxwork_query.get_messages_for_monitor(limit=10)

        message_ids = {item["message_id"] for item in messages}
        self.assertIn(1, message_ids)
        self.assertIn(3, message_ids)
        self.assertIn(10, message_ids)
        self.assertIn(11, message_ids)
        self.assertIn(20, message_ids)
        self.assertNotIn(2, message_ids)
        self.assertNotIn(30, message_ids)
        self.assertTrue(all(item["source_rowid"] > 0 for item in messages))

    def test_get_messages_for_monitor_supports_incremental_cursor(self):
        import wxwork_query

        after_cursor = {
            "send_time": 260,
            "sequence": 11,
            "message_id": 11,
            "source_rowid": 1,
            "source_table": "message_table",
        }

        with patch.object(wxwork_query, "_load_config", return_value=self._config()):
            messages = wxwork_query.get_messages_for_monitor(limit=10, after_cursor=after_cursor)

        message_ids = [item["message_id"] for item in messages]
        self.assertIn(20, message_ids)
        self.assertIn(3, message_ids)
        self.assertIn(10, message_ids)
        self.assertNotIn(11, message_ids)
        self.assertNotIn(1, message_ids)

    def test_get_messages_for_monitor_returns_stable_cursor(self):
        import wxwork_query

        with patch.object(wxwork_query, "_load_config", return_value=self._config()):
            messages = wxwork_query.get_messages_for_monitor(limit=2)

        cursor = wxwork_query.build_monitor_cursor(messages[0])
        self.assertEqual(
            cursor,
            {
                "send_time": messages[0]["send_time"],
                "sequence": messages[0]["sequence"],
                "message_id": messages[0]["message_id"],
                "source_rowid": messages[0]["source_rowid"],
                "source_table": messages[0]["source_table"],
            },
        )

    def test_mcp_server_registers_five_wxwork_tools(self):
        import mcp_wxwork_server

        tools = asyncio.run(mcp_wxwork_server.mcp.list_tools())
        tool_names = [tool.name for tool in tools]

        self.assertEqual(
            tool_names,
            [
                "wxwork_get_recent_sessions",
                "wxwork_get_chat_history",
                "wxwork_search_messages",
                "wxwork_get_contacts",
                "wxwork_get_new_messages",
            ],
        )


if __name__ == "__main__":
    unittest.main()
