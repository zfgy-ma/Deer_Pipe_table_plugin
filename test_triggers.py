"""Offline tests; do not import the SDK or execute the downloaded plugin."""
import ast
import asyncio
from datetime import datetime
import re
import unittest
from pathlib import Path
from typing import Any
from types import SimpleNamespace

SOURCE = Path(__file__).with_name("plugin.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
compile(TREE, "plugin.py", "exec")
HELPERS = [n for n in TREE.body if isinstance(n, ast.FunctionDef)
           and n.name in {"_record_trigger_words", "_record_command_pattern", "_monthly_command_pattern"}]
ENV = {"re": re}
exec(compile(ast.Module(body=HELPERS, type_ignores=[]), "helpers", "exec"), ENV)
parse = ENV["_record_trigger_words"]
pattern = ENV["_record_command_pattern"]
monthly_pattern = ENV["_monthly_command_pattern"]

class TriggerTests(unittest.TestCase):
    def test_single_word(self):
        self.assertIsNotNone(re.search(pattern("🦌"), "🦌"))
        self.assertIsNone(re.search(pattern("🦌"), "鹿"))

    def test_multiple_words(self):
        for word in ["🦌", "鹿", "撸", "打卡"]:
            self.assertIsNotNone(re.search(pattern("🦌,鹿，撸,打卡"), word))

    def test_strip_empty_dedupe(self):
        self.assertEqual(parse(" 🦌, 鹿，，,撸,鹿, "), ["🦌", "鹿", "撸"])

    def test_no_substring_or_combined_matches(self):
        for message in ["今天看到鹿了", "鹿排名", "我的鹿", "鹿鹿", "🦌,鹿", " 鹿", "鹿 ", "鹿\n", ""]:
            self.assertIsNone(re.search(pattern("🦌,鹿"), message), repr(message))

    def test_literal_regex_characters(self):
        for word in ["a+b", ".*", "[鹿]", "a|b", "(鹿)", "a.b"]:
            self.assertIsNotNone(re.search(pattern(word), word))
        self.assertIsNone(re.search(pattern(".*"), "任意消息"))
        self.assertIsNone(re.search(pattern("a|b"), "a"))

    def test_empty_config_does_not_match(self):
        for config in ["", "  ", ",，,"]:
            for message in ["", "鹿", "🦌"]:
                self.assertIsNone(re.search(pattern(config), message))

    def test_registration_uses_new_pattern(self):
        # Run only the actual get_components method with minimal SDK stubs.
        cls = next(n for n in TREE.body if isinstance(n, ast.ClassDef)
                   and n.name == "DeerPipeTablePlugin")
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                      and n.name == "get_components")
        class Base:
            def get_components(self):
                return [{"type": "service"}, {"type": "command", "name": "old"}]
        def command(name):
            class Command:
                command_name = name
                @classmethod
                def get_command_info(c):
                    return SimpleNamespace(name=c.command_name, component_type="command",
                                           command_pattern=c.command_pattern, description="")
            return Command
        env = dict(ENV, Any=Any, Base=Base)
        for name, suffix in [("DeerRecordCommand", "record"), ("DeerRankCommand", "rank"),
                             ("DeerPersonalCommand", "personal"), ("DeerMonthlyCommand", "monthly")]:
            env[name] = command("deer_pipe_" + suffix)
        harness = ast.ClassDef(name="Harness", bases=[ast.Name(id="Base", ctx=ast.Load())],
                               keywords=[], body=[method], decorator_list=[])
        exec(compile(ast.fix_missing_locations(ast.Module(body=[harness], type_ignores=[])),
                     "registration", "exec"), env)
        instance = env["Harness"]()
        instance.config = SimpleNamespace(trigger=SimpleNamespace(
            deer_pipe_record_words="🦌,鹿,撸", deer_pipe_rank_words="鹿排名，道馆排名",
            deer_pipe_personal_words="我的鹿,我的记录", deer_pipe_monthly_words="鹿表,月报"))
        components = instance.get_components()
        records = [c for c in components if c.get("name") == "deer_pipe_record"]
        self.assertEqual(len(records), 1)
        actual = records[0]["metadata"]["command_pattern"]
        for message in ["🦌", "鹿", "撸"]:
            self.assertIsNotNone(re.search(actual, message))
        self.assertIsNone(re.search(actual, "今天鹿"))
        for name, messages in [
            ("DeerRankCommand", ["鹿排名", "道馆排名"]),
            ("DeerPersonalCommand", ["我的鹿", "我的记录"]),
            ("DeerMonthlyCommand", ["鹿表7月", "上月月报", "本月鹿表", "月报"]),
        ]:
            for message in messages:
                self.assertIsNotNone(re.search(env[name].command_pattern, message))
            self.assertIsNone(re.search(env[name].command_pattern, "随便聊天"))
        self.assertEqual(len([c for c in components if c.get("type") == "command"]), 4)

    def test_monthly_forms_and_capture(self):
        regex = monthly_pattern("🦌表,鹿表，月报,月报")
        for word in ["🦌表", "鹿表", "月报"]:
            for text in [word, "上月" + word, "本月" + word]:
                match = re.search(regex, text)
                self.assertIsNotNone(match)
                self.assertIsNone(match.group("m"))
            for suffix in ["7月", " 12月", "01月"]:
                match = re.search(regex, word + suffix)
                self.assertIsNotNone(match)
                self.assertEqual(match.group("m"), suffix.strip()[:-1])
        for text in ["看月报", "上月月报7月", "月报123月", "月报\n", "鹿表,月报"]:
            self.assertIsNone(re.search(regex, text))

    def test_monthly_empty_and_literal(self):
        for text in ["", "上月", "本月", "7月"]:
            self.assertIsNone(re.search(monthly_pattern("，,"), text))
        regex = monthly_pattern("[表],a|b")
        self.assertIsNotNone(re.search(regex, "上月[表]"))
        self.assertIsNotNone(re.search(regex, "a|b7月"))
        self.assertIsNone(re.search(regex, "a7月"))

    def test_monthly_execute_routes_aliases(self):
        # Execute the real monthly handler with fake transport/chart generation.
        node = next(n for n in TREE.body if isinstance(n, ast.ClassDef)
                    and n.name == "DeerMonthlyCommand")
        class Base:
            def __init__(self, **kwargs):
                pass
        class FixedDate(datetime):
            @classmethod
            def now(cls):
                return cls(2026, 1, 10)
        env = dict(ENV, BaseCommand=Base, Any=Any, datetime=FixedDate)
        exec(compile(ast.Module(body=[node], type_ignores=[]), "monthly_handler", "exec"), env)
        calls = []
        async def chart(stream, group, month):
            calls.append((stream, group, month))
            return True, "ok", 2
        plugin = SimpleNamespace(config=SimpleNamespace(trigger=SimpleNamespace(
            enable_monthly=True, deer_pipe_monthly_words="鹿表,月报")),
            _handle_monthly_chart=chart)
        for alias in ["鹿表", "月报"]:
            for text, month in [(alias, 1), ("本月" + alias, 1), ("上月" + alias, 12),
                                (alias + "7月", 7)]:
                cmd = env["DeerMonthlyCommand"](plugin, text=text, group_id="test-group")
                cmd._stream_id = "test-stream"
                cmd.matched_groups = re.search(monthly_pattern("鹿表,月报"), text).groupdict()
                self.assertEqual(asyncio.run(cmd.execute()), (True, "ok", 2))
                self.assertEqual(calls[-1], ("test-stream", "test-group", month))
        self.assertEqual(len(calls), 8)

if __name__ == "__main__":
    unittest.main(verbosity=2)
